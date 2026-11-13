"""
Rotas (etapa 2): para cada trecho da malha (ex.: SOC-SP1 → SOC-RJ1) calcula
  1. quantos veículos precisa,
  2. quanto tempo o pacote espera para sair (só entre SOCs),
  3. quanto tempo leva a viagem (expressa oficial → New TT → cálculo por km),
  4. a fila no destino e o tempo total (TTFinal).
"""
import numpy as np
import pandas as pd

from ..configuracao import premissas
from .malha import COLUNAS_DISTANCIA, COLUNA_DO_TRECHO, ESTACOES
from .tempo_viagem import tt_expressa, tt_normal

VEICULOS = ["carreta_cap", "truck_cap", "others_cap"]
COLUNAS_SAIDA = ["period_start", "Route", "Origin", "Dest", "route_type", "ADO", "Distance",
                 "Final Pck-LHTr", "Pck-LHTr", "Raw Pck-LHTr", "Loading",
                 "TTFinal", "LHExpress Ident.", "TT Calc.", "TT with Express", "TT Queue and Unloading",
                 "Total Vehicles", "N Carretas", "N Truck", "N Others", "carreta_cap", "truck_cap", "others_cap"]


# ---------------- Inputs de tempo de rota ----------------
def _preenchido(s):
    return s.notna() & s.astype(str).str.strip().ne("")


def _hhmm_para_horas(s):
    """'06:30' -> 6.5. Formato inválido para a rodagem com a lista das células erradas."""
    if s.empty:
        return pd.Series(dtype=float)
    partes = s.astype(str).str.strip().str.split(":", n=2, expand=True)
    horas, minutos = pd.to_numeric(partes[0], errors="coerce"), pd.to_numeric(partes[1], errors="coerce")
    erradas = horas.isna() | minutos.isna()
    if erradas.any():
        raise ValueError(f"Transit time fora do formato HH:MM: {s[erradas].tolist()[:10]}")
    return horas + minutos / 60


def preparar_expressas(bruto):
    """Planilha oficial de expressas -> Route, TT (h) e início (menor data de ativação)."""
    ativas = bruto[~bruto["Status"].isin(["Expressa inativa", "Inativa"])
                   & ~bruto["Status"].str.contains("Expressa a ativar", na=False)]
    blocos = []
    # rotas ativas valem desde a última alteração; o histórico vale desde o ramp-up
    for df, col_data in [(ativas, "Data da última alteração"), (bruto, "Data de ramp-up")]:
        df = df[_preenchido(df["Rota atualizada com movings"]) & _preenchido(df["Transit time atualizado"])]
        blocos.append(pd.DataFrame({
            "Route": df["Rota atualizada com movings"].str.replace("|", ">", regex=False),
            "TT": _hhmm_para_horas(df["Transit time atualizado"]),
            "inicio": pd.to_datetime(df[col_data], format="%d/%b/%y"),
        }))
    return pd.concat(blocos).groupby(["Route", "TT"])["inicio"].min().reset_index()


def preparar_new_tt(bruto):
    """Planilha New TT -> {rota: horas}, só rotas ATIVA ou A INICIAR."""
    df = bruto
    if "STATUS DA ROTA" in df.columns:
        df = df[df["STATUS DA ROTA"].astype(str).str.upper().str.strip().isin(["ATIVA", "A INICIAR"])]
    if df.empty:
        return {}
    rota = df["ORIGEM"].astype(str).str.strip() + ">" + df["DESTINO"].astype(str).str.split("|").str[-1].str.strip()

    def horas(v):
        try:
            p = [float(x) for x in str(v).split(":")]
            return p[0] + (p[1] / 60 if len(p) > 1 else 0) + (p[2] / 3600 if len(p) > 2 else 0)
        except (ValueError, IndexError):
            return np.nan
    tabela = pd.DataFrame({"Route": rota, "TT": df["TT HRS"].map(horas)}).dropna().drop_duplicates("Route")
    return dict(zip(tabela["Route"], tabela["TT"]))


