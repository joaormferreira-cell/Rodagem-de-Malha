"""
Checagens de qualidade: conferem os INPUTS antes de calcular e os RESULTADOS depois.
Não mudam nenhum número; só dizem o que está errado ou merece atenção, em português, com exemplos.

Níveis:
  ERRO  → o resultado sairia errado ou a rodagem quebraria. A rodagem para.
  AVISO → roda, mas é ponto de atenção (ex.: estação sem meta usa a média).
  OK    → conferido, sem problema.
"""
import re

import numpy as np
import pandas as pd

from .calculo.initiatives import _rotulo
from .calculo.malha import COLUNAS_DISTANCIA
from .configuracao import fontes

ERRO, AVISO, OK = "ERRO", "AVISO", "OK"
LIMITE_LAT = (-34.5, 5.5)       # Brasil
LIMITE_LON = (-74.5, -28.5)
MAX_HORAS_ETAPA = 240           # meta de uma etapa acima de 10 dias é suspeita
MAX_BWT_TOTAL = 720             # BWT de um caminho acima de 30 dias é suspeito
_MES = re.compile(r"^\d{4}-\d{2}-01$")


class Relatorio:
    def __init__(self):
        self.linhas = []

    def add(self, fase, input_, checagem, nivel, qtd=0, exemplos=(), acao=""):
        self.linhas.append({"fase": fase, "input": input_, "checagem": checagem, "nivel": nivel,
                            "qtd": int(qtd), "exemplos": ", ".join(str(e) for e in list(exemplos)[:5]),
                            "o_que_fazer": acao})

    def conferir(self, fase, input_, checagem, problemas, nivel, acao):
        """problemas = lista/Series com o que está errado. Vazio → OK."""
        problemas = list(problemas)
        self.add(fase, input_, checagem, nivel if problemas else OK, len(problemas), problemas, acao if problemas else "")

    def tabela(self):
        return pd.DataFrame(self.linhas, columns=["fase", "input", "checagem", "nivel", "qtd", "exemplos", "o_que_fazer"])

    def tem_erro(self):
        return any(l["nivel"] == ERRO for l in self.linhas)

    def imprimir(self):
        t = self.tabela()
        n = t["nivel"].value_counts()
        print(f"\nChecagens: {n.get(OK, 0)} OK | {n.get(AVISO, 0)} aviso(s) | {n.get(ERRO, 0)} erro(s)")
        for _, l in t[t["nivel"] != OK].sort_values("nivel").iterrows():
            print(f"  [{l['nivel']}] {l['input']}: {l['checagem']} ({l['qtd']}) ex.: {l['exemplos']}")
            print(f"          → {l['o_que_fazer']}")


# ---------------- ajudantes ----------------
def _preenchido(s):
    return s.notna() & s.astype(str).str.strip().ne("")


def _nao_numerico(s):
    """Células preenchidas que não são número (ex.: '1,5', 'n/a', '#REF!')."""
    s = s.astype(str).str.strip()
    return s[_preenchido(s) & pd.to_numeric(s, errors="coerce").isna()].unique()


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _faltam_colunas(df, colunas):
    return [c for c in colunas if c not in df.columns]


