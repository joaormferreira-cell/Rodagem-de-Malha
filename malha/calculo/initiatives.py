"""
Três visões por etapa da By Step, lado a lado (Brasil, BR - BR):
    Meta da Rodagem | Meta da Initiatives | Realizado da By Step

Initiatives = aba "Nov26-27" da planilha Initiatives BWT (1Ug8Qi…), baixada como CSV (a grade inteira, desde A1).
Ela traz, por etapa (leg) do SPX D2D, "Share" e "LT" (horas) de cada mês: Actuals (Ago–Out/26) e Target (Nov/26, Nov/27).
As linhas de total ("(-) SPX D2D", "(-) Fulfillment D2D") vêm em DIAS: viram horas (× 24).

O realizado da própria Initiatives (Actuals) serve de conferência: se for muito diferente do realizado da By Step
no mesmo mês, a etapa não está cortada no mesmo ponto nas duas planilhas (aparece em "observação").
"""
import re

import numpy as np
import pandas as pd

from .by_step import TOTAL
from .meta_x_real import preparar_realizado

ROTA = "BR - BR"
D2D, FBS = "SPX D2D", "SPX Fulfillment"
DIFERENCA_DEFINICAO = 1.0   # horas: real da Initiatives × real da By Step acima disso = etapa cortada diferente

_NOTA_M07 = ("A meta da Rodagem ([T] 2.0) já vem diluída em todos os pedidos (≈ % dropoff × tempo). "
             "A Initiatives e o realizado mostram o tempo só de quem passa pela etapa.")
_NOTA_LMH = ("A Initiatives corta em 'LH transported'; a By Step, em 'arrived'. "
             "Somando LH SOC-LMH + chegada no LMH, as duas ficam parecidas.")

# etapa na Initiatives (coluna Status) → KPIs da By Step que ela junta, observação fixa
DE_PARA = [
    ("APT (Paid to Pickup or Dropoff)", ["M01"], ""),
    ("Dropoff to Pickup", ["M07"], _NOTA_M07),
    ("Pickup to SOC/FMH received", ["M09", "M10"], ""),
    ("FMH received to Packed", ["M18"], ""),
    ("FMH Packed to transporting", ["M19"], ""),
    ("LH FMH to SOC Transporting to Transported", ["M20"], ""),
    ("SOC1 Received to SoC Packed (With Transshipment)", ["M24"], ""),
    ("SoC1 Packed to SoC LH Transporting", ["M25"], ""),
    ("LH1 Transporting to LH Transported", ["M26"], ""),
    ("SOC2 Received to SoC Packed (With Transshipment)", ["M27"], ""),
    ("SoC2 Packed to SoC LH Transporting", ["M28"], ""),
    ("LH2 Transporting to LH Transported", ["M29"], ""),
    ("SOC3 Received to SoC Packed (With Transshipment)", ["M30"], ""),
    ("SoC3 Packed to SoC LH Transporting", ["M31"], ""),
    ("LH SOC-LMH Transporting to LH Transported", ["M32"], _NOTA_LMH),
    ("LH SOC-XPT Transporting to LH Arrived", ["M33"], ""),
    ("LH Transported to LMH received", ["M41"], _NOTA_LMH),
    ("LMH received to delivering/LH transporting", ["M42"], ""),
    ("LH LMH-XPT Transporting to LH Arrived", ["M43"], ""),
    ("XPT LH Arrived to XPT Received", ["M48"], ""),
    ("LH transported to Delivering", ["M49"], ""),
    ("LMH Delivering to 1st", ["M62"], ""),
    ("XPT Delivering to 1st", ["M63"], ""),
]
TOTAIS = [("(-) SPX D2D", D2D, "BWT total SPX D2D"), ("(-) Fulfillment D2D", FBS, "BWT total Fulfillment")]
_MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _limpo(texto):
    return re.sub(r"\s+", " ", str(texto)).strip().lower()


def _numero(valor):
    t = str(valor).strip()
    pct = t.endswith("%")
    v = pd.to_numeric(t.rstrip("%"), errors="coerce")
    return v / 100 if pct else v


def _rotulo(mes):
    d = pd.Timestamp(mes)
    return f"{_MESES_PT[d.month - 1]}/{d:%y}"