# ---------------- Malha -> rotas ----------------
def limpar_malha(malha, p):
    """Tira caminhos com erro, sem distância (-1) e de origem Cross Border."""
    df = malha.copy()
    if "ERRO" in df.columns:
        df = df[df["ERRO"].fillna("") == ""]
    df = df[~(df[COLUNAS_DISTANCIA].astype(str) == "-1").any(axis=1)]
    col_origem = "ORIGIN" if "ORIGIN" in df.columns else "FMH"
    df = df[~df[col_origem].astype(str).str[:7].isin(p["origens_cb"])]
    df["period_start"] = df["period_start"].astype(str).str[:10]
    df["ADO"] = pd.to_numeric(df["ADO"], errors="coerce")
    return df.reset_index(drop=True)


def quebrar_em_rotas(malha_mes):
    """Cada caminho vira os seus trechos. Trecho repetido em vários caminhos soma os pedidos (ADO)."""
    m = malha_mes.reset_index(drop=True)
    paradas = m[ESTACOES].where(m[ESTACOES].notna() & (m[ESTACOES].astype(str) != ""))
    paradas = paradas.reset_index(names="caminho").melt("caminho", var_name="coluna", value_name="estacao").dropna()
    paradas["ordem"] = paradas["coluna"].map({c: i for i, c in enumerate(ESTACOES)})
    paradas = paradas.sort_values(["caminho", "ordem"])
    paradas["coluna_seguinte"] = paradas.groupby("caminho")["coluna"].shift(-1)
    paradas["estacao_seguinte"] = paradas.groupby("caminho")["estacao"].shift(-1)
    trechos = paradas.dropna(subset=["coluna_seguinte"]).copy()

    coluna_km = [COLUNA_DO_TRECHO[(a, b)] for a, b in zip(trechos["coluna"], trechos["coluna_seguinte"])]
    km = m[COLUNAS_DISTANCIA].to_numpy(dtype=object)
    trechos["Distance"] = km[trechos["caminho"].to_numpy(), [COLUNAS_DISTANCIA.index(c) for c in coluna_km]]
    trechos["ADO"] = m["ADO"].to_numpy()[trechos["caminho"].to_numpy()]
    trechos["Origin"] = trechos["estacao"].str.replace("(XD)", "", regex=False)
    trechos["Dest"] = trechos["estacao_seguinte"].str.replace("(XD)", "", regex=False)
    trechos = trechos.drop_duplicates(["caminho", "Origin", "Dest"], keep="last")

    rotas = trechos.groupby(["Origin", "Dest"]).agg(Distance=("Distance", "first"), ADO=("ADO", "sum")).reset_index()
    rotas["Route"] = rotas["Origin"] + ">" + rotas["Dest"]
    rotas["route_type"] = rotas["Origin"].str[:3] + "-" + rotas["Dest"].str[:3]
    rotas["Distance"] = pd.to_numeric(rotas["Distance"], errors="coerce")
    sem_km = rotas["Distance"].isna()
    if sem_km.any():
        print(f"ATENÇÃO: {sem_km.sum()} rota(s) sem distância descartada(s)")
    return rotas[~sem_km].reset_index(drop=True)


# ---------------- Veículos e espera para sair ----------------
def capacidades(rotas, spr):
    """Capacidade de cada veículo: dado da rota → dado da estação de origem → média do tipo de rota."""
    spr = spr.copy()
    for v in VEICULOS:
        spr[v] = pd.to_numeric(spr[v], errors="coerce")
    por_rota = spr.drop_duplicates("route_code").set_index("route_code")
    # no SPR, a estação de origem está em destination_considered e o tipo de rota em origin_station_code
    por_estacao = spr.drop_duplicates(["destination_considered", "origin_station_code"]) \
        .set_index(["destination_considered", "origin_station_code"])
    chave_estacao = pd.MultiIndex.from_arrays([rotas["Origin"], rotas["route_type"]])
    for v in VEICULOS:
        da_rota = rotas["Route"].map(por_rota[v])
        da_estacao = pd.Series(por_estacao[v].reindex(chave_estacao).to_numpy(), index=rotas.index)
        media_do_tipo = rotas["route_type"].map(spr.groupby("route_type")[v].mean())
        rotas[v] = da_rota.fillna(da_estacao).fillna(media_do_tipo)
    return rotas


