"""
Aba "Real x Meta - por etapa" (ponte): de onde vem cada hora entre o REAL e a META do mês da meta (Brasil, BR - BR).
Duas comparações: o real do mês em andamento (parcial, se a By Step já tiver o mês) e o do último mês fechado.

Por etapa da By Step:
  peso da etapa no BWT = horas da etapa × % dos pedidos que passam por ela   (= horas × pedidos ÷ pedidos do canal)
  a reduzir = peso no real − peso na meta   (> 0: o real está acima da meta nessa etapa)
  Separado em duas partes que somam o "a reduzir":
    por tempo   = (horas real − horas meta) × % pedidos real      → a etapa demora mais (ou menos) que a meta
    por pedidos = horas meta × (% pedidos real − % pedidos meta)  → passam mais (ou menos) pedidos por ela
  As etapas da By Step sem meta (volta, avião, Pickup Point...) entram somadas numa linha só.

Aba "Real x Meta - top rotas e SOCs": rotas (tempo de estrada) e SOCs (fila de recebimento) da aba "Real x Meta - rotas".
  efeito no BWT Brasil = horas acima da meta × pacotes do mês ÷ pedidos do mês (By Step, SPX D2D + Fulfillment).
  É aproximado: a consulta por rota conta todos os pacotes que passaram na rota.
  Não cobre o tempo DENTRO dos SOCs (recebido → embalado → saída): não há realizado por SOC.
"""
import numpy as np
import pandas as pd

from .by_step import KPI, TOTAL
from .initiatives import _rotulo
from .meta_x_real import preparar_realizado

ROTA = "BR - BR"
CANAIS = ["SPX D2D", "SPX Fulfillment"]
RELEVANTE = 0.3   # horas no BWT: abaixo disso (para mais ou para menos) a etapa está "perto da meta"
TOP = 20
SEM_META = "Etapas da By Step sem meta (volta, avião, Pickup Point, Mobile HUB...)"
_NOTA_XD = ("Meta em horas recalculada contando também os SOCs cross-dock (meta 0h), como a By Step conta. "
            "Por isso difere da aba By Step por canal; o peso no BWT é o mesmo.")
_NOTAS = {
    KPI["M05+M06"]: ("A meta ([T] 3.1, cerca de 16h) parece cobrir só pago → recebido no FBS (M05). "
                     "Recebido → saída (M06, cerca de 12h no real) fica sem meta. Confirmar com o dono da [T] 3.1 "
                     "antes de tratar como problema da operação."),
    KPI["M07"]: ("A meta [T] 2.0 vem diluída em todos os pedidos; aqui ela foi convertida para os pedidos que passam "
                 "por dropoff (% do real). O peso no BWT é o mesmo."),
    KPI["M24"]: _NOTA_XD, KPI["M27"]: _NOTA_XD, KPI["M30"]: _NOTA_XD,
}
# % de pedidos da meta que não dá para comparar direto com a By Step (o peso no BWT não muda, só a abertura):
#   SOC recebido → embalado: cross-dock tem meta 0h e não conta como passagem na meta; na By Step conta.
#   Usa o % do embalado → saída do mesmo SOC.
_MESMO_PCT = {KPI["M24"]: KPI["M25"], KPI["M27"]: KPI["M28"], KPI["M30"]: KPI["M31"]}


def _ajustar_meta(em, er):
    """Ajusta o % de pedidos da meta (e as horas, mantendo o peso) onde a definição difere da By Step."""
    em = em.copy()
    peso = em["horas"] * em["share"]
    for etapa, par in _MESMO_PCT.items():
        if etapa in em.index and par in em.index and em.at[par, "share"] > em.at[etapa, "share"]:
            em.at[etapa, "share"] = em.at[par, "share"]
    if KPI["M07"] in em.index and er["share"].get(KPI["M07"], 0) > 0:   # meta diluída: usa o % de quem passa no real
        em.at[KPI["M07"], "share"] = er.at[KPI["M07"], "share"]
    em["horas"] = peso / em["share"]
    return em


