"""
Especificação das abas de tabela do Excel de saída (excel_padrao.Tabela): quais colunas são número da rodagem
(input, cabeçalho verde), quais são fórmula (cabeçalho cinza escuro) e o check de cada coluna na linha 3.
Regra: o que dá para calcular no Excel a partir de outras células vira fórmula; a célula só fica com número quando a
fórmula não reproduz a rodagem (exceção da regra), e a descrição da aba avisa.
"""
import pandas as pd

from .calculo.by_step import CANAIS, ETAPAS_BY_STEP, observacao, ordem_by_step
from .excel_padrao import ABA, COR, VALOR_PREMISSA, Coluna, Tabela

TOTAL_PONTE = "BWT total"
# Cabeçalhos da aba de rotas: nome claro · nome da coluna no output antigo ([T] 4.1)
TITULO_ROTAS = {
    "period_start": "Mês", "Route": "Rota", "Origin": "Origem", "Dest": "Destino", "route_type": "Tipo de rota",
    "ADO": "Pedidos/dia", "Distance": "Distância (km)",
    "Final Pck-LHTr": "Saída + carregamento (h) · Final Pck-LHTr", "Pck-LHTr": "Espera para sair (h) · Pck-LHTr",
    "Raw Pck-LHTr": "Espera bruta (h) · Raw Pck-LHTr", "Loading": "Carregamento (h) · Loading",
    "TTFinal": "Tempo total da rota (h) · TTFinal", "LHExpress Ident.": "Expressa? · LHExpress Ident.",
    "TT Calc.": "Viagem pela fórmula (h) · TT Calc.", "TT with Express": "Viagem usada (h) · TT with Express",
    "TT Queue and Unloading": "Fila e descarga no destino (h) · TT Queue and Unloading",
    "Total Vehicles": "Veículos · Total Vehicles", "N Carretas": "Carretas", "N Truck": "Trucks",
    "N Others": "Outros veículos", "carreta_cap": "Capacidade carreta", "truck_cap": "Capacidade truck",
    "others_cap": "Capacidade outros", "fonte_tt": "De onde vem a viagem", "fonte_fila": "De onde vem a fila",
}


def _num(df, colunas):
    for c in colunas:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _menos(a, b):
    return lambda r: None if r[a] is None or r[b] is None else r[a] - r[b]


def _divide(n, d):
    return lambda r: r[n] / r[d] if r[n] is not None and r[d] else None


def num(titulo, campo, fmt="#,##0.00", largura=12, **kw):
    return Coluna(titulo, campo, "input", fmt=fmt, largura=largura, **kw)


def txt(titulo, campo, largura=14):
    return Coluna(titulo, campo, "texto", largura=largura)


def fx(titulo, campo, formula, py=None, fmt="#,##0.00", largura=12, **kw):
    return Coluna(titulo, campo, "formula", formula=formula, py=py, fmt=fmt, largura=largura, **kw)


def _cap(titulo, unidade=""):
    """Cabeçalho padrão: primeira letra maiúscula e unidade no fim (se ainda não tiver)."""
    t = titulo[:1].upper() + titulo[1:]
    return f"{t} {unidade}" if unidade and not t.endswith(unidade) else t


def _dif(a, b):
    return f'=IF(OR({{{a}}}="",{{{b}}}=""),"",{{{a}}}-{{{b}}})'


