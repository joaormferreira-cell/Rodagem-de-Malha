"""
Excel único da rodagem, para quem vai usar o resultado (não precisa abrir código).
Arquitetura (excel_padrao.SECOES), na ordem "resposta primeiro", com uma aba divisória antes de cada seção:
  Comece aqui: Leia-me (capa com resultado, índice e legenda) · Check · Check - Rodagem · Premissas
  META >>: Resumo BWT · By Step BR · By Step SPM · By Step por canal · By Step antigo BR · By Step antigo SPM
  REAL x META >>: Meta x Initiatives x Real · Real x Meta - por etapa / top rotas e SOCs / por regra / rotas / detalhe
  SIMULADORES >>: Simulador - Iniciativas · Simulador - Malha
  BASES >>: Rotas - Meta · raw_meta_by_step · raw_steps_antigos          (+ CSV por caminho ao lado)
Padrão visual e de checks das planilhas de BWT do time: excel_padrao.py. Nomes das abas: excel_padrao.ABA.
"""
import numpy as np
import pandas as pd

from .calculo.bwt import COLUNAS_SAIDA as COLUNAS_BWT
from .calculo.rotas_x_real import resumo as resumo_rotas
from .excel_by_step import AbaByStep, escrever_aba, preparar_abas
from .excel_capa import escrever_capa, escrever_divisoria
from .excel_padrao import ABA, ABA_PREMISSAS, SECOES, Formatos, escrever_check, escrever_premissas
from .excel_simuladores import SimuladorIniciativas, SimuladorMalha
from .excel_tabelas import (tabela_checagens, tabela_meta_by_step, tabela_meta_x_realizado, tabela_onde_atacar,
                            tabela_ponte, tabela_regra_x_real, tabela_resumo, tabela_rotas, tabela_rotas_x_real,
                            tabela_tres_visoes)

FIXAS = {"leia_me", "check", "premissas"}   # abas que não vêm de tabela (sempre existem)


def _media_ponderada(df, grupo):
    g = df.assign(h_x_ado=df["bwt_total_hours"] * df["ADO"]).groupby(grupo, as_index=False) \
          .agg(pedidos_dia=("ADO", "sum"), caminhos=("E2E Path", "count"), h_x_ado=("h_x_ado", "sum"))
    g["bwt_horas"] = g["h_x_ado"] / g["pedidos_dia"]
    g["bwt_dias"] = g["bwt_horas"] / 24
    return g.drop(columns="h_x_ado")


def _resumo(caminhos):
    c = caminhos.copy()
    c["canal"] = np.where(c["fbs_flag"] == 1, "Fulfillment (FBS)", "SPX")
    c["regional"] = c["regional"].replace("", "(sem região)")
    brasil = _media_ponderada(c.assign(regional="BRASIL"), ["period_start", "canal", "regional"])
    regiao = _media_ponderada(c, ["period_start", "canal", "regional"])
    return pd.concat([brasil, regiao], ignore_index=True).rename(
        columns={"period_start": "mês", "regional": "região"})


def _linha_rotas_x_real(resultados):
    rr = resumo_rotas(resultados["rotas_x_real"]) if "rotas_x_real" in resultados else None
    if not rr:
        return []
    return [["Rotas: meta x real", f"{rr['rotas']} rotas comparadas. Pacotes em rotas com diferença até 2h: "
             f"{rr['ate_2h']:.0f}% · até 4h: {rr['ate_4h']:.0f}% · real 4h+ acima: {rr['acima_4h']:.0f}% · "
             f"real 4h+ abaixo: {rr['abaixo_4h']:.0f}%"]]


def gerar_excel(resultados, arquivo):
    """Excel no padrão das planilhas de BWT do time; o detalhe por caminho vai num CSV ao lado."""
    caminhos = resultados["bwt_caminhos"]
    caminhos[COLUNAS_BWT].to_csv(arquivo.with_name("BWT por caminho - todos os meses.csv"), index=False,
                                 encoding="utf-8-sig", sep=";", decimal=",")
    by_step, (raw_meta, raw_antiga) = preparar_abas(resultados)
    chave_de = {nome: chave for chave, nome in ABA.items()}
    checagens = resultados.get("checagens", pd.DataFrame(columns=["fase", "input", "checagem", "nivel", "qtd",
                                                                  "exemplos", "o_que_fazer"]))
    abas = {"resumo": tabela_resumo(_resumo(caminhos), raw_antiga),
            "bs_canal": tabela_meta_by_step(resultados["by_step_meta"], raw_meta),
            "rotas": tabela_rotas(resultados["rotas"]), "checagens": tabela_checagens(checagens),
            "raw_meta": raw_meta, "raw_antiga": raw_antiga, **{chave_de[a.nome]: a for a in by_step}}
    for chave, origem, montar in [("tres_visoes", "tres_visoes", tabela_tres_visoes), ("ponte", "ponte_bwt", tabela_ponte),
                                  ("onde_atacar", "onde_atacar", tabela_onde_atacar),
                                  ("regra", "calibracao", tabela_regra_x_real),
                                  ("rotas_x_real", "rotas_x_real", tabela_rotas_x_real),
                                  ("meta_x_real", "meta_x_realizado", tabela_meta_x_realizado)]:
        if resultados.get(origem) is not None and len(resultados[origem]):
            abas[chave] = montar(resultados[origem])
    if "simulador_resumo" in resultados:
        abas["sim_ini"] = SimuladorIniciativas(resultados)
    if "simulador_malha_rotas" in resultados:
        abas["sim_malha"] = SimuladorMalha(resultados, abas["bs_canal"])

    ordem = [(divisoria, descricao, [k for k in chaves if k in abas or k in FIXAS]) for divisoria, descricao, chaves
             in SECOES]
    linhas_check = []
    for _, _, chaves in ordem:
        for k in chaves:
            if k == "premissas":
                linhas_check.append((ABA_PREMISSAS, True, "Todas as premissas preenchidas"))
            elif k not in FIXAS:
                linhas_check.append((abas[k].nome, abas[k].n_falso == 0, abas[k].o_que_confere))
    mestre = sum(not ok for _, ok, _ in linhas_check)
    presentes = {k for _, _, chaves in ordem for k in chaves}

    with pd.ExcelWriter(arquivo, engine="xlsxwriter") as xl:
        livro = xl.book
        f = Formatos(livro)
        for divisoria, descricao, chaves in ordem:
            if divisoria and chaves:
                escrever_divisoria(livro, f, mestre, divisoria, descricao, chaves)
            for k in chaves:
                if k == "leia_me":
                    escrever_capa(livro, f, mestre, presentes, abas["resumo"], _linha_rotas_x_real(resultados))
                elif k == "check":
                    escrever_check(livro, f, linhas_check, mestre)
                elif k == "premissas":
                    escrever_premissas(livro, f, mestre)
                elif isinstance(abas[k], AbaByStep):
                    escrever_aba(livro, abas[k], by_step, f, mestre)
                else:
                    abas[k].escrever(livro, f, mestre)
    return arquivo
