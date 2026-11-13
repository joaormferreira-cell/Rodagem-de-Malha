"""
Teste pesado da etapa 4 (BWT): centenas de caminhos inventados cobrindo todos os casos
(FBS, sem FMH, cross-dock, aeroporto, 1 a 4 SOCs, sem HUB, com XPT, estação sem meta, origem CB,
caminho com erro, distância -1, HUB com sufixo -X, meta vazia...).
Roda o bwt_calculator.py original (pelo simulador) e a ferramenta nova com os MESMOS dados e compara.
"""
import csv
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from malha.calculo.bwt import (COLUNAS_1O_SOC, COLUNAS_RESUMO, COLUNAS_SAIDA, GRUPO_1O_SOC,  # noqa: E402
                               GRUPO_RESUMO, calcular_bwt)
from malha.comparar import _diferencas, novo_simulador  # noqa: E402
from malha.leitura import ler_aba, ler_api  # noqa: E402
from malha.pipeline import METAS  # noqa: E402

MESES = ["2026-10-01", "2026-11-01"]
FMH = ["FMH-SP-01", "FMH-SP-02", "FMH-MG-01", "FMH-PHP-01", "FMH-GRU-01", "FMH-SEM-META"]
FBS = ["FBS-SP-01", "FBS-GO3", "FBS-SEM-META"]
SOC = ["SOC-SP1", "SOC-SP2", "SOC-RJ1", "SOC-MG1", "SOC-SP6(XD)", "SOC-RJ1(XD)", "SOC-SEM-META",
       "Airport-GRU", "Airport-MAO", "Airport-SEM-META"]
HUB = ["HUB-LSP-01", "HUB-LRJ-01", "HUB-LMG-02", "HUB-LBA-01-X", "HUB-SEM-META", "HUB-LXX-09"]
XPT = ["XPT-BA-01", "XPT-LPR-01", "XPT-SEM-META", "XPT-SC-01-X"]