# ---------------- Resumo ----------------
def tabela_resumo(resumo, raw_antiga):
    d = _num(resumo.copy(), ["pedidos_dia", "caminhos", "bwt_horas", "bwt_dias"])
    d["h_x_ado"] = d["bwt_horas"] * d["pedidos_dia"]
    brasil = VALOR_PREMISSA["regiao_brasil"]
    # cada BRASIL logo acima das regiões do mesmo mês e canal (o fio de total fecha o bloco)
    d = d.assign(_regiao=d["região"] != brasil).sort_values(["mês", "canal", "_regiao", "região"])          .drop(columns="_regiao").reset_index(drop=True)
    regioes = d[d["região"] != brasil].groupby(["mês", "canal"])[["pedidos_dia", "caminhos", "h_x_ado"]].sum()

    def soma_regioes(campo):
        modelo = ("=SUMIFS({R:" + campo + "},{R:mês},{mês},{R:canal},{canal},{R:região},\"<>\"&{P:regiao_brasil})")

        def py(r):
            if r["região"] != brasil:
                return r[campo]
            chave = (r["mês"], r["canal"])
            return regioes.at[chave, campo] if chave in regioes.index else None
        return (lambda r: modelo if r["região"] == brasil else None), py

    f_ped, py_ped = soma_regioes("pedidos_dia")
    f_cam, py_cam = soma_regioes("caminhos")
    f_hxa, py_hxa = soma_regioes("h_x_ado")
    ra = raw_antiga
    total_raw = (f"SUMIFS({ra.rng('pedidos', True)},{ra.rng('recorte', True)},{{P:rota_br}},"
                 f"{ra.rng('step', True)},{{P:total_antiga}})")
    total_brasil = "SUMIFS({R},{R:região},{P:regiao_brasil})"
    raw = ra.df[(ra.df["recorte"] == VALOR_PREMISSA["rota_br"]) & (ra.df["step"] == VALOR_PREMISSA["total_antiga"])]
    ok_cruzado = abs(d.loc[d["região"] == brasil, "pedidos_dia"].sum() - raw["pedidos"].sum()) <= \
        1e-6 * max(1.0, raw["pedidos"].sum())
    return Tabela(ABA["resumo"], d, [
        Coluna("Mês", "mês", "input", data=True, check=None),
        txt("Canal", "canal", 18), txt("Região", "região", 16),
        Coluna("Pedidos/dia", "pedidos_dia", "input", formula=f_ped, py=py_ped, fmt="#,##0", largura=14,
               check=f"=ABS({total_brasil}-{total_raw})<={{P:tolerancia}}*MAX(1,ABS({total_brasil}),ABS({total_raw}))",
               check_valor=ok_cruzado),
        Coluna("Caminhos", "caminhos", "input", formula=f_cam, py=py_cam, fmt="#,##0", largura=11),
        Coluna("Horas × pedidos/dia", "h_x_ado", "input", formula=f_hxa, py=py_hxa, fmt="#,##0", largura=16),
        fx("BWT (h)", "bwt_horas", '=IF(N({pedidos_dia})=0,"",{h_x_ado}/{pedidos_dia})', _divide("h_x_ado", "pedidos_dia"),
           check="=AND(SUMPRODUCT(--ISERROR({R}))=0,MAX({R})<={P:max_bwt_h})",
           check_valor=bool(d["bwt_horas"].max() <= VALOR_PREMISSA["max_bwt_h"])),
        fx("BWT (dias)", "bwt_dias", '=IF({bwt_horas}="","",{bwt_horas}/{P:horas_dia})',
           lambda r: None if r["bwt_horas"] is None else r["bwt_horas"] / VALOR_PREMISSA["horas_dia"]),
    ], "BWT médio por mês, canal e região, ponderado pelos pedidos/dia: BWT = horas × pedidos/dia ÷ pedidos/dia. "
       "Linhas BRASIL (em cinza) = soma das regiões do mesmo mês e canal.",
       f"Source: Rodagem de Malha 2.0 (BWT por caminho). Check de pedidos/dia: total BRASIL = aba {ABA['raw_antiga']} "
       "(BR, TOTAL caminhos).",
       congelar=3, linhas_total=list(d.index[d["região"] == brasil]),
       o_que_confere="Sem erro/negativo; pedidos/dia BRASIL = base dos steps; BWT ≤ máximo (Premissas)")


