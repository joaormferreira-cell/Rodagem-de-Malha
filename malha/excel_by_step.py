"""
Abas de BWT por step (By Step BR/SPM e By Step antigo BR/SPM), no padrão de excel_padrao.py.

Os números da rodagem ficam nas abas de dados (verdes): raw_meta_by_step (etapas da By Step, bwt_n e bwt_d por
mês × canal × rota × KPI) e raw_steps_antigos (steps bwt_* por mês × recorte: pedidos/dia e horas × pedidos/dia).
Nas abas de BWT por step tudo é fórmula:
  pedidos/dia e horas × pedidos/dia de cada step = SUMIFS na aba de dados (mês do cabeçalho, recorte da aba
  Premissas, step da coluna B); Avg time step = horas ÷ pedidos do step; % Share = pedidos do step ÷ pedidos do
  recorte; BWT = horas ÷ pedidos do recorte; totais = soma dos steps e direto dos caminhos.
Linha 3 = um TRUE/FALSE por mês com o resumo dos checks do fim da aba (estação: quem entra = quem é processado =
quem sai; consistência: soma dos steps = total, % share, erros, aba antiga = aba nova).
"""
from datetime import datetime

import pandas as pd
from xlsxwriter.utility import xl_rowcol_to_cell

from .calculo.by_step import (CHECAGENS_ESTACAO, ETAPAS_BY_STEP, KPI, SEM_CHECAGEM_SOC, TOLERANCIA_CHECK, TOTAL,
                              confere, dados_bwt_por_etapa, leg_tipo, observacao, ordem_by_step)
from .calculo.by_step_antiga import (CHECAGENS_ANTIGAS, ETAPAS_ANTIGAS, FULL, NOTA_FULL, NOTA_NAO_TRANSBORDO,
                                     SEM_CHECAGEM_ANTIGA, dados_by_step_antiga)
from .excel_padrao import (ABA, COR, L_CHECK, VALOR_PREMISSA, Coluna, Tabela, cel, data_excel, faixa,
                           realcar_falso, ref_premissa, topo)

L_FAIXA, L_MES, L_CAB, L_SOMA, L_DIAS, L_CAMINHOS, L_ETAPA0 = 3, 4, 5, 6, 7, 8, 9
_EXCEL_DIA0 = datetime(1899, 12, 30)
RAW_META, RAW_ANTIGA = ABA["raw_meta"], ABA["raw_antiga"]