# ---------------- inputs ----------------
def checar_inputs(e, rel=None):
    rel = rel or Relatorio()
    f = "inputs"

    # demanda
    d = e["demanda"]
    falta = _faltam_colunas(d, ["period_start", "origin", "destination", "path", "forecast_ado"])
    rel.conferir(f, "demanda", "colunas obrigatórias", falta, ERRO, "Exportar a demanda com todas as colunas.")
    if not falta:
        rel.conferir(f, "demanda", "data do mês inválida", d.loc[pd.to_datetime(d["period_start"], errors="coerce").isna(),
                                                                "period_start"].unique(), ERRO,
                     "period_start precisa ser data (AAAA-MM-DD).")
        rel.conferir(f, "demanda", "pedidos/dia (ADO) não numérico", _nao_numerico(d["forecast_ado"]), ERRO,
                     "Corrigir o forecast_ado na base de demanda.")
        ado = _num(d["forecast_ado"])
        rel.conferir(f, "demanda", "ADO negativo", d.loc[ado < 0, "path"].unique(), ERRO,
                     "Volume negativo distorce as médias ponderadas.")
        zeros = int((ado == 0).sum())
        rel.add(f, "demanda", "linhas com ADO = 0 (informativo)", AVISO if zeros else OK, zeros,
                acao=f"{zeros / len(d):.0%} das linhas não têm volume: entram na malha mas não pesam na média." if zeros else "")
        rel.conferir(f, "demanda", "caminho vazio ou com '>>'",
                     d.loc[~d["path"].astype(str).str.fullmatch(r"[^>]+(>[^>]+)*"), "path"].unique(), ERRO,
                     "Caminho deve ser ESTAÇÃO>ESTAÇÃO>...")
        validos = d[d["destination"] != "3PL"]   # destino 3PL sai da malha
        dup = validos[validos.duplicated(["period_start", "path"], keep=False)]
        rel.conferir(f, "demanda", "caminho repetido no mesmo mês", dup["path"].unique(), AVISO,
                     "O mesmo caminho aparece 2 vezes no mês; o volume é somado em dobro nas rotas.")

    # distâncias
    dist = e["distancias"]
    if not dist.empty:
        rel.conferir(f, "distâncias", "km não numérico", _nao_numerico(dist["distance_km"]), ERRO,
                     "Corrigir a distância na aba 0.0 Distances Available.")
        km = _num(dist["distance_km"])
        rel.conferir(f, "distâncias", "km zero ou negativo", dist.loc[km <= 0, "route"].unique(), AVISO,
                     "Trecho com distância 0 vira tempo de viagem 0.")
        rel.conferir(f, "distâncias", "km acima de 6.000", dist.loc[km > 6000, "route"].unique(), AVISO,
                     "Mais que a maior distância rodoviária do Brasil; conferir.")

    # coordenadas
    for nome, cod, lat, lon in [("estacoes_historico", "station_code", "latitude", "longitude"),
                                ("estacoes_base", "Code", "Lat", "Lon")]:
        t = e[nome]
        if t.empty or _faltam_colunas(t, [cod, lat, lon]):
            rel.add(f, nome, "aba vazia ou sem colunas de coordenada", ERRO if nome == "estacoes_historico" else AVISO,
                    acao="Sem essa aba as estações sem distância cadastrada ficam sem coordenada (pedir acesso).")
            continue
        la, lo = _num(t[lat]), _num(t[lon])
        fora = t.loc[la.notna() & lo.notna() & ~(la.between(*LIMITE_LAT) & lo.between(*LIMITE_LON)), cod]
        rel.conferir(f, nome, "coordenada fora do Brasil (lat/lon trocadas?)", fora.unique(), AVISO,
                     "Conferir latitude e longitude da estação.")
        rel.conferir(f, nome, "coordenada não numérica", np.concatenate([_nao_numerico(t[lat]), _nao_numerico(t[lon])]),
                     AVISO, "Usar ponto como separador decimal.")

    # rotas: expressas, New TT, SPR, tempos de SOC, fila, aéreo
    ex = e["expressas"]
    if "Transit time atualizado" in ex.columns:
        tt = ex["Transit time atualizado"].astype(str).str.strip()
        rel.conferir(f, "expressas", "tempo fora do formato HH:MM", tt[_preenchido(tt) & ~tt.str.fullmatch(r"\d+:\d{2}(:\d{2})?")].unique(),
                     ERRO, "Transit time atualizado deve ser HH:MM.")
    nt = e["new_tt"]
    if "TT HRS" in nt.columns:
        tt = nt["TT HRS"].astype(str).str.strip()
        invalido = _preenchido(tt) & ~tt.str.fullmatch(r"\d+(\.\d+)?|\d+:\d{2}(:\d{2})?")
        rel.conferir(f, "new_tt", "TT fora do formato (número ou HH:MM)", tt[invalido].unique(), AVISO,
                     "Conferir a coluna TT HRS.")
    spr = e["spr"]
    for col in ["carreta_cap", "truck_cap"]:
        if col in spr.columns:
            cap = _num(spr[col])
            rel.conferir(f, "spr", f"{col} zero ou negativo (divisão por zero)", spr.loc[cap <= 0, "route_code"].unique(),
                         ERRO, "Capacidade 0 faz a conta de veículos dividir por zero.")
            rel.conferir(f, "spr", f"{col} não numérico", _nao_numerico(spr[col]), AVISO, "Usar número sem separador de milhar.")
    ts = e["tempos_soc"]
    if "Loading" in ts.columns:
        rel.conferir(f, "tempos_soc", "Loading não numérico", _nao_numerico(ts["Loading"]), AVISO, "Conferir a aba [I] 1.0.")
    datas = pd.to_datetime(d["period_start"], errors="coerce") if "period_start" in d.columns else pd.Series(dtype="datetime64[ns]")
    meses = sorted({p.strftime("%Y-%m-01") for p in datas.dropna()})
    ar = e["arrived_received"]
    rel.conferir(f, "arrived_received", "mês da demanda sem fila no destino", [m for m in meses if m not in ar.columns],
                 AVISO, "Sem o mês, a fila no destino fica 0 para todos os SOCs.")
    al = e["air_lh"]
    if "TT (hours)" in al.columns:
        rel.conferir(f, "air_lh", "TT não numérico", _nao_numerico(al["TT (hours)"]), AVISO, "Conferir a aba [I] 2.")

    # metas
    for nome, m in e.get("metas", {}).items():
        if m.empty:
            rel.add(f, nome, "aba de meta vazia", ERRO, acao="Conferir a aba na planilha de metas.")
            continue
        colunas_mes = [c for c in m.columns if _MES.match(str(c))]
        if nome in ("meta_3_0_1", "meta_3_0_2"):
            valores = m.get("Target Received to Transporting", pd.Series(dtype=str))
            sem_mes = [x for x in meses if x not in set(m.get("period_start", pd.Series(dtype=str)))]
        else:
            valores = pd.concat([m[c] for c in colunas_mes if c in meses]) if colunas_mes else pd.Series(dtype=str)
            sem_mes = [x for x in meses if x not in colunas_mes]
        rel.conferir(f, nome, "mês da demanda sem meta", sem_mes, ERRO, "Incluir a coluna do mês na aba de meta.")
        rel.conferir(f, nome, "meta não numérica", _nao_numerico(valores), AVISO, "Usar número com ponto decimal.")
        v = _num(valores)
        rel.conferir(f, nome, "meta negativa", v[v < 0].unique(), ERRO, "Meta de tempo não pode ser negativa.")
        rel.conferir(f, nome, f"meta acima de {MAX_HORAS_ETAPA}h", v[v > MAX_HORAS_ETAPA].unique(), AVISO,
                     "Valor improvável para uma etapa; conferir unidade (horas).")
        if nome in ("meta_2_1", "meta_3_1"):
            vazios = sum(int((~_preenchido(m[c]) & _preenchido(m.iloc[:, 0])).sum()) for c in colunas_mes if c in meses)
            rel.add(f, nome, "célula vazia (quebra o processo atual)", AVISO if vazios else OK, vazios,
                    acao="Preencher; o processo antigo para com erro nessa aba." if vazios else "")
    return rel


