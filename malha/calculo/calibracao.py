"""
Aba "Real x Meta - por regra": a meta da Rodagem erra sempre para o mesmo lado? Real × meta das rotas (aba "Real x Meta - rotas"),
agrupado pela regra que deu o tempo (expressa oficial, New TT, fórmula por km...), pelo tipo de rota e pela distância.
Só compara: não muda nenhum número da meta.

  viagem: meta = tempo de viagem da rota (TT with Express); real = estrada (saiu → chegou)
  fila:   meta = fila no SOC de destino;                     real = chegou → recebido (só destino SOC)
  médias ponderadas pelos pacotes reais do mês.

Se um grupo está sempre acima (ou abaixo) do real, a regra daquele grupo é que precisa de ajuste, não uma rota só.
"""
import numpy as np
import pandas as pd

FAIXAS_KM = [0, 100, 300, 600, 1000, np.inf]
ROTULOS_KM = ["até 100 km", "100 a 300 km", "300 a 600 km", "600 a 1.000 km", "mais de 1.000 km"]
PERTO_H, PERTO_PCT = 0.3, 0.10   # diferença até 0,3h ou até 10% da meta = perto


def _leitura(meta, real):
    dif = real - meta
    if abs(dif) <= PERTO_H or abs(dif) <= PERTO_PCT * meta:
        return "A regra acerta: real perto da meta."
    if dif > 0:
        return "Real acima da meta: a regra dá menos tempo do que a operação faz (ou a operação atrasa)."
    return "Real abaixo da meta: a regra dá mais tempo do que precisa (meta folgada)."


def _grupos(d, visao, por, col_meta, col_real):
    linhas = []
    for grupo, x in d.groupby(por, observed=True):
        w = x["real_pacotes"]
        meta, real = np.average(x[col_meta], weights=w), np.average(x[col_real], weights=w)
        linhas.append({"o que": visao, "grupo": grupo, "rotas": len(x), "pacotes no mês": w.sum(),
                       "meta (h)": meta, "real (h)": real, "real − meta (h)": real - meta,
                       "% rotas com real 10%+ acima": 100 * (x[col_real] > 1.1 * x[col_meta]).mean(),
                       "% rotas com real 10%+ abaixo": 100 * (x[col_real] < 0.9 * x[col_meta]).mean(),
                       "leitura": _leitura(meta, real)})
    return linhas


def calibracao(rotas_x_real):
    r = rotas_x_real.copy()
    for c in ["real_pacotes", "km", "meta_viagem_h", "meta_fila_h", "real_estrada_h", "real_fila_h"]:
        r[c] = pd.to_numeric(r[c], errors="coerce")
    r = r[r["real_pacotes"] > 0]
    r["faixa"] = pd.cut(r["km"], FAIXAS_KM, labels=ROTULOS_KM)
    linhas = []
    for mes in sorted(r["mes"].unique(), reverse=True):
        m = r[r["mes"] == mes]
        v = m[m["meta_viagem_h"].notna() & m["real_estrada_h"].notna()]
        f = m[m["real_fila_h"].notna() & m["fonte_fila"].notna() & m["rota"].str.split(">").str[1].str.startswith("SOC")]
        f = f.assign(meta_fila_h=f["meta_fila_h"].fillna(0))
        blocos = [
            ("Viagem: de onde vem o tempo", v, "fonte_tempo"),
            ("Viagem: tipo de rota", v, "tipo"),
            ("Viagem da planilha oficial de expressas, por distância", v[v["fonte_tempo"] == "Expressa oficial"], "faixa"),
            ("Viagem da planilha New TT, por distância", v[v["fonte_tempo"] == "New TT"], "faixa"),
            ("Viagem pela fórmula de km, por distância", v[v["fonte_tempo"] == "Cálculo por km"], "faixa"),
            ("Viagem pela fórmula de expressa, por distância", v[v["fonte_tempo"] == "Cálculo por km (expressa)"], "faixa"),
        ]
        for visao, d, por in blocos:
            linhas += [{"mês": mes, **x} for x in _grupos(d, visao, por, "meta_viagem_h", "real_estrada_h")]
        linhas += [{"mês": mes, **x} for x in _grupos(f, "Fila no SOC de destino: de onde vem a fila", "fonte_fila",
                                                      "meta_fila_h", "real_fila_h")]
    return pd.DataFrame(linhas) if linhas else None
