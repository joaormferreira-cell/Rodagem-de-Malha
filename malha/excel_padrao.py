"""
Padrão do Excel de saída, copiado das planilhas de BWT do time (BWT by Step, BWT Historical, BWT Targets) e do
guia "Do it right":
  - a cor vai na ABA, não na letra: Check dourado, Premissas azul, bases (inputs) verde, modelo/output sem cor;
  - letras pretas, Arial 10; cor só no fundo do cabeçalho: verde = coluna que vem pronta da rodagem (input),
    cinza escuro = coluna calculada por fórmula, azul = premissa, dourado = check;
  - topo de toda aba: A1 = nº de abas com check FALSE (aba Check), A2 = nº de FALSE na linha 3 desta aba,
    B1 = o que a aba mostra, B2 = de onde vêm os números; linha 3 = um check por coluna; linha 4 = cabeçalho;
    dados a partir da linha 5 (coluna B);
  - checks em cinza itálico, vermelho escuro quando dão FALSE; nenhum número ou texto digitado dentro de fórmula
    (tudo aponta para a aba Premissas); sem célula mesclada, sem linha ou coluna oculta.
Coluna de fórmula: a célula só vira fórmula quando a fórmula dá o mesmo número da rodagem; se a linha é exceção da
regra (ex.: tempo fixo de uma rota), fica o número e a descrição da aba avisa.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import pandas as pd
from xlsxwriter.utility import xl_col_to_name, xl_rowcol_to_cell

# ---------------- nomes das abas e arquitetura do arquivo (um lugar só) ----------------
ABA = {
    "leia_me": "Leia-me", "check": "Check", "checagens": "Check - Rodagem", "premissas": "Premissas",
    "resumo": "Resumo BWT", "bs_br": "By Step BR", "bs_spm": "By Step SPM", "bs_canal": "By Step por canal",
    "bs_antigo_br": "By Step antigo BR", "bs_antigo_spm": "By Step antigo SPM",
    "tres_visoes": "Meta x Initiatives x Real", "ponte": "Real x Meta - por etapa",
    "onde_atacar": "Real x Meta - top rotas e SOCs", "regra": "Real x Meta - por regra",
    "rotas_x_real": "Real x Meta - rotas", "meta_x_real": "Real x Meta - detalhe",
    "sim_ini": "Simulador - Iniciativas", "sim_malha": "Simulador - Malha",
    "rotas": "Rotas - Meta", "raw_meta": "raw_meta_by_step", "raw_antiga": "raw_steps_antigos",
}
# ordem do arquivo: resposta primeiro (meta), depois diagnóstico, simulação e as bases; divisória antes de cada seção
SECOES = [
    (None, "Comece aqui", ["leia_me", "check", "checagens", "premissas"]),
    ("META >>", "A meta de BWT da Rodagem: total e por etapa",
     ["resumo", "bs_br", "bs_spm", "bs_canal", "bs_antigo_br", "bs_antigo_spm"]),
    ("REAL x META >>", "Onde o realizado está longe da meta, e por quê",
     ["tres_visoes", "ponte", "onde_atacar", "regra", "rotas_x_real", "meta_x_real"]),
    ("SIMULADORES >>", "E se...? Mude uma premissa e veja a meta recalcular", ["sim_ini", "sim_malha"]),
    ("BASES >>", "Números que vêm prontos da rodagem (inputs das contas)", ["rotas", "raw_meta", "raw_antiga"]),
]
PERGUNTA = {
    "leia_me": "O que tem no arquivo e como navegar",
    "check": "Todos os checks do arquivo fecham? (A1 = 0 é tudo certo)",
    "checagens": "Os inputs e os resultados da rodagem passaram nas conferências?",
    "premissas": "Quais premissas as fórmulas e os checks usam?",
    "resumo": "Qual o BWT meta por mês, canal e região?",
    "bs_br": "Qual a meta de cada etapa da By Step (SPX D2D + FF D2D, BR > BR)?",
    "bs_spm": "Qual a meta de cada etapa da By Step (SPX D2D + FF D2D, SPM > SPM)?",
    "bs_canal": "Qual a meta de cada etapa por canal (SPX D2D e Fulfillment)?",
    "bs_antigo_br": "A mesma meta no formato do output antigo (steps bwt_*, BR > BR)",
    "bs_antigo_spm": "A mesma meta no formato do output antigo (steps bwt_*, SPM > SPM)",
    "tres_visoes": "Meta da Rodagem x meta da Initiatives x realizado, etapa por etapa",
    "ponte": "Quanto cada etapa precisa cair do real até a meta, e por quê?",
    "onde_atacar": "Quais rotas e SOCs mais puxam o BWT para cima?",
    "regra": "A regra que dá o tempo da meta erra sempre para o mesmo lado?",
    "rotas_x_real": "Meta x real de cada rota (estrada e fila)",
    "meta_x_real": "Meta x real de cada etapa, em todos os recortes da By Step",
    "sim_ini": "E se uma iniciativa da Initiatives não sair?",
    "sim_malha": "E se mudar a fila de um SOC, a viagem de uma rota ou a rota virar expressa?",
    "rotas": "Tempo de viagem, fila, saída e veículos de cada rota da meta",
    "raw_meta": "Base da meta por mês × canal × rota macro × etapa da By Step",
    "raw_antiga": "Base da meta nos steps do software antigo, por mês e recorte",
}
ABA_CHECK, ABA_PREMISSAS = ABA["check"], ABA["premissas"]
L_CHECK, L_CAB, L_DADOS = 2, 3, 4          # linhas 3, 4 e 5 do Excel
MAX_ABAS_CHECK = 60
COR = {"aba_check": "#BF9000", "aba_checagens": "#7F6000", "aba_input": "#38761D", "aba_premissa": "#1157CE",
       "cab_input": "#38761D", "cab_formula": "#434343", "cab_premissa": "#1157CE", "cab_check": "#BF9000",
       "faixa": "#666666", "mes": "#D8D8D8", "total": "#F3F3F3", "check": "#B7B7B7", "falso": "#990000",
       "nota": "#B7B7B7",
       # bordas: fio claro embaixo de cada linha, fio cinza no início de bloco, fio escuro embaixo de total,
       # borda branca entre as células do cabeçalho (como nas abas Target/Targets das planilhas do time)
       "linha": "#EFEFEF", "separador": "#999999", "total_linha": "#666666", "cab_borda": "#FFFFFF"}
TOL = 1e-9   # para decidir se a fórmula reproduz o número da rodagem

PREMISSAS = [  # (chave, premissa, valor, formato, onde é usada)
    ("tolerancia", "Tolerância dos checks (relativa)", 1e-6, "0.0E+00",
     "Checks que comparam dois números: |a − b| ≤ tolerância × MAX(1; |a|; |b|)"),
    ("horas_dia", "Horas por dia", 24, "0", "BWT em dias (Resumo e abas de BWT por step)"),
    ("max_etapa_h", "Máximo de horas numa etapa", 240, "#,##0", "Check de valor das abas Meta By Step e BWT por step"),
    ("max_bwt_h", "Máximo de BWT total (h)", 720, "#,##0", "Check de valor do Resumo"),
    ("rota_br", "Recorte Brasil (rota macro da By Step)", "BR - BR", "@",
     "Filtro das fórmulas das abas BWT por etapa BR, BWT by step antiga BR e Meta By Step"),
    ("rota_spm", "Recorte SPM (rota macro da By Step)", "SPM - SPM", "@",
     "Filtro das fórmulas das abas BWT por etapa SPM e BWT by step antiga SPM"),
    ("total_by_step", "Linha de total na base da By Step", "FLOW BWT TOT", "@",
     "Pedidos/dia e horas do recorte nas abas BWT por etapa"),
    ("total_antiga", "Linha de total na base dos steps antigos", "TOTAL caminhos", "@",
     "Pedidos/dia e horas do recorte nas abas BWT by step antiga"),
    ("regiao_brasil", "Linha Brasil no Resumo", "BRASIL", "@", "Resumo: linha Brasil = soma das regiões"),
    ("ponte_resto", "Diferença aceita na Ponte sem linha de resto (h)", 0.05, "0.00",
     "Check 'fecha?' da Ponte do BWT (a rodagem só mostra a linha de resto acima disso)"),
    ("nivel_erro", "Nível de checagem que para a rodagem", "ERRO", "@", "Check da aba Checagens"),
    ("ligada", "Valor que liga (simuladores)", 1, "0",
     "'Ligada?' do Simulador de iniciativas e 'Virar expressa?' do Simulador de malha"),
    ("desligada", "Valor que desliga (simuladores)", 0, "0", "'Ligada?' do Simulador de iniciativas"),
]
VALOR_PREMISSA = {chave: valor for chave, _, valor, _, _ in PREMISSAS}


def ref_premissa(chave):
    i = [p[0] for p in PREMISSAS].index(chave)
    return f"'{ABA_PREMISSAS}'!$C${L_DADOS + 1 + i}"


def cel(linha, col, aba=None, fixa=False):
    ref = xl_rowcol_to_cell(linha, col, row_abs=fixa, col_abs=fixa)
    return f"'{aba}'!{ref}" if aba else ref


def faixa(l1, c1, l2, c2, aba=None, fixa=True):
    ref = f"{xl_rowcol_to_cell(l1, c1, row_abs=fixa, col_abs=fixa)}:{xl_rowcol_to_cell(l2, c2, row_abs=fixa, col_abs=fixa)}"
    return f"'{aba}'!{ref}" if aba else ref


def data_excel(mes):
    return datetime.strptime(str(mes)[:10], "%Y-%m-%d")


class Formatos:
    """Formatos do padrão (Arial 10, letra preta), criados uma vez por arquivo."""

    def __init__(self, livro):
        self.livro, self._cache = livro, {}

    def __call__(self, **props):
        chave = tuple(sorted(props.items()))
        if chave not in self._cache:
            self._cache[chave] = self.livro.add_format({"font_name": "Arial", "font_size": 10, **props})
        return self._cache[chave]

    def cabecalho(self, cor, centro=False, **props):
        """Cabeçalho: fundo da cor do tipo, letra branca, borda branca separando as colunas."""
        if centro:
            props["align"] = "center"
        return self(bold=True, font_color="white", bg_color=cor, text_wrap=True, valign="vcenter", border=1,
                    border_color=COR["cab_borda"], **props)

    def dado(self, sep=False, total=False, **props):
        """Célula de tabela: fio claro embaixo; sep = fio cinza à esquerda (início de bloco); total = fio escuro embaixo."""
        borda = {"bottom": 1, "bottom_color": COR["total_linha"] if total else COR["linha"]}
        if sep:
            borda.update({"left": 1, "left_color": COR["separador"]})
        return self(**borda, **props)

    def check(self, **props):
        return self(italic=True, font_color=COR["check"], align="center", **props)

    def nota(self):
        return self(italic=True, font_color=COR["nota"])


def topo(ws, f, mestre, descricao, fonte, n_falso, ref_linha_check, cor_aba=None):
    """A1 (indicador geral), A2 (checks desta aba), B1 (o que é), B2 (de onde vem); sem grade, coluna A estreita."""
    ws.hide_gridlines(2)
    ws.set_column(0, 0, 2.6)
    if cor_aba:
        ws.set_tab_color(cor_aba)
    ws.write_formula(0, 0, f"=COUNTIF('{ABA_CHECK}'!$C$3:$C${3 + MAX_ABAS_CHECK},FALSE)", f(bold=True, align="center"),
                     mestre)
    ws.write_formula(1, 0, f"=COUNTIF({ref_linha_check},FALSE)" if ref_linha_check else "=0",
                     f(bold=True, align="center"), n_falso)
    vermelho = {"type": "cell", "criteria": ">", "value": 0, "format": f(bold=True, font_color=COR["falso"])}
    ws.conditional_format(0, 0, 1, 0, vermelho)
    ws.write(0, 1, descricao, f(italic=True))
    ws.write(1, 1, fonte, f.nota())


def realcar_falso(ws, f, l1, c1, l2, c2):
    ws.conditional_format(l1, c1, l2, c2, {"type": "cell", "criteria": "==", "value": "FALSE",
                                           "format": f(bold=True, italic=True, font_color=COR["falso"])})


# ---------------- tabela padrão ----------------
@dataclass
class Coluna:
    """
    Uma coluna da tabela.
      tipo: "input" (vem pronta da rodagem), "texto" (input de texto), "formula" (conta no Excel)
      formula: modelo com {campo} = célula da mesma linha, {P:chave} = premissa, {R:campo} = faixa da coluna;
               ou função (linha → modelo ou None) quando a conta muda conforme a linha
      py: a mesma conta em Python (linha → valor), para conferir que a fórmula reproduz a rodagem
      check: fórmula do check da linha 3 ({R} = faixa desta coluna, {P:chave}, {R:campo}); "auto" = padrão do tipo
    """
    titulo: str
    campo: Optional[str] = None
    tipo: str = "input"
    formula: object = None
    py: Optional[Callable] = None
    fmt: Optional[str] = None
    largura: float = 12
    escala: float = 1.0
    data: bool = False
    titulo_data: Optional[str] = None   # cabeçalho é um mês (data de verdade, critério de SUMIFS): "AAAA-MM-DD"
    check: Optional[str] = "auto"
    check_valor: Optional[bool] = None
    separador: bool = False             # fio cinza à esquerda (início de bloco) mesmo sem trocar de rótulo para número


@dataclass
class Tabela:
    nome: str
    df: pd.DataFrame
    colunas: list
    descricao: str
    fonte: str
    cor_aba: Optional[str] = None
    congelar: int = 1
    o_que_confere: str = ""
    linhas_total: list = field(default_factory=list)   # índices de linhas em negrito/fundo cinza

    def __post_init__(self):
        self.df = self.df.reset_index(drop=True)
        self.n = len(self.df)
        self.col_de = {c.campo or c.titulo: 1 + j for j, c in enumerate(self.colunas)}
        self.ultima = L_DADOS + max(self.n, 1) - 1
        self._valores()
        self._checks()

    # posições
    def ref(self, campo, i, fixa=False):
        return cel(L_DADOS + i, self.col_de[campo], fixa=fixa)

    def rng(self, campo, aba=False):
        c = self.col_de[campo]
        return faixa(L_DADOS, c, self.ultima, c, self.nome if aba else None)

    def linha_check_ref(self):
        return faixa(L_CHECK, 1, L_CHECK, len(self.colunas))

    def _render(self, modelo, i, col_propria=None):
        texto = modelo
        for chave in [p[0] for p in PREMISSAS]:
            texto = texto.replace("{P:" + chave + "}", ref_premissa(chave))
        texto = re.sub(r"\{RL:([^:{}]+):(\d+):(\d+)\}", lambda m: faixa(
            L_DADOS + int(m.group(2)), self.col_de[m.group(1)], L_DADOS + int(m.group(3)), self.col_de[m.group(1)],
            fixa=False), texto)
        for campo in sorted(self.col_de, key=len, reverse=True):
            texto = texto.replace("{H:" + campo + "}", cel(L_CAB, self.col_de[campo], fixa=True))
            texto = texto.replace("{R:" + campo + "}", self.rng(campo))
            if i is not None:
                texto = texto.replace("{" + campo + "}", self.ref(campo, i))
        if col_propria is not None:
            texto = texto.replace("{R}", faixa(L_DADOS, col_propria, self.ultima, col_propria))
        return texto

    # valores e decisão fórmula × número
    def _valores(self):
        self.celulas = {}   # (i, campo) → ("formula", texto, valor) | ("valor", valor)
        self.excecoes = {}
        linhas = self.df.to_dict("records")
        for linha in linhas:   # vazio = None; escala antes de qualquer conta (ex.: % que vem × 100)
            for c in self.colunas:
                v = linha.get(c.campo) if c.campo else None
                if isinstance(v, float) and np.isnan(v):
                    v = None
                elif v is not None and not isinstance(v, str) and c.escala != 1.0:
                    v = v * c.escala
                if c.campo:
                    linha[c.campo] = v
        for c in self.colunas:
            campo = c.campo or c.titulo
            for i, linha in enumerate(linhas):
                v = linha.get(c.campo) if c.campo else None
                linha["_i"] = i
                modelo = c.formula(linha) if callable(c.formula) else c.formula
                if modelo:
                    if c.py is not None and c.campo:
                        esperado = c.py(linha)
                        if not _igual(esperado, v):
                            self.celulas[(i, campo)] = ("valor", v)
                            self.excecoes[campo] = self.excecoes.get(campo, 0) + 1
                            continue
                    self.celulas[(i, campo)] = ("formula", self._render(modelo, i), "" if v is None else v)
                else:
                    self.celulas[(i, campo)] = ("valor", v)
            if c.data:
                for i in range(self.n):
                    tipo, v = self.celulas[(i, campo)][:2]
                    if tipo == "valor" and v is not None:
                        self.celulas[(i, campo)] = ("valor", data_excel(v))

    def _serie(self, campo):
        vals = []
        for i in range(self.n):
            cel_ = self.celulas[(i, campo)]
            vals.append(cel_[2] if cel_[0] == "formula" else cel_[1])
        return vals

    def _checks(self):
        self.check = {}
        for j, c in enumerate(self.colunas):
            campo = c.campo or c.titulo
            modelo = c.check
            if modelo == "auto":
                if c.tipo == "input" and not c.data:
                    modelo = "=AND(SUMPRODUCT(--ISERROR({R}))=0,COUNTIF({R},\"<0\")=0)"
                    nums = [v for v in self._serie(campo) if isinstance(v, (int, float)) and not isinstance(v, bool)]
                    valor = all(v >= 0 for v in nums)
                elif c.tipo == "formula":
                    modelo, valor = "=SUMPRODUCT(--ISERROR({R}))=0", True
                elif c.tipo == "check":
                    modelo = "=COUNTIF({R},FALSE)=0"
                    valor = all(v is not False for v in self._serie(campo))
                else:
                    modelo = None
            else:
                valor = c.check_valor
            if modelo and self.n:
                self.check[campo] = (self._render(modelo, None, 1 + j), bool(valor))
        self.n_falso = sum(not v for _, v in self.check.values())

    # escrita
    def escrever(self, livro, f, mestre):
        ws = livro.add_worksheet(self.nome)
        topo(ws, f, mestre, self.descricao, self.fonte, self.n_falso, self.linha_check_ref(), self.cor_aba)
        rotulo = [c.tipo == "texto" or c.data for c in self.colunas]   # rótulo × número: troca = início de bloco
        for j, c in enumerate(self.colunas):
            col = 1 + j
            campo = c.campo or c.titulo
            sep = j > 0 and (rotulo[j] != rotulo[j - 1] or c.separador)
            cor = {"formula": COR["cab_formula"], "check": COR["cab_check"]}.get(c.tipo, COR["cab_input"])
            if c.titulo_data:
                ws.write_datetime(L_CAB, col, data_excel(c.titulo_data), f.cabecalho(cor, True, num_format="mmm/yy"))
            else:
                ws.write(L_CAB, col, c.titulo, f.cabecalho(cor, centro=not rotulo[j]))
            ws.set_column(col, col, c.largura)
            if campo in self.check:
                texto, valor = self.check[campo]
                ws.write_formula(L_CHECK, col, texto, f.check(), valor)
            fmt_base = {"num_format": c.fmt} if c.fmt else {}
            if c.tipo == "check":
                fmt_base = {"italic": True, "font_color": COR["check"], "align": "center"}
            for i in range(self.n):
                total = i in self.linhas_total
                destaque = {"bold": True, "bg_color": COR["total"]} if total else {}
                fmt = f.dado(sep, total, **fmt_base, **destaque)
                cel_ = self.celulas[(i, campo)]
                if cel_[0] == "formula":
                    ws.write_formula(L_DADOS + i, col, cel_[1], fmt, cel_[2])
                elif cel_[1] is None:
                    ws.write_blank(L_DADOS + i, col, None, fmt)
                elif isinstance(cel_[1], datetime):
                    ws.write_datetime(L_DADOS + i, col, cel_[1],
                                      f.dado(sep, total, num_format=c.fmt or "yyyy-mm-dd", align="left", **destaque))
                elif isinstance(cel_[1], str):
                    ws.write_string(L_DADOS + i, col, cel_[1], fmt)
                elif isinstance(cel_[1], (bool, np.bool_)):
                    ws.write_boolean(L_DADOS + i, col, bool(cel_[1]), fmt)
                else:
                    ws.write_number(L_DADOS + i, col, float(cel_[1]), fmt)
        ws.set_row(L_CAB, 30)
        realcar_falso(ws, f, L_CHECK, 1, L_CHECK, len(self.colunas))
        for j, c in enumerate(self.colunas):
            if c.tipo == "check" and self.n:
                realcar_falso(ws, f, L_DADOS, 1 + j, self.ultima, 1 + j)
        if self.n:
            ws.autofilter(L_CAB, 1, self.ultima, len(self.colunas))
        ws.freeze_panes(L_DADOS, 1 + self.congelar)
        return ws


def _igual(a, b):
    vazio = lambda x: x is None or x == "" or (isinstance(x, float) and np.isnan(x))
    if vazio(a) or vazio(b):
        return vazio(a) and vazio(b)
    try:
        return abs(float(a) - float(b)) <= TOL * max(1.0, abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


# ---------------- abas Premissas e Check ----------------
def escrever_premissas(livro, f, mestre):
    ws = livro.add_worksheet(ABA_PREMISSAS)
    n = len(PREMISSAS)
    topo(ws, f, mestre, "Premissas usadas nas fórmulas e nos checks do arquivo (mudar aqui muda todas as contas).",
         "Fonte: Rodagem de Malha 2.0 (valores padrão da ferramenta)", 0, faixa(L_CHECK, 1, L_CHECK, 3),
         COR["aba_premissa"])
    ws.write_formula(L_CHECK, 2, f"=COUNTBLANK({faixa(L_DADOS, 2, L_DADOS + n - 1, 2)})=0", f.check(), True)
    realcar_falso(ws, f, L_CHECK, 1, L_CHECK, 3)
    ws.write_row(L_CAB, 1, ["Premissa", "Valor", "Onde é usada"], f.cabecalho(COR["cab_premissa"]))
    caixa = {"border": 1, "border_color": COR["separador"], "align": "center"}   # valor que se pode mudar: caixa
    for i, (_, nome, valor, fmt, uso) in enumerate(PREMISSAS):
        ws.write(L_DADOS + i, 1, nome, f.dado())
        if isinstance(valor, str):
            ws.write_string(L_DADOS + i, 2, valor, f(**caixa))
        else:
            ws.write_number(L_DADOS + i, 2, valor, f(num_format=fmt, **caixa))
        ws.write(L_DADOS + i, 3, uso, f.dado(italic=True))
    ws.set_column(1, 1, 48)
    ws.set_column(2, 2, 16)
    ws.set_column(3, 3, 90)
    ws.freeze_panes(L_DADOS, 0)


def escrever_check(livro, f, abas, mestre):
    """abas: [(nome, ok, o que confere)]. Uma linha por aba: ='Aba'!A2=0. A1 = nº de abas com FALSE."""
    ws = livro.add_worksheet(ABA_CHECK)
    ws.hide_gridlines(2)
    ws.set_tab_color(COR["aba_check"])
    ws.set_column(0, 0, 2.6)
    ws.set_column(1, 1, 30)
    ws.set_column(2, 2, 10)
    ws.set_column(3, 3, 110)
    ws.write_formula(0, 0, f"=COUNTIF(C3:C{3 + MAX_ABAS_CHECK},FALSE)", f(bold=True, align="center"), mestre)
    ws.conditional_format(0, 0, 0, 0, {"type": "cell", "criteria": ">", "value": 0,
                                       "format": f(bold=True, font_color=COR["falso"])})
    ws.write(0, 1, "Check: uma linha por aba. A1 = nº de abas com algum check FALSE (0 = tudo certo).", f(italic=True))
    ws.write_row(1, 1, ["Aba", "Check", "O que confere"], f.cabecalho(COR["cab_check"]))
    for i, (nome, ok, o_que) in enumerate(abas):
        ws.write_url(2 + i, 1, f"internal:'{nome}'!A1", f.dado(underline=1), string=nome)
        ws.write_formula(2 + i, 2, f"='{nome}'!A2=0", f.dado(italic=True, font_color=COR["check"], align="center"),
                         bool(ok))
        ws.write(2 + i, 3, o_que, f.dado())
    realcar_falso(ws, f, 2, 2, 2 + len(abas), 2)
    ws.freeze_panes(2, 0)
