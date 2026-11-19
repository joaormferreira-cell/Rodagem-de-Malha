"""
Testes automáticos da ferramenta nova.  Rodar:  python -m pytest tests -q
- paridade: dá o mesmo resultado que o processo atual, com os dados de exemplo;
- carga: aguenta o volume real (~95 mil caminhos por mês) em poucos segundos.
"""
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from malha.comparar import comparar  # noqa: E402
from malha.pipeline import calcular  # noqa: E402

CAMINHOS_NO_TESTE_DE_CARGA = 100_000
LIMITE_SEGUNDOS = 60


def test_paridade_com_processo_atual():
    assert comparar(RAIZ / "teste_local" / "dados_exemplo")


def _inputs_sinteticos(n, semente=42):
    """Malha inventada no formato real: FMH → SOC → (SOC) → HUB → (XPT), estações espalhadas pelo Brasil."""
    rng = np.random.default_rng(semente)
    estacoes = {"FMH": [f"FMH-X{i:03d}" for i in range(300)], "SOC": [f"SOC-X{i:02d}" for i in range(40)],
                "HUB": [f"HUB-X{i:03d}" for i in range(500)], "XPT": [f"XPT-X{i:03d}" for i in range(150)]}
    todas = [e for lista in estacoes.values() for e in lista]
    coords = pd.DataFrame({"station_code": todas, "station_type": [e[:3] for e in todas],
                           "latitude": rng.uniform(-30, -3, len(todas)).round(4).astype(str),
                           "longitude": rng.uniform(-55, -35, len(todas)).round(4).astype(str)})
    pega = lambda tipo: rng.choice(estacoes[tipo], n)  # noqa: E731
    fmh, soc1, soc2, hub, xpt = pega("FMH"), pega("SOC"), pega("SOC"), pega("HUB"), pega("XPT")
    com_soc2, com_xpt = rng.random(n) < 0.6, rng.random(n) < 0.15
    caminhos = [">".join([f, s1] + ([s2] if c2 and s2 != s1 else []) + [h] + ([x] if cx else []))
                for f, s1, s2, h, x, c2, cx in zip(fmh, soc1, soc2, hub, xpt, com_soc2, com_xpt)]
    demanda = pd.DataFrame({"period_start": "2026-11-01", "period_end": "2026-11-30", "origin": fmh,
                            "destination": np.where(com_xpt, xpt, hub), "path": caminhos,
                            "forecast_ado": rng.uniform(10, 3000, n).round(2).astype(str)})
    vazio = lambda cols: pd.DataFrame({c: pd.Series(dtype=str) for c in cols})  # noqa: E731
    return {
        "demanda": demanda,
        "distancias": vazio(["origin", "destini", "distance_km", "route"]),  # tudo pela linha reta
        "estacoes_historico": coords,
        "estacoes_base": vazio(["Code", "SubRegion", "Lat", "Lon"]),
        "expressas": vazio(["Rota atualizada com movings", "Transit time atualizado", "Status",
                            "Data da última alteração", "Data de ramp-up"]),
        "new_tt": vazio(["ORIGEM", "DESTINO", "TT HRS", "STATUS DA ROTA"]),
        "spr": pd.DataFrame({"route_code": ["x"], "route_type": ["SOC-SOC"], "origin_station_code": ["SOC-SOC"],
                             "destination_considered": ["x"], "carreta_cap": ["4500"], "truck_cap": ["2000"],
                             "others_cap": ["800"]}),
        "tempos_soc": pd.DataFrame({"Sites": ["SOC-X00", "Other"], "Loading": ["2", "1"]}),
        "arrived_received": pd.DataFrame({"code": ["SOC-X00"], "nome": ["x"], "reg": ["x"], "2026-11-01": ["3"]}),
        "air_lh": vazio(["Route", "TT (hours)"]),
        "metas": _metas_sinteticas(rng, estacoes),
        "estacoes_subregiao": pd.DataFrame({"Code": estacoes["FMH"][:50], "SubRegion": "SAO"}),
        "spx_info": pd.DataFrame({"station_code": estacoes["HUB"][:50], "zipcode": "01001000"}),
        "estacoes_estado": pd.DataFrame({"station_code": estacoes["XPT"], "state_name": "Bahia", "status": "1"}),
    }


