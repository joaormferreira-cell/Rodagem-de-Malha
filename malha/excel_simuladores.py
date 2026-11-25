"""
Abas de simulador (Simulador de iniciativas e Simulador de malha) no padrão de excel_padrao.py:
  - topo padrão: A1 (checks do arquivo), A2 (checks da aba), B1 (o que é e como usar), B2 (de onde vem);
  - linha 3 = todos os checks da aba OK?; a partir da linha 4: quadro do resultado, lista de checks (fórmula aberta,
    um TRUE/FALSE por check) e as tabelas;
  - colunas para digitar têm cabeçalho verde "(digite aqui)"; colunas calculadas, cabeçalho cinza escuro;
    letras pretas, sem célula colorida; 1/0 de "ligada" vêm da aba Premissas;
  - tudo o que é conta é fórmula (ponte do BWT, impactos, efeitos, viagem simulada).
"""
import pandas as pd
from xlsxwriter.utility import xl_rowcol_to_cell

from .calculo.by_step import TOLERANCIA_CHECK, TOTAL, confere
from .calculo.initiatives import _rotulo
from .calculo.simulador import rotulos as rotulos_simulador
from .excel_padrao import ABA, COR, L_CHECK, L_DADOS, VALOR_PREMISSA, cel, faixa, realcar_falso, ref_premissa, topo

L_QUADRO = 3        # linha 4: cabeçalho do quadro do resultado
TOL = ref_premissa("tolerancia")
H2, PCT, MIL = "#,##0.00", "0.0%", "#,##0"


def _compara(a, b):
    return f"=ABS({a}-{b})<={TOL}*MAX(1,ABS({a}),ABS({b}))"


def _num(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)


class _Simulador:
    """Base: topo, quadro, lista de checks e rollup da linha 3."""

    def _escrever_topo(self, ws, f, mestre, descricao, fonte):
        topo(ws, f, mestre, descricao, fonte, self.n_falso, faixa(L_CHECK, 1, L_CHECK, 2, fixa=False))
        ws.write(L_CHECK, 1, "Todos os checks da aba OK?", f(bold=True))
        ok = faixa(self.l_chk + 1, 2, self.l_chk + len(self.checks), 2)
        ws.write_formula(L_CHECK, 2, f"=COUNTIF({ok},FALSE)=0", f.check(), self.n_falso == 0)
        realcar_falso(ws, f, L_CHECK, 2, L_CHECK, 2)

    def _escrever_checks(self, ws, f):
        ws.write(self.l_chk, 1, "Check (fórmula na célula ao lado)", f.cabecalho(COR["cab_check"]))
        ws.write(self.l_chk, 2, "OK?", f.cabecalho(COR["cab_check"], centro=True))
        for i, (texto, formula, valor) in enumerate(self.checks):
            ws.write(self.l_chk + 1 + i, 1, texto, f.dado())
            ws.write_formula(self.l_chk + 1 + i, 2, formula,
                             f.dado(sep=True, italic=True, font_color=COR["check"], align="center"), bool(valor))
        realcar_falso(ws, f, self.l_chk + 1, 2, self.l_chk + len(self.checks), 2)

    @staticmethod
    def _cabecalho(ws, f, linha, colunas):
        """colunas: [(nome, tipo)]; tipo 'f' = fórmula (cinza escuro), 'i' = número da rodagem ou digitar (verde),
        't' = rótulo (verde, alinhado à esquerda)."""
        for j, (nome, tipo) in enumerate(colunas):
            cor = COR["cab_formula"] if tipo == "f" else COR["cab_input"]
            ws.write(linha, 1 + j, nome, f.cabecalho(cor, centro=tipo != "t"))

    @staticmethod
    def _fundo(ws, f, linha, n_colunas, seps):
        """Fio claro na linha inteira da tabela (células vazias também), fio cinza no início de cada bloco."""
        for c in range(1, 1 + n_colunas):
            ws.write_blank(linha, c, None, f.dado(sep=c in seps))

    @property
    def n_falso(self):
        return int(not all(v for _, _, v in self.checks))


