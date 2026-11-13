"""
Excel único da rodagem, para quem vai usar o resultado (não precisa abrir código).
Abas: Leia-me · Resumo · Meta By Step · BWT por caminho · Rotas · Checagens.
"""
from datetime import datetime

import numpy as np
import pandas as pd

from .calculo.bwt import COLUNAS_SAIDA as COLUNAS_BWT
from .calculo.by_step import TOTAL

ABAS = [
    ("Resumo", "BWT médio (horas e dias) por mês, canal e região, ponderado pelos pedidos/dia."),
    ("Meta x Realizado", "Só se houver o realizado da By Step: meta, realizado e diferença (h) por etapa e recorte. "
                         "dif_h > 0 = realizado acima da meta."),
    ("Meta By Step", "Meta de cada etapa no formato da By Step (Brasil, BR - BR). Comparar com o realizado."),
    ("Meta By Step (rotas)", "Mesma meta por rota macro (SPM - SPM, SP > RJ, BR>BA State...)."),
    ("BWT por caminho AAAA-MM", "Mês mais recente, uma linha por caminho: estações, pedidos/dia, BWT total e o tempo "
                                "de cada etapa (horas). Todos os meses: arquivo 'BWT por caminho - todos os meses.csv'."),
    ("Rotas", "Uma linha por rota: veículos, espera para sair, viagem, fila e de onde veio o tempo (fonte_tt)."),
    ("Checagens", "Conferências dos inputs e dos resultados. ERRO para a rodagem; AVISO é ponto de atenção."),
]


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


def _by_step_brasil(meta):
    br = meta[meta["main_route"] == "BR - BR"]
    tabela = br.pivot_table(index="kpi", columns=["spx_channel", "attempt_month"], values="media_h", aggfunc="first")
    tabela = tabela.reindex(sorted(tabela.index, key=lambda k: (k == TOTAL, k)))
    tabela.columns = [f"{canal} | {mes}" for canal, mes in tabela.columns]
    return tabela.reset_index().rename(columns={"kpi": "etapa (KPI By Step)"})


def gerar_excel(resultados, arquivo):
    """Excel leve: o detalhe por caminho só do mês mais recente (todos os meses ficam no CSV ao lado)."""
    caminhos = resultados["bwt_caminhos"]
    ultimo_mes = caminhos["period_start"].max()
    caminhos[COLUNAS_BWT].to_csv(arquivo.with_name("BWT por caminho - todos os meses.csv"), index=False,
                                 encoding="utf-8-sig", sep=";", decimal=",")
    abas = {"Resumo": _resumo(caminhos)}
    if "meta_x_realizado" in resultados:
        abas["Meta x Realizado"] = resultados["meta_x_realizado"]
    abas.update({
        "Meta By Step": _by_step_brasil(resultados["by_step_meta"]),
        "Meta By Step (rotas)": resultados["by_step_meta"],
        f"BWT por caminho {ultimo_mes[:7]}": caminhos.loc[caminhos["period_start"] == ultimo_mes, COLUNAS_BWT],
        "Rotas": resultados["rotas"],
        "Checagens": resultados.get("checagens", pd.DataFrame()),
    })
    ado = caminhos["ADO"].sum()
    leia_me = [
        ["Rodagem de Malha: target de BWT por caminho"],
        [f"Gerado em {datetime.now():%d/%m/%Y %H:%M}"],
        [],
        ["Meses", ", ".join(sorted(caminhos["period_start"].unique()))],
        ["Caminhos", f"{len(caminhos):,}".replace(",", ".")],
        ["Pedidos/dia (soma dos meses)", f"{ado:,.0f}".replace(",", ".")],
        ["BWT médio (ponderado)", f"{(caminhos['bwt_total_hours'] * caminhos['ADO']).sum() / ado:.1f} horas"],
        [],
        ["Aba", "O que tem"],
    ] + [[nome, desc] for nome, desc in ABAS] + [
        [],
        ["Como ler", "Todos os tempos em horas. Média = soma(horas × pedidos/dia) ÷ soma(pedidos/dia)."],
        ["", "Estação sem meta usa a média do mês da aba [T] correspondente; etapa que o caminho não tem vale 0."],
    ]

    with pd.ExcelWriter(arquivo, engine="xlsxwriter") as xl:
        livro = xl.book
        titulo = livro.add_format({"bold": True, "font_size": 14})
        negrito = livro.add_format({"bold": True})
        cab = livro.add_format({"bold": True, "bg_color": "#EE4D2D", "font_color": "white", "text_wrap": True,
                                "valign": "top"})
        num = livro.add_format({"num_format": "0.0"})

        ws = livro.add_worksheet("Leia-me")
        for i, linha in enumerate(leia_me):
            for j, valor in enumerate(linha):
                ws.write(i, j, valor, titulo if i == 0 else (negrito if j == 0 or linha[0] == "Aba" else None))
        ws.set_column(0, 0, 30)
        ws.set_column(1, 1, 110)

        for nome, df in abas.items():
            df.to_excel(xl, sheet_name=nome, index=False)
            ws = xl.sheets[nome]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, cab)
                largura = min(max(len(str(col)), 10) + 2, 45)
                numerica = pd.api.types.is_float_dtype(df[col])
                ws.set_column(j, j, largura, num if numerica else None)
            ws.freeze_panes(1, 0)
            if len(df):
                ws.autofilter(0, 0, len(df), len(df.columns) - 1)
    return arquivo