def _metas_sinteticas(rng, estacoes):
    mes = "2026-11-01"
    por_codigo = lambda tipo: pd.DataFrame({"code": estacoes[tipo],  # noqa: E731
                                            mes: rng.uniform(1, 20, len(estacoes[tipo])).round(2).astype(str)})
    unico = pd.DataFrame({mes: ["20"]})
    fmh = pd.DataFrame({"code": estacoes["FMH"], "period_start": mes, "Target Received to Transporting": "3"})
    return {"meta_1_0": unico, "meta_2_0": unico, "meta_2_1": por_codigo("FMH"), "meta_3_0_1": fmh,
            "meta_3_0_2": fmh, "meta_3_1": pd.DataFrame({"code": ["FBS-X"], mes: ["5"]}),
            "meta_4_0": por_codigo("SOC"), "meta_4_2": por_codigo("SOC"), "meta_4_9": por_codigo("HUB"),
            "meta_5_0": por_codigo("HUB"), "meta_5_1_0": por_codigo("HUB"), "meta_5_1_1": por_codigo("HUB"),
            "meta_5_9": por_codigo("XPT"), "meta_6_0": por_codigo("XPT"), "meta_7_0": por_codigo("HUB"),
            "meta_7_1": por_codigo("XPT"), "meta_8": pd.DataFrame({"code": ["Airport-GRU"], mes: ["6"]})}


def test_carga_volume_real():
    entradas = _inputs_sinteticos(CAMINHOS_NO_TESTE_DE_CARGA)
    inicio = time.perf_counter()
    with redirect_stdout(io.StringIO()):
        resultado = calcular(entradas)
    segundos = time.perf_counter() - inicio
    print(f"\n{CAMINHOS_NO_TESTE_DE_CARGA:,} caminhos -> {len(resultado['rotas']):,} rotas em {segundos:.1f}s")
    assert len(resultado["malha"]) == CAMINHOS_NO_TESTE_DE_CARGA
    assert len(resultado["bwt_caminhos"]) == CAMINHOS_NO_TESTE_DE_CARGA
    assert segundos < LIMITE_SEGUNDOS


def test_checagens():
    from malha.checagens import checar_inputs
    from malha.pipeline import ler_inputs
    entradas = ler_inputs(RAIZ / "teste_local" / "dados_exemplo")
    assert not checar_inputs(entradas).tem_erro()            # dados de exemplo: sem erro
    entradas["spr"] = entradas["spr"].assign(carreta_cap="0")   # capacidade 0 = divisão por zero
    rel = checar_inputs(entradas).tabela()
    linha = rel[rel["checagem"].str.startswith("carreta_cap zero")].iloc[0]
    assert linha["nivel"] == "ERRO" and linha["qtd"] > 0


def test_gravacao_substitui_mes_sem_duplicar():
    from malha.calculo.bwt import COLUNAS_1O_SOC, COLUNAS_RESUMO, COLUNAS_SAIDA
    from malha.gravar import plano_de_gravacao
    novo = pd.DataFrame({c: [0] * 2 for c in COLUNAS_RESUMO})
    novo["period_start"] = ["2026-10-01", "2026-11-01"]
    hoje = pd.DataFrame([["2026-08-01"] + [""] * (len(COLUNAS_RESUMO) - 1),      # o que já está na planilha
                         ["2026-10-01"] + [""] * (len(COLUNAS_RESUMO) - 1)], columns=["x"] * len(COLUNAS_RESUMO))
    resultados = {"bwt_resumo": novo, "bwt_caminhos": pd.DataFrame(columns=COLUNAS_SAIDA),
                  "bwt_1o_soc": pd.DataFrame(columns=COLUNAS_1O_SOC)}
    p = plano_de_gravacao(resultados, {"raw_bwt": hoje}, ["2026-11-01"])["raw_bwt"]
    assert p["manter"] == 1                                       # agosto fica; outubro antigo sai
    assert list(p["linhas"]["period_start"]) == ["2026-08-01", "2026-10-01", "2026-11-01"]