# ---------------- Rodagem x Initiatives x Real ----------------
def tabela_tres_visoes(t):
    titulos = list(t.columns)
    chaves = ["etapa", "kpi", "canal", "meta_rod", "meta_ini", "real_m", "real_m1", "real_ini", "rod_ini", "real_rod",
              "pct_rod", "pct_ini", "obs"]
    d = _num(t.copy().set_axis(chaves, axis=1), chaves[3:12])
    t = [_cap(x, "(h)") if 3 <= i <= 9 else _cap(x) for i, x in enumerate(titulos)]
    return Tabela(ABA["tres_visoes"], d, [
        txt(t[0], "etapa", 36), txt(t[1], "kpi", 12), txt(t[2], "canal", 16),
        num(t[3], "meta_rod"), num(t[4], "meta_ini"), num(t[5], "real_m"), num(t[6], "real_m1"), num(t[7], "real_ini"),
        fx(t[8], "rod_ini", _dif("meta_rod", "meta_ini"), _menos("meta_rod", "meta_ini")),
        fx(t[9], "real_rod", _dif("real_m", "meta_rod"), _menos("real_m", "meta_rod")),
        num(t[10], "pct_rod", fmt="0.0%", escala=0.01), num(t[11], "pct_ini", fmt="0.0%", escala=0.01),
        txt(t[12], "obs", 70),
    ], "Por etapa (Brasil, BR - BR): meta da Rodagem | meta da Initiatives | realizado da By Step. As diferenças são "
       "fórmula. O mês atual do realizado é parcial.",
       "Source: meta = Rodagem de Malha 2.0; meta Initiatives = aba Nov26-27 da Initiatives; realizado = By Step "
       "(dev_brbi_opslgc.joao_bwt_by_step_mece)", congelar=3,
       o_que_confere="Sem erro/negativo nas metas e realizados; diferenças sem erro")


# ---------------- Ponte do BWT ----------------
def tabela_ponte(p):
    titulos = [_cap(x) for x in p.columns]
    chaves = ["comp", "canal", "etapa", "real", "meta", "sr", "sm", "mais", "tempo", "pedidos", "leitura", "obs"]
    d = _num(p.copy().set_axis(chaves, axis=1), ["real", "meta", "sr", "sm", "mais", "tempo", "pedidos"])
    totais = list(d.index[d["etapa"] == TOTAL_PONTE])
    fim = {i: (totais[j + 1] - 1 if j + 1 < len(totais) else len(d) - 1) for j, i in enumerate(totais)}
    fim = {i: f for i, f in fim.items() if f > i}   # bloco com pelo menos uma linha abaixo do total
    d["fecha"] = [abs(d.at[i, "mais"] - d.loc[i + 1:fim[i], "mais"].sum()) <= VALOR_PREMISSA["ponte_resto"]
                  if i in fim else None for i in d.index]
    parte = lambda r: r["etapa"] != TOTAL_PONTE and (r["sr"] is not None or r["sm"] is not None)
    z = lambda v: v or 0.0
    return Tabela(ABA["ponte"], d, [
        txt(titulos[0], "comp", 40), txt(titulos[1], "canal", 16), txt(titulos[2], "etapa", 40),
        num(titulos[3], "real"), num(titulos[4], "meta"),
        num(titulos[5], "sr", fmt="0.0%", escala=0.01), num(titulos[6], "sm", fmt="0.0%", escala=0.01),
        fx(titulos[7], "mais",
           lambda r: "={real}-{meta}" if r["etapa"] == TOTAL_PONTE else ("={tempo}+{pedidos}" if parte(r) else None),
           lambda r: (r["real"] - r["meta"]) if r["etapa"] == TOTAL_PONTE else (z(r["tempo"]) + z(r["pedidos"])
                                                                               if parte(r) else r["mais"]), largura=14),
        fx(titulos[8], "tempo", lambda r: "=(N({real})-N({meta}))*N({sr})" if parte(r) else None,
           lambda r: (z(r["real"]) - z(r["meta"])) * z(r["sr"]) if parte(r) else r["tempo"], largura=14),
        fx(titulos[9], "pedidos", lambda r: "=N({meta})*(N({sr})-N({sm}))" if parte(r) else None,
           lambda r: z(r["meta"]) * (z(r["sr"]) - z(r["sm"])) if parte(r) else r["pedidos"], largura=14),
        Coluna("Fecha? (total = soma das linhas)", "fecha", "check",
               formula=lambda r: ("=ABS({mais}-SUM({RL:mais:" + f"{r['_i'] + 1}:{fim[r['_i']]}" + "}))<={P:ponte_resto}")
               if r["_i"] in fim else None, largura=12,
               check="=COUNTIF({R},FALSE)=0", check_valor=all(v is not False for v in d.loc[totais, "fecha"])),
        txt(titulos[10], "leitura", 60), txt(titulos[11], "obs", 50),
    ], "Quanto cada etapa precisa cair do real até a meta: horas a mais = porque demorou mais [(Real − Meta) × % real] "
       "+ porque passaram mais pedidos [Meta × (% real − % meta)]. Linha 'BWT total' = Real − Meta. As linhas 'sem meta' "
       "e 'resto' vêm da rodagem.",
       "Source: meta = Rodagem de Malha 2.0; real = By Step (joao_bwt_by_step_mece). 'fecha?' confere total = soma "
       "das linhas do bloco (diferença aceita na aba Premissas).",
       congelar=3, linhas_total=totais,
       o_que_confere="Sem erro/negativo nos tempos; cada bloco fecha: horas a mais do total = soma das etapas")


