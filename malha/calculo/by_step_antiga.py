"""
Abas "By Step antigo BR/SPM": a tabela de BWT por step do software antigo (steps bwt_*, com as linhas
Non-transshipment e With Transshipment), no recorte SPX D2D + FF D2D, sem CB, BR > BR ou SPM > SPM.

Para cada step e mês o Python entrega só dois números (inputs da aba):
  pedidos/dia que passam no step (tempo > 0)   e   horas × pedidos/dia.
Avg time step, % Share e BWT são fórmulas no Excel em cima deles.

With Transshipment: pedidos = todos que chegam no SOC (o transbordo XD conta com 0h); horas = as da linha
Non-transshipment. O BWT fica igual ao da Non-transshipment e por isso não entra de novo na soma.
SPM > SPM usa as flags origin_spm/dest_spm dos caminhos (as mesmas da raw_bwt).
"""
import pandas as pd

ETAPAS_ANTIGAS = [  # (coluna, Leg, Type, Status) na ordem da tabela antiga
    ("bwt_apt_paid_to_dropoff", "Seller", "processing", "APT (Paid to Pickup or Dropoff)"),
    ("bwt_dropoff_to_pickup", "FM", "processing", "Dropoff to Pickup"),
    ("bwt_pickup_to_received", "FM", "traveling", "Pickup to SOC/FMH received"),
    ("bwt_fbs_processing", "FM", "processing", "FBS"),
    ("bwt_fmh_received_to_packed", "FMH", "processing", "FMH received to Packed"),
    ("bwt_fmh_packed_to_transporting", "FMH", "processing", "FMH packed to Transporting"),
    ("bwt_lh_fmh_to_soc", "LH FMH to SOC", "traveling", "LH FMH to SOC Transporting to Transported"),
    ("bwt_lh_fbs_to_soc", "LH FBS to SOC", "traveling", "LH FBS to SOC Transporting to Transported"),
    ("bwt_lh_fmh_to_lmh_arrived", "LH FMH to LMH", "traveling", "LH FMH to LMH Transporting to Arrived"),
    ("bwt_lh_fbs_to_lmh_arrived", "LH FBS to LMH", "traveling", "LH FBS to LMH Transporting to Arrived"),
    *[linha for i, n, leg in [(1, "1st", "LH inter SOC 1>2"), (2, "2nd", "LH inter SOC 2>3"),
                              (3, "3rd", "LH inter SOC 3>4"), (4, "4th", None)]
      for linha in [
          (f"bwt_soc{i}_received_to_packed", f"{n} SOC", "processing",
           f"SOC{i} Received to SoC Packed (Non-transshipment)"),
          (f"bwt_soc{i}_received_to_packed_full", f"{n} SOC", "processing",
           f"SOC{i} Received to SoC Packed (With Transshipment)"),
          (f"bwt_soc{i}_packed_to_transporting", f"{n} SOC", "processing", f"SoC{i} Packed to SoC LH Transporting"),
          *([(f"bwt_lh_soc{i}_to_soc{i + 1}", leg, "traveling", f"LH{i} Transporting to LH Transported")]
            if leg else []),
      ]],
    ("bwt_lh_soc_to_lmh", "LH SOC to LMH", "traveling", "LH SOC-LMH Transporting to LH Transported"),
    ("bwt_lh_soc_to_xpt_arrived", "LH SOC to XPT", "traveling", "LH SOC-XPT Transporting to LH Arrived"),
    ("bwt_lh_arrived_to_transported", "LMH", "queue", "LH Arrived to LMH Transported"),
    ("bwt_lh_transported_to_lmh_received", "LMH", "processing", "LH Transported to LMH received"),
    ("bwt_lmh_received_to_LH_xpt_or_delivering", "LMH", "processing", "LMH received to delivering/LH transporting"),
    ("bwt_lmh_transporting_to_xpt_arrived", "LH LMH to XPT", "traveling", "LH LMH-XPT Transporting to LH Arrived"),
    ("bwt_lh_xpt_arrived_to_xpt_received", "XPT", "processing", "XPT Arrived to XPT Received"),
    ("bwt_lh_lmh_transported_to_xpt_to_delivering", "XPT", "processing", "LH transported to Delivering"),
    ("bwt_hub_delivering_to_1st_attempt", "Fleet", "traveling", "LMH Delivering to 1st"),
    ("bwt_xpt_delivering_to_1st_attempt", "Fleet", "traveling", "XPT Delivering to 1st"),
]
# With Transshipment → linha Non-transshipment de onde vêm as horas
FULL = {f"bwt_soc{i}_received_to_packed_full": f"bwt_soc{i}_received_to_packed" for i in range(1, 5)}

_SOC_SAIDA = [f"bwt_soc{i}_packed_to_transporting" for i in range(1, 5)]
_LH_ENTRE_SOCS = ["bwt_lh_soc1_to_soc2", "bwt_lh_soc2_to_soc3", "bwt_lh_soc3_to_soc4"]