def contar_veiculos(pedidos, cap_carreta, cap_truck, p):
    """
    Enche carretas primeiro. O que sobra, nesta ordem:
      - zero: nada a fazer;
      - mais de 70% de uma carreta: abre mais uma carreta;
      - menos de 1.000 pedidos: não abre veículo;
      - senão: completa com um truck.
    Rota menor que uma carreta faz o mesmo com trucks (e completa com 'outros').
    Devolve (carretas, trucks, outros).
    """
    if not pedidos > 0:
        return 0, 0, 0
    for cap, e_carreta in [(cap_carreta, True), (cap_truck, False)]:
        if cap > 0 and pedidos > cap:
            cheios, sobra = divmod(pedidos, cap)
            cheios = int(cheios)
            # ordem igual à do processo atual: exato → sobra > 70% → sobra < 1.000 → completa
            if sobra == 0:
                n, extra = cheios, 0
            elif sobra / cap > p["fracao_arredonda_cima"]:
                n, extra = cheios + 1, 0
            elif sobra < p["sobra_min_novo_veiculo"]:
                n, extra = cheios, 0
            else:
                n, extra = cheios, 1
            return (n, extra, 0) if e_carreta else (0, n, extra)
    return 0, 1, 0


def espera_para_sair(rotas, tempos_soc, p):
    """Só SOC → SOC: 12h ÷ nº de veículos (mínimo 4h) + tempo de carregar no SOC de origem."""
    n = [contar_veiculos(o, c, t, p) for o, c, t in zip(rotas["ADO"], rotas["carreta_cap"], rotas["truck_cap"])]
    rotas[["N Carretas", "N Truck", "N Others"]] = pd.DataFrame(n, index=rotas.index)
    rotas["Total Vehicles"] = rotas[["N Carretas", "N Truck", "N Others"]].sum(axis=1)

    carga = tempos_soc.assign(Loading=pd.to_numeric(tempos_soc["Loading"], errors="coerce"))
    outros = carga["Sites"] == "Other"
    media_soc, media_outros = carga.loc[~outros, "Loading"].mean(), carga.loc[outros, "Loading"].mean()
    do_soc = rotas["Origin"].map(carga.set_index("Sites")["Loading"])
    rotas["Loading"] = np.where(rotas["Origin"].str[:3] == "SOC", do_soc.fillna(media_soc), media_outros)

    janela = p["janela_outbound_h"]
    rotas["Raw Pck-LHTr"] = (janela / rotas["Total Vehicles"].replace(0, np.nan)).fillna(janela)
    rotas["Pck-LHTr"] = rotas["Raw Pck-LHTr"].clip(lower=p["outbound_min_h"])
    rotas["Final Pck-LHTr"] = rotas["Loading"] + rotas["Pck-LHTr"]
    nao_soc_soc = ~rotas["route_type"].isin(p["tipos_com_outbound"])
    rotas.loc[nao_soc_soc, ["Final Pck-LHTr", "Pck-LHTr", "Raw Pck-LHTr", "Loading"]] = np.nan
    return rotas


# ---------------- Tempo de viagem ----------------
def tempo_de_viagem(rotas, expressas, new_tt, periodo, p):
    """
    Prioridade 1: rota na planilha oficial de expressas, já ativa no mês → TT oficial e selo expressa.
    Prioridade 2: rota na planilha New TT → TT de lá.
    Prioridade 3: cálculo pela distância (fórmula expressa se a rota tem o selo).
    Selo expressa também para rota com 750 km ou mais (exceto origem 3PL e destino XPT).
    """
    rotas = rotas.merge(expressas, how="left", on="Route")
    p1 = rotas["TT"].notna() & (pd.to_datetime(periodo) >= rotas["inicio"])
    p2 = ~p1 & rotas["Route"].map(new_tt).notna()
    p3 = ~p1 & ~p2

    longa = (~rotas["Origin"].str.contains("3PL") & ~rotas["Dest"].str.contains("XPT")
             & (rotas["Distance"] >= p["dist_min_expressa_km"]))
    rotas["LHExpress Ident."] = p1 | (~p1 & longa)

    rotas["TT Calc."] = np.where(rotas["Distance"] < p["dist_min_tt_km"], p["tt_min_h"], tt_normal(rotas["Distance"]))
    rotas["TT with Express"] = np.select(
        [p1, p2, p3 & rotas["LHExpress Ident."], p3],
        [rotas["TT"], rotas["Route"].map(new_tt), tt_expressa(rotas["Distance"]), rotas["TT Calc."]])
    rotas["fonte_tt"] = np.select([p1, p2, p3 & rotas["LHExpress Ident."]],
                                  ["Expressa oficial", "New TT", "Cálculo por km (expressa)"], "Cálculo por km")
    print(f"  Tempo de viagem — expressa oficial: {p1.sum()} | New TT: {p2.sum()} | cálculo por km: {p3.sum()}")
    return rotas.drop(columns=["TT", "inicio"])