# ---------------- Onde atacar ----------------
def tabela_onde_atacar(a):
    t = [_cap(x) for x in a.columns]   # posição, o que, onde, pacotes, meta, real, fonte, acima, efeito, pedidos
    d = _num(a.copy().set_axis(["pos", "oque", "onde", "pacotes", "meta", "real", "fonte", "acima", "efeito",
                                "pedidos"], axis=1), ["pos", "pacotes", "meta", "real", "acima", "efeito", "pedidos"])
    return Tabela(ABA["onde_atacar"], d, [
        num(t[0], "pos", fmt="0", largura=8), txt(t[1], "oque", 40), txt(t[2], "onde", 24),
        num(t[3], "pacotes", fmt="#,##0", largura=14), num(t[4], "meta"), num(t[5], "real"), txt(t[6], "fonte", 30),
        num(t[9], "pedidos", fmt="#,##0", largura=16),
        fx(t[7], "acima", _dif("real", "meta"), _menos("real", "meta")),
        fx(t[8], "efeito", '=IF(OR({acima}="",N({pedidos})=0),"",{acima}*{pacotes}/{pedidos})',
           lambda r: r["acima"] * r["pacotes"] / r["pedidos"] if r["acima"] is not None and r["pedidos"] else None,
           fmt="#,##0.000", largura=14),
    ], "Rotas (estrada) e SOCs (fila de recebimento) que mais puxam o BWT para cima: efeito no BWT Brasil = horas "
       "acima da meta × pacotes ÷ pedidos/dia do Brasil no mês.",
       f"Source: aba {ABA['rotas_x_real']} (meta e real por rota) e By Step realizado (pedidos Brasil)", congelar=3,
       o_que_confere="Sem erro/negativo; acima e efeito sem erro")


# ---------------- Regra x Real ----------------
def tabela_regra_x_real(c):
    t = [_cap(x) for x in c.columns]
    d = _num(c.copy().set_axis(["mes", "oque", "grupo", "rotas", "pacotes", "meta", "real", "dif", "acima", "abaixo",
                                "leitura"], axis=1), ["rotas", "pacotes", "meta", "real", "dif", "acima", "abaixo"])
    return Tabela(ABA["regra"], d, [
        Coluna(t[0], "mes", "input", data=True, check=None), txt(t[1], "oque", 44), txt(t[2], "grupo", 30),
        num(t[3], "rotas", fmt="#,##0", largura=8), num(t[4], "pacotes", fmt="#,##0", largura=14),
        num(t[5], "meta"), num(t[6], "real"),
        fx(t[7], "dif", _dif("real", "meta"), _menos("real", "meta")),
        num(t[8], "acima", fmt="0.0%", escala=0.01, largura=14), num(t[9], "abaixo", fmt="0.0%", escala=0.01, largura=14),
        txt(t[10], "leitura", 70),
    ], "A meta erra sempre para o mesmo lado? Real × meta das rotas agrupado pela regra que deu o tempo, pelo tipo de "
       "rota e pela distância (médias ponderadas pelos pacotes reais). real − meta é fórmula.",
       f"Source: aba {ABA['rotas_x_real']}", congelar=3, o_que_confere="Sem erro/negativo; real − meta sem erro")