# ---------------- resultados ----------------
def checar_resultados(r, e, rel=None):
    rel = rel or Relatorio()
    f = "resultados"
    malha = r["malha"]
    erro = malha["ERRO"].fillna("").astype(str).str.strip() != ""
    rel.conferir(f, "malha", "caminho com ERRO (não entra no BWT)",
                 (malha.loc[erro, "E2E Path"] + " [" + malha.loc[erro, "ERRO"].astype(str) + "]").unique(), AVISO,
                 "Motivo entre colchetes: fora do padrão (ex.: mais de 4 SOCs) ou estação sem distância/coordenada.")
    menos1 = (_num(malha[COLUNAS_DISTANCIA].stack()).unstack() == -1).any(axis=1)
    rel.conferir(f, "malha", "trecho sem distância (-1)", malha.loc[menos1, "E2E Path"].unique(), AVISO,
                 "Estação sem coordenada e sem distância cadastrada: caminho sai do BWT.")

    rotas = r["rotas"]
    ttf = _num(rotas["TTFinal"])
    rel.conferir(f, "rotas", "rota sem tempo final", rotas.loc[ttf.isna(), "Route"].unique(), AVISO,
                 "Rota sem tempo: a viagem fica vazia no BWT dos caminhos que passam nela.")
    rel.conferir(f, "rotas", "tempo final negativo", rotas.loc[ttf < 0, "Route"].unique(), ERRO, "Conferir inputs da rota.")

    bwt = r["bwt_caminhos"]
    tot = _num(bwt["bwt_total_hours"])
    rel.conferir(f, "bwt", "BWT total zero", bwt.loc[tot <= 0, "E2E Path"].unique(), AVISO, "Caminho sem nenhum tempo.")
    rel.conferir(f, "bwt", f"BWT total acima de {MAX_BWT_TOTAL}h", bwt.loc[tot > MAX_BWT_TOTAL, "E2E Path"].unique(),
                 AVISO, "Mais de 30 dias: conferir metas e rotas do caminho.")
    viagens = [c for c in bwt.columns if c.startswith("bwt_lh_")]
    sem_tt = bwt[viagens].apply(_num).isna().any(axis=1)
    rel.conferir(f, "bwt", "viagem sem tempo de rota (conta como 0 no total)", bwt.loc[sem_tt, "E2E Path"].unique(), AVISO,
                 "A rota não está na tabela de rotas do mês; o total desse caminho fica menor que o real.")

    # o volume tem que fechar: demanda → malha → BWT
    d = e["demanda"]
    ado_malha = _num(malha["ADO"]).sum()
    ado_bwt = _num(bwt["ADO"]).sum()
    rel.add(f, "volume", "pedidos/dia: malha → BWT", OK if ado_bwt <= ado_malha + 1e-6 else ERRO,
            acao=f"malha {ado_malha:,.0f} | BWT {ado_bwt:,.0f} ({ado_bwt / ado_malha:.1%}; o resto saiu por erro, -1 ou CB)"
            if ado_malha else "")
    if "by_step_meta" in r:
        m = r["by_step_meta"]
        br = m[m["main_route"] == "BR - BR"]
        kpis = br[br["kpi"] != "FLOW BWT TOT"].groupby(["attempt_month", "spx_channel"])["bwt_n"].sum()
        tot_bs = br[br["kpi"] == "FLOW BWT TOT"].set_index(["attempt_month", "spx_channel"])["bwt_n"]
        dif = (kpis.reindex(tot_bs.index) - tot_bs).abs() > 1e-6 * tot_bs.abs().clip(lower=1)
        rel.conferir(f, "by_step", "soma das etapas ≠ BWT total", list(tot_bs.index[dif]), ERRO,
                     "Algum tempo da meta não foi encaixado em KPI.")
    rel.conferir(f, "metas", "meta zero em estação usada pela demanda", _metas_zero(e.get("metas", {}), bwt), AVISO,
                 "A meta 0 entra como zero de verdade (só a célula vazia usa a média): os pedidos que passam ali "
                 "ficam sem esse tempo. Confirmar com o dono da aba se é de propósito; se faltar preencher, "
                 "corrigir na planilha de metas e rodar de novo.")
    return rel


