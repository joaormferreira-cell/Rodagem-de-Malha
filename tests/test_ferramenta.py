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