# ---------------- Meta x Realizado ----------------
def tabela_meta_x_realizado(m):
    d = _num(m.copy(), ["meta_h", "real_h", "dif_h", "bwt_d_meta", "bwt_d_real", "bwt_n_meta", "bwt_n_real"])
    return Tabela(ABA["meta_x_real"], d, [
        Coluna("Mês", "attempt_month", "input", data=True, check=None),
        txt("Canal", "spx_channel", 16), txt("Rota macro", "main_route", 18), txt("Etapa (KPI By Step)", "kpi", 42),
        txt("Situação", "situacao", 14),
        num("Horas × pedidos/dia meta", "bwt_n_meta", fmt="#,##0", largura=16),
        num("Pedidos/dia meta", "bwt_d_meta", fmt="#,##0", largura=14),
        num("Horas × pedidos/dia real", "bwt_n_real", fmt="#,##0", largura=16),
        num("Pedidos/dia real", "bwt_d_real", fmt="#,##0", largura=14),
        fx("Meta (h)", "meta_h", '=IF(N({bwt_d_meta})=0,"",{bwt_n_meta}/{bwt_d_meta})', _divide("bwt_n_meta", "bwt_d_meta")),
        fx("Real (h)", "real_h", '=IF(N({bwt_d_real})=0,"",{bwt_n_real}/{bwt_d_real})', _divide("bwt_n_real", "bwt_d_real")),
        fx("Real − meta (h)", "dif_h", _dif("real_h", "meta_h"), _menos("real_h", "meta_h")),
    ], "Meta e realizado por etapa no mesmo recorte (mês × canal × rota macro × KPI): média = horas × pedidos ÷ pedidos. "
       "real − meta > 0 = realizado acima da meta.",
       f"Source: meta = Rodagem de Malha 2.0 ({ABA['raw_meta']}); realizado = By Step (joao_bwt_by_step_mece)",
       congelar=4, o_que_confere="Sem erro/negativo nas somas; médias e diferença sem erro")


# ---------------- Meta By Step (Brasil) ----------------
def tabela_meta_by_step(meta, raw_meta):
    m = _num(meta.copy(), ["bwt_n", "bwt_d"])
    br = m[m["main_route"] == VALOR_PREMISSA["rota_br"]]
    meses = sorted(br["attempt_month"].unique())
    media = (br.groupby(["kpi", "spx_channel", "attempt_month"])["bwt_n"].sum()
             / br.groupby(["kpi", "spx_channel", "attempt_month"])["bwt_d"].sum())
    kpis = sorted(set(br["kpi"]) | set(ETAPAS_BY_STEP), key=ordem_by_step)
    linhas = []
    for k in kpis:
        tem = any(k == x[0] for x in media.index)
        for canal in CANAIS.values():
            linha = {"kpi": k, "canal": canal, "obs": observacao(k, tem)}
            for j, mes in enumerate(meses):
                v = media.get((k, canal, mes))
                linha[f"m{j}"] = None if v is None or pd.isna(v) else float(v)
            linhas.append(linha)
    d = pd.DataFrame(linhas)
    r = raw_meta
    criterios = (f"{r.rng('attempt_month', True)},{{H:#}},{r.rng('spx_channel', True)},{{canal}},"
                 f"{r.rng('main_route', True)},{{P:rota_br}},{r.rng('kpi', True)},{{kpi}}")
    colunas = [txt("Etapa (KPI By Step)", "kpi", 44), txt("Canal", "canal", 16)]
    for j, mes in enumerate(meses):
        crit = criterios.replace("#", f"m{j}")
        colunas.append(fx(mes, f"m{j}", f'=IFERROR(SUMIFS({r.rng("bwt_n", True)},{crit})/'
                                        f'SUMIFS({r.rng("bwt_d", True)},{crit}),"")', titulo_data=mes,
                          check="=AND(SUMPRODUCT(--ISERROR({R}))=0,MAX({R})<={P:max_etapa_h})",
                          check_valor=bool(d[f"m{j}"].max() <= VALOR_PREMISSA["max_etapa_h"])))
    colunas.append(txt("Observação", "obs", 70))
    return Tabela(ABA["bs_canal"], d, colunas,
                  "Meta de cada etapa no formato da By Step (Brasil, BR - BR), por canal e mês: média = SUMIFS das horas "
                  f"÷ SUMIFS dos pedidos na aba {ABA['raw_meta']}. Etapa sem meta fica vazia; a 'Observação' diz por quê.",
                  f"Source: aba {ABA['raw_meta']} (Rodagem de Malha 2.0). Rota do recorte na aba Premissas.",
                  congelar=2, o_que_confere="Sem erro; nenhuma etapa acima do máximo de horas (Premissas)")