def fila_no_destino(rotas, arrived_received, periodo, p):
    """Fila para descarregar no SOC de destino (média dos SOCs se faltar); 2h fora de SOC; zero onde não há fila."""
    mes = periodo[:8] + "01"
    # [PARIDADE] o processo atual converte as colunas da 4ª em diante em número e descarta o SOC
    # que tenha QUALQUER mês vazio (até mês antigo): esse SOC passa a usar a média. Ver MAPA.md.
    tabela = arrived_received.copy()
    tabela[tabela.columns[3:]] = tabela[tabela.columns[3:]].apply(pd.to_numeric, errors="coerce")
    tabela = tabela.dropna()
    if mes not in tabela.columns:
        print(f"AVISO: mês {mes} não está em Arrived to Received; fila = 0")
        fila = pd.Series(0.0, index=rotas.index)
    else:
        horas = pd.to_numeric(tabela[mes], errors="coerce")
        do_soc = rotas["Dest"].map(pd.Series(horas.to_numpy(), index=tabela["code"]))
        fila = pd.Series(np.where(rotas["Dest"].str[:3] == "SOC", do_soc.fillna(horas.mean()), p["fila_nao_soc_h"]),
                         index=rotas.index)
    fila[rotas["route_type"].isin(p["tipos_sem_fila"]) | (rotas["Distance"] < p["dist_min_tt_km"])] = 0
    rotas["TT Queue and Unloading"] = fila.astype(float)
    rotas["TTFinal"] = rotas["TT Queue and Unloading"] + rotas["TT with Express"]
    return rotas


def rotas_aereas_e_fixas(rotas, air_lh, p):
    """Aeroporto → aeroporto usa o TT da planilha de Air LH; rotas com TT fixo usam o valor da premissa."""
    aerea = (rotas["Origin"].str.split("-").str[0] == "Airport") & (rotas["Dest"].str.split("-").str[0] == "Airport")
    tt_aereo = pd.to_numeric(air_lh.drop_duplicates("Route").set_index("Route")["TT (hours)"], errors="coerce")
    fixas = p["tt_final_fixo"]
    fixa = rotas["Route"].isin(fixas)
    rotas.loc[aerea, "TTFinal"] = rotas.loc[aerea, "Route"].map(tt_aereo)
    rotas.loc[fixa, "TTFinal"] = rotas.loc[fixa, "Route"].map(fixas)
    rotas.loc[aerea | fixa, ["TT with Express", "TT Calc.", "TT Queue and Unloading"]] = np.nan
    rotas.loc[aerea | fixa, "LHExpress Ident."] = False
    rotas.loc[aerea, "fonte_tt"] = "Air LH"
    rotas.loc[fixa, "fonte_tt"] = "Valor fixo"
    return rotas


# ---------------- Execução ----------------
def calcular_rotas(malha, expressas_bruto, new_tt_bruto, spr, tempos_soc, arrived_received, air_lh):
    """Uma linha por rota e mês, com as colunas da aba [T] 4.1 + a origem do tempo de viagem (fonte_tt)."""
    p = premissas()["rotas"]
    malha = limpar_malha(malha, p)
    expressas = preparar_expressas(expressas_bruto)
    new_tt = preparar_new_tt(new_tt_bruto)
    resultado = []
    for periodo in sorted(malha["period_start"].unique()):
        print(f"Rotas do mês {periodo}")
        rotas = quebrar_em_rotas(malha[malha["period_start"] == periodo])
        rotas["period_start"] = periodo
        rotas = capacidades(rotas, spr)
        rotas = espera_para_sair(rotas, tempos_soc, p)
        rotas = tempo_de_viagem(rotas, expressas, new_tt, periodo, p)
        rotas = fila_no_destino(rotas, arrived_received, periodo, p)
        rotas = rotas_aereas_e_fixas(rotas, air_lh, p)
        resultado.append(rotas[COLUNAS_SAIDA + ["fonte_tt"]])
    return pd.concat(resultado, ignore_index=True)