# ---------------- Simulador de iniciativas ----------------
class SimuladorIniciativas(_Simulador):
    nome = ABA["sim_ini"]
    o_que_confere = ("Ligada? só 1/0; BWT simulado = Σ % pedidos × etapa simulada; total ligado = ponte; com tudo "
                     "ligado = meta das etapas; % pedidos entre 0 e 100%; fórmulas sem erro")

    def __init__(self, resultados):
        self.r = resultados["simulador_resumo"].iloc[0].to_dict()
        self.ini = resultados["simulador_iniciativas"].reset_index(drop=True)
        self.et = resultados["simulador_etapas"].reset_index(drop=True)
        self.m = rotulos_simulador(self.r)
        self.l_ponte = L_QUADRO + 1
        self.l_chk = self.l_ponte + 9
        n_chk = 6
        self.l_ini = self.l_chk + n_chk + 3
        self.p_ini, self.u_ini = self.l_ini + 1, self.l_ini + len(self.ini)
        self.l_et = self.u_ini + 4
        self.p_et, self.u_et = self.l_et + 1, self.l_et + len(self.et)
        ri = lambda c: faixa(self.p_ini, c, self.u_ini, c)
        re_ = lambda c: faixa(self.p_et, c, self.u_et, c)
        self.ini_etapa, self.ini_total, self.ini_share, self.ini_bwt, self.ini_lig, self.ini_ligado = \
            ri(1), ri(7), ri(8), ri(9), ri(10), ri(11)
        self.et_etapa, self.et_sr, self.et_sb, self.et_real, self.et_mb, self.et_dev, self.et_sim, self.et_aj = \
            re_(1), re_(3), re_(4), re_(5), re_(7), re_(8), re_(9), re_(10)
        self.c_sim = cel(self.l_ponte + 4, 2)          # BWT simulado
        self.c_lig = cel(self.l_ponte + 2, 2)          # iniciativas ligadas
        self._checks()

    def _checks(self):
        r, et, ini = self.r, self.et, self.ini
        sb, mb, sr = (pd.to_numeric(et[c], errors="coerce").fillna(0) for c in ("share_b", "meta_b_h", "share_r"))
        sim = r["soma_b_h"]
        soma_et = float((sb * mb).sum())
        shares = pd.concat([sr, sb])
        ligado = float(pd.to_numeric(ini["impacto_bwt_h"], errors="coerce").fillna(0).sum())
        sp = f"SUMPRODUCT({self.et_sb},{self.et_sim})"
        sm = f"SUMPRODUCT({self.et_sb},{self.et_mb})"
        lig, des = ref_premissa("ligada"), ref_premissa("desligada")
        self.checks = [
            ("Ligada? só 1 ou 0 (valores da aba Premissas)",
             f"=SUMPRODUCT(({self.ini_lig}<>{lig})*({self.ini_lig}<>{des}))=0", True),
            ("BWT simulado = Σ % pedidos × etapa simulada",
             _compara(self.c_sim, sp), confere(sim, soma_et)),
            ("Total 'Impacto ligado' = 'Iniciativas ligadas'",
             _compara(f"SUM({self.ini_ligado})", self.c_lig), confere(ligado, r["iniciativas_h"])),
            ("Tudo ligado: simulado = Σ % pedidos × meta",
             f"=IF(COUNTIF({self.ini_lig},{des})=0,{_compara(self.c_sim, sm)[1:]},TRUE)", confere(sim, soma_et)),
            ("% pedidos das etapas entre 0% e 100%",
             f"=AND(MIN({self.et_sr},{self.et_sb})>=0,MAX({self.et_sr},{self.et_sb})<=1)",
             bool(shares.min() >= 0 and shares.max() <= 1)),
            ("Nenhuma fórmula com erro",
             f"=SUMPRODUCT(--ISERROR({faixa(self.l_ponte, 2, self.l_ponte + 6, 2)}))"
             f"+SUMPRODUCT(--ISERROR({faixa(self.p_ini, 7, self.u_ini, 11)}))"
             f"+SUMPRODUCT(--ISERROR({faixa(self.p_et, 8, self.u_et, 10)}))=0", True),
        ]

    def escrever(self, livro, f, mestre):
        r, m, ini, et = self.r, self.m, self.ini, self.et
        ws = livro.add_worksheet(self.nome)
        self._escrever_topo(
            ws, f, mestre,
            f"Simulador de iniciativas: BWT do SPX D2D em {m['mes_b']}. Na coluna 'Ligada?' (cabeçalho verde, digite "
            "aqui) troque 1 por 0 para tirar uma iniciativa: a ponte, as etapas e os checks recalculam sozinhos.",
            f"Source: aba Nov26-27 da Initiatives. Impacto no BWT = horas na etapa ({m['mes_a']} + {m['mes_b']}) × % de "
            f"pedidos da etapa em {m['mes_b']}. Negativo = reduz o BWT.")
        destaque = {"bold": True, "bg_color": COR["total"]}
        total_baixo = {"top": 1, "top_color": COR["total_linha"], **destaque}   # linha de total embaixo da tabela

        # ponte (quadro do resultado)
        ws.write(L_QUADRO, 1, "Ponte", f.cabecalho(COR["cab_formula"]))
        ws.write(L_QUADRO, 2, "horas", f.cabecalho(COR["cab_formula"], centro=True))
        lp = self.l_ponte
        ponte = [
            (f"BWT real {m['mes_real']} (soma das etapas da Initiatives)",
             f"=SUMPRODUCT({self.et_sr},{self.et_real})", r["soma_real_h"]),
            (f"Mudança no % de pedidos por etapa ({m['mes_real']} → {m['mes_b']})",
             f"=SUMPRODUCT({self.et_sb}-{self.et_sr},{self.et_real})", r["mix_h"]),
            ("Iniciativas ligadas", f"=SUMPRODUCT({self.ini_bwt},{self.ini_lig})", r["iniciativas_h"]),
            ("Ajustes nas etapas que nenhuma iniciativa explica", f"=SUMPRODUCT({self.et_sb},{self.et_aj})",
             r["ajustes_h"]),
        ]
        for k, (rotulo, formula, valor) in enumerate(ponte):
            ws.write(lp + k, 1, rotulo, f.dado())
            ws.write_formula(lp + k, 2, formula, f.dado(sep=True, num_format=H2), valor)
        ws.write(lp + 4, 1, f"BWT {m['mes_b']} simulado", f.dado(total=True, **destaque))
        ws.write_formula(lp + 4, 2, f"=SUM({faixa(lp, 2, lp + 3, 2, fixa=False)})",
                         f.dado(sep=True, total=True, num_format=H2, **destaque), r["soma_b_h"])
        ws.write(lp + 5, 1, f"Meta oficial {m['mes_b']} da Initiatives (linha '(-) SPX D2D')", f.dado())
        ws.write_number(lp + 5, 2, r["total_b_h"], f.dado(sep=True, num_format=H2))
        ws.write(lp + 6, 1, "Falta para a meta oficial (> 0 = simulado acima da meta)", f.dado(total=True, **destaque))
        ws.write_formula(lp + 6, 2, f"={self.c_sim}-{cel(lp + 5, 2)}",
                         f.dado(sep=True, total=True, num_format=H2, **destaque), r["soma_b_h"] - r["total_b_h"])
        ws.write(lp + 7, 1, f"Para comparar: meta {m['mes_a']} = {r['total_a_h']:.1f}h; real {m['mes_real']} (total "
                            f"oficial) = {r['total_real_h']:.1f}h. No real, a soma das etapas fica abaixo do total "
                            "porque a Initiatives não lista todas as etapas.", f(italic=True))
        self._escrever_checks(ws, f)

        # iniciativas: rótulos | impactos da planilha | contas | Ligada? (digitar) | conta | texto
        ws.write(self.l_ini - 1, 1, "Iniciativas (troque 1 por 0 em 'Ligada?')", f(bold=True))
        cab = [("Etapa (Initiatives)", "t"), ("KPI By Step", "t"), ("Iniciativa", "t"), ("Dono", "t"),
               (f"Impacto {m['mes_a']} na etapa (h)", "i"), (f"Impacto {m['mes_b']} na etapa (h)", "i"),
               ("Impacto total na etapa (h)", "f"), (f"% pedidos da etapa {m['mes_b']}", "f"),
               ("Impacto no BWT (h)", "f"), ("Ligada? 1 = sim, 0 = não (digite aqui)", "i"),
               ("Impacto ligado no BWT (h)", "f"), ("Observação", "t"), ("Racional (da planilha)", "t")]
        self._cabecalho(ws, f, self.l_ini, cab)
        seps = {5, 7, 10, 11, 12}
        fd = lambda c, **props: f.dado(sep=c in seps, **props)
        kpis = et.set_index("etapa")["kpis"]
        for k, i in enumerate(ini.itertuples(index=False)):
            lin = self.p_ini + k
            self._fundo(ws, f, lin, len(cab), seps)
            for j, v in enumerate([i.etapa, kpis.get(i.etapa, ""), i.iniciativa, i.dono]):
                ws.write(lin, 1 + j, v, fd(1 + j))
            for j, v in [(5, i.impacto_a_h), (6, i.impacto_b_h)]:
                if _num(v) is not None:
                    ws.write_number(lin, j, _num(v), fd(j, num_format=H2))
            a, b, tot_c, sh, bwt, lg = (cel(lin, j) for j in (5, 6, 7, 8, 9, 10))
            ws.write_formula(lin, 7, f"=N({a})+N({b})", fd(7, num_format=H2), _num(i.impacto_total_h) or 0.0)
            etapa = xl_rowcol_to_cell(lin, 1, col_abs=True)
            ws.write_formula(lin, 8, f'=IFERROR(INDEX({self.et_sb},MATCH({etapa},{self.et_etapa},0)),"")',
                             fd(8, num_format=PCT), "" if _num(i.share_b) is None else _num(i.share_b))
            ws.write_formula(lin, 9, f'=IF({sh}="","",{tot_c}*{sh})', fd(9, num_format=H2),
                             "" if _num(i.impacto_bwt_h) is None else _num(i.impacto_bwt_h))
            ws.write_number(lin, 10, VALOR_PREMISSA["ligada"], fd(10, align="center"))
            ws.write_formula(lin, 11, f'=IF({bwt}="","",{bwt}*{lg})', fd(11, num_format=H2),
                             "" if _num(i.impacto_bwt_h) is None else _num(i.impacto_bwt_h))
            ws.write(lin, 12, i.observacao, fd(12))
            ws.write(lin, 13, str(i.racional)[:250], fd(13))
        ws.data_validation(self.p_ini, 10, self.u_ini, 10, {
            "validate": "list", "source": [str(VALOR_PREMISSA["ligada"]), str(VALOR_PREMISSA["desligada"])],
            "error_message": "Use 1 (ligada) ou 0 (desligada)."})
        for c in range(1, 1 + len(cab)):
            ws.write_blank(self.u_ini + 1, c, None, f(**total_baixo))
        ws.write(self.u_ini + 1, 1, "Total", f(**total_baixo))
        ws.write_formula(self.u_ini + 1, 9, f"=SUM({self.ini_bwt})", f(num_format=H2, **total_baixo), r["iniciativas_h"])
        ws.write_formula(self.u_ini + 1, 11, f"=SUM({self.ini_ligado})", f(num_format=H2, **total_baixo),
                         r["iniciativas_h"])
        ws.autofilter(self.l_ini, 1, self.u_ini, len(cab))

        # etapas: rótulos | números da planilha | contas
        ws.write(self.l_et - 1, 1, "Etapas (com as iniciativas desligadas, a etapa volta a ter as horas delas)",
                 f(bold=True))
        cab_et = [("Etapa (Initiatives)", "t"), ("KPI By Step", "t"), (f"% pedidos {m['mes_real']}", "i"),
                  (f"% pedidos {m['mes_b']}", "i"), (f"Real {m['mes_real']} (h)", "i"), (f"Meta {m['mes_a']} (h)", "i"),
                  (f"Meta {m['mes_b']} (h)", "i"), ("Desligadas devolvem (h)", "f"),
                  (f"Etapa simulada {m['mes_b']} (h)", "f"), ("Ajuste sem iniciativa (h)", "f")]
        self._cabecalho(ws, f, self.l_et, cab_et)
        seps_et = {3, 8}
        fe = lambda c, **props: f.dado(sep=c in seps_et, **props)
        liga = ref_premissa("ligada")
        for k, e in enumerate(et.itertuples(index=False)):
            lin = self.p_et + k
            self._fundo(ws, f, lin, len(cab_et), seps_et)
            ws.write(lin, 1, e.etapa, fe(1))
            ws.write(lin, 2, e.kpis, fe(2))
            ws.write_number(lin, 3, _num(e.share_r) or 0.0, fe(3, num_format=PCT))
            ws.write_number(lin, 4, _num(e.share_b) or 0.0, fe(4, num_format=PCT))
            for j, v in [(5, e.real_h), (6, e.meta_a_h), (7, e.meta_b_h)]:
                if _num(v) is not None:
                    ws.write_number(lin, j, _num(v), fe(j, num_format=H2))
            etapa, real, mb, dev = xl_rowcol_to_cell(lin, 1, col_abs=True), cel(lin, 5), cel(lin, 7), cel(lin, 8)
            ws.write_formula(lin, 8, f'=-SUMIFS({self.ini_total},{self.ini_etapa},{etapa},{self.ini_lig},"<>"&{liga})',
                             fe(8, num_format=H2), 0)
            ws.write_formula(lin, 9, f"={mb}+{dev}", fe(9, num_format=H2), _num(e.meta_b_h) or 0.0)
            ws.write_formula(lin, 10, f'=IF(OR({mb}="",{real}=""),"",{mb}-{real}-SUMIFS({self.ini_total},'
                                      f'{self.ini_etapa},{etapa}))', fe(10, num_format=H2),
                             "" if _num(e.ajuste_h) is None else _num(e.ajuste_h))
        for c, w in [(1, 58), (2, 14), (3, 46), (4, 15), (5, 14), (6, 14), (7, 14), (8, 14), (9, 14), (10, 16),
                     (11, 14), (12, 38), (13, 70)]:
            ws.set_column(c, c, w)
        ws.set_row(self.l_ini, 45)
        ws.set_row(self.l_et, 45)