# Checks de estação em pedidos/dia: (grupo, regra, lado esquerdo, lado direito; None = pedidos/dia do recorte)
CHECAGENS_ANTIGAS = [
    ("Seller", "APT + FBS = 100% dos pedidos", ["bwt_apt_paid_to_dropoff", "bwt_fbs_processing"], None),
    ("FM", "Dropoff→Pickup = APT", ["bwt_dropoff_to_pickup"], ["bwt_apt_paid_to_dropoff"]),
    ("FM", "Pickup→Recebido = Dropoff→Pickup", ["bwt_pickup_to_received"], ["bwt_dropoff_to_pickup"]),
    ("FBS", "FBS = LH saindo do FBS (para SOC ou LMH)", ["bwt_fbs_processing"],
     ["bwt_lh_fbs_to_soc", "bwt_lh_fbs_to_lmh_arrived"]),
    ("FMH", "FMH: recebido→embalado = embalado→saída", ["bwt_fmh_received_to_packed"],
     ["bwt_fmh_packed_to_transporting"]),
    ("FMH", "FMH saída = LH saindo do FMH (para SOC ou LMH)", ["bwt_fmh_packed_to_transporting"],
     ["bwt_lh_fmh_to_soc", "bwt_lh_fmh_to_lmh_arrived"]),
    ("1st SOC", "Chegada no FMH + no SOC1 (com transbordo) = Pickup→Recebido + LH FMH-SOC + LH FBS-SOC",
     ["bwt_fmh_received_to_packed", "bwt_soc1_received_to_packed_full"],
     ["bwt_pickup_to_received", "bwt_lh_fmh_to_soc", "bwt_lh_fbs_to_soc"]),
    *[chk for i, n in [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th")] for chk in [
        *([(f"{n} SOC", f"LH{i - 1} = chegada no SOC{i} (com transbordo)", [_LH_ENTRE_SOCS[i - 2]],
            [f"bwt_soc{i}_received_to_packed_full"])] if i > 1 else []),
        (f"{n} SOC", f"SOC{i}: chegada (com transbordo) = saída", [f"bwt_soc{i}_received_to_packed_full"],
         [f"bwt_soc{i}_packed_to_transporting"]),
    ]],
    ("SOC", "Saída dos SOCs = LH entre SOCs + LH SOC-LMH + LH SOC-XPT", _SOC_SAIDA,
     _LH_ENTRE_SOCS + ["bwt_lh_soc_to_lmh", "bwt_lh_soc_to_xpt_arrived"]),
    ("LMH", "Chegada no LMH = LH chegando no LMH (do SOC, FMH ou FBS)", ["bwt_lh_arrived_to_transported"],
     ["bwt_lh_soc_to_lmh", "bwt_lh_fmh_to_lmh_arrived", "bwt_lh_fbs_to_lmh_arrived"]),
    ("LMH", "LMH: chegada = recebido", ["bwt_lh_transported_to_lmh_received"], ["bwt_lh_arrived_to_transported"]),
    ("LMH", "LMH: recebido = saída", ["bwt_lmh_received_to_LH_xpt_or_delivering"],
     ["bwt_lh_transported_to_lmh_received"]),
    ("LMH", "LMH saída = LH LMH-XPT + entrega do LMH", ["bwt_lmh_received_to_LH_xpt_or_delivering"],
     ["bwt_lmh_transporting_to_xpt_arrived", "bwt_hub_delivering_to_1st_attempt"]),
    ("XPT", "Chegada no XPT = LH SOC-XPT + LH LMH-XPT", ["bwt_lh_xpt_arrived_to_xpt_received"],
     ["bwt_lh_soc_to_xpt_arrived", "bwt_lmh_transporting_to_xpt_arrived"]),
    ("XPT", "XPT: recebido = saída", ["bwt_lh_lmh_transported_to_xpt_to_delivering"],
     ["bwt_lh_xpt_arrived_to_xpt_received"]),
    ("Fleet", "Entrega do XPT = saída do XPT", ["bwt_xpt_delivering_to_1st_attempt"],
     ["bwt_lh_lmh_transported_to_xpt_to_delivering"]),
    ("Fleet", "Entrega do LMH + entrega do XPT = 100% dos pedidos",
     ["bwt_hub_delivering_to_1st_attempt", "bwt_xpt_delivering_to_1st_attempt"], None),
]
SEM_CHECAGEM_ANTIGA = ("SOC recebido→embalado (Non-transshipment): sem check de entrada/saída, porque o transbordo "
                       "(XD) passa sem ser processado. O check usa a linha With Transshipment.")
NOTA_FULL = ("BWT igual ao da linha Non-transshipment (não entra de novo na soma). Avg = esse BWT ÷ % de todos "
             "que chegam no SOC, inclusive transbordo (0h).")
NOTA_NAO_TRANSBORDO = "Só quem é processado no SOC (o transbordo XD fica de fora)."


def _num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def dados_by_step_antiga(caminhos, spm=False):
    """
    Inputs da aba, por step × mês: pedidos/dia que passam (tempo > 0) e horas × pedidos/dia.
    Totais do recorte vêm direto dos caminhos (pedidos/dia e BWT total × pedidos/dia), sem somar steps.
    """
    c = caminhos
    filtro = ((_num(c["spx_flag"]) == 1) | (_num(c["fbs_flag"]) == 1)) & (_num(c["cb_flag"]) != 1)
    if spm:
        filtro &= (c["origin_spm"] == "SPM") & (c["dest_spm"] == "SPM")
    c = c[filtro]
    mes = c["period_start"].astype(str).str[:10]
    ado = _num(c["ADO"])
    colunas = [col for col, *_ in ETAPAS_ANTIGAS]
    horas = pd.DataFrame({col: _num(c[col]) for col in colunas})
    pedidos = horas.gt(0).mul(ado, axis=0).groupby(mes).sum().T
    horas_pedidos = horas.mul(ado, axis=0).groupby(mes).sum().T
    for full, base in FULL.items():   # With Transshipment: horas da Non-transshipment
        horas_pedidos.loc[full] = horas_pedidos.loc[base]
    meses = sorted(mes.unique())
    return {"meses": meses, "pedidos": pedidos.reindex(columns=meses), "horas": horas_pedidos.reindex(columns=meses),
            "total_pedidos": ado.groupby(mes).sum().reindex(meses),
            "total_horas": (_num(c["bwt_total_hours"]) * ado).groupby(mes).sum().reindex(meses)}
