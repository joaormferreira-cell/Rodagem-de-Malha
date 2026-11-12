"""
Montagem da malha (etapa 1): cada caminho de demanda vira uma linha com as estações
nas colunas FMH / SOC1-4 / LMH / XPT e a distância de cada trecho.
"""
import pandas as pd

from ..configuracao import premissas
from .distancias import SEM_DISTANCIA, linha_reta_ajustada, sem_coordenada, tabela_coordenadas, tabela_distancias

PREFIXO_ERRO_LATLON = "sem distancia/lat-lon: "
SOCS = ["SOC1", "SOC2", "SOC3", "SOC4"]
ESTACOES = ["FMH"] + SOCS + ["LMH", "XPT"]
COLUNAS_DISTANCIA = ["FMH-SOC", "SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT"]
# trecho (coluna de origem, coluna de destino) -> coluna da distância; o que não está aqui vai para ERRO
COLUNA_DO_TRECHO = {
    ("FMH", "SOC1"): "FMH-SOC", ("FMH", "LMH"): "FMH-HUB",
    ("SOC1", "SOC2"): "SOC1-SOC2", ("SOC2", "SOC3"): "SOC2-SOC3", ("SOC3", "SOC4"): "SOC3-SOC4",
    ("SOC1", "FMH"): "SOC1-SOC2", ("SOC2", "FMH"): "SOC2-SOC3", ("SOC3", "FMH"): "SOC3-SOC4",
    ("SOC1", "LMH"): "SOC-HUB", ("SOC2", "LMH"): "SOC-HUB", ("SOC3", "LMH"): "SOC-HUB", ("SOC4", "LMH"): "SOC-HUB",
    ("SOC1", "XPT"): "SOC-XPT", ("SOC2", "XPT"): "SOC-XPT", ("SOC3", "XPT"): "SOC-XPT", ("SOC4", "XPT"): "SOC-XPT",
    ("LMH", "XPT"): "HUB-XPT",
}
COLUNAS_SAIDA = (["period_start", "period_end", "ORIGIN", "DESTINATION", "E2E Path", "ADO"]
                 + ESTACOES + COLUNAS_DISTANCIA + ["ERRO"])


def _sem_xd(codigo):
    return codigo.replace("(XD)", "")


def preparar_demanda(demanda, p=None):
    p = p or premissas()["malha"]
    df = demanda.rename(columns={"ADO": "forecast_ado", "ORIGIN": "origin", "DESTINATION": "destination",
                                 "E2E Path": "path"}).copy()
    df["forecast_ado"] = pd.to_numeric(df["forecast_ado"], errors="coerce")
    df = df[~df["destination"].isin(p["destinos_excluidos"])]
    df["period_start"] = pd.to_datetime(df["period_start"]).dt.normalize()
    # só a 1ª data de cada mês entra (regra do processo atual)
    datas = pd.Series(df["period_start"].unique())
    primeiras = datas.groupby([datas.dt.year, datas.dt.month]).min()
    df = df[df["period_start"].isin(primeiras)]
    return df.sort_values("period_start", kind="stable").reset_index(drop=True)


def conferir_estacoes(demanda, lat, lon):
    """Estação fora do cadastro para a rodagem; estação sem coordenada só gera aviso."""
    codigos = {_sem_xd(c).strip() for caminho in demanda["path"].dropna().unique() for c in str(caminho).split(">")}
    codigos.discard("")
    fora = sorted(c for c in codigos if c not in lat)
    if fora:
        raise ValueError("Estações fora do cadastro (Station List Historical / Base):\n"
                         + "\n".join(f"  - {c}" for c in fora))
    sem_coord = sorted(c for c in codigos if sem_coordenada(c, lat, lon))
    if sem_coord:
        print("AVISO: estações sem latitude/longitude (trechos sem distância cadastrada ficam com -1):\n"
              + "\n".join(f"  - {c}" for c in sem_coord))
    return sem_coord


def distribuir_estacoes(estacoes, distancias):
    """Põe cada estação na sua coluna e cada distância na coluna do trecho (mesma regra do processo atual)."""
    linha, alocacao = {}, []
    tipos = [e[:3] for e in estacoes]
    inicio = 0
    if tipos[0] in ("FMH", "FBS"):
        linha["FMH"] = estacoes[0]
        alocacao.append("FMH")
        inicio = 1
    posicao = 0
    for i in range(inicio, len(estacoes)):
        if tipos[i] == "HUB":
            coluna = "LMH"
        elif tipos[i] == "XPT":
            coluna = "XPT" if alocacao[i - 1] != "FMH" else "ERRO"
        elif posicao < len(SOCS):
            coluna = SOCS[posicao]
        else:
            coluna = "ERRO"
        linha[coluna] = estacoes[i]
        alocacao.append(coluna)
        posicao += 1
    for i in range(len(alocacao) - 1):
        linha[COLUNA_DO_TRECHO.get((alocacao[i], alocacao[i + 1]), "ERRO")] = distancias[i]
    return linha


def _montar_caminho(caminho, km_cadastro, lat, lon):
    estacoes = caminho.split(">")
    trechos = [_sem_xd(a) + ">" + _sem_xd(b) for a, b in zip(estacoes, estacoes[1:])]
    distancias = [km_cadastro.get(t, "") for t in trechos]
    if "" in distancias:
        distancias = [linha_reta_ajustada(lat.get(t.split(">")[0], ""), lon.get(t.split(">")[0], ""),
                                          lat.get(t.split(">")[1], ""), lon.get(t.split(">")[1], ""))
                      if d == "" else d for d, t in zip(distancias, trechos)]
    linha = distribuir_estacoes(estacoes, distancias)
    if SEM_DISTANCIA in distancias:
        falhos = [t for t, d in zip(trechos, distancias) if d == SEM_DISTANCIA]
        codigos = sorted({c for t in falhos for c in t.split(">") if sem_coordenada(c, lat, lon)})
        linha["trechos_sem_distancia"] = "; ".join(falhos)
        linha["ERRO"] = PREFIXO_ERRO_LATLON + ", ".join(codigos)
        linha = {k: ("-1" if v == SEM_DISTANCIA else v) for k, v in linha.items()}
    return linha


def montar_malha(demanda, cadastro_distancias, estacoes_historico, estacoes_base):
    """Devolve a malha (uma linha por caminho) nas colunas que o processo atual sobe para o Hive."""
    demanda = preparar_demanda(demanda)
    km_cadastro = tabela_distancias(cadastro_distancias)
    lat, lon = tabela_coordenadas(estacoes_historico, estacoes_base)
    conferir_estacoes(demanda, lat, lon)

    por_caminho = {c: _montar_caminho(c, km_cadastro, lat, lon) for c in demanda["path"].unique()}
    colunas = pd.DataFrame([por_caminho[c] for c in demanda["path"]])
    malha = pd.concat([demanda.drop(columns=[c for c in colunas.columns if c in demanda.columns]), colunas], axis=1)
    malha = malha.rename(columns={"path": "E2E Path", "forecast_ado": "ADO", "origin": "ORIGIN",
                                  "destination": "DESTINATION"})
    malha["period_start"] = malha["period_start"].dt.strftime("%Y-%m-%d")
    for c in COLUNAS_SAIDA + ["trechos_sem_distancia"]:
        if c not in malha.columns:
            malha[c] = ""
    malha = malha.astype(object).where(malha.notna(), "")
    n_erro = (malha["ERRO"] != "").sum()
    print(f"Malha: {len(malha)} caminhos, {n_erro} com erro")
    return malha[COLUNAS_SAIDA + ["trechos_sem_distancia"]]
