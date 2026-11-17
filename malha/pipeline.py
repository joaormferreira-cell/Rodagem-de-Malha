"""Rodagem completa: lê os inputs → monta a malha → calcula as rotas → salva os resultados."""
import time
from datetime import datetime
from pathlib import Path

from .calculo.ajuste_expressas import aplicar_ajuste, ler_lista
from .calculo.bwt import calcular_bwt
import pandas as pd

from .calculo.by_step import meta_by_step
from .calculo.meta_x_real import comparar as comparar_meta_real
from .calculo.rotas_x_real import comparar_rotas
from .calculo.initiatives import tres_visoes
from .checagens import checar_inputs, checar_resultados
from .gravar import exportar_para_botao
from .relatorio import gerar_excel
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
    """Parquet de cada tabela (completo, para sistemas) + um Excel único para pessoas."""
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for nome, tabela in resultados.items():
        tabela.astype(str).to_parquet(pasta / f"{nome}.parquet", index=False)
        arquivos.append(pasta / f"{nome}.parquet")
    if "bwt_caminhos" in resultados:
        arquivos.append(gerar_excel(resultados, pasta / f"Rodagem de Malha {datetime.now():%Y-%m-%d}.xlsx"))
        arquivos += exportar_para_botao(resultados, pasta)   # CSVs para o botão da planilha
    else:   # rodagem interrompida: só as checagens
        resultados["checagens"].to_excel(pasta / "checagens.xlsx", index=False)
        arquivos.append(pasta / "checagens.xlsx")
    return arquivos


def rodar(pasta_dados, pasta_saida):
    inicio = time.perf_counter()
    entradas = ler_inputs(pasta_dados)
    rel = checar_inputs(entradas)
    if rel.tem_erro():
        rel.imprimir()
        salvar({"checagens": rel.tabela()}, pasta_saida)
        raise SystemExit(f"\nRodagem interrompida: corrija os ERROS acima (lista em {Path(pasta_saida) / 'checagens.xlsx'}).")
    resultados = calcular(entradas)
    realizado = Path(pasta_dados) / "by_step" / "realizado.csv"
    bruto = None
    if realizado.exists():   # opcional: compara a meta com o realizado da By Step
        bruto = pd.read_csv(realizado, dtype={"bwt_n": float, "bwt_d": float})
        resultados["meta_x_realizado"] = comparar_meta_real(resultados["by_step_meta"], bruto)
    initiatives = Path(pasta_dados) / "initiatives" / "initiatives.csv"
    if initiatives.exists():   # opcional: meta da Initiatives (aba Nov26-27) para as 3 visões por etapa
        grade = pd.read_csv(initiatives, header=None, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        visoes = tres_visoes(resultados["by_step_meta"], grade, bruto)
        if visoes is not None:
            resultados["tres_visoes"] = visoes
    lh_real = Path(pasta_dados) / "lh_real" / "realizado_rotas.csv"
    if lh_real.exists():   # opcional: tempo real de estrada por rota (consultas/lh_real_por_rota.sql)
        resultados["rotas_x_real"] = comparar_rotas(resultados["rotas"], pd.read_csv(lh_real, encoding="utf-8-sig"))
    checar_resultados(resultados, entradas, rel)
    rel.imprimir()
    arquivos = salvar({**resultados, "checagens": rel.tabela()}, pasta_saida)
    print(f"\nRodagem concluída em {time.perf_counter() - inicio:.1f}s. Arquivos:")
    for a in arquivos:
        print(f"  {a}")
    return resultados
