"""
Abas de BWT por step: abre o Excel gerado e confere as fórmulas por fora (sem confiar no código que as escreveu):
  - cada check de estação aponta para as linhas dos steps da regra, no bloco de pedidos/dia, no mesmo mês;
  - o TRUE/FALSE gravado bate com a conta refeita a partir das células;
  - a soma dos steps = BWT direto dos caminhos, e a aba antiga bate com a nova (BR > BR).
"""
import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import openpyxl
import pandas as pd
import xlsxwriter

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from malha.calculo.by_step import meta_by_step  # noqa: E402
from malha.excel_by_step import L_CAB, L_CAMINHOS, L_MES, L_SOMA, escrever_aba, preparar_abas  # noqa: E402
from malha.excel_padrao import ABA, VALOR_PREMISSA, Formatos, escrever_check, escrever_premissas  # noqa: E402
from test_by_step import _caminhos  # noqa: E402

_REF = re.compile(r"(?:'([^']+)'!)?\$?([A-Z]+)\$?(\d+)")


def _gerar(tmp_path):
    caminhos = _caminhos(tmp_path)
    spx_info = pd.DataFrame({"station_code": [], "state_name": [], "city_name": []})
    with redirect_stdout(io.StringIO()):
        meta = meta_by_step(caminhos, spx_info)
    abas, raws = preparar_abas({"bwt_caminhos": caminhos, "by_step_meta": meta})
    arquivo = tmp_path / "by_step.xlsx"
    livro = xlsxwriter.Workbook(arquivo)
    f = Formatos(livro)
    escrever_check(livro, f, [(a.nome, a.n_falso == 0, "") for a in abas], 0)
    escrever_premissas(livro, f, 0)
    for a in abas:
        escrever_aba(livro, a, abas, f, 0)
    for t in raws:
        t.escrever(livro, f, 0)
    livro.close()
    return abas, openpyxl.load_workbook(arquivo), openpyxl.load_workbook(arquivo, data_only=True)


def _celulas(texto):
    """'SUM(L13,L20)' → [(13, 'L'), (20, 'L')]; '0' → []."""
    return [(int(linha), coluna) for _, coluna, linha in _REF.findall(texto)]


def test_formulas_dos_checks_apontam_para_o_lugar_certo(tmp_path):
    abas, wb_f, wb_v = _gerar(tmp_path)
    for a in abas:
        if not a.meses:
            continue
        ws_f, ws_v = wb_f[a.nome], wb_v[a.nome]
        rotulo = {r: ws_v.cell(row=r, column=2).value for r in range(1, a.ultima + 2)}   # coluna B
        for chk in [c for c in a.checks if c["tipo"] == "estacao"]:
            for k, mes in enumerate(a.meses):
                formula = ws_f.cell(row=chk["linha"] + 1, column=a.col(k, 1) + 1).value
                lados = re.match(r"=ABS\((.*?)\)<=", formula).group(1)
                esq, dir_ = re.match(r"^(SUM\([^)]*\)|0)-(SUM\([^)]*\)|\$?[A-Z]+\$?\d+|0)$", lados).groups()
                for lado, chaves in [(esq, chk["esq"]), (dir_, chk["dir"])]:
                    cels = _celulas(lado)
                    if chaves is None:   # 100% = pedidos/dia do recorte (linha de total)
                        assert [r for r, _ in cels] == [L_CAMINHOS + 1]
                    else:
                        assert sorted(rotulo[r] for r, _ in cels) == sorted(chaves), (a.nome, chk["texto"])
                    for r, coluna in cels:   # bloco de pedidos/dia, mesmo mês
                        assert ws_v[f"{coluna}{L_CAB + 1}"].value == "Pedidos/dia"
                        assert ws_v[f"{coluna}{L_MES + 1}"].value == ws_v.cell(row=L_MES + 1,
                                                                               column=a.col(k, 0) + 1).value

                def valor(lado):
                    return sum(ws_v[f"{c}{r}"].value or 0 for r, c in _celulas(lado))

                x, y = valor(esq), valor(dir_)
                refeito = abs(x - y) <= wb_v["Premissas"]["C5"].value * max(1, abs(x), abs(y))
                assert "'Premissas'!$C$5" in formula   # tolerância vem da aba Premissas, não digitada
                assert ws_v.cell(row=chk["linha"] + 1, column=a.col(k, 1) + 1).value == refeito


