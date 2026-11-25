"""
Capa (Leia-me) e abas divisórias do Excel de saída, como na frente de um modelo de consultoria:
  Leia-me: status (data, meses, checks), o resultado principal em fórmula (BWT meta por mês, puxado da aba Resumo BWT),
           índice com link para cada aba e a pergunta que ela responde, legenda de cores e como ler.
  Divisórias ("META >>", "REAL x META >>", "SIMULADORES >>", "BASES >>"): uma antes de cada seção, com as abas dela.
Cor só no fundo (cabeçalho e amostra da legenda); letras pretas; links sublinhados.
"""
from datetime import datetime

from .excel_padrao import ABA, ABA_CHECK, COR, PERGUNTA, SECOES, VALOR_PREMISSA, cel, data_excel, ref_premissa, topo


def _link(ws, f, linha, col, aba, texto=None, negrito=False, **props):
    ws.write_url(linha, col, f"internal:'{aba}'!A1", f.dado(underline=1, bold=negrito, **props), string=texto or aba)


def escrever_divisoria(livro, f, mestre, titulo, descricao, chaves):
    ws = livro.add_worksheet(titulo)
    topo(ws, f, mestre, descricao, "Divisória de seção: clique no nome da aba para abrir.", 0, None)
    ws.write(0, 1, titulo.replace(" >>", ""), f(bold=True, font_size=14))
    ws.write(1, 1, descricao, f(italic=True))
    ws.write_row(3, 1, ["Aba", "Pergunta que responde"], f.cabecalho(COR["cab_formula"]))
    for i, chave in enumerate(chaves):
        _link(ws, f, 4 + i, 1, ABA[chave])
        ws.write(4 + i, 2, PERGUNTA[chave], f.dado())
    ws.write_url(6 + len(chaves), 1, f"internal:'{ABA['leia_me']}'!A1", f(underline=1), string="← Voltar ao Leia-me")
    ws.set_column(1, 1, 34)
    ws.set_column(2, 2, 90)