# ---------------- Rotas meta x real ----------------
def tabela_rotas_x_real(x):
    numericas = ["pedidos_dia_meta", "real_pacotes", "km", "meta_viagem_h", "meta_fila_h", "meta_total_h",
                 "real_estrada_h", "real_fila_h", "real_total_h", "real_mediana_h", "dif_estrada_h", "dif_fila_h",
                 "dif_total_h"]
    d = _num(x.copy(), numericas)
    soma_meta = lambda r: None if r["meta_viagem_h"] is None else r["meta_viagem_h"] + (r["meta_fila_h"] or 0.0)
    tab = Tabela(ABA["rotas_x_real"], d, [
        Coluna("Mês", "mes", "input", data=True, check=None), txt("Rota", "rota", 30), txt("Tipo de rota", "tipo", 10),
        txt("Situação", "situacao", 30),
        num("Pedidos/dia meta", "pedidos_dia_meta", fmt="#,##0", largura=12),
        num("Pacotes real", "real_pacotes", fmt="#,##0", largura=12),
        num("Distância (km)", "km", fmt="#,##0", largura=9),
        txt("De onde vem a viagem", "fonte_tempo", 22), txt("De onde vem a fila", "fonte_fila", 22),
        num("Meta viagem (h)", "meta_viagem_h"), num("Meta fila (h)", "meta_fila_h"),
        fx("Meta total (h)", "meta_total_h", '=IF({meta_viagem_h}="","",{meta_viagem_h}+N({meta_fila_h}))', soma_meta),
        num("Real estrada (h)", "real_estrada_h"), num("Real fila (h)", "real_fila_h"),
        num("Real total (h)", "real_total_h"), num("Real mediana (h)", "real_mediana_h"),
        fx("Real − meta estrada (h)", "dif_estrada_h", _dif("real_estrada_h", "meta_viagem_h"),
           _menos("real_estrada_h", "meta_viagem_h")),
        fx("Real − meta fila (h)", "dif_fila_h", '=IF({real_fila_h}="","",{real_fila_h}-N({meta_fila_h}))',
           lambda r: None if r["real_fila_h"] is None else r["real_fila_h"] - (r["meta_fila_h"] or 0.0)),
        fx("Real − meta total (h)", "dif_total_h", _dif("real_total_h", "meta_total_h"), _menos("real_total_h", "meta_total_h")),
    ], "", f"Source: meta = aba {ABA['rotas']}; real = tempo real por rota (consultas/lh_real_por_rota.sql)",
        congelar=2,
        o_que_confere="Sem erro/negativo nos tempos e pacotes; contas sem erro")
    tab.descricao = ("Meta × real de cada rota, separando estrada (saiu → chegou) e fila (chegou → recebido). Meta total = "
                     "viagem + fila; real − meta > 0 = real acima da meta."
                     + (f" Linhas com número na 'meta total': {tab.excecoes['meta_total_h']} (tempo fixo, ex.: "
                        "SOC-SP6>HUB-LAM-02 com 47h)." if tab.excecoes.get("meta_total_h") else ""))
    return tab


