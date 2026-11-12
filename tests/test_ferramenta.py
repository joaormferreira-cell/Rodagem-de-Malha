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
    }


def test_carga_volume_real():
    entradas = _inputs_sinteticos(CAMINHOS_NO_TESTE_DE_CARGA)
    inicio = time.perf_counter()
    with redirect_stdout(io.StringIO()):
        resultado = calcular(entradas)
    segundos = time.perf_counter() - inicio
    print(f"\n{CAMINHOS_NO_TESTE_DE_CARGA:,} caminhos -> {len(resultado['rotas']):,} rotas em {segundos:.1f}s")
    assert len(resultado["malha"]) == CAMINHOS_NO_TESTE_DE_CARGA
    assert segundos < LIMITE_SEGUNDOS
