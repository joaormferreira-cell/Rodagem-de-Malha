"""
Excel único da rodagem, para quem vai usar o resultado (não precisa abrir código).
Abas: Leia-me · Resumo · Meta By Step · BWT por caminho · Rotas · Rotas meta x real · Checagens.
"""
from datetime import datetime

import numpy as np
import pandas as pd

from .calculo.bwt import COLUNAS_SAIDA as COLUNAS_BWT
from .calculo.by_step import TOTAL
from .calculo.rotas_x_real import resumo as resumo_rotas

ABAS = [
    ("Resumo", "BWT médio (horas e dias) por mês, canal e região, ponderado pelos pedidos/dia."),
    ("Meta x Realizado", "Só se houver o realizado da By Step: meta, realizado e diferença (h) por etapa e recorte. "
                         "dif_h > 0 = realizado acima da meta."),
    ("Meta By Step", "Meta de cada etapa no formato da By Step (Brasil, BR - BR). Comparar com o realizado."),
    ("Meta By Step (rotas)", "Mesma meta por rota macro (SPM - SPM, SP > RJ, BR>BA State...)."),
    ("(arquivo CSV ao lado)", "'BWT por caminho - todos os meses.csv': uma linha por caminho com estações, pedidos/dia, "
                              "BWT total e o tempo de cada etapa (horas). Abre no Excel (separador ';')."),
    ("Rotas", "Uma linha por rota: veículos, espera para sair, viagem, fila e de onde veio o tempo (fonte_tt)."),
    ("Rotas meta x real", "Só se houver o tempo real por rota (consultas/lh_real_por_rota.sql): meta × real de cada "
                          "rota, separando estrada (saiu → chegou) e fila (chegou → recebido). dif > 0 = real acima."),
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


def _linha_rotas_x_real(resultados):
    rr = resumo_rotas(resultados["rotas_x_real"]) if "rotas_x_real" in resultados else None
    if not rr:
        return []
    return [["Rotas: meta x real", f"{rr['rotas']} rotas comparadas. Pacotes em rotas com diferença até 2h: "
             f"{rr['ate_2h']:.0f}% · até 4h: {rr['ate_4h']:.0f}% · real 4h+ acima: {rr['acima_4h']:.0f}% · "
             f"real 4h+ abaixo: {rr['abaixo_4h']:.0f}%"]]


def gerar_excel(resultados, arquivo):
    """Excel leve, só com resumos; o detalhe por caminho (centenas de milhares de linhas) vai num CSV ao lado."""
    caminhos = resultados["bwt_caminhos"]
    caminhos[COLUNAS_BWT].to_csv(arquivo.with_name("BWT por caminho - todos os meses.csv"), index=False,
                                 encoding="utf-8-sig", sep=";", decimal=",")
    abas = {"Resumo": _resumo(caminhos)}
    if "meta_x_realizado" in resultados:
        abas["Meta x Realizado"] = resultados["meta_x_realizado"]
    abas.update({
        "Meta By Step": _by_step_brasil(resultados["by_step_meta"]),
        "Meta By Step (rotas)": resultados["by_step_meta"],
        "Rotas": resultados["rotas"],
        **({"Rotas meta x real": resultados["rotas_x_real"]} if "rotas_x_real" in resultados else {}),
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
        *_linha_rotas_x_real(resultados),
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