def test_rotas_meta_x_real():
    """Junta meta e real pela rota (mesmo com sufixo [DC]/-X no código) e classifica a diferença."""
    from malha.calculo.rotas_x_real import comparar_rotas
    rotas = pd.DataFrame({"period_start": "2026-10-01", "Route": ["SOC-A>SOC-B", "SOC-A>HUB-C-X", "SOC-A>SOC-D"],
                          "route_type": ["SOC-SOC", "SOC-HUB", "SOC-SOC"], "Origin": "SOC-A",
                          "Dest": ["SOC-B", "HUB-C-X", "SOC-D"], "ADO": [100, 50, 10], "Distance": [500, 30, 900],
                          "fonte_tt": "New TT", "TT with Express": [10, 2, 20], "TT Queue and Unloading": [4, 0, 4],
                          "TTFinal": [14, 2, 24]})
    real = pd.DataFrame({"rota": ["SOC-A>SOC-B", "SOC-A[DC]>HUB-C", "SOC-A>SOC-E"], "mes": "2026-10-01",
                         "pacotes": [1000, 500, 300], "horas_media": [20, 2.5, 8], "horas_mediana": [19, 2, 8],
                         "estrada_media": [11, 2.5, 6], "fila_media": [9, None, 2]})
    t = comparar_rotas(rotas, real).set_index("rota")
    assert t.loc["SOC-A>SOC-B", "situacao"] == "real acima da meta (+4h)"
    assert t.loc["SOC-A>SOC-B", "dif_fila_h"] == 5 and t.loc["SOC-A>SOC-B", "dif_estrada_h"] == 1
    assert t.loc["SOC-A>HUB-C-X", "situacao"] == "ok (até 2h)"
    assert t.loc["SOC-A>SOC-D", "situacao"].startswith("sem real")
    assert t.loc["SOC-A>SOC-E", "situacao"].startswith("só no real")


def test_tres_visoes_initiatives():
    """Lê a grade da aba Nov26-27 (total em dias, etapa em horas) e põe Rodagem | Initiatives | By Step lado a lado."""
    from malha.calculo.initiatives import tres_visoes
    grade = pd.DataFrame([
        ["", "", "", "", "Share", "LT", "Share", "LT"],
        ["", "", "", "", "Actuals", "Actuals", "Target", "Target"],
        ["", "Key", "Leg", "Status", "Oct/26", "Oct/26", "Nov/26", "Nov/26"],
        ["", "", "   (-) SPX D2D", "-", "85%", "4.90", "81%", "4.75"],
        ["", "", "1st SOC", "SOC1 Received to SoC Packed (With Transshipment)", "98%", "8.46", "98%", "8.04"],
    ])
    linha = lambda mes, kpi, n, d: {"attempt_month": mes, "spx_channel": "SPX D2D",  # noqa: E731
                                     "main_route": "BR - BR", "kpi": kpi, "bwt_n": n, "bwt_d": d}
    meta = pd.DataFrame([linha("2026-11-01", "FLOW BWT TOT", 1100, 10),
                         linha("2026-11-01", "M24 SOC1: Received to Packed", 72, 9)])
    real = pd.DataFrame([linha("2026-10-01", "FLOW BWT TOT", 1200, 10),
                         linha("2026-10-01", "M24 SOC1: Received to Packed", 50, 5)])
    t = tres_visoes(meta, grade, real).set_index("etapa (Initiatives)")
    total, soc1 = "BWT total SPX D2D", "SOC1 Received to SoC Packed (With Transshipment)"
    assert t.loc[total, "Meta Initiatives Nov/26"] == 4.75 * 24        # dias → horas
    assert t.loc[total, "Meta Rodagem Nov/26"] == 110
    assert t.loc[soc1, "Meta Rodagem Nov/26"] == 8 and t.loc[soc1, "Meta Initiatives Nov/26"] == 8.04
    assert t.loc[soc1, "% pedidos Rodagem"] == 90
    assert t.loc[soc1, "Real By Step Out/26"] == 10
    assert "medida diferente" in t.loc[soc1, "observação"]            # 8,46h na Initiatives × 10h na By Step


