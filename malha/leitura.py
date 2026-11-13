"""
Leitura dos inputs no modo teste: cada aba é um CSV baixado do Google Sheets
(a aba inteira, linha 1 do CSV = linha 1 da aba) e cada API é um CSV.
"""
import csv
import io
import re
from pathlib import Path

import pandas as pd

from .configuracao import fontes

_INTERVALO = re.compile(r"^([A-Za-z]+)(\d+):([A-Za-z]+)(\d*)$")


def _coluna(letras):
    n = 0
    for c in letras.upper():
        n = n * 26 + ord(c) - ord("A") + 1
    return n


def _grade(caminho):
    dados = caminho.read_bytes()
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = dados.decode("latin-1")
    inicio = "\n".join(texto.splitlines()[:10])
    sep = ";" if inicio.count(";") > inicio.count(",") else ","
    return list(csv.reader(io.StringIO(texto), delimiter=sep))


def ler_aba(pasta_dados, nome):
    """Lê o trecho da aba definido em fontes.toml. Cabeçalho = 1ª linha do trecho; células vazias = ''."""
    cfg = fontes()["planilhas"][nome]
    arquivo = Path(pasta_dados) / cfg["pasta"] / f"{cfg['aba']}.csv"
    if not arquivo.exists():
        raise FileNotFoundError(
            f"Falta o input '{nome}': {arquivo}\n"
            f"  Baixe a aba '{cfg['aba']}' de https://docs.google.com/spreadsheets/d/{cfg['planilha']} como CSV.")
    # arquivo grande (ex.: distâncias, 72 MB): guarda uma cópia rápida (Parquet) e reaproveita
    # enquanto o CSV não mudar
    cache = arquivo.with_name(f"{arquivo.stem}.{cfg['intervalo'].replace(':', '-')}.cache.parquet")
    grande = arquivo.stat().st_size > 5_000_000
    if grande and cache.exists() and cache.stat().st_mtime >= arquivo.stat().st_mtime:
        return pd.read_parquet(cache)
    df = _ler_intervalo(arquivo, cfg)
    if grande:
        df.to_parquet(cache, index=False)
    return df


def _ler_intervalo(arquivo, cfg):
    grade = _grade(arquivo)
    m = _INTERVALO.match(cfg["intervalo"])
    c1, l1, c2 = _coluna(m.group(1)), int(m.group(2)), _coluna(m.group(3))
    l2 = int(m.group(4)) if m.group(4) else len(grade)
    linhas = [[(lin[c - 1] if c - 1 < len(lin) else "") for c in range(c1, c2 + 1)] for lin in grade[l1 - 1:l2]]
    if not linhas:
        return pd.DataFrame()
    cabecalho = [h.strip() for h in linhas[0]]
    while cabecalho and cabecalho[-1] == "":
        cabecalho.pop()
    corpo = [lin[:len(cabecalho)] for lin in linhas[1:] if any(v.strip() for v in lin)]
    return pd.DataFrame(corpo, columns=cabecalho)


def ler_api(pasta_dados, nome):
    cfg = fontes()["api"][nome]
    arquivo = Path(pasta_dados) / "api" / cfg["arquivo"]
    if not arquivo.exists():
        raise FileNotFoundError(f"Falta o input da API '{cfg['nome']}': {arquivo}")
    return pd.read_csv(arquivo, dtype=str, keep_default_na=False)