def escrever_capa(livro, f, mestre, presentes, resumo, linhas_extra):
    """resumo: Tabela da aba Resumo BWT (o resultado da capa é SUMIFS nela); presentes: chaves das abas do arquivo."""
    ws = livro.add_worksheet(ABA["leia_me"])
    meses = sorted({str(m)[:10] for m in resumo.df["mês"]})
    periodo = f"{data_excel(meses[0]):%m/%Y} a {data_excel(meses[-1]):%m/%Y}" if meses else "-"
    topo(ws, f, mestre, "", f"Gerado em {datetime.now():%d/%m/%Y %H:%M} · demanda S&OP · meses {periodo}", 0, None)
    ws.write(0, 1, "Rodagem de Malha 2.0: meta (target) de BWT por caminho", f(bold=True, font_size=14))
    ws.write(2, 1, "Checks com FALSE no arquivo (0 = tudo certo)", f(bold=True))
    ws.write_formula(2, 2, f"='{ABA_CHECK}'!A1", f(bold=True, align="left"), mestre)
    ws.conditional_format(2, 2, 2, 2, {"type": "cell", "criteria": ">", "value": 0,
                                       "format": f(bold=True, font_color=COR["falso"])})

    # resultado principal: BWT meta por mês (Brasil, SPX + FBS), em fórmula sobre a aba Resumo BWT
    lin = 4
    ws.write(lin, 1, "Resultado: meta de BWT por mês (Brasil, SPX D2D + Fulfillment)", f(bold=True, font_size=12))
    lin += 1
    ws.write(lin, 1, "Mês", f.cabecalho(COR["cab_formula"]))
    ws.write_row(lin, 2, ["Caminhos", "Pedidos/dia", "BWT meta (h)", "BWT meta (dias)"],
                 f.cabecalho(COR["cab_formula"], centro=True))
    d = resumo.df[resumo.df["região"] == VALOR_PREMISSA["regiao_brasil"]]
    crit = f"{resumo.rng('mês', True)},{{m}},{resumo.rng('região', True)},{ref_premissa('regiao_brasil')}"
    for mes in meses:
        lin += 1
        g = d[d["mês"].astype(str).str[:10] == mes]
        m = cel(lin, 1)
        c = crit.replace("{m}", m)
        ped, hxp = float(g["pedidos_dia"].sum()), float(g["h_x_ado"].sum())
        ws.write_datetime(lin, 1, data_excel(mes), f.dado(num_format="mmm/yy", align="left"))
        ws.write_formula(lin, 2, f"=SUMIFS({resumo.rng('caminhos', True)},{c})", f.dado(sep=True, num_format="#,##0"),
                         float(g["caminhos"].sum()))
        ws.write_formula(lin, 3, f"=SUMIFS({resumo.rng('pedidos_dia', True)},{c})", f.dado(num_format="#,##0"), ped)
        ws.write_formula(lin, 4, f'=IF({cel(lin, 3)}=0,"",SUMIFS({resumo.rng("h_x_ado", True)},{c})/{cel(lin, 3)})',
                         f.dado(num_format="#,##0.00", bold=True), hxp / ped if ped else "")
        ws.write_formula(lin, 5, f'=IF({cel(lin, 4)}="","",{cel(lin, 4)}/{ref_premissa("horas_dia")})',
                         f.dado(num_format="#,##0.00"), hxp / ped / 24 if ped else "")
    for rotulo, texto in linhas_extra:
        lin += 2
        ws.write(lin, 1, rotulo, f(bold=True))
        ws.write(lin, 2, texto, f())

    # índice
    lin += 3
    ws.write(lin, 1, "Índice: clique no nome da aba para abrir", f(bold=True, font_size=12))
    lin += 1
    ws.write_row(lin, 1, ["Seção", "Aba", "Pergunta que responde"], f.cabecalho(COR["cab_formula"]))
    for divisoria, descricao, chaves in SECOES:
        chaves = [k for k in chaves if k in presentes]
        if not chaves:
            continue
        lin += 1
        secao = f.dado(bold=True, bg_color=COR["total"])
        if divisoria:
            ws.write(lin, 1, divisoria.replace(" >>", ""), secao)
            _link(ws, f, lin, 2, divisoria, negrito=True, bg_color=COR["total"])
        else:
            ws.write(lin, 1, descricao, secao)
            ws.write_blank(lin, 2, None, secao)
        ws.write(lin, 3, descricao if divisoria else "", secao)
        for c in range(4, 6):
            ws.write_blank(lin, c, None, secao)
        for chave in chaves:
            lin += 1
            ws.write_blank(lin, 1, None, f.dado())
            _link(ws, f, lin, 2, ABA[chave])
            ws.write(lin, 3, PERGUNTA[chave], f.dado())
            for c in range(4, 6):
                ws.write_blank(lin, c, None, f.dado())

    # legenda e como ler
    lin += 3
    ws.write(lin, 1, "Legenda: a cor vai na aba e no fundo do cabeçalho; as letras são sempre pretas", f(bold=True,
                                                                                                            font_size=12))
    for cor, texto in [(COR["aba_check"], "Dourado: aba Check e colunas de check"),
                       (COR["aba_premissa"], "Azul: aba Premissas (tolerância, recortes, limites usados nas fórmulas)"),
                       (COR["aba_input"], "Verde: base com números que vêm prontos da rodagem; no cabeçalho, coluna com "
                                          "número da rodagem ou onde você digita"),
                       (COR["cab_formula"], "Cinza escuro (cabeçalho): coluna calculada por fórmula"),
                       (None, "Aba sem cor: contas e resultados")]:
        lin += 1
        if cor:
            ws.write_blank(lin, 1, None, f(bg_color=cor))
        else:
            ws.write_blank(lin, 1, None, f(border=1))
        ws.write(lin, 2, texto, f())
    lin += 1
    ws.write(lin, 1, "TRUE", f.check())
    ws.write(lin, 2, "Check em cinza = OK; fica vermelho escuro quando dá FALSE", f())
    lin += 2
    ws.write(lin, 1, "Como ler", f(bold=True, font_size=12))
    for texto in ["Topo de toda aba: A1 = nº de abas com check FALSE (aba Check) · A2 = nº de FALSE nesta aba · "
                  "B1 = o que a aba mostra · B2 = de onde vêm os números · linha 3 = checks · tabela a partir de B4/B5.",
                  "Todos os tempos em horas. Média = soma(horas × pedidos/dia) ÷ soma(pedidos/dia).",
                  "Estação sem meta usa a média do mês da aba [T] correspondente; etapa que o caminho não tem vale 0.",
                  "Para mudar uma premissa (tolerância, recorte, limites), mude na aba Premissas: as fórmulas acompanham.",
                  "Arquivo ao lado: 'BWT por caminho - todos os meses.csv' (uma linha por caminho, separador ';')."]:
        lin += 1
        ws.write(lin, 1, "·", f(align="right"))
        ws.write(lin, 2, texto, f())
    ws.set_column(1, 1, 30)
    ws.set_column(2, 2, 34)
    ws.set_column(3, 3, 16)
    ws.set_column(4, 5, 15)
    ws.activate()