def test_totais_e_cruzamento_entre_abas(tmp_path):
    abas, wb_f, wb_v = _gerar(tmp_path)
    por_nome = {a.nome: a for a in abas}
    for nome in [ABA["bs_br"], ABA["bs_antigo_br"]]:
        a, ws = por_nome[nome], wb_v[nome]
        for k in range(len(a.meses)):
            soma = ws.cell(row=L_SOMA + 1, column=a.col(k, 2) + 1).value
            direto = ws.cell(row=L_CAMINHOS + 1, column=a.col(k, 2) + 1).value
            assert abs(soma - direto) < 1e-9 * max(1, direto)
            # soma = BWT das linhas (sem as With Transshipment, que repetem o BWT da Non-transshipment)
            linhas = [a.linha_de[l["chave"]] + 1 for l in a.linhas if l["com_dado"] and not l["fora_da_soma"]]
            assert abs(sum(ws.cell(row=r, column=a.col(k, 2) + 1).value or 0 for r in linhas) - soma) < 1e-9 * max(1, soma)
    nova, antiga = por_nome[ABA["bs_br"]], por_nome[ABA["bs_antigo_br"]]
    assert nova.meses == antiga.meses
    for k in range(len(nova.meses)):
        assert abs(nova.v[("soma", k)] - antiga.v[("soma", k)]) < 1e-9 * max(1, nova.v[("soma", k)])
    # os checks cruzados apontam para a outra aba e dão TRUE
    i = next(i for i, c in enumerate(antiga.checks) if c["tipo"] == "par_bwt")
    formula = wb_f[antiga.nome].cell(row=antiga.checks[i]["linha"] + 1, column=antiga.col(0, 1) + 1).value
    assert f"'{ABA['bs_br']}'!" in formula and all(antiga.ok[(i, k)] for k in range(len(antiga.meses)))
    # aba Check: uma linha por aba (='Aba'!A2=0); A1 = nº de FALSE
    ws = wb_f["Check"]
    assert ws["A1"].value.startswith("=COUNTIF(") and [ws.cell(row=3 + j, column=2).value for j in range(4)] == \
        [a.nome for a in abas]
    assert ws["C3"].value == f"='{abas[0].nome}'!A2=0"
    # pedidos de cada step = SUMIFS na base verde (nada digitado na aba), recorte vindo da aba Premissas
    a = por_nome[ABA["bs_antigo_br"]]
    formula = wb_f[a.nome].cell(row=a.linha_de["bwt_apt_paid_to_dropoff"] + 1, column=a.col_ped(0) + 1).value
    assert formula.startswith("=SUMIFS('raw_steps_antigos'!") and "'Premissas'!$C$" in formula
    assert wb_v["Premissas"]["C9"].value == VALOR_PREMISSA["rota_br"]


