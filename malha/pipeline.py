"""Rodagem completa: lê os inputs → monta a malha → calcula as rotas → salva os resultados."""
import time
from pathlib import Path

from .calculo.malha import montar_malha
from .calculo.rotas import calcular_rotas
from .leitura import ler_api, ler_aba


def ler_inputs(pasta_dados):
    return {
        "demanda": ler_api(pasta_dados, "demanda"),
        "distancias": ler_aba(pasta_dados, "distancias"),
        "estacoes_historico": ler_aba(pasta_dados, "estacoes_historico"),
        "estacoes_base": ler_aba(pasta_dados, "estacoes_base"),
        "expressas": ler_aba(pasta_dados, "expressas"),
        "new_tt": ler_aba(pasta_dados, "new_tt"),
        "spr": ler_aba(pasta_dados, "spr"),
        "tempos_soc": ler_aba(pasta_dados, "tempos_soc"),
        "arrived_received": ler_aba(pasta_dados, "arrived_received"),
        "air_lh": ler_aba(pasta_dados, "air_lh"),
    }


def calcular(entradas):
    malha = montar_malha(entradas["demanda"], entradas["distancias"],
                         entradas["estacoes_historico"], entradas["estacoes_base"])
    rotas = calcular_rotas(malha, entradas["expressas"], entradas["new_tt"], entradas["spr"],
                           entradas["tempos_soc"], entradas["arrived_received"], entradas["air_lh"])
    return {"malha": malha, "rotas": rotas}


def salvar(resultados, pasta_saida):
    """Parquet (completo, para volume) + Excel (para abrir e conferir)."""
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for nome, tabela in resultados.items():
        tabela.astype(str).to_parquet(pasta / f"{nome}.parquet", index=False)
        arquivos.append(pasta / f"{nome}.parquet")
        if len(tabela) <= 1_000_000:
            tabela.to_excel(pasta / f"{nome}.xlsx", index=False)
            arquivos.append(pasta / f"{nome}.xlsx")
    return arquivos


def rodar(pasta_dados, pasta_saida):
    inicio = time.perf_counter()
    resultados = calcular(ler_inputs(pasta_dados))
    arquivos = salvar(resultados, pasta_saida)
    print(f"\nRodagem concluída em {time.perf_counter() - inicio:.1f}s. Arquivos:")
    for a in arquivos:
        print(f"  {a}")
    return resultados
