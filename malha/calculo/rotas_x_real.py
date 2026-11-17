"""
Meta × real por ROTA (tempo de estrada de cada trecho A → B).

Real = resultado da consulta consultas/lh_real_por_rota.sql (Data Studio), uma linha por rota × mês:
    rota | mes | pacotes | horas_media | horas_mediana | estrada_media | fila_media
Mesma regra do By Step: começa quando o pacote SAI de A; termina quando é RECEBIDO no SOC/FMH (inclui fila)
ou quando CHEGA no HUB/XPT. "estrada" = saiu de A → chegou em B; "fila" = chegou em B → recebido.
As colunas estrada/fila são opcionais (versões antigas da consulta não trazem).

Meta = aba Rotas: viagem (TT with Express) + fila no destino (TT Queue and Unloading) = TTFinal.
O mesmo código de estação às vezes vem com sufixo ([DC], _fix, -X, -EX): é tirado dos dois lados antes de juntar.
"""
import numpy as np
import pandas as pd

SUFIXO = r"(\[DC\]|_fix|-X|-EX)$"
FAIXA_OK = 2.0      # horas: diferença até 2h = dentro da meta
FAIXA_ALERTA = 4.0  # horas: acima de 4h = fora


def _normalizar(codigo):
    return codigo.astype(str).str.strip().str.replace(SUFIXO, "", regex=True)


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def preparar_real(bruto):
    """CSV da consulta → uma linha por mês × rota (códigos sem sufixo), médias ponderadas pelos pacotes."""
    r = bruto.copy()
    for c in ["estrada_media", "fila_media"]:
        if c not in r.columns:
            r[c] = np.nan
    partes = r["rota"].astype(str).str.split(">", n=1, expand=True)
    r["origem"], r["destino"] = _normalizar(partes[0]), _normalizar(partes[1])
    r["mes"] = pd.to_datetime(r["mes"]).dt.strftime("%Y-%m-%d")
    r["pacotes"] = _num(r["pacotes"]).fillna(0)
    medidas = {"horas_media": "real_total_h", "horas_mediana": "real_mediana_h",
               "estrada_media": "real_estrada_h", "fila_media": "real_fila_h"}
    for col in medidas:
        v = _num(r[col])
        r[col + "_x"] = v * r["pacotes"]
        r[col + "_p"] = np.where(v.notna(), r["pacotes"], 0)
    g = r.groupby(["mes", "origem", "destino"], as_index=False).sum(numeric_only=True)
    for col, nome in medidas.items():
        g[nome] = g[col + "_x"] / g[col + "_p"].replace(0, np.nan)
    return g[["mes", "origem", "destino", "pacotes"] + list(medidas.values())].rename(
        columns={"pacotes": "real_pacotes"})


def _situacao(dif):
    return np.select(
        [dif.isna(), dif.abs() <= FAIXA_OK, dif > FAIXA_ALERTA, dif > FAIXA_OK, dif < -FAIXA_ALERTA],
        ["", "ok (até 2h)", "real acima da meta (+4h)", "real acima da meta (2 a 4h)", "meta folgada (real 4h+ abaixo)"],
        "meta folgada (real 2 a 4h abaixo)")


def comparar_rotas(rotas, real_bruto):
    """Uma linha por rota × mês do realizado: meta (viagem, fila, total), real e diferença (horas)."""
    real = preparar_real(real_bruto)
    meses = set(real["mes"])
    m = rotas[rotas["period_start"].isin(meses)]
    meta = pd.DataFrame({
        "mes": m["period_start"], "rota": m["Route"], "tipo": m["route_type"],
        "origem": _normalizar(m["Origin"]), "destino": _normalizar(m["Dest"]),
        "pedidos_dia_meta": _num(m["ADO"]), "km": _num(m["Distance"]), "fonte_tempo": m["fonte_tt"],
        "meta_viagem_h": _num(m["TT with Express"]), "meta_fila_h": _num(m["TT Queue and Unloading"]),
        "meta_total_h": _num(m["TTFinal"]),
    })
    t = meta.merge(real, on=["mes", "origem", "destino"], how="outer", indicator=True)
    so_real = t["_merge"] == "right_only"
    t.loc[so_real, "rota"] = t["origem"] + ">" + t["destino"]
    t["dif_total_h"] = t["real_total_h"] - t["meta_total_h"]
    t["dif_estrada_h"] = t["real_estrada_h"] - t["meta_viagem_h"]
    t["dif_fila_h"] = t["real_fila_h"] - t["meta_fila_h"].fillna(0)
    t["situacao"] = _situacao(t["dif_total_h"])
    t.loc[t["_merge"] == "left_only", "situacao"] = "sem real (rota não rodou ou poucos pacotes)"
    t.loc[so_real, "situacao"] = "só no real (rota fora da malha planejada)"
    t["ordem"] = np.where(so_real, 1, 0)
    t = t.sort_values(["mes", "ordem", "pedidos_dia_meta", "real_pacotes"], ascending=[True, True, False, False])
    colunas = ["mes", "rota", "tipo", "situacao", "pedidos_dia_meta", "real_pacotes", "km", "fonte_tempo",
               "meta_viagem_h", "meta_fila_h", "meta_total_h", "real_estrada_h", "real_fila_h", "real_total_h",
               "real_mediana_h", "dif_estrada_h", "dif_fila_h", "dif_total_h"]
    return t[colunas].reset_index(drop=True)


def resumo(tabela):
    """% dos pacotes reais (rotas que existem na meta e no real) por faixa de diferença."""
    c = tabela[tabela["dif_total_h"].notna()]
    total = c["real_pacotes"].sum()
    if not total:
        return None
    dif = c["dif_total_h"]
    pct = lambda filtro: 100 * c.loc[filtro, "real_pacotes"].sum() / total  # noqa: E731
    return {"rotas": len(c), "ate_2h": pct(dif.abs() <= FAIXA_OK), "ate_4h": pct(dif.abs() <= FAIXA_ALERTA),
            "acima_4h": pct(dif > FAIXA_ALERTA), "abaixo_4h": pct(dif < -FAIXA_ALERTA)}
