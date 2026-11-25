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


def test_dados_bwt_por_etapa(tmp_path):
    from malha.calculo.by_step import dados_bwt_por_etapa
    caminhos = _caminhos(tmp_path)
    spx_info = pd.DataFrame({"station_code": [], "state_name": [], "city_name": []})
    with redirect_stdout(io.StringIO()):
        d = dados_bwt_por_etapa(meta_by_step(caminhos, spx_info))
    # BWT de cada etapa = horas × pedidos ÷ pedidos do recorte; a soma das etapas dá o BWT total dos caminhos
    soma = d["horas"].sum() / d["total_pedidos"]
    assert np.allclose(soma, d["total_horas"] / d["total_pedidos"])
    assert ((d["pedidos"].fillna(0) / d["total_pedidos"]).stack().between(0, 1)).all()
    # BWT total = média dos caminhos (SPX D2D + FF D2D) ponderada pelos pedidos
    c = caminhos.assign(mes=caminhos["period_start"].astype(str), h=pd.to_numeric(caminhos["bwt_total_hours"]),
                        ado=pd.to_numeric(caminhos["ADO"]))
    esperado = (c["h"] * c["ado"]).groupby(c["mes"]).sum() / c.groupby("mes")["ado"].sum()
    assert np.allclose((d["total_horas"] / d["total_pedidos"]).reindex(esperado.index), esperado)


def test_checks_de_estacao():
    from malha.calculo.by_step import CHECAGENS_ESTACAO, KPI, leg_tipo
    from malha.excel_by_step import AbaByStep
    # 100 pedidos: 90 SPX (60 Pickup→SOC, 30 Pickup→FMH; FMH manda 25 ao SOC e 5 ao LMH), 10 FBS (8 ao SOC, 2 ao LMH);
    # SOC1 recebe 93: 50 seguem para o SOC2, 33 para o LMH e 10 para o XPT; SOC2 manda tudo ao LMH.
    pedidos = {"M01": 90, "M05+M06": 10, "M07": 90, "M09": 60, "M10": 30, "M13": 8, "M15": 2, "M18": 30, "M19": 30,
               "M20": 25, "M21": 5, "M24": 85, "M25": 93, "M26": 50, "M27": 50, "M28": 50, "M32": 83, "M33": 10,
               "M41": 90, "M42": 90, "M43": 5, "M48": 15, "M49": 15, "M62": 85, "M63": 15}
    regras = [(leg_tipo(KPI[o])[0], t, [KPI[c] for c in e], None if d is None else [KPI[c] for c in d])
              for o, t, e, d in CHECAGENS_ESTACAO]

    def aba(ped):
        idx = [KPI[k] for k in ped]
        dados = {"meses": ["2026-11-01"], "pedidos": pd.DataFrame({"2026-11-01": list(ped.values())}, index=idx),
                 "horas": pd.DataFrame({"2026-11-01": [10.0 * v for v in ped.values()]}, index=idx),
                 "total_pedidos": pd.Series({"2026-11-01": 100.0}), "total_horas": pd.Series({"2026-11-01": 0.0})}
        linhas = [{"chave": k, "rotulos": [k], "obs": "", "com_dado": True, "fora_da_soma": False} for k in idx]
        a = AbaByStep("t", "t", ["Etapa"], [10], linhas, dados, regras, "", None, {}, "rota_br", "total_by_step")
        a.resultados({})
        return a

    a = aba(pedidos)
    estacao = [i for i, c in enumerate(a.checks) if c["tipo"] == "estacao"]
    assert all(a.ok[(i, 0)] for i in estacao)
    # SOC1 com saída zerada para 3 pedidos (como uma meta 0 na [T] 4.2): acusa SOC1 e a saída dos SOCs, só elas
    a = aba({**pedidos, "M25": 90})
    falhas = {a.checks[i]["texto"] for i in estacao if not a.ok[(i, 0)]}
    assert falhas == {"SOC1 saída = chegada no SOC1 (Pickup→SOC + LH FMH-SOC + LH FBS-SOC)",
                      "Saída dos SOCs = LH entre SOCs + LH SOC-LMH + LH SOC-XPT"}
    assert leg_tipo(KPI["M24"]) == ("1st SOC", "processing") and leg_tipo(KPI["M32"]) == ("LH SOC", "traveling")
    assert leg_tipo(TOTAL) == ("", "")


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


def test_meta_x_realizado():
    from malha.calculo.by_step import KPI
    from malha.calculo.meta_x_real import comparar
    mes, ch, rota = "2026-11-01", "SPX D2D", "BR - BR"
    meta = pd.DataFrame({"attempt_month": mes, "spx_channel": ch, "main_route": rota,
                         "kpi": [KPI["M01"], KPI["M24"]], "bwt_n": [200.0, 30.0], "bwt_d": [10.0, 10.0]})
    real = pd.DataFrame({"attempt_month": "2026-11-01 00:00:00", "spx_channel": ch, "main_route": rota,
                         "kpi": ["M02 Seller: Paid to Label", "M04 Seller: Label to Pickup",
                                 "M24 SOC1: Received to Packed", "M56 SOC to Pickup Point", "Z Pedidos sem nenhum bipe"],
                         "bwt_n": [100.0, 150.0, 40.0, 5.0, 99.0], "bwt_d": [10.0, 8.0, 10.0, 1.0, 3.0]})
    t = comparar(meta, real).set_index("kpi")
    assert t.loc[KPI["M01"], "real_h"] == 25.0          # (100 + 150) ÷ pedidos do M02 (10)
    assert t.loc[KPI["M01"], "meta_h"] == 20.0
    assert t.loc[KPI["M24"], "dif_h"] == 1.0             # 4h realizado − 3h meta
    assert t.loc["M56 SOC to Pickup Point", "situacao"] == "sem meta"
    assert "Z Pedidos sem nenhum bipe" not in t.index