def test_metas_padronizadas_nao_perdem_nada():
    """As 17 abas de meta viram uma tabela única e voltam: o BWT calculado tem de ser idêntico."""
    from malha.comparar import _diferencas
    from malha.calculo.bwt import COLUNAS_SAIDA
    from malha.padronizar import metas_longas, metas_para_abas
    from malha.pipeline import ler_inputs
    entradas = ler_inputs(RAIZ / "teste_local" / "dados_exemplo")
    reconstruidas = dict(entradas, metas=metas_para_abas(metas_longas(entradas["metas"])))
    with redirect_stdout(io.StringIO()):
        a, b = calcular(entradas), calcular(reconstruidas)
    assert not _diferencas(a["bwt_caminhos"], b["bwt_caminhos"], ["period_start", "E2E Path"], COLUNAS_SAIDA)


def test_meta_by_step_tem_todas_as_linhas_da_by_step():
    from malha.calculo.by_step import ETAPAS_BY_STEP, KPI, TOTAL
    from malha.relatorio import _by_step_brasil
    meta = pd.DataFrame({"attempt_month": "2026-11-01", "spx_channel": "SPX D2D", "main_route": "BR - BR",
                         "kpi": [KPI["M01"], KPI["M24"], TOTAL], "media_h": [28.0, 8.0, 110.0]})
    t = _by_step_brasil(meta).set_index("etapa (KPI By Step)")
    assert set(ETAPAS_BY_STEP) <= set(t.index) and t.index[-1] == TOTAL
    assert t.index.get_loc(KPI["M01"]) < t.index.get_loc("M02 Seller: Paid to Label")
    assert t.loc[KPI["M24"], "observação"] == ""                          # tem meta: sem nota
    assert "M01" in t.loc["M03 Seller: Label to Dropoff", "observação"]   # meta junta: aponta para o M01
    assert t.loc["M44 LH LMH-SOC", "observação"].startswith("Sem meta")


def test_ponte_do_bwt():
    """A ponte fecha: soma das etapas = real − meta; tempo + pedidos = total da etapa; onde atacar sem rota dobrada."""
    from malha.calculo.by_step import KPI, TOTAL
    from malha.calculo.ponte import onde_atacar, ponte_etapas
    from malha.calculo.rotas_x_real import comparar_rotas

    def base(mes, linhas):   # (kpi, horas, pedidos)
        return pd.DataFrame([{"attempt_month": mes, "spx_channel": "SPX D2D", "main_route": "BR - BR", "kpi": k,
                              "bwt_n": h * d, "bwt_d": d} for k, h, d in linhas])
    meta = base("2026-11-01", [(TOTAL, 30, 100), (KPI["M24"], 10, 100), (KPI["M26"], 20, 100)])
    real = base("2026-10-01", [(TOTAL, 36, 100), (KPI["M24"], 12, 100), (KPI["M26"], 20, 100),
                               ("M44 LH LMH-SOC", 40, 10)])
    p = ponte_etapas(meta, real).set_index("etapa (KPI By Step)")
    assert abs(p.loc["BWT total", "a reduzir no BWT (h)"] - 6) < 1e-9
    assert abs(p.loc[KPI["M24"], "a reduzir no BWT (h)"] - 2) < 1e-9 and abs(p.loc[KPI["M26"], "a reduzir no BWT (h)"]) < 1e-9
    assert abs(p.iloc[1:]["a reduzir no BWT (h)"].sum() - 6) < 1e-9   # a etapa sem meta (M44) completa a ponte
    e = p.loc[KPI["M24"]]
    assert abs(e["por tempo (h)"] + e["por nº de pedidos (h)"] - e["a reduzir no BWT (h)"]) < 1e-9

    rotas = pd.DataFrame({"period_start": "2026-10-01", "Route": ["SOC-A>HUB-B", "SOC-A>HUB-B-X", "SOC-A>SOC-C"],
                          "route_type": ["SOC-HUB", "SOC-HUB", "SOC-SOC"], "Origin": "SOC-A",
                          "Dest": ["HUB-B", "HUB-B-X", "SOC-C"], "ADO": [100, 50, 80], "Distance": 500,
                          "fonte_tt": "New TT", "fonte_fila": ["Sem fila (regra)", "Sem fila (regra)", "Fila do próprio SOC"],
                          "TT with Express": [10, 10, 10], "TT Queue and Unloading": [0, 0, 4], "TTFinal": [10, 10, 14]})
    lh = pd.DataFrame({"rota": ["SOC-A>HUB-B", "SOC-A>SOC-C"], "mes": "2026-10-01", "pacotes": [1000, 1000],
                       "horas_media": [14, 20], "horas_mediana": [14, 20], "estrada_media": [14, 12], "fila_media": [None, 8]})
    rx = comparar_rotas(rotas, lh)
    assert rx["real_pacotes"].sum() == 2000                                # HUB-B e HUB-B-X: real contado uma vez só
    real_out = base("2026-10-01", [(TOTAL, 36, 100)])
    a = onde_atacar(rx, real_out).set_index("onde")
    assert a.loc["SOC-C", "efeito no BWT Brasil (h)"] == 4 * 1000 / 100    # fila 8h × meta 4h
    assert a.loc["SOC-A>HUB-B", "efeito no BWT Brasil (h)"] == 4 * 1000 / 100
    assert "SOC-A>HUB-B-X" not in a.index