def _pesos(base, mes, canal):
    """horas e % dos pedidos de cada etapa; BWT total e pedidos do canal no mês."""
    b = base[(base["attempt_month"] == mes) & (base["spx_channel"] == canal) & (base["main_route"] == ROTA)]
    tot = b[b["kpi"] == TOTAL]
    pedidos = tot["bwt_d"].sum()
    if not pedidos:
        return None, np.nan
    e = b[b["kpi"] != TOTAL].groupby("kpi")[["bwt_n", "bwt_d"]].sum()
    etapas = pd.DataFrame({"horas": e["bwt_n"] / e["bwt_d"].replace(0, np.nan), "share": e["bwt_d"] / pedidos})
    return etapas, tot["bwt_n"].sum() / pedidos


def _leitura(total, tempo, pedidos):
    if total > RELEVANTE:
        return ("Real acima da meta: a etapa demora mais do que a meta." if tempo >= pedidos else
                "Real acima da meta: passam mais pedidos por esta etapa do que a malha prevê.")
    if total < -RELEVANTE:
        return "Real já abaixo da meta (folga)."
    return "Perto da meta."


def meses_da_ponte(by_step_meta, real):
    """Mês da meta = o último da rodagem; mês do real = o último fechado antes dele."""
    mes_meta = by_step_meta["attempt_month"].max()
    antes = sorted(m for m in set(real["attempt_month"]) if m < mes_meta)
    return mes_meta, (antes[-1] if antes else None)


def ponte_etapas(by_step_meta, realizado_bruto, ultimo_dia=None):
    """Duas comparações com a meta do mês: o real do mês em andamento (parcial) e o do último mês fechado.
    ultimo_dia: {mês: último dia com dado no realizado} (opcional, só para o rótulo)."""
    meta = by_step_meta.assign(bwt_n=pd.to_numeric(by_step_meta["bwt_n"]), bwt_d=pd.to_numeric(by_step_meta["bwt_d"]))
    real = preparar_realizado(realizado_bruto)
    mes_meta, mes_fechado = meses_da_ponte(meta, real)
    m = _rotulo(mes_meta)
    comparacoes = []
    if mes_meta in set(real["attempt_month"]):
        dia = (ultimo_dia or {}).get(mes_meta)
        ate = f" até {pd.Timestamp(dia):%d/%m}" if dia else ""
        comparacoes.append((mes_meta, f"{m}{ate}", f"Real {m}{ate} (mês em andamento) × Meta {m}"))
    if mes_fechado is not None:
        r = _rotulo(mes_fechado)
        comparacoes.append((mes_fechado, r, f"Real {r} (último mês fechado) × Meta {m}"))
    linhas = []
    for mes_real, r, comparacao in comparacoes:
        linhas += _ponte(meta, real, mes_meta, mes_real, m, r, comparacao)
    return pd.DataFrame(linhas) if linhas else None


def _ponte(meta, real, mes_meta, mes_real, m, r, comparacao):
    col_real, col_meta = "Real (h)", "Meta (h)"
    linhas = []
    for canal in CANAIS:
        em, total_meta = _pesos(meta, mes_meta, canal)
        er, total_real = _pesos(real, mes_real, canal)
        if em is None or er is None:
            continue
        em = _ajustar_meta(em, er)
        t = em.join(er, how="outer", lsuffix="_meta", rsuffix="_real")
        hm, sm = t["horas_meta"].fillna(0), t["share_meta"].fillna(0)
        hr, sr = t["horas_real"].fillna(0), t["share_real"].fillna(0)
        t["tempo"], t["pedidos"] = (hr - hm) * sr, hm * (sr - sm)
        t["reduzir"] = t["tempo"] + t["pedidos"]
        com_meta = t.index.isin(em.index)

        def linha(etapa, real_h, meta_h, share_r, share_m, reduzir, tempo, pedidos, leitura, obs=""):
            return {"comparação": comparacao, "canal": canal, "etapa (KPI By Step)": etapa, col_real: real_h,
                    col_meta: meta_h, "% pedidos real": share_r, "% pedidos meta": share_m, "horas a mais no BWT (h)": reduzir,
                    "porque demorou mais (h)": tempo, "porque passaram mais pedidos (h)": pedidos,
                    "leitura": leitura, "observação": obs}

        dif = total_real - total_meta
        linhas.append(linha("BWT total", total_real, total_meta, np.nan, np.nan, dif, np.nan, np.nan,
                            f"Para chegar na meta de {m}, o BWT precisa cair {dif:.1f}h em relação ao real de {r}."
                            if dif > 0 else f"O real de {r} já está abaixo da meta de {m}."))
        for kpi, e in t[com_meta].sort_values("reduzir", ascending=False).iterrows():
            linhas.append(linha(kpi, e["horas_real"], e["horas_meta"], 100 * sr[kpi], 100 * sm[kpi], e["reduzir"],
                                e["tempo"], e["pedidos"], _leitura(e["reduzir"], e["tempo"], e["pedidos"]),
                                _NOTAS.get(kpi, "")))
        fora = t[~com_meta]
        if len(fora):
            linhas.append(linha(SEM_META, np.nan, np.nan, np.nan, np.nan, fora["reduzir"].sum(), np.nan, np.nan,
                                "Sem meta: tempo que a malha não prevê. Lista na aba By Step por canal."))
        resto = dif - t["reduzir"].sum()
        if abs(resto) >= 0.05:
            linhas.append(linha("Resto (pedidos que não fecham por etapa)", np.nan, np.nan, np.nan, np.nan, resto,
                                np.nan, np.nan, "Diferença entre o total e a soma das etapas."))
    return linhas


