"""
Simulador de iniciativas: BWT do SPX D2D no último mês de meta da Initiatives (ex.: Nov/27), ligando e desligando
cada iniciativa.

Fonte: aba "Nov26-27" da planilha Initiatives BWT (a mesma de dados_reais/initiatives.csv). Na seção "SPX D2D",
cada etapa (leg) vem seguida das suas iniciativas, com o impacto em HORAS DA ETAPA em cada mês de meta.
A própria planilha monta a meta assim:  etapa no mês de meta = etapa no mês anterior + soma das iniciativas do mês.

Ponte do simulador (BWT = soma de % de pedidos × horas de cada etapa):
    real do último mês (soma das etapas)
  + mudança no % de pedidos por etapa (real → último mês de meta)
  + iniciativas ligadas (impacto na etapa somado em todos os meses de meta × % de pedidos da etapa no último mês)
  + ajustes nas etapas que nenhuma iniciativa explica
  = BWT simulado no último mês de meta. Com todas as iniciativas ligadas, dá a soma das etapas da Initiatives.
"""
import numpy as np
import pandas as pd

from .initiatives import D2D, DE_PARA, TOTAIS, _limpo, _numero, _rotulo, cabecalho

_COLUNAS_TEXTO = {"owner": "dono", "saving rationale": "racional"}


def _coluna_por_nome(g, cab):
    achadas = {}
    for j in range(g.shape[1]):
        nome = _limpo(g.iat[cab, j])
        if nome in _COLUNAS_TEXTO:
            achadas.setdefault(_COLUNAS_TEXTO[nome], j)
    return achadas


def _observacao(nome, wip, imp_b):
    obs = []
    if "feriad" in _limpo(nome):
        obs.append("Não é iniciativa: efeito dos feriados.")
    if wip:
        obs.append("Em parte marcada como WIP na planilha.")
    if not imp_b:
        obs.append("Impacto só no primeiro mês de meta.")
    return " ".join(obs)


def ler_simulador(grade):
    """
    Grade da aba Nov26-27 → dict com:
      resumo: meses, totais oficiais do SPX D2D (h) e a ponte real → último mês de meta
      etapas: uma linha por etapa (% de pedidos e horas: real, metas, ajuste sem iniciativa)
      iniciativas: uma linha por iniciativa × etapa, com o impacto (h na etapa) em cada mês de meta e no BWT
    """
    g = grade.fillna("").astype(str)
    cab, colunas = cabecalho(g)
    metas = sorted((mes, j_h, j_s) for j_h, j_s, mes, tipo in colunas if tipo == "Target")
    reais = sorted((mes, j_h, j_s) for j_h, j_s, mes, tipo in colunas if tipo == "Actuals")
    if len(metas) < 2 or not reais:
        return None
    (mes_a, ha, _), (mes_b, hb, sb) = metas[0], metas[-1]
    mes_r, hr, sr = reais[-1]
    texto = _coluna_por_nome(g, cab)
    pernas = {_limpo(nome): (nome, kpis) for nome, kpis, _ in DE_PARA}
    total_chave = next(_limpo(chave) for chave, canal, _ in TOTAIS if canal == D2D)
    inicio = next((i for i in range(cab + 1, len(g)) if _limpo(g.iat[i, 2]) == _limpo(D2D)
                   and not g.iat[i, 3].strip()), None)
    total = next((i for i in range(cab + 1, len(g)) if _limpo(g.iat[i, 2]) == total_chave), None)
    if inicio is None or total is None:
        return None

    etapas, iniciativas, atual = [], [], None
    for i in range(inicio + 1, len(g)):
        status = g.iat[i, 3].strip()
        if _limpo(status) in pernas:
            atual, kpis = pernas[_limpo(status)]
            etapas.append({"etapa": atual, "kpis": " + ".join(kpis),
                           "share_r": _numero(g.iat[i, sr]), "share_b": _numero(g.iat[i, sb]),
                           "real_h": _numero(g.iat[i, hr]), "meta_a_h": _numero(g.iat[i, ha]),
                           "meta_b_h": _numero(g.iat[i, hb])})
        elif atual and status and _limpo(status) != "true":
            bruto = [g.iat[i, j_h].strip() for _, j_h, _ in metas]
            impactos = [_numero(b) for b in bruto]
            wip = any("wip" in _limpo(b) for b in bruto)
            if all(np.isnan(v) or v == 0 for v in impactos) and not wip:
                continue   # linha sem impacto em nenhum mês
            imp_a, imp_b = impactos[0], impactos[-1]
            iniciativas.append({"etapa": atual, "iniciativa": status,
                                "dono": g.iat[i, texto["dono"]].strip() if "dono" in texto else "",
                                "impacto_a_h": imp_a, "impacto_b_h": imp_b,
                                "impacto_total_h": float(np.nansum(impactos)),
                                "observacao": _observacao(status, wip, imp_b if not np.isnan(imp_b) else 0),
                                "racional": g.iat[i, texto["racional"]].strip() if "racional" in texto else ""})
    etapas = pd.DataFrame(etapas).drop_duplicates("etapa").reset_index(drop=True)
    if etapas.empty:
        return None
    iniciativas = pd.DataFrame(iniciativas, columns=["etapa", "iniciativa", "dono", "impacto_a_h", "impacto_b_h",
                                                     "impacto_total_h", "observacao", "racional"])
    for c in ["share_r", "share_b"]:
        etapas[c] = etapas[c].fillna(0)
    share_b = etapas.set_index("etapa")["share_b"]
    iniciativas["share_b"] = iniciativas["etapa"].map(share_b)
    iniciativas["impacto_bwt_h"] = iniciativas["impacto_total_h"] * iniciativas["share_b"]
    soma_ini = iniciativas.groupby("etapa")["impacto_total_h"].sum()
    etapas["ajuste_h"] = etapas["meta_b_h"] - etapas["real_h"] - etapas["etapa"].map(soma_ini).fillna(0)

    soma_r = float((etapas["share_r"] * etapas["real_h"]).sum())
    soma_b = float((etapas["share_b"] * etapas["meta_b_h"]).sum())
    resumo = {"mes_real": mes_r, "mes_a": mes_a, "mes_b": mes_b,
              "total_real_h": _numero(g.iat[total, hr]) * 24, "total_a_h": _numero(g.iat[total, ha]) * 24,
              "total_b_h": _numero(g.iat[total, hb]) * 24,
              "soma_real_h": soma_r, "soma_b_h": soma_b,
              "mix_h": float(((etapas["share_b"] - etapas["share_r"]) * etapas["real_h"]).sum()),
              "iniciativas_h": float(iniciativas["impacto_bwt_h"].sum()),
              "ajustes_h": float((etapas["share_b"] * etapas["ajuste_h"]).sum())}
    return {"resumo": resumo, "etapas": etapas, "iniciativas": iniciativas}


def bwt_simulado(sim, desligadas=()):
    """BWT (h) do último mês de meta, pela soma das etapas, com as iniciativas desligadas (índices da tabela)."""
    volta = sim["iniciativas"].loc[list(desligadas), "impacto_bwt_h"].sum() if len(desligadas) else 0.0
    return sim["resumo"]["soma_b_h"] - volta


def rotulos(resumo):
    return {k: _rotulo(resumo[k]) for k in ["mes_real", "mes_a", "mes_b"]}