# ---------------- Simulador de malha ----------------
class SimuladorMalha(_Simulador):
    nome = ABA["sim_malha"]
    o_que_confere = ("Nova fila/viagem ≥ 0; Virar expressa? vazio ou 1; sem nada digitado efeito = 0; % pedidos entre "
                     "0 e 100%; fórmulas sem erro")

    def __init__(self, resultados, meta_by_step):
        self.r = resultados["simulador_malha_resumo"].iloc[0]
        self.filas = resultados["simulador_malha_filas"].reset_index(drop=True)
        self.rotas = resultados["simulador_malha_rotas"].reset_index(drop=True)
        self.l_q = L_QUADRO + 1
        self.l_chk = self.l_q + 6
        self.hoje = self._meta_hoje(meta_by_step)
        n_chk = 6 + sum(ref is None for ref, _ in self.hoje)
        self.l_f = self.l_chk + n_chk + 3
        self.p_f, self.u_f = self.l_f + 1, self.l_f + max(len(self.filas), 1)
        self.l_r = self.u_f + 4
        self.p_r, self.u_r = self.l_r + 1, self.l_r + max(len(self.rotas), 1)
        self._checks()

    def _meta_hoje(self, tab):
        """Meta de BWT hoje: fórmula apontando para a aba By Step por canal (FLOW BWT TOT do mês), se bater."""
        saida = []
        for canal, valor in [("SPX D2D", self.r["bwt_spx_h"]), ("SPX Fulfillment", self.r["bwt_fbs_h"])]:
            ref = None
            if tab is not None:
                meses = {c.titulo_data[:10]: c.campo for c in tab.colunas if c.titulo_data}
                campo = meses.get(str(self.r["mes"])[:10])
                linhas = tab.df.index[(tab.df["kpi"] == TOTAL) & (tab.df["canal"] == canal)]
                if campo and len(linhas) and _num(valor) is not None:
                    i = int(linhas[0])
                    if confere(_num(tab.df.at[i, campo]) or 0.0, _num(valor)):
                        ref = cel(L_DADOS + i, tab.col_de[campo], tab.nome, fixa=True)
            saida.append((ref, _num(valor)))
        return saida

    def _checks(self):
        nf = faixa(self.p_f, 7, self.u_f, 7)
        nr, vx = faixa(self.p_r, 12, self.u_r, 12), faixa(self.p_r, 13, self.u_r, 13)
        pesos = [faixa(self.p_f, 4, self.u_f, 4), faixa(self.p_f, 5, self.u_f, 5),
                 faixa(self.p_r, 7, self.u_r, 7), faixa(self.p_r, 8, self.u_r, 8)]
        valores = pd.concat([pd.to_numeric(self.filas.get(c), errors="coerce") for c in ("peso_spx", "peso_fbs")] +
                            [pd.to_numeric(self.rotas.get(c), errors="coerce") for c in ("peso_spx", "peso_fbs")]).dropna()
        efeitos = faixa(self.l_q + 1, 2, self.l_q + 2, 3)
        self.checks = [
            ("Nova fila: vazio ou 0 h para cima", f'=AND(COUNTIF({nf},"<0")=0,COUNTA({nf})=COUNT({nf}))', True),
            ("Nova viagem: vazio ou 0 h para cima", f'=AND(COUNTIF({nr},"<0")=0,COUNTA({nr})=COUNT({nr}))',
             True),
            ("Virar expressa?: vazio ou 1 (aba Premissas)",
             f'=SUMPRODUCT(({vx}<>"")*({vx}<>{ref_premissa("ligada")}))=0', True),
            ("Nada digitado: efeitos no BWT = 0",
             f"=IF(COUNTA({nf})+COUNTA({nr})+COUNTA({vx})=0,SUMPRODUCT(ABS({efeitos}))=0,TRUE)", True),
            ("% pedidos de filas e rotas entre 0% e 100%",
             f"=AND(MIN({','.join(pesos)})>=0,MAX({','.join(pesos)})<=1)",
             bool(valores.empty or (valores.min() >= 0 and valores.max() <= 1 + TOLERANCIA_CHECK))),
            ("Nenhuma fórmula com erro",
             f"=SUMPRODUCT(--ISERROR({faixa(self.l_q, 2, self.l_q + 4, 3)}))"
             f"+SUMPRODUCT(--ISERROR({faixa(self.p_f, 8, self.u_f, 9)}))"
             f"+SUMPRODUCT(--ISERROR({faixa(self.p_r, 14, self.u_r, 16)}))=0", True),
        ]
        for j, (ref, valor) in enumerate(self.hoje):
            if ref is None and valor is not None:
                self.checks.append((f"Meta hoje {'SPX D2D' if j == 0 else 'FBS'} ≠ aba {ABA['bs_canal']}", "=FALSE", False))

    def escrever(self, livro, f, mestre):
        r, filas, rotas = self.r, self.filas, self.rotas
        ws = livro.add_worksheet(self.nome)
        self._escrever_topo(
            ws, f, mestre,
            f"Simulador de malha: meta de BWT de {_rotulo(r['mes'])} (Brasil). Digite só nas colunas de cabeçalho verde "
            "'(digite aqui)': nova fila do SOC, nova viagem da rota ou 1 em 'Virar expressa?'. Para voltar, apague.",
            "Mudar o tempo de uma rota em X horas muda a meta de BWT em X × % dos pedidos que passam por ela. É uma "
            "simulação da META: a oficial só muda quando muda a planilha de origem e a ferramenta roda de novo.")
        destaque = {"bold": True, "bg_color": COR["total"]}

        # quadro: rótulo | SPX D2D | FBS; as duas últimas linhas são o resultado
        ws.write(L_QUADRO, 1, "Meta de BWT (h)", f.cabecalho(COR["cab_formula"]))
        ws.write(L_QUADRO, 2, "SPX D2D", f.cabecalho(COR["cab_formula"], centro=True))
        ws.write(L_QUADRO, 3, "Fulfillment (FBS)", f.cabecalho(COR["cab_formula"], centro=True))
        lq = self.l_q
        rotulos = [f"Meta de BWT hoje (aba {ABA['bs_canal']})", "Efeito das filas que você mudou",
                   "Efeito das rotas que você mudou", "Meta de BWT simulada", "Diferença (negativo = BWT menor)"]
        fq = lambda k, c, **props: f.dado(sep=c == 2, total=k == 4, **({**destaque, **props} if k >= 3 else props))
        for k, rotulo in enumerate(rotulos):
            ws.write(lq + k, 1, rotulo, fq(k, 1))
            for c in (2, 3):
                ws.write_blank(lq + k, c, None, fq(k, c, num_format=H2))
        for j, (ref, valor) in enumerate(self.hoje):
            col = 2 + j
            if valor is None:
                continue
            if ref:
                ws.write_formula(lq, col, f"={ref}", fq(0, col, num_format=H2), valor)
            else:
                ws.write_number(lq, col, valor, fq(0, col, num_format=H2))
            ef_f, ef_r = faixa(self.p_f, 8 + j, self.u_f, 8 + j), faixa(self.p_r, 15 + j, self.u_r, 15 + j)
            ws.write_formula(lq + 1, col, f"=SUM({ef_f})", fq(1, col, num_format=H2), 0)
            ws.write_formula(lq + 2, col, f"=SUM({ef_r})", fq(2, col, num_format=H2), 0)
            ws.write_formula(lq + 3, col, f"=SUM({faixa(lq, col, lq + 2, col, fixa=False)})", fq(3, col, num_format=H2),
                             valor)
            ws.write_formula(lq + 4, col, f"={cel(lq + 3, col)}-{cel(lq, col)}", fq(4, col, num_format=H2), 0)
        self._escrever_checks(ws, f)

        # filas: rótulos | números da rodagem | nova fila (digitar) | efeitos (fórmula)
        ws.write(self.l_f - 1, 1, "Filas nos SOCs de destino (chegou → recebido). 'Destinos fora de SOC' = premissa "
                                  "única de fila.", f(bold=True))
        cab_f = [("SOC de destino", "t"), ("De onde vem a fila", "t"), ("Rotas que chegam com fila", "i"),
                 ("% pedidos SPX D2D", "i"), ("% pedidos FBS", "i"), ("Fila hoje (h)", "i"),
                 ("Nova fila (h) (digite aqui)", "i"), ("Efeito SPX D2D (h)", "f"), ("Efeito FBS (h)", "f")]
        self._cabecalho(ws, f, self.l_f, cab_f)
        seps_f = {3, 7, 8}
        ff = lambda c, **props: f.dado(sep=c in seps_f, **props)
        for k, t in enumerate(filas.itertuples(index=False)):
            lin = self.p_f + k
            self._fundo(ws, f, lin, len(cab_f), seps_f)
            ws.write(lin, 1, t.destino, ff(1))
            ws.write(lin, 2, t.fonte_fila, ff(2))
            ws.write_number(lin, 3, float(t.rotas), ff(3, num_format=MIL))
            ws.write_number(lin, 4, float(t.peso_spx), ff(4, num_format=PCT))
            ws.write_number(lin, 5, float(t.peso_fbs), ff(5, num_format=PCT))
            if _num(t.fila_h) is not None:
                ws.write_number(lin, 6, float(t.fila_h), ff(6, num_format=H2))
            ws.write_blank(lin, 7, None, ff(7, num_format=H2))
            nova, hoje = cel(lin, 7), cel(lin, 6)
            for j, peso in [(8, cel(lin, 4)), (9, cel(lin, 5))]:
                ws.write_formula(lin, j, f'=IF({nova}="",0,({nova}-{hoje})*{peso})', ff(j, num_format=H2), 0)
        if len(filas):
            ws.data_validation(self.p_f, 7, self.u_f, 7, {"validate": "decimal", "criteria": ">=", "value": 0,
                                                          "error_message": "Digite a fila em horas (0 ou mais)."})

        # rotas: rota | km | expressa e fonte | números da rodagem | digitar | fórmulas
        ws.write(self.l_r - 2, 1, "Rotas (viagem = saiu → chegou). As que levam mais pedidos primeiro; use o filtro de "
                                  "'Rota' para achar uma rota.", f(bold=True))
        if pd.notna(r.get("expressa_mes")):
            nota = (f"'Virar expressa' usa a velocidade real das rotas da planilha oficial de expressas com distância "
                    f"parecida ({_rotulo(r['expressa_mes'])}): {r['expressa_velocidades']}. Só para rotas de 600 km ou "
                    "mais: abaixo disso não há expressa no real para comparar.")
        else:
            nota = "'Virar expressa' usa a fórmula de expressa por km (troca de motorista, sem descanso longo)."
        ws.write(self.l_r - 1, 1, nota + " Se a rota entrar na planilha oficial de expressas, a meta passa a ser o "
                                         "tempo combinado de lá.", f(italic=True))
        cab_r = [("Rota", "t"), ("Tipo", "t"), ("km", "i"), ("Hoje é expressa?", "i"), ("De onde vem a viagem", "t"),
                 ("Pedidos/dia que passam", "i"), ("% pedidos SPX D2D", "i"), ("% pedidos FBS", "i"),
                 ("Viagem hoje (h)", "i"), ("Fila no destino hoje (h)", "i"), ("Viagem se virar expressa (h)", "i"),
                 ("Nova viagem (h) (digite aqui)", "i"), ("Virar expressa? 1 = sim (digite aqui)", "i"),
                 ("Viagem simulada (h)", "f"), ("Efeito SPX D2D (h)", "f"), ("Efeito FBS (h)", "f")]
        self._cabecalho(ws, f, self.l_r, cab_r)
        seps_r = {3, 4, 6, 12, 14}
        fr = lambda c, **props: f.dado(sep=c in seps_r, **props)
        liga = ref_premissa("ligada")
        for k, t in enumerate(rotas.itertuples(index=False)):
            lin = self.p_r + k
            self._fundo(ws, f, lin, len(cab_r), seps_r)
            ws.write(lin, 1, t.Route, fr(1))
            ws.write(lin, 2, t.route_type, fr(2))
            if _num(t.Distance) is not None:
                ws.write_number(lin, 3, float(t.Distance), fr(3, num_format=MIL))
            ws.write_boolean(lin, 4, bool(t.expressa), fr(4, align="center"))
            ws.write(lin, 5, t.fonte_tt, fr(5))
            ws.write_number(lin, 6, float(t.pedidos_dia), fr(6, num_format=MIL))
            ws.write_number(lin, 7, float(t.peso_spx), fr(7, num_format=PCT))
            ws.write_number(lin, 8, float(t.peso_fbs), fr(8, num_format=PCT))
            for j, v in [(9, t.viagem_h), (10, t.fila_h), (11, t.viagem_expressa_h)]:
                if _num(v) is not None:
                    ws.write_number(lin, j, float(v), fr(j, num_format=H2))
            ws.write_blank(lin, 12, None, fr(12, num_format=H2))
            ws.write_blank(lin, 13, None, fr(13, align="center"))
            hoje, exp, nova, virar, sim = (cel(lin, j) for j in (9, 11, 12, 13, 14))
            ws.write_formula(lin, 14, f'=IF({nova}<>"",{nova},IF(AND({virar}={liga},{exp}<>""),{exp},{hoje}))',
                             fr(14, num_format=H2), _num(t.viagem_h) or 0.0)
            for j, peso in [(15, cel(lin, 7)), (16, cel(lin, 8))]:
                ws.write_formula(lin, j, f"=({sim}-{hoje})*{peso}", fr(j, num_format=H2), 0)
        if len(rotas):
            ws.data_validation(self.p_r, 12, self.u_r, 12, {"validate": "decimal", "criteria": ">=", "value": 0,
                                                            "error_message": "Digite a viagem em horas (0 ou mais)."})
            ws.data_validation(self.p_r, 13, self.u_r, 13, {"validate": "list", "source": [str(VALOR_PREMISSA["ligada"])],
                                                            "error_message": "Use 1 (virar expressa) ou deixe vazio."})
            ws.autofilter(self.l_r, 1, self.u_r, len(cab_r))
        ws.set_row(self.l_f, 45)
        ws.set_row(self.l_r, 45)
        ws.set_column(1, 1, 52)
        ws.set_column(2, 2, 34)
        ws.set_column(3, 17, 13)
        ws.set_column(5, 5, 24)