def onde_atacar(rotas_x_real, realizado_bruto, top=TOP):
    """Rotas (estrada) e SOCs (fila) com real acima da meta, ordenados pelo efeito no BWT Brasil."""
    t = rotas_x_real.copy()
    for c in ["real_pacotes", "meta_viagem_h", "meta_fila_h", "meta_total_h", "real_estrada_h", "real_fila_h"]:
        t[c] = pd.to_numeric(t[c], errors="coerce")
    t = t[t["meta_total_h"].notna() & (t["real_pacotes"] > 0)]
    if t.empty:
        return None
    mes = t["mes"].max()
    t = t[t["mes"] == mes]
    real = preparar_realizado(realizado_bruto)
    pedidos = real.loc[(real["attempt_month"] == mes) & real["spx_channel"].isin(CANAIS) &
                       (real["main_route"] == ROTA) & (real["kpi"] == TOTAL), "bwt_d"].sum()
    if not pedidos:
        return None
    rotulo = _rotulo(mes)

    e = t[t["real_estrada_h"].notna() & t["meta_viagem_h"].notna()]
    estrada = pd.DataFrame({"o que": "Rota: tempo de estrada (saiu → chegou)", "onde": e["rota"],
                            "pacotes": e["real_pacotes"], "meta": e["meta_viagem_h"], "real": e["real_estrada_h"],
                            "de onde vem a meta": e["fonte_tempo"]})

    f = t[t["real_fila_h"].notna() & t["rota"].str.split(">").str[1].str.startswith("SOC")].copy()
    f["soc"] = f["rota"].str.split(">").str[1]
    f["meta_x"], f["real_x"] = f["meta_fila_h"].fillna(0) * f["real_pacotes"], f["real_fila_h"] * f["real_pacotes"]
    g = f.groupby("soc").agg(pacotes=("real_pacotes", "sum"), meta_x=("meta_x", "sum"), real_x=("real_x", "sum"),
                             fonte=("fonte_fila", lambda s: s.mode().iat[0] if len(s.mode()) else ""))
    fila = pd.DataFrame({"o que": "SOC: fila de recebimento (chegou → recebido)", "onde": g.index,
                         "pacotes": g["pacotes"], "meta": g["meta_x"] / g["pacotes"], "real": g["real_x"] / g["pacotes"],
                         "de onde vem a meta": g["fonte"]})

    a = pd.concat([estrada, fila], ignore_index=True)
    a["acima"] = a["real"] - a["meta"]
    a["efeito"] = a["acima"] * a["pacotes"] / pedidos
    a["pedidos"] = pedidos   # divisor do efeito: pedidos/dia do Brasil no mês (By Step realizado)
    a = a[a["efeito"] > 0].sort_values("efeito", ascending=False).head(top)
    a.insert(0, "posição", range(1, len(a) + 1))
    return a.rename(columns={"pacotes": f"pacotes em {rotulo}", "meta": "meta da Rodagem (h)", "real": f"real {rotulo} (h)",
                             "acima": "acima da meta (h)", "efeito": "efeito no BWT Brasil (h)",
                             "pedidos": f"pedidos Brasil em {rotulo} (By Step)"}).reset_index(drop=True)
