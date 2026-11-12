"""
Ajuste manual de expressas (etapa 3, opcional).
A aba express_route_mngmt lista rotas e se devem ser expressas (TRUE) ou não (FALSE).
Só as rotas da lista cujo selo é diferente do calculado são alteradas; o resto fica idêntico.
Tempo de viagem da rota alterada: expressa oficial (só se virou expressa) → New TT → cálculo por km.
"""
import numpy as np
import pandas as pd

from ..configuracao import premissas
from .tempo_viagem import tt_expressa, tt_normal

SIM = {"TRUE", "T", "S", "SIM", "1", "1.0"}
NAO = {"FALSE", "F", "N", "NÃO", "NAO", "0", "0.0"}


def ler_selo(valor):
    """TRUE/FALSE/SIM/NÃO/1/0 → True/False; vazio ou outra coisa → None."""
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    texto = str(valor).strip().upper()
    return True if texto in SIM else False if texto in NAO else None


def ler_lista(bruto):
    """Aba express_route_mngmt → {rota: True/False}. 1ª coluna = rota, 2ª = selo desejado."""
    if bruto is None or bruto.empty:
        return {}
    rota_col, selo_col = bruto.columns[:2]
    lista = {}
    for rota, selo in zip(bruto[rota_col], bruto[selo_col]):
        rota = str(rota).strip() if pd.notna(rota) else ""
        selo = ler_selo(selo)
        if rota and rota.lower() != "route" and selo is not None:
            lista[rota] = selo
    return lista


def expressas_oficiais(bruto):
    """
    Planilha oficial de expressas → uma linha por rota (Route, TT, inicio), menor data de ativação.
    Regra do processo atual: o histórico (Data de ramp-up) só entra se a aba também tiver 'Data final de ramp-up'.
    """
    def _bloco(df, col_data):
        df = df[df["Rota atualizada com movings"].astype(str).str.strip().ne("")
                & df["Transit time atualizado"].astype(str).str.strip().ne("")]
        partes = df["Transit time atualizado"].astype(str).str.strip().str.split(":", n=2, expand=True)
        tt = (pd.to_numeric(partes[0], errors="coerce") + pd.to_numeric(partes[1], errors="coerce") / 60
              if not df.empty else pd.Series(dtype=float))
        return pd.DataFrame({"Route": df["Rota atualizada com movings"].astype(str).str.replace("|", ">", regex=False),
                             "TT": tt,
                             "inicio": pd.to_datetime(df[col_data], format="%d/%b/%y", errors="coerce")})

    ativas = bruto[~bruto["Status"].isin(["Expressa inativa", "Inativa"])
                   & ~bruto["Status"].astype(str).str.contains("Expressa a ativar", na=False)]
    blocos = [_bloco(ativas, "Data da última alteração")]
    if {"Data de ramp-up", "Data final de ramp-up"} <= set(bruto.columns):
        blocos.append(_bloco(bruto, "Data de ramp-up"))
    p1 = pd.concat(blocos).groupby(["Route", "TT"], as_index=False)["inicio"].min()
    p1["Route"] = p1["Route"].str.strip()
    p1 = p1.dropna(subset=["Route", "TT"]).sort_values("inicio", na_position="last")
    return p1.drop_duplicates("Route", keep="first").set_index("Route")


def aplicar_ajuste(rotas, lista, expressas_bruto, new_tt):
    """Devolve as rotas com o ajuste aplicado e quantas foram alteradas."""
    p = premissas()["rotas"]
    rotas = rotas.copy()
    atual = rotas["LHExpress Ident."].map(ler_selo)
    desejado = rotas["Route"].map(lambda r: lista.get(str(r).strip()))
    na_lista = desejado.notna()
    mudar = na_lista & (atual.isna() | (desejado != atual))
    if not mudar.any():
        print("Ajuste de expressas: nenhuma rota alterada")
        return rotas, 0

    alvo = rotas[mudar]
    quer_expressa = desejado[mudar].astype(bool)
    oficiais = expressas_oficiais(expressas_bruto)
    km = pd.to_numeric(alvo["Distance"], errors="coerce").fillna(0.0)
    mes = pd.to_datetime(alvo["period_start"], errors="coerce")
    tt_oficial = alvo["Route"].map(oficiais["TT"])
    inicio = pd.to_datetime(alvo["Route"].map(oficiais["inicio"]), errors="coerce")

    p1 = quer_expressa & tt_oficial.notna() & mes.notna() & inicio.notna() & (mes >= inicio)
    p2 = ~p1 & alvo["Route"].map(new_tt).notna()
    por_km_normal = np.where(km <= 0, 0.0, np.where(km < p["dist_min_tt_km"], p["tt_min_h"], tt_normal(km)))
    por_km_expressa = np.where(km <= 0, 0.0, tt_expressa(km))
    tt = np.select([p1, p2, quer_expressa], [tt_oficial, alvo["Route"].map(new_tt), por_km_expressa], por_km_normal)

    fila = pd.to_numeric(alvo["TT Queue and Unloading"], errors="coerce").fillna(0.0)
    rotas["LHExpress Ident."] = rotas["LHExpress Ident."].astype(object)
    rotas.loc[mudar, "LHExpress Ident."] = quer_expressa.to_numpy()
    rotas.loc[mudar, "TT with Express"] = tt
    rotas.loc[mudar, "TTFinal"] = fila.to_numpy() + np.nan_to_num(tt.astype(float))
    rotas.loc[mudar, "fonte_tt"] = "Ajuste manual: " + pd.Series(
        np.select([p1, p2, quer_expressa], ["expressa oficial", "New TT", "cálculo por km (expressa)"],
                  "cálculo por km"), index=alvo.index)
    print(f"Ajuste de expressas: {mudar.sum()} rota(s) alterada(s): {sorted(alvo['Route'])[:15]}")
    return rotas, int(mudar.sum())