# ---------------- abas de dados (verdes) ----------------
def tabela_raw_meta(meta):
    df = meta[["attempt_month", "spx_channel", "main_route", "kpi", "bwt_n", "bwt_d"]].copy()
    for c in ["bwt_n", "bwt_d"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["media_h"] = df["bwt_n"] / df["bwt_d"]
    return Tabela(RAW_META, df, [
        Coluna("attempt_month", "attempt_month", "input", data=True, largura=12, check=None),
        Coluna("spx_channel", "spx_channel", "texto", largura=16),
        Coluna("main_route", "main_route", "texto", largura=18),
        Coluna("kpi", "kpi", "texto", largura=42),
        Coluna("bwt_n", "bwt_n", fmt="#,##0", largura=16),
        Coluna("bwt_d", "bwt_d", fmt="#,##0", largura=14),
        Coluna("media_h", "media_h", "formula", formula='=IF(N({bwt_d})=0,"",{bwt_n}/{bwt_d})',
               py=lambda r: r["bwt_n"] / r["bwt_d"] if r["bwt_d"] else None, fmt="#,##0.00"),
    ], "Meta da Rodagem no formato da By Step: bwt_n = horas × pedidos/dia, bwt_d = pedidos/dia, media_h = bwt_n ÷ "
       f"bwt_d, por mês × canal × rota macro × etapa. Base das abas {ABA['bs_br']}, {ABA['bs_spm']} e {ABA['bs_canal']}.",
       "Source: Rodagem de Malha 2.0 (meta_by_step, calculado a partir dos caminhos da demanda S&OP)",
       COR["aba_input"], congelar=4, o_que_confere="Sem erro e sem número negativo em nenhuma coluna")


def tabela_raw_antiga(caminhos):
    linhas = []
    for rota, spm in [("rota_br", False), ("rota_spm", True)]:
        d = dados_by_step_antiga(caminhos, spm=spm)
        for mes in d["meses"]:
            for col, *_ in ETAPAS_ANTIGAS:
                linhas.append({"mes": mes, "recorte": VALOR_PREMISSA[rota], "step": col,
                               "pedidos": d["pedidos"].at[col, mes], "horas": d["horas"].at[col, mes]})
            linhas.append({"mes": mes, "recorte": VALOR_PREMISSA[rota], "step": VALOR_PREMISSA["total_antiga"],
                           "pedidos": d["total_pedidos"][mes], "horas": d["total_horas"][mes]})
    df = pd.DataFrame(linhas, columns=["mes", "recorte", "step", "pedidos", "horas"])
    return Tabela(RAW_ANTIGA, df, [
        Coluna("mes", "mes", "input", data=True, largura=12, check=None),
        Coluna("recorte", "recorte", "texto", largura=12),
        Coluna("step", "step", "texto", largura=44),
        Coluna("pedidos_dia", "pedidos", fmt="#,##0", largura=16),
        Coluna("horas_x_pedidos", "horas", fmt="#,##0", largura=16),
    ], "Steps do software antigo (bwt_*) por mês e recorte (SPX D2D + FF D2D, sem CB): pedidos_dia = pedidos/dia que "
       "passam no step (tempo > 0); horas_x_pedidos = horas × pedidos/dia. 'TOTAL caminhos' = o recorte inteiro. "
       f"With Transshipment: pedidos = todos que chegam no SOC; horas = as da Non-transshipment. Base das abas "
       f"{ABA['bs_antigo_br']} e {ABA['bs_antigo_spm']}.",
       "Source: Rodagem de Malha 2.0 (BWT por caminho; SPM pelas flags origin_spm/dest_spm, como na raw_bwt)",
       COR["aba_input"], congelar=3, o_que_confere="Sem erro e sem número negativo")


# ---------------- abas de BWT por step ----------------
class AbaByStep:
    """Uma aba de BWT por step: rótulos, fórmulas (SUMIFS na aba de dados) e checks, com a posição de cada célula."""

    def __init__(self, nome, titulo, cabecalho, larguras, linhas, dados, regras, sem_check, raw, campos_raw,
                 rota, total, par=""):
        self.nome, self.titulo, self.par, self.sem_check = nome, titulo, par, sem_check
        self.cabecalho, self.larguras, self.linhas, self.dados = cabecalho, larguras, linhas, dados
        self.raw, self.campos_raw, self.rota, self.chave_total = raw, campos_raw, rota, total
        self.meses = list(dados["meses"])
        n_rot, n = len(cabecalho), len(self.meses)
        self.c0 = 1 + n_rot
        self.c_obs = self.c0 + 3 * n + 1
        self.c_ped0 = self.c_obs + 2
        self.c_hor0 = self.c_ped0 + n + 1
        self.linha_de = {l["chave"]: L_ETAPA0 + i for i, l in enumerate(linhas)}
        self.ultima = L_ETAPA0 + len(linhas) - 1
        lin = self.ultima + 2
        self.titulo_estacao, lin = lin, lin + 1
        self.checks = []
        for grupo, texto, esq, dir_ in regras:
            self.checks.append({"linha": lin, "tipo": "estacao", "grupo": grupo, "texto": texto,
                                "esq": [k for k in esq if k in self.linha_de],
                                "dir": None if dir_ is None else [k for k in dir_ if k in self.linha_de]})
            lin += 1
        self.linha_sem_check, lin = lin, lin + 2
        self.titulo_consistencia, lin = lin, lin + 1
        consistencia = [("soma", "BWT total: soma dos steps = direto dos caminhos"),
                        ("share", "% Share entre 0% e 100% em todos os steps"),
                        ("erro", "Nenhuma célula com erro (#DIV/0!, #REF!, #VALUE!)")]
        if par:
            consistencia += [("par_bwt", f"BWT total = aba '{par}' (mesmo recorte, outra quebra de steps)"),
                             ("par_ped", f"Pedidos/dia do recorte = aba '{par}'")]
        for tipo, texto in consistencia:
            self.checks.append({"linha": lin, "tipo": tipo, "grupo": "Consistência", "texto": texto})
            lin += 1
        self._calcular()

    @property
    def o_que_confere(self):
        n_est = sum(c["tipo"] == "estacao" for c in self.checks)
        return (f"Por mês: {n_est} checks de estação (entra = processa = sai) + {len(self.checks) - n_est} de "
                f"consistência (soma dos steps = total, % share, erros, cruzado com '{self.par}')")

    def col(self, k, j):       # j: 0 Avg time step, 1 % Share, 2 BWT
        return self.c0 + 3 * k + j

    def col_ped(self, k):
        return self.c_ped0 + k

    def col_hor(self, k):
        return self.c_hor0 + k

    def faixa_checks(self):
        return self.checks[0]["linha"], self.checks[-1]["linha"]

    def rollup_ref(self):
        return faixa(L_CHECK, self.col(0, 1), L_CHECK, self.col(len(self.meses) - 1, 1), fixa=False)

    def _num(self, tabela, chave, mes):
        t = self.dados[tabela]
        if chave not in t.index or mes not in t.columns:
            return 0.0
        v = t.at[chave, mes]
        return 0.0 if pd.isna(v) else float(v)

    def total(self, serie, mes):
        v = self.dados[serie].get(mes, 0.0)
        return 0.0 if pd.isna(v) else float(v)

    def _calcular(self):
        self.v = {}
        for k, mes in enumerate(self.meses):
            tot_p, tot_h = self.total("total_pedidos", mes), self.total("total_horas", mes)
            soma = 0.0
            for l in self.linhas:
                if not l["com_dado"]:
                    continue
                p, h = self._num("pedidos", l["chave"], mes), self._num("horas", l["chave"], mes)
                self.v[(l["chave"], k)] = (h / p if p else "", p / tot_p if tot_p else "", h / tot_p if tot_p else "")
                if not l["fora_da_soma"] and tot_p:
                    soma += h / tot_p
            self.v[("soma", k)] = soma
            self.v[("caminhos", k)] = tot_h / tot_p if tot_p else ""
            self.v[("tot_p", k)] = tot_p

    def pedidos(self, chave, k):
        return self._num("pedidos", chave, self.meses[k])

    def resultado(self, chk, k, abas):
        tipo = chk["tipo"]
        if tipo == "estacao":
            a = sum(self.pedidos(c, k) for c in chk["esq"])
            b = self.v[("tot_p", k)] if chk["dir"] is None else sum(self.pedidos(c, k) for c in chk["dir"])
            return confere(a, b)
        if tipo == "soma":
            return self.v[("caminhos", k)] == "" or confere(self.v[("soma", k)], self.v[("caminhos", k)])
        if tipo == "share":
            shares = [self.v[(l["chave"], k)][1] for l in self.linhas if (l["chave"], k) in self.v]
            shares = [s for s in shares if s != ""]
            return not shares or (min(shares) >= 0 and max(shares) <= 1 + TOLERANCIA_CHECK)
        if tipo == "erro":
            return True
        par = abas[self.par]
        if self.meses[k] not in par.meses:
            return False
        kp = par.meses.index(self.meses[k])
        chave = "soma" if tipo == "par_bwt" else "tot_p"
        return confere(self.v[(chave, k)], par.v[(chave, kp)])

    def resultados(self, abas):
        self.ok = {(i, k): self.resultado(c, k, abas) for i, c in enumerate(self.checks) for k in range(len(self.meses))}
        self.meses_ok = [all(self.ok[(i, k)] for i in range(len(self.checks))) for k in range(len(self.meses))]
        self.n_falso = sum(not ok for ok in self.meses_ok)
        return self.meses_ok

    def formula_check(self, chk, k, abas):
        tipo, tol = chk["tipo"], ref_premissa("tolerancia")

        def compara(a, b):
            return f"=ABS({a}-{b})<={tol}*MAX(1,ABS({a}),ABS({b}))"

        def soma(chaves):
            return f"SUM({','.join(cel(self.linha_de[c], self.col_ped(k)) for c in chaves)})" if chaves else "0"

        if tipo == "estacao":
            direita = cel(L_CAMINHOS, self.col_ped(k)) if chk["dir"] is None else soma(chk["dir"])
            return compara(soma(chk["esq"]), direita)
        if tipo == "soma":
            return compara(cel(L_SOMA, self.col(k, 2)), cel(L_CAMINHOS, self.col(k, 2)))
        faixa_share = f"{cel(L_ETAPA0, self.col(k, 1))}:{cel(self.ultima, self.col(k, 1))}"
        if tipo == "share":
            return f"=AND(MIN({faixa_share})>=0,MAX({faixa_share})<=1+{tol})"
        if tipo == "erro":
            return f"=SUMPRODUCT(--ISERROR({cel(L_SOMA, self.col(k, 0))}:{cel(self.ultima, self.col(k, 2))}))=0"
        par = abas[self.par]
        if self.meses[k] not in par.meses:
            return "=FALSE"
        kp = par.meses.index(self.meses[k])
        if tipo == "par_bwt":
            return compara(cel(L_SOMA, self.col(k, 2)), cel(L_SOMA, par.col(kp, 2), par.nome))
        return compara(cel(L_CAMINHOS, self.col_ped(k)), cel(L_CAMINHOS, par.col_ped(kp), par.nome))

    def formula_sumifs(self, campo_valor, k, criterio_step):
        r, c = self.raw, self.campos_raw
        mes = cel(L_MES, self.col_ped(k) if campo_valor == c["pedidos"] else self.col_hor(k))
        return (f"=SUMIFS({r.rng(campo_valor, aba=True)},{r.rng(c['mes'], aba=True)},{mes},"
                f"{r.rng(c['rota'], aba=True)},{ref_premissa(self.rota)},{r.rng(c['step'], aba=True)},{criterio_step})")


def preparar_abas(resultados):
    """BWT por etapa (steps novos da By Step) e BWT by step antiga (steps bwt_*), BR > BR e SPM > SPM + abas de dados."""
    meta, caminhos = resultados["by_step_meta"], resultados["bwt_caminhos"]
    raw_meta, raw_antiga = tabela_raw_meta(meta), tabela_raw_antiga(caminhos)
    campos_meta = {"mes": "attempt_month", "rota": "main_route", "step": "kpi", "pedidos": "bwt_d", "horas": "bwt_n"}
    campos_antiga = {"mes": "mes", "rota": "recorte", "step": "step", "pedidos": "pedidos", "horas": "horas"}
    abas = []
    for rota, sufixo, rotulo in [("rota_br", "br", "BR > BR"), ("rota_spm", "spm", "SPM > SPM")]:
        dados = dados_bwt_por_etapa(meta, VALOR_PREMISSA[rota])
        com = set(dados["pedidos"].index[dados["pedidos"].fillna(0).sum(axis=1) > 0])
        kpis = sorted(set(dados["pedidos"].index) | set(ETAPAS_BY_STEP), key=ordem_by_step)
        linhas = [{"chave": k, "rotulos": [k, *leg_tipo(k)], "obs": observacao(k, k in com), "com_dado": k in com,
                   "fora_da_soma": False} for k in kpis]
        regras = [(leg_tipo(KPI[onde])[0], texto, [KPI[c] for c in esq], None if dir_ is None else [KPI[c] for c in dir_])
                  for onde, texto, esq, dir_ in CHECAGENS_ESTACAO]
        abas.append(AbaByStep(
            ABA[f"bs_{sufixo}"], f"Meta por etapa da By Step · SPX D2D + FF D2D · {rotulo} · sem CB. Avg time step, "
            f"% Share e BWT por mês, tudo em fórmula sobre a aba {RAW_META}.",
            ["Etapa (KPI By Step)", "Leg", "Type"], [46, 13, 11], linhas, dados, regras, SEM_CHECAGEM_SOC,
            raw_meta, campos_meta, rota, "total_by_step", par=ABA[f"bs_antigo_{sufixo}"]))
    for rota, spm, sufixo, rotulo in [("rota_br", False, "br", "BR > BR"), ("rota_spm", True, "spm", "SPM > SPM")]:
        dados = dados_by_step_antiga(caminhos, spm=spm)
        linhas = [{"chave": col, "rotulos": [col, leg, tipo, status, "Hours"],
                   "obs": NOTA_FULL if col in FULL else (NOTA_NAO_TRANSBORDO if f"{col}_full" in FULL else ""),
                   "com_dado": True, "fora_da_soma": col in FULL}
                  for col, leg, tipo, status in ETAPAS_ANTIGAS]
        abas.append(AbaByStep(
            ABA[f"bs_antigo_{sufixo}"], f"Meta no formato do output antigo (steps bwt_*) · SPX D2D + FF D2D · {rotulo} · "
            f"sem CB. Mesma tabela do output antigo, tudo em fórmula sobre a aba {RAW_ANTIGA}.",
            ["Step", "Leg", "Type", "Status", "UOM"], [44, 16, 11, 46, 7], linhas, dados, CHECAGENS_ANTIGAS,
            SEM_CHECAGEM_ANTIGA, raw_antiga, campos_antiga, rota, "total_antiga", par=ABA[f"bs_{sufixo}"]))
    por_nome = {a.nome: a for a in abas}
    for a in abas:
        a.resultados(por_nome)
    return abas, [raw_meta, raw_antiga]


def _serial(mes):
    return (data_excel(mes) - _EXCEL_DIA0).days


def _consecutivos(meses):
    datas = [data_excel(m) for m in meses]
    return all((b.year - a.year) * 12 + b.month - a.month == 1 for a, b in zip(datas, datas[1:]))


def escrever_aba(livro, aba, abas, f, mestre):
    ws = livro.add_worksheet(aba.nome)
    n = len(aba.meses)
    fonte = (f"Source: aba {aba.raw.nome} (Rodagem de Malha 2.0). Recorte e linha de total vêm da aba Premissas. "
             "Linha 3 = todos os checks do mês OK? (checks no fim da aba)")
    topo(ws, f, mestre, aba.titulo, fonte, aba.n_falso, aba.rollup_ref() if n else None)
    for j, largura in enumerate(aba.larguras):
        ws.set_column(1 + j, 1 + j, largura)
    if not n:
        ws.write(L_CHECK, 1, "Sem pedidos neste recorte nesta rodada.", f.nota())
        return
    fmt_check = f.check()
    ws.write(L_CHECK, 1, "Todos os checks do mês OK?", f(bold=True))
    c_ini, c_fim = aba.faixa_checks()
    for k in range(n):
        col = aba.col(k, 1)
        ws.write_formula(L_CHECK, col, f"=COUNTIF({cel(c_ini, col)}:{cel(c_fim, col)},FALSE)=0", fmt_check,
                         aba.meses_ok[k])

    # faixa, meses e cabeçalho
    banda = f(bold=True, font_color="white", bg_color=COR["faixa"])
    for c0, largura_bloco, texto in [(aba.c0, 3 * n, "BWT por step (fórmulas)"),
                                     (aba.c_ped0, n, "Pedidos/dia que passam no step (SUMIFS na base)"),
                                     (aba.c_hor0, n, "Horas × pedidos/dia (SUMIFS na base)")]:
        for c in range(c0, c0 + largura_bloco):
            ws.write_blank(L_FAIXA, c, None, banda)
        ws.write(L_FAIXA, c0, texto, banda)
    # bordas: fio cinza no início de cada bloco (mês, observação, pedidos, horas); fio claro embaixo de cada linha
    seps = {aba.col(k, 0) for k in range(n)} | {aba.c_obs, aba.c_ped0, aba.c_hor0}
    colunas_tabela = (list(range(1, aba.c0 + 3 * n)) + [aba.c_obs] + [aba.col_ped(k) for k in range(n)]
                      + [aba.col_hor(k) for k in range(n)])

    def fd(c, total=False, **props):
        return f.dado(sep=c in seps, total=total, **props)

    def fundo_da_linha(r, total=False, **props):   # fio na linha inteira da tabela, inclusive nas células vazias
        for c in colunas_tabela:
            ws.write_blank(r, c, None, fd(c, total, **props))

    def fmt_mes_col(c):
        borda = {"left": 1, "left_color": COR["separador"]} if c in seps else {}
        return f(bold=True, bg_color=COR["mes"], num_format="mmm/yy", align="center", **borda)

    seguidos = _consecutivos(aba.meses)
    for k, mes in enumerate(aba.meses):
        col = aba.col(k, 0)
        if k and seguidos:
            ws.write_formula(L_MES, col, f"=EDATE({cel(L_MES, aba.col(k - 1, 0))},1)", fmt_mes_col(col), _serial(mes))
        else:
            ws.write_datetime(L_MES, col, data_excel(mes), fmt_mes_col(col))
        for c in [aba.col(k, 1), aba.col(k, 2), aba.col_ped(k), aba.col_hor(k)]:
            ws.write_formula(L_MES, c, f"={cel(L_MES, col)}", fmt_mes_col(c), _serial(mes))
    cab_in, cab_f = f.cabecalho(COR["cab_input"]), f.cabecalho(COR["cab_formula"], centro=True)
    ws.write_row(L_CAB, 1, aba.cabecalho, cab_in)
    for k in range(n):
        ws.write_row(L_CAB, aba.col(k, 0), ["Avg time step (h)", "% Share", "BWT (h)"], cab_f)
        ws.write(L_CAB, aba.col_ped(k), "Pedidos/dia", cab_f)
        ws.write(L_CAB, aba.col_hor(k), "Horas × pedidos/dia", cab_f)
    ws.write(L_CAB, aba.c_obs, "Observação", cab_in)
    ws.set_row(L_CAB, 30)

    # totais
    destaque = {"bold": True, "bg_color": COR["total"]}
    tot_h = lambda c, linha: fd(c, linha == L_CAMINHOS, num_format="#,##0.00", **destaque)
    tot_n = lambda c, linha: fd(c, linha == L_CAMINHOS, num_format="#,##0", **destaque)
    rotulos_tot = {L_SOMA: "BWT total (h) · soma dos steps", L_DIAS: "BWT total (dias)",
                   L_CAMINHOS: "BWT total (h) · direto dos caminhos"}
    for linha, texto in rotulos_tot.items():
        fundo_da_linha(linha, linha == L_CAMINHOS, **destaque)
        ws.write(linha, 1, texto, fd(1, linha == L_CAMINHOS, **destaque))
    fora = [aba.linha_de[l["chave"]] for l in aba.linhas if l["fora_da_soma"]]
    total_criterio = ref_premissa(aba.chave_total)
    for k in range(n):
        col = aba.col(k, 2)
        menos = f"-SUM({','.join(cel(r, col) for r in fora)})" if fora else ""
        ws.write_formula(L_SOMA, col, f"=SUM({cel(L_ETAPA0, col)}:{cel(aba.ultima, col)}){menos}",
                         tot_h(col, L_SOMA), aba.v[("soma", k)])
        ws.write_formula(L_DIAS, col, f"={cel(L_SOMA, col)}/{ref_premissa('horas_dia')}", tot_h(col, L_DIAS),
                         aba.v[("soma", k)] / 24)
        p, h = cel(L_CAMINHOS, aba.col_ped(k)), cel(L_CAMINHOS, aba.col_hor(k))
        ws.write_formula(L_CAMINHOS, col, f'=IF({p}=0,"",{h}/{p})', tot_h(col, L_CAMINHOS), aba.v[("caminhos", k)])
        ws.write_formula(L_CAMINHOS, aba.col_ped(k), aba.formula_sumifs(aba.campos_raw["pedidos"], k, total_criterio),
                         tot_n(aba.col_ped(k), L_CAMINHOS), aba.v[("tot_p", k)])
        ws.write_formula(L_CAMINHOS, aba.col_hor(k), aba.formula_sumifs(aba.campos_raw["horas"], k, total_criterio),
                         tot_n(aba.col_hor(k), L_CAMINHOS), aba.total("total_horas", aba.meses[k]))
    if fora:
        ws.write(L_SOMA, aba.c_obs, "As linhas With Transshipment repetem o BWT da Non-transshipment: ficam fora da soma.",
                 fd(aba.c_obs, italic=True, **destaque))

    # steps
    h2 = lambda c: fd(c, num_format="#,##0.00")
    pct = lambda c: fd(c, num_format="0.0%")
    n0 = lambda c: fd(c, num_format="#,##0")
    for l in aba.linhas:
        r = aba.linha_de[l["chave"]]
        fundo_da_linha(r)
        for j, rot in enumerate(l["rotulos"]):
            ws.write(r, 1 + j, rot, fd(1 + j))
        if l["obs"]:
            ws.write(r, aba.c_obs, l["obs"], fd(aba.c_obs, italic=True))
        if not l["com_dado"]:
            continue
        passo = xl_rowcol_to_cell(r, 1, col_abs=True)                     # step da coluna B
        for k in range(n):
            p, h = cel(r, aba.col_ped(k)), cel(r, aba.col_hor(k))
            t = xl_rowcol_to_cell(L_CAMINHOS, aba.col_ped(k), row_abs=True)   # pedidos/dia do recorte no mês
            avg, share, bwt = aba.v[(l["chave"], k)]
            ws.write_formula(r, aba.col(k, 0), f'=IF({p}=0,"",{h}/{p})', h2(aba.col(k, 0)), avg)
            ws.write_formula(r, aba.col(k, 1), f'=IF({t}=0,"",{p}/{t})', pct(aba.col(k, 1)), share)
            ws.write_formula(r, aba.col(k, 2), f'=IF({t}=0,"",{h}/{t})', h2(aba.col(k, 2)), bwt)
            ws.write_formula(r, aba.col_ped(k), aba.formula_sumifs(aba.campos_raw["pedidos"], k, passo),
                             n0(aba.col_ped(k)), aba.pedidos(l["chave"], k))
            ws.write_formula(r, aba.col_hor(k), aba.formula_sumifs(aba.campos_raw["horas"], k, passo),
                             n0(aba.col_hor(k)), aba._num("horas", l["chave"], aba.meses[k]))

    # checks
    ws.write(aba.titulo_estacao, 1, "Checks de estação · pedidos/dia (quem entra no step = quem é processado = quem sai)",
             f(bold=True))
    ws.write(aba.linha_sem_check, 1, aba.sem_check, f(italic=True))
    ws.write(aba.titulo_consistencia, 1, "Checks de consistência", f(bold=True))
    por_nome = {a.nome: a for a in abas}
    for i, chk in enumerate(aba.checks):
        for c in range(1, aba.c0 + 3 * n):
            ws.write_blank(chk["linha"], c, None, fd(c))
        ws.write(chk["linha"], 1, chk["texto"], fd(1))
        ws.write(chk["linha"], 2, chk["grupo"], fd(2, italic=True))
        for k in range(n):
            ws.write_formula(chk["linha"], aba.col(k, 1), aba.formula_check(chk, k, por_nome),
                             fd(aba.col(k, 1), italic=True, font_color=COR["check"], align="center"), aba.ok[(i, k)])
    realcar_falso(ws, f, L_CHECK, aba.c0, L_CHECK, aba.c0 + 3 * n - 1)
    realcar_falso(ws, f, c_ini, aba.c0, c_fim, aba.c0 + 3 * n - 1)

    ws.set_column(aba.c0, aba.c0 + 3 * n - 1, 11)
    ws.set_column(aba.c_obs - 1, aba.c_obs - 1, 2)
    ws.set_column(aba.c_obs, aba.c_obs, 60)
    ws.set_column(aba.c_obs + 1, aba.c_obs + 1, 2)
    ws.set_column(aba.c_ped0, aba.c_ped0 + n - 1, 13)
    ws.set_column(aba.c_hor0 - 1, aba.c_hor0 - 1, 2)
    ws.set_column(aba.c_hor0, aba.c_hor0 + n - 1, 16)
    ws.freeze_panes(L_CAB + 1, aba.c0)
