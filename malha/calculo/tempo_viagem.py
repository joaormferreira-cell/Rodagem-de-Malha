"""Tempo de viagem por distância (horas), pelas premissas de malha/config/premissas.toml."""
import numpy as np

from ..configuracao import premissas


def _dirigindo(km, p):
    km = np.asarray(km, dtype=float)
    return np.minimum(km, p["km_inicio"]) / p["vel_inicio_kmh"] + np.maximum(km - p["km_inicio"], 0) / p["vel_estrada_kmh"]


def tt_normal(km, p=None):
    p = p or premissas()["tempo_viagem"]["normal"]
    base = _dirigindo(km, p)
    return (base + np.floor(base / p["descanso_longo_a_cada_h"]) * p["descanso_longo_h"]
            + np.floor(base / p["descanso_curto_a_cada_h"]) * p["descanso_curto_h"])


def tt_expressa(km, p=None):
    p = p or premissas()["tempo_viagem"]["expressa"]
    base = _dirigindo(km, p)
    return (base + np.floor(base / p["troca_motorista_a_cada_h"]) * p["troca_motorista_h"]
            + np.floor(base / p["descanso_curto_a_cada_h"]) * p["descanso_curto_h"])