def ler_initiatives(grade):
    """Grade da aba Nov26-27 → tabela longa: etapa | kpis | canal | mes | tipo (Actuals/Target) | share | horas."""
    g = grade.fillna("").astype(str)
    cab = next(i for i in range(len(g)) if _limpo(g.iat[i, 2]) == "leg" and _limpo(g.iat[i, 3]) == "status")
    colunas = []   # (coluna da hora, coluna do share, mês, tipo)
    for j in range(4, g.shape[1]):
        if _limpo(g.iat[cab - 2, j]) != "lt" or not re.match(r"^[A-Za-z]{3}/\d{2}$", g.iat[cab, j].strip()):
            continue
        mes = pd.to_datetime("01/" + g.iat[cab, j].strip(), format="%d/%b/%y").strftime("%Y-%m-%d")
        colunas.append((j, j - 1, mes, g.iat[cab - 1, j].strip()))
    etapas = {_limpo(nome): (nome, kpis) for nome, kpis, _ in DE_PARA}
    totais = {_limpo(chave): (canal, nome) for chave, canal, nome in TOTAIS}
    linhas = []
    for i in range(cab + 1, len(g)):
        leg, status = _limpo(g.iat[i, 2]), _limpo(g.iat[i, 3])
        if status in etapas:
            (nome, kpis), canal, fator = etapas[status], D2D, 1
        elif leg in totais:
            (canal, nome), kpis, fator = totais[leg], [TOTAL], 24   # total vem em dias
        else:
            continue
        for j_h, j_s, mes, tipo in colunas:
            linhas.append({"etapa": nome, "kpis": "+".join(kpis), "canal": canal, "mes": mes, "tipo": tipo,
                           "share": _numero(g.iat[i, j_s]), "horas": _numero(g.iat[i, j_h]) * fator})
    return pd.DataFrame(linhas).drop_duplicates(["etapa", "canal", "mes"])


def _media(base, mes, canal, kpis):
    """horas médias e % de pedidos (sobre o total) de um grupo de KPIs, em BR - BR."""
    b = base[(base["attempt_month"] == mes) & (base["spx_channel"] == canal) & (base["main_route"] == ROTA)]
    codigo = b["kpi"].str.split(" ").str[0]
    sel = b[b["kpi"].isin(kpis)] if kpis == [TOTAL] else b[codigo.isin(kpis)]
    total = b.loc[b["kpi"] == TOTAL, "bwt_d"].sum()
    n, d = sel["bwt_n"].sum(), sel["bwt_d"].sum()
    return (n / d if d else np.nan), (d / total if total else np.nan)


def tres_visoes(by_step_meta, grade_initiatives, realizado_bruto=None):
    """Uma linha por etapa: meta Rodagem, meta Initiatives e realizado By Step (mês da meta e mês anterior)."""
    ini = ler_initiatives(grade_initiatives)
    meta = by_step_meta.assign(bwt_n=pd.to_numeric(by_step_meta["bwt_n"]), bwt_d=pd.to_numeric(by_step_meta["bwt_d"]))
    comuns = set(ini.loc[ini["tipo"] == "Target", "mes"]) & set(meta["attempt_month"])
    if not comuns:
        return None
    mes = max(comuns)
    ant = (pd.Timestamp(mes) - pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    real = preparar_realizado(realizado_bruto) if realizado_bruto is not None else None
    m, a = _rotulo(mes), _rotulo(ant)
    linhas = []
    ordem = [(nome, canal, [TOTAL], "") for _, canal, nome in TOTAIS] + \
            [(nome, D2D, kpis, nota) for nome, kpis, nota in DE_PARA]
    for nome, canal, kpis, nota in ordem:
        i = ini[(ini["etapa"] == nome) & (ini["canal"] == canal)].set_index("mes")
        rod_h, rod_share = _media(meta, mes, canal, kpis)
        real_h, _ = _media(real, mes, canal, kpis) if real is not None else (np.nan, np.nan)
        real_ant, _ = _media(real, ant, canal, kpis) if real is not None else (np.nan, np.nan)
        ini_h = i["horas"].get(mes, np.nan)
        ini_ant = i["horas"].get(ant, np.nan)
        obs = [nota] if nota else []
        if abs(ini_ant - real_ant) > DIFERENCA_DEFINICAO:
            obs.append(f"Etapa medida diferente nas duas planilhas: real de {a} = {ini_ant:.1f}h na Initiatives "
                       f"× {real_ant:.1f}h na By Step.")
        linhas.append({
            "etapa (Initiatives)": nome, "KPI By Step": "TOTAL" if kpis == [TOTAL] else " + ".join(kpis),
            "canal": canal,
            f"Meta Rodagem {m}": rod_h, f"Meta Initiatives {m}": ini_h, f"Real By Step {m}": real_h,
            f"Real By Step {a}": real_ant, f"Real Initiatives {a}": ini_ant,
            "Rodagem − Initiatives": rod_h - ini_h, f"Real {m} − Rodagem": real_h - rod_h,
            # % dos pedidos do canal que passam pela etapa (no total não se aplica)
            "% pedidos Rodagem": np.nan if kpis == [TOTAL] else 100 * rod_share,
            "% pedidos Initiatives": np.nan if kpis == [TOTAL] else 100 * i["share"].get(mes, np.nan),
            "observação": " ".join(obs),
        })
    return pd.DataFrame(linhas)
