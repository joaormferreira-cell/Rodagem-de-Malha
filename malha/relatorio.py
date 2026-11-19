"""
Excel único da rodagem, para quem vai usar o resultado (não precisa abrir código).
Abas: Leia-me · Resumo · Rodagem x Initiatives x Real · Ponte do BWT · Onde atacar · Simulador de iniciativas ·
Meta By Step · BWT por caminho ·
Rotas · Rotas meta x real · Checagens.
"""
from datetime import datetime

import numpy as np
import pandas as pd

from .calculo.bwt import COLUNAS_SAIDA as COLUNAS_BWT
from .calculo.by_step import ETAPAS_BY_STEP, observacao, ordem_by_step
from .calculo.rotas_x_real import resumo as resumo_rotas
from .calculo.simulador import rotulos as rotulos_simulador

ABAS = [
    ("Resumo", "BWT médio (horas e dias) por mês, canal e região, ponderado pelos pedidos/dia."),
    ("Rodagem x Initiatives x Real", "Só se houver a aba Nov26-27 da Initiatives: para cada etapa (Brasil, BR - BR), "
                                     "meta da Rodagem | meta da Initiatives | realizado da By Step, lado a lado. "
                                     "O mês atual do realizado é parcial. Leia a coluna 'observação'."),
    ("Ponte do BWT", "Só se houver o realizado da By Step: quanto cada etapa precisa cair (h no BWT) do real do último "
                     "mês fechado até a meta. 'por tempo' = a etapa demora mais; 'por nº de pedidos' = passam mais "
                     "pedidos por ela do que a malha prevê. As duas partes somam o 'a reduzir'."),
    ("Onde atacar", "Só se houver o tempo real por rota: as rotas (estrada) e os SOCs (fila de recebimento) que mais "
                    "puxam o BWT para cima. Efeito aproximado no BWT Brasil = horas acima da meta × pacotes ÷ pedidos "
                    "do mês. Não cobre o tempo dentro dos SOCs (não há realizado por SOC)."),
    ("Simulador de iniciativas", "Só se houver a aba Nov26-27 da Initiatives: BWT do SPX D2D no último mês de meta "
                                 "(Nov/27), ligando e desligando cada iniciativa (coluna amarela 'Ligada?', 1 ou 0). "
                                 "Mostra também quanto da meta oficial nenhuma iniciativa explica."),
    ("Meta x Realizado", "Só se houver o realizado da By Step: meta, realizado e diferença (h) por etapa e recorte. "
                         "dif_h > 0 = realizado acima da meta."),
    ("Meta By Step", "Meta de cada etapa no formato da By Step (Brasil, BR - BR), com todas as linhas da By Step. "
                     "Etapa sem meta fica vazia e a coluna 'observação' diz por quê."),
    ("Meta By Step (rotas)", "Mesma meta por rota macro (SPM - SPM, SP > RJ, BR>BA State...)."),
    ("(arquivo CSV ao lado)", "'BWT por caminho - todos os meses.csv': uma linha por caminho com estações, pedidos/dia, "
                              "BWT total e o tempo de cada etapa (horas). Abre no Excel (separador ';')."),
    ("Rotas", "Uma linha por rota: veículos, espera para sair, viagem, fila e de onde veio a viagem (fonte_tt) "
              "e a fila (fonte_fila)."),
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
    """Todas as etapas da By Step, na mesma ordem; etapa sem meta fica vazia e a 'observação' diz por quê."""
    br = meta[meta["main_route"] == "BR - BR"]
    tabela = br.pivot_table(index="kpi", columns=["spx_channel", "attempt_month"], values="media_h", aggfunc="first")
    tabela = tabela.reindex(sorted(set(tabela.index) | set(ETAPAS_BY_STEP), key=ordem_by_step))
    tabela.columns = [f"{canal} | {mes}" for canal, mes in tabela.columns]
    tabela["observação"] = [observacao(k, tem) for k, tem in zip(tabela.index, tabela.notna().any(axis=1))]
    return tabela.reset_index().rename(columns={"kpi": "etapa (KPI By Step)"})


def _linha_rotas_x_real(resultados):
    rr = resumo_rotas(resultados["rotas_x_real"]) if "rotas_x_real" in resultados else None
    if not rr:
        return []
    return [["Rotas: meta x real", f"{rr['rotas']} rotas comparadas. Pacotes em rotas com diferença até 2h: "
             f"{rr['ate_2h']:.0f}% · até 4h: {rr['ate_4h']:.0f}% · real 4h+ acima: {rr['acima_4h']:.0f}% · "
             f"real 4h+ abaixo: {rr['abaixo_4h']:.0f}%"]]


def _escrever_simulador(livro, resultados, titulo, negrito, cab):
    """Aba com fórmulas: a coluna 'Ligada?' (1/0) recalcula o BWT simulado no Excel."""
    from xlsxwriter.utility import xl_range, xl_rowcol_to_cell as celula
    r = resultados["simulador_resumo"].iloc[0].to_dict()
    ini, et, m = resultados["simulador_iniciativas"], resultados["simulador_etapas"], rotulos_simulador(r)
    ws = livro.add_worksheet("Simulador de iniciativas")
    h2 = livro.add_format({"num_format": "0.00"})
    h2_negrito = livro.add_format({"num_format": "0.00", "bold": True})
    pct = livro.add_format({"num_format": "0%"})
    entrada = livro.add_format({"bg_color": "#FFF2CC", "font_color": "#0000FF", "bold": True, "align": "center"})

    ws.write(0, 0, f"Simulador de iniciativas: BWT do SPX D2D em {m['mes_b']}", titulo)
    ws.write(1, 0, "Como usar: na coluna 'Ligada?' (amarela) troque 1 por 0 para tirar uma iniciativa. "
                   "O resumo e a tabela de etapas recalculam sozinhos.")
    ws.write(2, 0, f"Fonte: aba Nov26-27 da Initiatives. Impacto no BWT = horas na etapa ({m['mes_a']} + {m['mes_b']}) "
                   f"× % de pedidos da etapa em {m['mes_b']}. Negativo = reduz o BWT.")

    lin_ini = 16                       # cabeçalho da tabela de iniciativas
    p, u = lin_ini + 1, lin_ini + len(ini)
    etapa_i, total_i, bwt_i, ligada_i = (xl_range(p, c, u, c) for c in (0, 6, 8, 9))

    ws.write(4, 0, "Ponte", cab)
    ws.write(4, 1, "horas", cab)
    linhas = [
        (f"BWT real {m['mes_real']} (soma das etapas da Initiatives)", r["soma_real_h"], None),
        (f"Mudança no % de pedidos por etapa ({m['mes_real']} → {m['mes_b']})", r["mix_h"], None),
        ("Iniciativas ligadas", r["iniciativas_h"], f"=SUMPRODUCT({bwt_i},{ligada_i})"),
        ("Ajustes nas etapas que nenhuma iniciativa explica", r["ajustes_h"], None),
    ]
    for k, (rotulo, valor, formula) in enumerate(linhas):
        ws.write(5 + k, 0, rotulo)
        if formula:
            ws.write_formula(5 + k, 1, formula, h2, valor)
        else:
            ws.write_number(5 + k, 1, valor, h2)
    ws.write(9, 0, f"BWT {m['mes_b']} simulado", negrito)
    ws.write_formula(9, 1, f"=SUM({xl_range(5, 1, 8, 1)})", h2_negrito, r["soma_b_h"])
    ws.write(10, 0, f"Meta oficial {m['mes_b']} da Initiatives (linha '(-) SPX D2D')")
    ws.write_number(10, 1, r["total_b_h"], h2)
    ws.write(11, 0, "Falta para a meta oficial (> 0 = simulado acima da meta)", negrito)
    ws.write_formula(11, 1, f"={celula(9, 1)}-{celula(10, 1)}", h2_negrito, r["soma_b_h"] - r["total_b_h"])
    ws.write(12, 0, f"Para comparar: meta {m['mes_a']} = {r['total_a_h']:.1f}h; real {m['mes_real']} (total oficial) = "
                    f"{r['total_real_h']:.1f}h. No real, a soma das etapas fica abaixo do total porque a Initiatives "
                    "não lista todas as etapas.")

    ws.write(lin_ini - 1, 0, "Iniciativas (troque 1 por 0 em 'Ligada?')", negrito)
    cab_ini = ["Etapa (Initiatives)", "KPI By Step", "Iniciativa", "Dono", f"Impacto {m['mes_a']} na etapa (h)",
               f"Impacto {m['mes_b']} na etapa (h)", "Impacto total na etapa (h)", f"% pedidos da etapa {m['mes_b']}",
               "Impacto no BWT (h)", "Ligada? (1 = sim, 0 = não)", "Impacto ligado no BWT (h)", "Observação",
               "Racional (da planilha)"]
    kpis = et.set_index("etapa")["kpis"]
    for j, nome in enumerate(cab_ini):
        ws.write(lin_ini, j, nome, cab)
    for k, (_, i) in enumerate(ini.iterrows()):
        lin = p + k
        ws.write(lin, 0, i["etapa"])
        ws.write(lin, 1, kpis.get(i["etapa"], ""))
        ws.write(lin, 2, i["iniciativa"])
        ws.write(lin, 3, i["dono"])
        for j, c in [(4, "impacto_a_h"), (5, "impacto_b_h"), (6, "impacto_total_h"), (8, "impacto_bwt_h")]:
            if pd.notna(i[c]):
                ws.write_number(lin, j, i[c], h2)
        ws.write_number(lin, 7, i["share_b"], pct)
        ws.write_number(lin, 9, 1, entrada)
        ws.write_formula(lin, 10, f"={celula(lin, 8)}*{celula(lin, 9)}", h2, i["impacto_bwt_h"])
        ws.write(lin, 11, i["observacao"])
        ws.write(lin, 12, i["racional"][:250])
    ws.data_validation(p, 9, u, 9, {"validate": "integer", "criteria": "between", "minimum": 0, "maximum": 1,
                                    "error_message": "Use 1 (ligada) ou 0 (desligada)."})
    ws.write(u + 1, 0, "Total", negrito)
    ws.write_formula(u + 1, 8, f"=SUM({bwt_i})", h2_negrito, ini["impacto_bwt_h"].sum())
    ws.write_formula(u + 1, 10, f"=SUM({xl_range(p, 10, u, 10)})", h2_negrito, ini["impacto_bwt_h"].sum())
    ws.autofilter(lin_ini, 0, u, len(cab_ini) - 1)

    lin_et = u + 4
    ws.write(lin_et - 1, 0, "Etapas (com as iniciativas desligadas, a etapa volta a ter as horas delas)", negrito)
    cab_et = ["Etapa (Initiatives)", "KPI By Step", f"% pedidos {m['mes_real']}", f"% pedidos {m['mes_b']}",
              f"Real {m['mes_real']} (h)", f"Meta {m['mes_a']} (h)", f"Meta {m['mes_b']} (h)",
              "Desligadas devolvem (h)", f"Etapa simulada {m['mes_b']} (h)", "Ajuste sem iniciativa (h)"]
    for j, nome in enumerate(cab_et):
        ws.write(lin_et, j, nome, cab)
    for k, (_, e) in enumerate(et.iterrows()):
        lin = lin_et + 1 + k
        ws.write(lin, 0, e["etapa"])
        ws.write(lin, 1, e["kpis"])
        ws.write_number(lin, 2, e["share_r"], pct)
        ws.write_number(lin, 3, e["share_b"], pct)
        for j, c in [(4, "real_h"), (5, "meta_a_h"), (6, "meta_b_h"), (9, "ajuste_h")]:
            if pd.notna(e[c]):
                ws.write_number(lin, j, e[c], h2)
        ws.write_formula(lin, 7, f'=-SUMIFS({total_i},{etapa_i},{celula(lin, 0)},{ligada_i},"<>1")', h2, 0)
        ws.write_formula(lin, 8, f"={celula(lin, 6)}+{celula(lin, 7)}", h2, e["meta_b_h"])
    ws.set_column(0, 0, 48)
    ws.set_column(1, 1, 11)
    ws.set_column(2, 2, 46)
    ws.set_column(3, 10, 15)
    ws.set_column(11, 11, 38)
    ws.set_column(12, 12, 70)


def gerar_excel(resultados, arquivo):
    """Excel leve, só com resumos; o detalhe por caminho (centenas de milhares de linhas) vai num CSV ao lado."""
    caminhos = resultados["bwt_caminhos"]
    caminhos[COLUNAS_BWT].to_csv(arquivo.with_name("BWT por caminho - todos os meses.csv"), index=False,
                                 encoding="utf-8-sig", sep=";", decimal=",")
    abas = {"Resumo": _resumo(caminhos)}
    if "tres_visoes" in resultados:
        abas["Rodagem x Initiatives x Real"] = resultados["tres_visoes"]
    for chave, nome in [("ponte_bwt", "Ponte do BWT"), ("onde_atacar", "Onde atacar")]:
        if chave in resultados:
            abas[nome] = resultados[chave]
    if "simulador_resumo" in resultados:
        abas["Simulador de iniciativas"] = None   # escrita à parte, com fórmulas
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
            if df is None:
                _escrever_simulador(livro, resultados, titulo, negrito, cab)
                continue
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
