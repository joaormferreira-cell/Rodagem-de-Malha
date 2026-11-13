"""Rodagem completa: lê os inputs → monta a malha → calcula as rotas → salva os resultados."""
import time
from pathlib import Path

from .calculo.ajuste_expressas import aplicar_ajuste, ler_lista
from .calculo.bwt import calcular_bwt
from .calculo.by_step import meta_by_step
from .calculo.malha import montar_malha
from .calculo.rotas import calcular_rotas, preparar_new_tt
from .leitura import ler_api, ler_aba


METAS = ["meta_1_0", "meta_2_0", "meta_2_1", "meta_3_0_1", "meta_3_0_2", "meta_3_1", "meta_4_0", "meta_4_2",
         "meta_4_9", "meta_5_0", "meta_5_1_0", "meta_5_1_1", "meta_5_9", "meta_6_0", "meta_7_0", "meta_7_1", "meta_8"]


def ler_inputs(pasta_dados):
    return {
        "metas": {m: ler_aba(pasta_dados, m) for m in METAS},
        "estacoes_subregiao": ler_aba(pasta_dados, "estacoes_subregiao"),
        "spx_info": ler_aba(pasta_dados, "spx_info"),
        "estacoes_estado": ler_api(pasta_dados, "estacoes_estado"),
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
        "ajuste_expressas": ler_aba(pasta_dados, "ajuste_expressas"),
    }


def calcular(entradas):
    malha = montar_malha(entradas["demanda"], entradas["distancias"],
                         entradas["estacoes_historico"], entradas["estacoes_base"])
    rotas_padrao = calcular_rotas(malha, entradas["expressas"], entradas["new_tt"], entradas["spr"],
                                  entradas["tempos_soc"], entradas["arrived_received"], entradas["air_lh"])
    rotas, _ = aplicar_ajuste(rotas_padrao, ler_lista(entradas.get("ajuste_expressas")),
                              entradas["expressas"], preparar_new_tt(entradas["new_tt"]))
    bwt = calcular_bwt(malha, rotas, entradas["metas"], entradas["estacoes_subregiao"],
                       entradas["spx_info"], entradas["estacoes_estado"])
    meta = meta_by_step(bwt["bwt_caminhos"], entradas["spx_info"])
    return {"malha": malha, "rotas_padrao": rotas_padrao, "rotas": rotas, **bwt, "by_step_meta": meta}


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