def _grade(arquivo, linhas):
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with open(arquivo, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(linhas)


def _sem(c):
    return c.replace("(XD)", "")


def _sorteia_caminhos(rng, n):
    linhas = []
    for i in range(n):
        tipo = rng.choice(["FMH", "FBS", "SEM_FMH"], p=[0.6, 0.25, 0.15])
        fmh = "" if tipo == "SEM_FMH" else str(rng.choice(FMH if tipo == "FMH" else FBS))
        socs = [str(s) for s in rng.choice(SOC, rng.choice([0, 1, 2, 3, 4], p=[.1, .3, .3, .2, .1]), replace=False)]
        if not fmh and not socs:
            socs = ["SOC-SP1"]
        hub = "" if rng.random() < 0.2 else str(rng.choice(HUB))
        xpt = str(rng.choice(XPT)) if (rng.random() < 0.35 or not hub) else ""
        estacoes = [fmh] + socs + [""] * (4 - len(socs)) + [hub, xpt]
        caminho = ">".join(e for e in estacoes if e)
        dist = [str(round(float(x), 1)) for x in rng.uniform(1, 900, 8)]
        dist[6] = str(rng.choice(["0", "2", "45.5", "640"])) if hub and xpt else "0"   # HUB-XPT
        if rng.random() < 0.03:
            dist[rng.integers(0, 8)] = "-1"
        erro = "tem erro" if rng.random() < 0.03 else ""
        for mes in MESES:
            linhas.append([mes, mes[:8] + "30", fmh or socs[0], xpt or hub, caminho,
                           repr(float(rng.uniform(0.5, 5000)))] + estacoes + dist + [erro])
    colunas = (["period_start", "period_end", "ORIGIN", "DESTINATION", "E2E Path", "ADO",
                "FMH", "SOC1", "SOC2", "SOC3", "SOC4", "LMH", "XPT",
                "FMH-SOC", "SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT", "ERRO"])
    df = pd.DataFrame(linhas, columns=colunas)
    return df.drop_duplicates(["period_start", "E2E Path"]).reset_index(drop=True)


def _rotas(rng, rede):
    """[T] 4.1: TTFinal para ~85% das rotas que aparecem nos caminhos (o resto fica sem tempo)."""
    linhas = []
    for _, r in rede.iterrows():
        est = [_sem(r[c]) for c in ["FMH", "SOC1", "SOC2", "SOC3", "SOC4", "LMH", "XPT"] if r[c]]
        for a, b in zip(est, est[1:]):
            linhas.append((r["period_start"], f"{a}>{b}"))
    linhas = sorted(set(linhas))
    return [[p, rota, "", "", "", "", "", "", "", "", "", repr(float(rng.uniform(1, 60)))]
            for p, rota in linhas if rng.random() < 0.85]


def _meta_por_codigo(rng, codigos, extras=(), com_vazio=True):
    """com_vazio=False nas abas 2.1 e 3.1: célula vazia nelas quebra o processo atual (astype(float))."""
    linhas = [["code"] + MESES]
    for c in list(codigos) + list(extras):
        linhas.append([c] + [("" if com_vazio and rng.random() < 0.05 else str(round(float(rng.uniform(0.5, 30)), 2)))
                             for _ in MESES])
    return linhas


def _montar_pasta(pasta, semente=7, n=400):
    rng = np.random.default_rng(semente)
    rede = _sorteia_caminhos(rng, n)
    (pasta / "api").mkdir(parents=True)
    rede.to_csv(pasta / "api" / "network_bwt.csv", index=False)
    topo = [["Metas (TESTE)"], []]
    m = pasta / "metas_1mSxSQ"
    _grade(m / "[T] 4.1 TT and SOC Packed to Transporting to SOC.csv",
           [[], [], ["period_start", "Route", "Origin", "Dest", "route_type", "ADO", "Distance", "Final Pck-LHTr",
                     "Pck-LHTr", "Raw Pck-LHTr", "Loading", "TTFinal"]] + _rotas(rng, rede))
    _grade(m / "[T] 1.0 APT (Paid to Pickup or dropoff).csv", topo + [["", "", ""] + MESES, ["", "", "", "20", "18.5"]])
    _grade(m / "[T] 2.0 FM Dropoff to Pickup.csv", topo + [["", "", ""] + MESES, ["", "", "", "10", "9.25"]])
    fmh_com_meta = [c for c in FMH if "SEM" not in c]
    _grade(m / "[T] 2.1 FM Pickup to SOC_FMH Received.csv", topo + _meta_por_codigo(rng, fmh_com_meta + ["SOC-SP1"], com_vazio=False))
    for aba in ["[T] 3.0.1 FMH Received to Packed", "[T] 3.0.2 FMH Packed to Transporting"]:
        linhas = [["code", "period_start", "Target Received to Transporting"]]
        for mes in MESES:
            for c in fmh_com_meta + ["FBS-SP-01"]:
                linhas.append([c, mes, "" if rng.random() < 0.1 else str(round(float(rng.uniform(1, 8)), 2))])
        _grade(m / f"{aba}.csv", topo + linhas)
    _grade(m / "[T] 3.1 FBS Processing.csv", topo + _meta_por_codigo(rng, ["FBS-SP-01", "FBS-GO3"], com_vazio=False))
    socs_com_meta = ["SOC-SP1", "SOC-SP2", "SOC-RJ1", "SOC-MG1", "SOC-SP6"]
    _grade(m / "[T] 4.0 SOC Received to Packed.csv", topo + _meta_por_codigo(rng, socs_com_meta, [""]))
    _grade(m / "[T] 4.2 SOC Packed to LH Transporting.csv", topo + _meta_por_codigo(rng, socs_com_meta, [""]))
    hubs = ["HUB-LSP-01", "HUB-LRJ-01", "HUB-LMG-02", "HUB-LBA-01", "HUB-LXX-09"]
    xpts = ["XPT-BA-01", "XPT-LPR-01", "XPT-SC-01"]
    for aba, codigos in [("[T] 4.9 LMH LH Arrived to Transported", hubs), ("[T] 5.0 LMH LH Transported to Received", hubs),
                         ("[T] 5.1.0 LMH Received to Delivering", hubs), ("[T] 5.1.1 LMH Received to LH transporting to XPT", hubs),
                         ("[T] 5.9 XPT LH Arrived to XPT Received", xpts), ("[T] 6.0 XPT Received to Delivering", xpts),
                         ("[T] 7.0 LMH Delivering to 1st", hubs), ("[T] 7.1 XPT Delivering to 1st", xpts)]:
        _grade(m / f"{aba}.csv", topo + _meta_por_codigo(rng, codigos, [""]))
    _grade(m / "[T] 8. Airport Received to Flight Departure.csv", topo + _meta_por_codigo(rng, ["Airport-GRU", "Airport-MAO"]))

    b = pasta / "estacoes_base_1hZSIs"
    _grade(b / "Base.csv", [["Network Station List"], ["Code", "SubRegion"], ["FMH-SP-01", "SAO"], ["FMH-MG-01", "BHZ"],
                            ["HUB-LSP-01", "SAO"], ["XPT-BA-01", "SSA"], ["FBS-SP-01", "SAO"]])
    _grade(b / "SPX_info.csv", [["station_code", "zipcode"], ["FMH-SP-02", "1001000"], ["HUB-LRJ-01", "20040000"],
                                ["FMH-SP-01", "30140000"], ["XPT-LPR-01", ""], ["HUB-LMG-02", "30100000"]])
    _grade(pasta / "api" / "station_names.csv",
           [["station_code", "state_name", "status"], ["XPT-BA-01", "Bahia", "1"], ["XPT-LPR-01", "Paraná", "1"],
            ["XPT-LPR-01", "Santa Catarina", "0"], ["HUB-LRJ-01", "Rio de Janeiro", "1"], ["HUB-LMG-02", "nan", "1"],
            ["XPT-SC-01", "Estado Inexistente", "1"]])
    return rede


def _original(pasta):
    sim = novo_simulador(pasta, pasta / "_saida")
    with redirect_stdout(io.StringIO()):
        ctx = sim.rodar_script("bwt_calculator.py", "x")
    return ctx["network_output"], ctx["bwt_grouped"], ctx["bwt_1stSOC_grouped"]


def test_bwt_igual_ao_original_em_todos_os_casos(tmp_path):
    rede = _montar_pasta(tmp_path)
    caminhos, resumo, primeiro = _original(tmp_path)

    aba = list(csv.reader(open(tmp_path / "metas_1mSxSQ" / "[T] 4.1 TT and SOC Packed to Transporting to SOC.csv",
                               encoding="utf-8")))
    rotas = pd.DataFrame([l + [""] * (len(aba[2]) - len(l)) for l in aba[3:]], columns=aba[2])
    with redirect_stdout(io.StringIO()):
        nova = calcular_bwt(rede, rotas, {k: ler_aba(tmp_path, k) for k in METAS},
                            ler_aba(tmp_path, "estacoes_subregiao"), ler_aba(tmp_path, "spx_info"),
                            ler_api(tmp_path, "estacoes_estado"))

    assert len(caminhos) > 300
    for nome, atual, novo, chave, colunas in [
            ("caminhos", caminhos, nova["bwt_caminhos"], ["period_start", "E2E Path"],
             COLUNAS_SAIDA + ["origin_spm", "dest_spm"]),
            ("resumo", resumo, nova["bwt_resumo"], GRUPO_RESUMO, COLUNAS_RESUMO),
            ("1o SOC", primeiro, nova["bwt_1o_soc"], GRUPO_1O_SOC, COLUNAS_1O_SOC)]:
        erros = _diferencas(atual, novo, chave, colunas)
        assert not erros, f"{nome}: {len(erros)} diferença(s), ex.: {erros[:5]}"