ESTACOES_DO_CAMINHO = ["ORIGIN", "FMH", "SOC1", "SOC2", "SOC3", "SOC4", "LMH", "XPT"]


def _metas_zero(metas, bwt):
    """
    Estação × aba × mês com meta = 0 por onde a demanda passa, da que tem mais pedidos/dia para a que tem menos.
    Texto: 'SOC-SP26 · [T] 4.2 SOC Packed to LH Transporting · Nov/26 · 181.713 pedidos/dia'.
    """
    cols = [c for c in ESTACOES_DO_CAMINHO if c in bwt.columns]
    if not cols:
        return []
    longa = bwt[cols].assign(mes=bwt["period_start"].astype(str).str[:10], ADO=_num(bwt["ADO"]).fillna(0.0)) \
                     .melt(id_vars=["mes", "ADO"], value_name="code", ignore_index=False)
    longa["code"] = longa["code"].fillna("").astype(str).str.replace("(XD)", "", regex=False).str.strip()
    longa = longa[longa["code"] != ""].reset_index().drop_duplicates(["index", "code"])   # cada caminho conta 1 vez
    pedidos = longa.groupby(["mes", "code"])["ADO"].sum()
    meses = sorted(longa["mes"].unique())

    achados = []
    for nome, m in metas.items():
        if m.empty or "code" not in m.columns:
            continue
        aba = fontes()["planilhas"].get(nome, {}).get("aba", nome)
        for mes in meses:
            if "period_start" in m.columns:      # FMH (3.0.1 / 3.0.2): uma linha por mês
                valor = m[m["period_start"] == mes].drop_duplicates("code") \
                         .set_index("code").get("Target Received to Transporting")
            elif mes in m.columns:
                valor = m.drop_duplicates("code").set_index("code")[mes]
            else:
                continue
            if valor is None:
                continue
            for code in valor.index[_num(valor) == 0]:
                if (mes, code) in pedidos.index:
                    achados.append((pedidos[(mes, code)], f"{code} · {aba} · {_rotulo(mes)} · "
                                    + f"{pedidos[(mes, code)]:,.0f} pedidos/dia".replace(",", ".")))
    return [texto for _, texto in sorted(achados, reverse=True)]
