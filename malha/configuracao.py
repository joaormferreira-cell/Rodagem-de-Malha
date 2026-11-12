"""Lê as premissas e o mapa de fontes (arquivos .toml em malha/config/)."""
import tomllib
from functools import cache
from pathlib import Path

PASTA_CONFIG = Path(__file__).resolve().parent / "config"


@cache
def premissas():
    with open(PASTA_CONFIG / "premissas.toml", "rb") as f:
        return tomllib.load(f)


@cache
def fontes():
    with open(PASTA_CONFIG / "fontes.toml", "rb") as f:
        return tomllib.load(f)
