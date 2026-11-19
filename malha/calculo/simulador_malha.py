"""
Simulador de malha: "e se" a viagem de uma rota mudar (ou a rota virar expressa) ou a fila de um SOC mudar,
quanto muda a meta de BWT do mês da meta (Brasil, SPX D2D e Fulfillment)?

O BWT de um caminho é a soma das etapas, e cada viagem entra com o tempo total da rota (TTFinal = viagem + fila).
Mudar o tempo de uma rota em X horas muda o BWT do canal em X × (pedidos/dia que passam pela rota ÷ pedidos/dia
do canal). Esse peso sai do próprio cálculo do BWT (as mesmas funções de bwt.py): o tempo de cada rota é trocado
por um código, e cada etapa de viagem do caminho mostra qual rota usou.
"""
import numpy as np
import pandas as pd

from ..configuracao import premissas
from .bwt import COMPONENTES, _bwt_do_mes, preparar_metas
from .tempo_viagem import tt_expressa

COLUNAS_VIAGEM = [c for c, _, fonte in COMPONENTES if fonte.startswith("TTFinal da rota")]
CODIGO = 1e7   # tempo falso de cada rota = CODIGO + nº da rota (o cálculo por km dá sempre bem menos que isso)
FONTES_COM_FILA = ["Fila do próprio SOC", "Média dos SOCs (SOC sem fila própria)", "Fora de SOC (valor padrão)"]
FORA_DE_SOC = "Destinos fora de SOC (valor padrão)"
SEM_FILA_PROPRIA = ["Air LH", "Valor fixo"]   # tempo total fixo: a "viagem" é o tempo todo


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def pesos_das_rotas(caminhos, rotas, metas, periodo):
    """
    Pedidos/dia de cada canal que passam por cada rota, do jeito que o BWT usa a rota.
    caminhos: bwt_caminhos de um mês; rotas: rotas do mesmo mês; metas: já preparadas (preparar_metas).
    Devolve DataFrame indexado pela rota com as colunas spx e fbs (pedidos/dia).
    """
    p = {**premissas()["bwt"], **premissas()["rotas"]}
    tt = _num(rotas.drop_duplicates("Route").set_index("Route")["TTFinal"]).dropna()
    nomes = tt.index.to_numpy()
    codigos = pd.Series(CODIGO + np.arange(len(tt)), index=nomes)
    c = _bwt_do_mes(caminhos.copy(), metas, periodo, codigos, p)
    fbs = (_num(caminhos["fbs_flag"]) == 1).to_numpy()
    ado = _num(caminhos["ADO"]).fillna(0).to_numpy()
    usos = []
    for col in COLUNAS_VIAGEM:
        v = _num(pd.Series(np.asarray(c[col]))).to_numpy()
        usa = v >= CODIGO - 0.5
        usos.append(pd.DataFrame({"rota": nomes[np.rint(v[usa] - CODIGO).astype(int)],
                                  "fbs": fbs[usa], "ado": ado[usa]}))
    u = pd.concat(usos, ignore_index=True)
    pesos = u.pivot_table(index="rota", columns="fbs", values="ado", aggfunc="sum").reindex(columns=[False, True])
    return pesos.fillna(0.0).set_axis(["spx", "fbs"], axis=1)


def simular_malha(resultados, metas):
    """Tabelas do simulador para o mês da meta (o último mês da rodagem): resumo, filas por SOC e rotas."""
    caminhos, rotas = resultados["bwt_caminhos"], resultados["rotas"]
    periodo = max(caminhos["period_start"].astype(str).str[:10])
    c = caminhos[caminhos["period_start"].astype(str).str[:10] == periodo].reset_index(drop=True)
    r = rotas[rotas["period_start"].astype(str).str[:10] == periodo].drop_duplicates("Route").reset_index(drop=True)
    if c.empty or r.empty:
        return {}
    fbs = _num(c["fbs_flag"]) == 1
    ado, horas = _num(c["ADO"]).fillna(0), _num(c["bwt_total_hours"]).fillna(0)
    total = {"spx": ado[~fbs].sum(), "fbs": ado[fbs].sum()}
    bwt = {k: ((horas * ado)[m].sum() / total[k] if total[k] else np.nan) for k, m in [("spx", ~fbs), ("fbs", fbs)]}

    pedidos = pesos_das_rotas(c, r, preparar_metas(metas), periodo)
    r = r.merge(pedidos, left_on="Route", right_index=True, how="inner")
    r = r[(r["spx"] + r["fbs"]) > 0].copy()
    for k in ["spx", "fbs"]:
        r[f"peso_{k}"] = r[k] / total[k] if total[k] else 0.0

    p = premissas()["rotas"]
    fixa = r["fonte_tt"].isin(SEM_FILA_PROPRIA)
    km = _num(r["Distance"])
    expressa = r["LHExpress Ident."].astype(str).str.upper().isin(["TRUE", "1", "1.0"])
    r["viagem_h"] = np.where(fixa, _num(r["TTFinal"]), _num(r["TT with Express"]))
    r["fila_h"] = np.where(fixa, 0.0, _num(r["TT Queue and Unloading"]).fillna(0.0))
    pode_virar = ~expressa & ~fixa & (km >= p["dist_min_tt_km"])
    r["viagem_expressa_h"] = np.where(pode_virar, tt_expressa(km.fillna(0)), np.nan)
    r["expressa"] = np.where(expressa, "Sim", "Não")
    r["pedidos_dia"] = r["spx"] + r["fbs"]
    tabela_rotas = r.sort_values("pedidos_dia", ascending=False)[
        ["Route", "route_type", "Distance", "expressa", "fonte_tt", "pedidos_dia", "peso_spx", "peso_fbs",
         "viagem_h", "fila_h", "viagem_expressa_h"]].reset_index(drop=True)

    com_fila = r[r["fonte_fila"].isin(FONTES_COM_FILA)].copy()
    com_fila["destino"] = np.where(com_fila["fonte_fila"] == "Fora de SOC (valor padrão)", FORA_DE_SOC,
                                   com_fila["Dest"])
    filas = com_fila.groupby("destino", as_index=False).agg(
        fonte_fila=("fonte_fila", "first"), rotas=("Route", "count"), peso_spx=("peso_spx", "sum"),
        peso_fbs=("peso_fbs", "sum"), fila_h=("fila_h", "first"))
    filas = filas.sort_values("peso_spx", ascending=False).reset_index(drop=True)

    resumo = pd.DataFrame([{"mes": periodo, "bwt_spx_h": bwt["spx"], "bwt_fbs_h": bwt["fbs"],
                            "pedidos_spx": total["spx"], "pedidos_fbs": total["fbs"]}])
    return {"simulador_malha_resumo": resumo, "simulador_malha_filas": filas, "simulador_malha_rotas": tabela_rotas}


def efeito(sim, novas_viagens=None, novas_filas=None):
    """Mudança na meta de BWT (h) por canal. novas_viagens = {rota: horas}; novas_filas = {destino: horas}."""
    efeito = {"spx": 0.0, "fbs": 0.0}
    for tabela, novos, coluna, chave in [(sim["simulador_malha_rotas"], novas_viagens, "viagem_h", "Route"),
                                         (sim["simulador_malha_filas"], novas_filas, "fila_h", "destino")]:
        for nome, horas in (novos or {}).items():
            linha = tabela[tabela[chave] == nome].iloc[0]
            for k in efeito:
                efeito[k] += (horas - linha[coluna]) * linha[f"peso_{k}"]
    return efeito
