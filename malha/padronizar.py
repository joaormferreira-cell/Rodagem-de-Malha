"""
Inputs padronizados: as abas de hoje (cada uma com seu formato) viram tabelas num modelo único.

METAS: as 17 abas [T] de meta viram UMA tabela longa
    etapa | codigo_by_step | estacao | mes | horas | fonte | aba_origem | ordem
- uma linha por estação × mês (mês novo = linhas novas, a tabela nunca muda de formato);
- "codigo_by_step" liga a meta à By Step (e à Initiatives);
- metas de valor único (APT, dropoff) usam estacao = "TODAS".

metas_para_abas() faz o caminho de volta (tabela longa → abas no formato antigo), para provar que nada se perde:
o cálculo com as abas reconstruídas tem de dar exatamente o mesmo resultado.
"""
import re

import numpy as np
import pandas as pd

_MES = re.compile(r"^\d{4}-\d{2}-01$")
TODAS = "TODAS"
VALOR_FMH = "Target Received to Transporting"   # nome da coluna nas abas 3.0.1 e 3.0.2 (as duas usam o mesmo)

# chave interna: (etapa, código By Step, formato da aba de hoje, aba de origem)
METAS = {
    "meta_1_0": ("Seller: pago → coleta/dropoff (APT)", "1.01", "valor_unico", "[T] 1.0"),
    "meta_2_0": ("FM: dropoff → coleta", "3.01", "valor_unico", "[T] 2.0"),
    "meta_2_1": ("FM: coleta → recebido no FMH/SOC", "3.03 / 3.04", "mensal", "[T] 2.1"),
    "meta_3_1": ("FBS: processamento", "2.01 + 2.02", "mensal", "[T] 3.1"),
    "meta_3_0_1": ("FMH: recebido → embalado", "4.06", "fmh", "[T] 3.0.1"),
    "meta_3_0_2": ("FMH: embalado → saída", "4.07", "fmh", "[T] 3.0.2"),
    "meta_4_0": ("SOC: recebido → embalado", "4.12 / 4.15 / 4.18", "mensal", "[T] 4.0"),
    "meta_4_2": ("SOC: embalado → saída", "4.13 / 4.16 / 4.19", "mensal", "[T] 4.2"),
    "meta_8": ("Aeroporto: recebido → voo", "4.24", "mensal", "[T] 8"),
    "meta_4_9": ("HUB: chegou → descarregado", "5.01 (parte)", "mensal", "[T] 4.9"),
    "meta_5_0": ("HUB: descarregado → recebido", "5.01 (parte)", "mensal", "[T] 5.0"),
    "meta_5_1_0": ("HUB: recebido → saída para entrega", "5.02", "mensal", "[T] 5.1.0"),
    "meta_5_1_1": ("HUB: recebido → saída para XPT", "5.02", "mensal", "[T] 5.1.1"),
    "meta_5_9": ("XPT: chegou → recebido", "5.04", "mensal", "[T] 5.9"),
    "meta_6_0": ("XPT: recebido → saída para entrega", "5.05", "mensal", "[T] 6.0"),
    "meta_7_0": ("Entrega pelo HUB: saiu → 1ª tentativa", "6.01", "mensal", "[T] 7.0"),
    "meta_7_1": ("Entrega pelo XPT: saiu → 1ª tentativa", "6.02", "mensal", "[T] 7.1"),
}
COLUNAS_METAS = ["etapa", "codigo_by_step", "estacao", "mes", "horas", "chave", "aba_origem", "ordem"]


def _horas(s):
    """Texto → número; '-', '48%', vazio ou texto → sem valor (mesma regra do cálculo)."""
    return pd.to_numeric(s.astype(str).str.strip().replace({"-": "", "": np.nan}), errors="coerce")


def metas_longas(metas):
    """Abas [T] de hoje → tabela METAS (uma linha por estação × mês)."""
    partes = []
    for chave, (etapa, codigo, formato, aba) in METAS.items():
        m = metas[chave].reset_index(drop=True)
        if formato == "fmh":
            df = pd.DataFrame({"estacao": m["code"], "mes": m["period_start"], "horas": _horas(m[VALOR_FMH])})
            df["ordem"] = np.arange(len(m))
        else:
            meses = [c for c in m.columns if _MES.match(str(c))]
            base = m.head(1) if formato == "valor_unico" else m   # valor único: só a 1ª linha vale
            estacao = pd.Series(TODAS, index=base.index) if formato == "valor_unico" else base["code"]
            larga = pd.DataFrame({c: _horas(base[c]) for c in meses}).assign(estacao=estacao.values,
                                                                                ordem=np.arange(len(base)))
            df = larga.melt(id_vars=["estacao", "ordem"], var_name="mes", value_name="horas")
        df = df.assign(etapa=etapa, codigo_by_step=codigo, chave=chave, aba_origem=aba)
        partes.append(df[COLUNAS_METAS])
    longa = pd.concat(partes, ignore_index=True)
    longa["estacao"] = longa["estacao"].fillna("").astype(str).str.strip()
    # linha sem estação e sem valor não tem informação nenhuma
    return longa[~((longa["estacao"] == "") & longa["horas"].isna())].reset_index(drop=True)


def metas_para_abas(longa):
    """Tabela METAS → abas no formato que o cálculo lê hoje (caminho de volta)."""
    abas = {}
    for chave, (_, _, formato, _) in METAS.items():
        d = longa[longa["chave"] == chave]
        if formato == "fmh":
            d = d.sort_values("ordem")
            abas[chave] = pd.DataFrame({"code": d["estacao"].values, "period_start": d["mes"].values,
                                        VALOR_FMH: d["horas"].values})
            continue
        larga = d.pivot_table(index="ordem", columns="mes", values="horas", aggfunc="first", dropna=False)
        larga = larga.reindex(sorted(d["ordem"].unique()))
        larga = larga[sorted(larga.columns)]
        estacao = d.drop_duplicates("ordem").set_index("ordem")["estacao"].reindex(larga.index)
        if formato == "valor_unico":
            abas[chave] = larga.reset_index(drop=True)
        else:
            abas[chave] = pd.concat([estacao.rename("code"), larga], axis=1).reset_index(drop=True)
        abas[chave].columns.name = None
    return abas