def test_excel_inteiro_no_padrao(tmp_path):
    """Excel completo (dados de exemplo) no padrão das planilhas de BWT do time e do 'Do it right'."""
    from malha.excel_padrao import ABA_CHECK, COR
    from malha.pipeline import calcular, ler_inputs
    from malha.relatorio import gerar_excel
    with redirect_stdout(io.StringIO()):
        resultados = calcular(ler_inputs(RAIZ / "teste_local" / "dados_exemplo"))
    arquivo = gerar_excel(resultados, tmp_path / "saida.xlsx")
    wb = openpyxl.load_workbook(arquivo)
    cor = lambda c: ("FF" + COR[c][1:]).upper()
    abas = {ws.title: ws for ws in wb.worksheets}
    assert wb.sheetnames[:4] == [ABA["leia_me"], ABA_CHECK, ABA["checagens"], ABA["premissas"]]   # comece aqui
    assert wb.sheetnames.index("META >>") < wb.sheetnames.index(ABA["resumo"]) < wb.sheetnames.index("BASES >>")
    assert abas[ABA_CHECK].sheet_properties.tabColor.rgb == cor("aba_check")
    assert abas["Premissas"].sheet_properties.tabColor.rgb == cor("aba_premissa")
    assert abas["raw_meta_by_step"].sheet_properties.tabColor.rgb == cor("aba_input")
    assert abas[ABA["resumo"]].sheet_properties.tabColor is None                       # modelo/output: aba sem cor
    no_check = [abas[ABA_CHECK].cell(row=r, column=2).value for r in range(3, 3 + 40)]
    for nome, ws in abas.items():
        if nome in (ABA["leia_me"], ABA_CHECK) or nome.endswith(">>") or nome.startswith("Simulador"):
            continue
        assert nome in no_check, nome                                             # toda aba tem linha na Check
        assert ws["A1"].value.startswith(f"=COUNTIF('{ABA_CHECK}'!"), nome       # indicador geral
        assert ws["A2"].value.startswith("=COUNTIF(") or ws["A2"].value == "=0", nome
        for row in ws.iter_rows(min_row=5, max_row=min(ws.max_row, 200)):     # letras pretas nos dados
            for c in row:
                if c.value is None or c.font is None or c.font.color is None or c.font.color.type != "rgb":
                    continue
                assert c.font.color.rgb in ("FF000000", "FFFFFFFF", cor("check")), (nome, c.coordinate, c.font.color.rgb)
        if nome.startswith("By Step") and nome != ABA["bs_canal"]:
            continue
        for col in range(2, ws.max_column + 1):                                  # coluna de fórmula = fórmula
            cab = ws.cell(row=4, column=col)
            if cab.fill is not None and cab.fill.fgColor.rgb == cor("cab_formula"):
                valores = [ws.cell(row=r, column=col).value for r in range(5, ws.max_row + 1)]
                digitados = [v for v in valores if v is not None and not (isinstance(v, str) and v.startswith("="))]
                assert len(digitados) <= 0.01 * max(1, len(valores)), (nome, cab.value, digitados[:3])


def test_bordas_no_padrao(tmp_path):
    """Bordas como nas planilhas de BWT do time: fio claro por linha, fio cinza no início de bloco, fio escuro no total."""
    from malha.excel_by_step import L_CAMINHOS as L_CAM
    from malha.excel_padrao import ABA, COR
    from malha.pipeline import calcular, ler_inputs
    from malha.relatorio import gerar_excel
    with redirect_stdout(io.StringIO()):
        resultados = calcular(ler_inputs(RAIZ / "teste_local" / "dados_exemplo"))
    wb = openpyxl.load_workbook(gerar_excel(resultados, tmp_path / "saida.xlsx"))
    rgb = lambda c: ("FF" + COR[c][1:]).upper()
    ws = wb[ABA["resumo"]]
    assert ws["B5"].border.bottom.color.rgb in (rgb("linha"), rgb("total_linha"))     # toda linha tem fio embaixo
    assert ws["E5"].border.left.color.rgb == rgb("separador")                          # rótulos | números
    assert ws["B4"].border.bottom.color.rgb == rgb("cab_borda")                        # cabeçalho: borda branca
    brasil = [r for r in range(5, ws.max_row + 1) if ws.cell(row=r, column=4).value == "BRASIL"]
    assert brasil and all(ws.cell(row=r, column=2).border.bottom.color.rgb == rgb("total_linha") for r in brasil)
    bs = wb[ABA["bs_antigo_br"]]
    assert bs.cell(row=L_CAM + 1, column=2).border.bottom.color.rgb == rgb("total_linha")   # fecha os totais
    assert bs.cell(row=L_CAM + 2, column=2).border.bottom.color.rgb == rgb("linha")
