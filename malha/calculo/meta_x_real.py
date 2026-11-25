"""
Meta × realizado por etapa (KPI da By Step), no mesmo recorte: mês × canal × rota macro.

Realizado = base dev_brbi_opslgc.joao_bwt_by_step_mece somada por mês (bwt_n = horas × pedidos, bwt_d = pedidos).
Ajustes para ficar no mesmo nível da meta (iguais ao export mensal da By Step):
  - M01 APT = M02 + M03 + M04 (pedidos = os do M02);
  - FBS: o M02 dos canais Fulfillment vai para o M05; meta do FBS = M05 + M06;
  - pedidos sem bipe (Z ...) não entram por etapa, só no total.
KPI sem meta (só existe no realizado, como Pickup Point, fluxos de volta, Mobile HUB, ou sem caminho na demanda) aparece como "sem meta".
"""
import numpy as np
import pandas as pd

from .by_step import KPI, TOTAL

CANAIS_FBS = {"SPX Fulfillment", "Fulfillment XD", "Fulfillment SB"}
CHAVE = ["attempt_month", "spx_channel", "main_route"]


def _codigo(kpi):
    return kpi.str.split(" ").str[0]


def preparar_realizado(bruto):
    r = bruto.copy()
    r["attempt_month"] = pd.to_datetime(r["attempt_month"]).dt.strftime("%Y-%m-%d")
    r["bwt_n"] = pd.to_numeric(r["bwt_n"], errors="coerce").fillna(0.0)
    r["bwt_d"] = pd.to_numeric(r["bwt_d"], errors="coerce").fillna(0.0)
    r = r[~r["kpi"].str.startswith("Z ")]
    cod = _codigo(r["kpi"])
    fbs = r["spx_channel"].isin(CANAIS_FBS)
    grupo = np.select([cod.isin(["M02", "M03", "M04"]) & ~(fbs & (cod == "M02")),
                       cod.isin(["M05", "M06"]) | (fbs & (cod == "M02"))],
                      [KPI["M01"], KPI["M05+M06"]], r["kpi"])
    # pedidos: no APT contam os do M02; no FBS, os do M05 (ou M02, o maior); nos outros, soma normal
    conta = np.select([grupo == KPI["M01"], grupo == KPI["M05+M06"]], [cod == "M02", cod.isin(["M02", "M05"])], True)
    r = r.assign(kpi=grupo, d_conta=np.where(conta, r["bwt_d"], 0.0))
    g = r.groupby(CHAVE + ["kpi"], as_index=False).agg(bwt_n=("bwt_n", "sum"), d_soma=("d_conta", "sum"),
                                                        d_maior=("d_conta", "max"))
    g["bwt_d"] = np.where(g["kpi"] == KPI["M05+M06"], g["d_maior"], g["d_soma"])
    return g.drop(columns=["d_soma", "d_maior"])


def comparar(meta, realizado_bruto):
    """Uma linha por mês × canal × rota × KPI, com média da meta, média realizada e diferença (horas)."""
    real = preparar_realizado(realizado_bruto)
    m = meta[CHAVE + ["kpi", "bwt_n", "bwt_d"]]
    t = m.merge(real, on=CHAVE + ["kpi"], how="outer", suffixes=("_meta", "_real"))
    t["meta_h"] = t["bwt_n_meta"] / t["bwt_d_meta"]
    t["real_h"] = t["bwt_n_real"] / t["bwt_d_real"]
    t["dif_h"] = t["real_h"] - t["meta_h"]
    modelados = set(KPI.values()) | {TOTAL}
    t["situacao"] = np.select(
        [~t["kpi"].isin(modelados), t["bwt_d_meta"].isna(), t["bwt_d_real"].isna()],
        ["sem meta", "sem meta", "sem realizado"], "comparável")
    colunas = CHAVE + ["kpi", "situacao", "meta_h", "real_h", "dif_h", "bwt_d_meta", "bwt_d_real",
                       "bwt_n_meta", "bwt_n_real"]
    return t[colunas].sort_values(CHAVE + ["kpi"]).reset_index(drop=True)
