"""
Compara a ferramenta nova com o processo atual, com os mesmos dados.
O processo atual roda pelo simulador de teste_local (sem internet, sem gravar nada).
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

from .calculo.malha import COLUNAS_SAIDA as COLUNAS_MALHA
from .calculo.rotas import COLUNAS_SAIDA as COLUNAS_ROTAS
from .pipeline import calcular, ler_inputs

RAIZ = Path(__file__).resolve().parents[1]


def _processo_atual(pasta_dados):
    """Roda as etapas 1 e 2 originais em sequência (a 2 lê o que a 1 subiria no Hive)."""
    sys.path.insert(0, str(RAIZ / "teste_local"))
    from simulador import Simulador
    sim = Simulador(pasta_dados, RAIZ / "teste_local" / "saida" / "_comparacao")
    with redirect_stdout(io.StringIO()):
        etapa1 = sim.rodar_script("network_input_to_bwt_generation.py", "x",
                                  [(r"ingestion_token =[ \t]*\n", "ingestion_token = None\n", "")])
        etapa2 = sim.rodar_script("outobund_by_soc_tt_by_routes.py", "x")
        sim.rodar_script("outobund_by_soc_tt_by_routes_manual_express.py", "x")
    # a etapa 3 só grava na planilha: pega a aba [T] 4.1 como ficou (cabeçalho na linha 3)
    aba = sim.planilhas[("1HdplQWZuaSrEYQLNWQYA0gc5rCqXaLCt-aaLJ2xD3FE",
                         "[T] 4.1 TT and SOC Packed to Transporting to SOC")]
    largura = len(aba[2])
    linhas = [l + [""] * (largura - len(l)) for l in aba[3:] if any(l)]
    etapa3 = pd.DataFrame([l[:largura] for l in linhas], columns=aba[2])
    return {"malha": etapa1["network_output"], "rotas_padrao": etapa2["routes_output"], "rotas": etapa3}


def _diferencas(atual, nova, chave, colunas):
    vazio = {"nan": "", "None": "", "NaN": "", "<NA>": ""}  # célula sem valor, escrita de jeitos diferentes
    a = atual[colunas].fillna("").astype(str).replace(vazio).sort_values(chave).reset_index(drop=True)
    b = nova[colunas].fillna("").astype(str).replace(vazio).sort_values(chave).reset_index(drop=True)
    if len(a) != len(b) or not (a[chave].values == b[chave].values).all():
        return [("(lista de linhas)", "", f"atual={len(a)} linhas", f"nova={len(b)} linhas")]
    erros = []
    for col in colunas:
        x = pd.to_numeric(a[col].replace("", np.nan), errors="coerce")
        y = pd.to_numeric(b[col].replace("", np.nan), errors="coerce")
        numerico = x.notna() | y.notna()
        iguais = np.where(numerico, np.isclose(x, y, equal_nan=True),
                          a[col].str.upper() == b[col].str.upper())
        for i in np.where(~iguais)[0]:
            erros.append((" | ".join(a.loc[i, chave]), col, a.loc[i, col], b.loc[i, col]))
    return erros


def comparar(pasta_dados):
    atual = _processo_atual(pasta_dados)
    with redirect_stdout(io.StringIO()):
        nova = calcular(ler_inputs(pasta_dados))
    testes = [("Malha (etapa 1)", "malha", ["period_start", "E2E Path"], COLUNAS_MALHA),
              ("Rotas (etapa 2)", "rotas_padrao", ["period_start", "Route"], COLUNAS_ROTAS),
              ("Rotas após ajuste manual (etapa 3)", "rotas", ["period_start", "Route"], COLUNAS_ROTAS)]
    tudo_ok = True
    for titulo, nome, chave, colunas in testes:
        erros = _diferencas(atual[nome], nova[nome], chave, colunas)
        if erros:
            tudo_ok = False
            print(f"[DIFERENTE] {titulo}: {len(erros)} diferença(s)")
            for linha, col, va, vb in erros[:20]:
                print(f"    {linha:45} {col:24} atual={va!r:14} nova={vb!r}")
        else:
            print(f"[IGUAL] {titulo}: {len(atual[nome])} linhas iguais em {len(colunas)} colunas")
    return tudo_ok
