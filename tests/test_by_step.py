"""
Visão By Step da meta:
- nada se perde: soma das horas × pedidos de todos os KPIs = BWT total × pedidos (FLOW BWT TOT);
- a rota macro segue a mesma regra da query da By Step.
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
sys.path.insert(0, str(RAIZ / "tests"))

from malha.calculo.bwt import calcular_bwt  # noqa: E402
from malha.calculo.by_step import TOTAL, caminho_etapa, meta_by_step, rotas_macro  # noqa: E402
from malha.leitura import ler_aba, ler_api  # noqa: E402
from malha.pipeline import METAS  # noqa: E402
from test_bwt_variado import _montar_pasta  # noqa: E402


def _caminhos(tmp_path):
    rede = _montar_pasta(tmp_path, semente=5, n=500)
    aba = list(csv.reader(open(tmp_path / "metas_1mSxSQ" / "[T] 4.1 TT and SOC Packed to Transporting to SOC.csv",
                               encoding="utf-8")))
    rotas = pd.DataFrame([l + [""] * (len(aba[2]) - len(l)) for l in aba[3:]], columns=aba[2])
    with redirect_stdout(io.StringIO()):
        return calcular_bwt(rede, rotas, {k: ler_aba(tmp_path, k) for k in METAS},
                            ler_aba(tmp_path, "estacoes_subregiao"), ler_aba(tmp_path, "spx_info"),
                            ler_api(tmp_path, "estacoes_estado"))["bwt_caminhos"]


def test_soma_dos_kpis_igual_ao_total(tmp_path):
    caminhos = _caminhos(tmp_path)
    # por caminho: soma das etapas = bwt_total_hours
    longa = caminho_etapa(caminhos)
    por_caminho = longa.groupby(["period_start", "E2E Path"])["horas"].sum()
    total = caminhos.set_index(["period_start", "E2E Path"])["bwt_total_hours"]
    assert np.allclose(por_caminho.reindex(total.index).fillna(0), total)

    # agregado: soma do bwt_n dos KPIs = bwt_n do FLOW BWT TOT
    spx_info = pd.DataFrame({"station_code": [], "state_name": [], "city_name": []})
    with redirect_stdout(io.StringIO()):
        meta = meta_by_step(caminhos, spx_info)
    br = meta[meta["main_route"] == "BR - BR"]
    kpis = br[br["kpi"] != TOTAL].groupby(["attempt_month", "spx_channel"])["bwt_n"].sum()
    tot = br[br["kpi"] == TOTAL].set_index(["attempt_month", "spx_channel"])["bwt_n"]
    assert np.allclose(kpis.reindex(tot.index), tot)


def test_rota_macro_igual_a_by_step():
    assert rotas_macro("sao paulo", "osasco", "sao paulo", "sao paulo") == [
        "BR - BR", "SPM - SPM", "SP > SP", "BR>Sudeste", "BR>SP State", "BR>SP Metro", "SP Metro>SP Metro",
        "BR>SP Capital"]
    assert rotas_macro("sao paulo", "cajamar", "bahia", "salvador") == [
        "BR - BR", "SP > BA", "BR>Nordeste", "BR>BA State", "BR>Not Metro"]
    assert rotas_macro("rio de janeiro", "rio de janeiro", "sao paulo", "sao paulo") == [
        "BR - BR", "RJ > SP", "BR>Sudeste", "BR>SP State", "BR>SP Metro", "RJ Metro>SP Metro",
        "BR>SP Capital", "RJ Capital>SP Capital"]
    assert rotas_macro("", "", "", "") == ["BR - BR", "BR>Not Metro"]