def test_simulador_de_iniciativas():
    """Ponte real → meta fecha; todas ligadas = soma das etapas da meta; desligar devolve o impacto × % de pedidos."""
    from malha.calculo.simulador import bwt_simulado, ler_simulador
    soc1 = "SOC1 Received to SoC Packed (With Transshipment)"
    grade = pd.DataFrame([
        ["", "", "", "", "Share", "LT", "Share", "LT", "Share", "LT", "", ""],
        ["", "", "", "", "Actuals", "Actuals", "Target", "Target", "Target", "Target", "", ""],
        ["", "Key", "Leg", "Status", "Oct/26", "Oct/26", "Nov/26", "Nov/26", "Nov/27", "Nov/27", "Owner", "Saving rationale"],
        ["", "", "   (-) SPX D2D", "-", "85%", "1.00", "81%", "0.95", "80%", "0.90", "", ""],
        ["", "", "SPX D2D", "", "", "", "", "", "", "", "", ""],
        ["", "", "Seller", "APT (Paid to Pickup or Dropoff)", "100%", "20.00", "100%", "20.50", "100%", "19.50", "Ana", ""],
        ["", "", "Seller", "Feriados (Impactos de feriados)", "-", "-", "-", "0.50", "-", "0.00", "Ana", ""],
        ["", "", "Seller", "Iniciativa A", "-", "-", "-", "0.00", "-", "-1.00", "Ana", "porque sim"],
        ["", "", "Seller", "Sem impacto", "-", "-", "-", "0.00", "-", "0.00", "Ana", ""],
        ["", "", "1st SOC", soc1, "50%", "8.00", "50%", "8.00", "60%", "7.00", "", ""],
        ["", "", "SOC", "Iniciativa B", "-", "-", "-", "-0.50", "-", "-0.50", "", ""],
    ])
    s = ler_simulador(grade)
    r, ini = s["resumo"], s["iniciativas"].set_index("iniciativa")
    assert list(ini.index) == ["Feriados (Impactos de feriados)", "Iniciativa A", "Iniciativa B"]   # sem a linha zerada
    assert r["total_b_h"] == 0.90 * 24 and r["soma_real_h"] == 20 + 0.5 * 8
    assert abs(r["soma_real_h"] + r["mix_h"] + r["iniciativas_h"] + r["ajustes_h"] - r["soma_b_h"]) < 1e-9
    assert abs(r["soma_b_h"] - (19.5 + 0.6 * 7)) < 1e-9
    assert ini.loc["Iniciativa B", "impacto_bwt_h"] == -1.0 * 0.6          # (−0,5 −0,5) × 60%
    assert "feriados" in ini.loc["Feriados (Impactos de feriados)", "observacao"]
    assert abs(bwt_simulado(s, [s["iniciativas"].index[2]]) - (r["soma_b_h"] + 0.6)) < 1e-9