# ---------------- Rotas ----------------
def tabela_rotas(rotas):
    texto = {"period_start", "Route", "Origin", "Dest", "route_type", "LHExpress Ident.", "fonte_tt", "fonte_fila"}
    d = _num(rotas.copy(), [c for c in rotas.columns if c not in texto])
    soma = lambda *cs: (lambda r: None if any(r[c] is None for c in cs) else sum(r[c] for c in cs))
    modelo = lambda *cs: ("=IF(OR(" + ",".join("{" + c + "}=\"\"" for c in cs) + "),\"\","
                          + "+".join("{" + c + "}" for c in cs) + ")")
    colunas = []
    for c in rotas.columns:
        t = TITULO_ROTAS.get(c, c)
        if c == "period_start":
            colunas.append(Coluna(t, c, "input", data=True, check=None))
        elif c in texto:
            colunas.append(txt(t, c, 28 if c in ("Route", "fonte_tt", "fonte_fila") else 14))
        elif c == "Final Pck-LHTr":
            colunas.append(fx(t, c, modelo("Pck-LHTr", "Loading"), soma("Pck-LHTr", "Loading"), largura=16))
        elif c == "TTFinal":
            colunas.append(fx(t, c, modelo("TT with Express", "TT Queue and Unloading"),
                              soma("TT with Express", "TT Queue and Unloading"), largura=16))
        elif c == "Total Vehicles":
            colunas.append(fx(t, c, modelo("N Carretas", "N Truck", "N Others"),
                              soma("N Carretas", "N Truck", "N Others")))
        else:
            colunas.append(num(t, c, fmt="#,##0" if c in ("ADO", "Distance") else "#,##0.00", largura=14))
    tab = Tabela(ABA["rotas"], d, colunas, "", "Source: Rodagem de Malha 2.0 (etapas 2 e 3: tempo de viagem, fila, "
                 "veículos e saída de cada rota)", congelar=2,
                 o_que_confere="Sem erro/negativo nos números; TTFinal, Final Pck-LHTr e Total Vehicles sem erro")
    exc = tab.excecoes.get("TTFinal", 0)
    tab.descricao = ("Uma linha por rota e mês: veículos, espera para sair, viagem, fila e de onde veio a viagem "
                     "e a fila. Depois do '·' fica o nome da coluna no output antigo ([T] 4.1). Fórmulas: tempo total = "
                     "viagem usada + fila e descarga; saída + carregamento = espera para sair + carregamento; "
                     "veículos = carretas + trucks + outros."
                     + (f" {exc} linha(s) de tempo total com número: tempo fixo (ex.: SOC-SP6>HUB-LAM-02 = 47h, [TEMP])."
                        if exc else ""))
    return tab


# ---------------- Checagens ----------------
def tabela_checagens(chk):
    d = _num(chk.copy(), ["qtd"])
    sem_erro = not (d["nivel"] == VALOR_PREMISSA["nivel_erro"]).any()
    return Tabela(ABA["checagens"], d, [
        txt("Fase", "fase", 11), txt("Input", "input", 20), txt("Checagem", "checagem", 44),
        Coluna("Nível", "nivel", "texto", largura=8, check="=COUNTIF({R},{P:nivel_erro})=0", check_valor=sem_erro),
        num("Qtd", "qtd", fmt="#,##0", largura=8), txt("Exemplos", "exemplos", 60), txt("O que fazer", "o_que_fazer", 80),
    ], "Conferências dos inputs e dos resultados feitas pela rodagem. ERRO para a rodagem; AVISO é ponto de atenção.",
       "Source: Rodagem de Malha 2.0 (malha/checagens.py)", COR["aba_checagens"], congelar=3,
       o_que_confere="Nenhuma checagem com ERRO")
