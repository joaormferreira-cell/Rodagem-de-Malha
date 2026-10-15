"""
Override Manual Express: aplica APENAS nas rotas da lista (express_route_mngmt /
express_route_override). Todas as demais linhas do Outbound padrão permanecem
bit-a-bit iguais.

Regra de negócio (mesma hierarquia do Outbound padrão, só nas rotas da lista):
  - lista define o selo desejado (TRUE/FALSE)
  - TT resolve por prioridade:
      P1: planilha oficial de expressas (só se selo desejado = TRUE)
      P2: New TT (ATIVA / A INICIAR), se existir
      P3: fórmula por km (normal ou expressa conforme o selo) — só sem P1 e sem P2
  - lista e selo já coincidem -> não mexe
  - rota fora da lista -> não mexe
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd

from transit_time_lib import compute_dist_time, compute_dist_time_express_routes

COL_ROUTE = "Route"
COL_PERIOD = "period_start"
COL_LH_EXPRESS = "LHExpress Ident."
COL_TT_WITH_EXPRESS = "TT with Express"
COL_TT_FINAL = "TTFinal"
COL_DISTANCE = "Distance"
COL_QUEUE = "TT Queue and Unloading"

COL_P1_TT = "TT"
COL_P1_RAMPUP = "period_rampup_express"

CONST_MIN_TT_TIME = 1.0
CONST_MIN_DIST_TT_TIME = 3.0

_TRUE_TOKENS = {"TRUE", "T", "S", "SIM", "1", "1.0"}
_FALSE_TOKENS = {"FALSE", "F", "N", "NÃO", "NAO", "0", "0.0"}


def parse_express_flag(value) -> bool | None:
    """Converte célula/flag da lista em bool. None = valor inválido/vazio."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    text = str(value).strip().upper()
    if text == "" or text == "NAN":
        return None
    if text in _TRUE_TOKENS:
        return True
    if text in _FALSE_TOKENS:
        return False
    return None


def load_overrides_from_mngmt_df(df: pd.DataFrame) -> dict[str, bool]:
    """
    Lê aba express_route_mngmt (colunas Route + express_route).
    Ignora linhas sem rota ou sem flag válido.
    """
    if df is None or df.empty:
        return {}
    cols = list(df.columns)
    if len(cols) < 2:
        raise ValueError("express_route_mngmt precisa de pelo menos 2 colunas (Route, express_route).")

    route_col = cols[0]
    flag_col = cols[1]
    out: dict[str, bool] = {}
    for _, row in df.iterrows():
        route = str(row[route_col]).strip() if pd.notna(row[route_col]) else ""
        if not route or route.lower() == "route":
            continue
        flag = parse_express_flag(row[flag_col])
        if flag is None:
            continue
        out[route] = flag
    return out


def _convert_tt_to_hours(tt_str):
    try:
        if tt_str is None or tt_str == "" or (isinstance(tt_str, float) and np.isnan(tt_str)):
            return np.nan
        parts = str(tt_str).split(":")
        if len(parts) == 3:
            return float(parts[0]) + float(parts[1]) / 60 + float(parts[2]) / 3600
        if len(parts) == 2:
            return float(parts[0]) + float(parts[1]) / 60
        return float(tt_str)
    except Exception:
        return np.nan


def build_p2_new_tt_dict(df_new_tt: pd.DataFrame) -> dict[str, float]:
    """Monta Route -> horas a partir da aba ABA ROTAS (STATUS ATIVA / A INICIAR)."""
    if df_new_tt is None or df_new_tt.empty:
        return {}
    df = df_new_tt.copy()
    if "STATUS DA ROTA" in df.columns:
        df = df[
            df["STATUS DA ROTA"].astype(str).str.upper().str.strip().isin(["ATIVA", "A INICIAR"])
        ].copy()
    if "ORIGEM" not in df.columns or "DESTINO" not in df.columns or "TT HRS" not in df.columns:
        raise ValueError("New TT sheet precisa de colunas ORIGEM, DESTINO, TT HRS.")

    df["DESTINO_LIMPO"] = df["DESTINO"].astype(str).str.split("|").str[-1].str.strip()
    df[COL_ROUTE] = df["ORIGEM"].astype(str).str.strip() + ">" + df["DESTINO_LIMPO"]
    df["TT_Hours"] = df["TT HRS"].apply(_convert_tt_to_hours)
    return (
        df.dropna(subset=["TT_Hours"])
        .drop_duplicates(subset=[COL_ROUTE], keep="first")
        .set_index(COL_ROUTE)["TT_Hours"]
        .astype(float)
        .to_dict()
    )


def normalize_p1_express_df(df_p1: pd.DataFrame) -> pd.DataFrame:
    """Garante colunas Route / TT / period_rampup_express para lookup P1."""
    if df_p1 is None or df_p1.empty:
        return pd.DataFrame(columns=[COL_ROUTE, COL_P1_TT, COL_P1_RAMPUP])
    need = {COL_ROUTE, COL_P1_TT, COL_P1_RAMPUP}
    missing = need - set(df_p1.columns)
    if missing:
        raise ValueError(f"p1_express sem colunas: {sorted(missing)}")
    out = df_p1[[COL_ROUTE, COL_P1_TT, COL_P1_RAMPUP]].copy()
    out[COL_ROUTE] = out[COL_ROUTE].astype(str).str.strip()
    out[COL_P1_TT] = pd.to_numeric(out[COL_P1_TT], errors="coerce")
    out[COL_P1_RAMPUP] = pd.to_datetime(out[COL_P1_RAMPUP], errors="coerce")
    out = out.dropna(subset=[COL_ROUTE, COL_P1_TT])
    # Uma linha por rota: menor ramp-up (mesma ideia do groupby do Outbound)
    out = (
        out.sort_values(COL_P1_RAMPUP, na_position="last")
        .drop_duplicates(subset=[COL_ROUTE], keep="first")
        .reset_index(drop=True)
    )
    return out


def _as_bool_series(series: pd.Series) -> pd.Series:
    return series.map(parse_express_flag)


def _is_string_like_series(series: pd.Series) -> bool:
    """True quando a coluna veio do Sheets como texto (object/string/Arrow)."""
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return False
    if pd.api.types.is_string_dtype(dtype):
        return True
    if str(dtype).startswith("string"):
        return True
    sample = series.dropna().head(50)
    if sample.empty:
        return True
    return all(isinstance(v, str) for v in sample)


def _express_cell_value(series: pd.Series, flag: bool):
    """Espelha o dtype da coluna: bool nativo ou 'TRUE'/'FALSE' do Sheets."""
    if _is_string_like_series(series):
        return "TRUE" if flag else "FALSE"
    return bool(flag)


def _set_numeric_on_mask(df: pd.DataFrame, mask: pd.Series, col: str, values) -> None:
    """Grava floats só nas linhas do mask, preservando o resto (Sheets string)."""
    values = np.asarray(values, dtype=float)
    if _is_string_like_series(df[col]) or str(df[col].dtype) == "object":
        if not pd.api.types.is_object_dtype(df[col]):
            df[col] = df[col].astype(object)
    df.loc[mask, col] = values


def _set_express_on_mask(df: pd.DataFrame, mask: pd.Series, flag: bool) -> None:
    if not mask.any():
        return
    df.loc[mask, COL_LH_EXPRESS] = _express_cell_value(df[COL_LH_EXPRESS], flag)


def _normal_tt_from_distance(
    distances: pd.Series,
    min_tt: float = CONST_MIN_TT_TIME,
    min_dist: float = CONST_MIN_DIST_TT_TIME,
) -> np.ndarray:
    dist = pd.to_numeric(distances, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    tt = np.asarray(compute_dist_time(dist), dtype=float)
    tt = np.where((dist > 0) & (dist < min_dist), min_tt, tt)
    tt = np.where(dist <= 0, 0.0, tt)
    return tt


def _express_tt_from_distance(distances: pd.Series) -> np.ndarray:
    dist = pd.to_numeric(distances, errors="coerce").fillna(0.0).to_numpy(dtype=float)
    tt = np.asarray(compute_dist_time_express_routes(dist), dtype=float)
    tt = np.where(dist <= 0, 0.0, tt)
    return tt


def _resolve_tt_for_rows(
    routes: pd.Series,
    periods: pd.Series,
    want_express: pd.Series,
    distances: pd.Series,
    p1_express: pd.DataFrame,
    p2_new_tt: Mapping[str, float],
    *,
    min_tt: float,
    min_dist: float,
) -> tuple[np.ndarray, dict]:
    """
    Hierarquia P1 → P2 → P3 para um subconjunto de linhas (já alinhadas).
    P1 só entra se want_express=True.
    """
    n = len(routes)
    tt_out = np.full(n, np.nan, dtype=float)

    route_key = routes.astype(str).str.strip().reset_index(drop=True)
    period_dt = pd.to_datetime(periods, errors="coerce").reset_index(drop=True)
    want = want_express.fillna(False).astype(bool).reset_index(drop=True)
    dist = pd.to_numeric(distances, errors="coerce").reset_index(drop=True)

    p1 = normalize_p1_express_df(p1_express)
    if p1.empty:
        p1_tt = pd.Series(np.nan, index=range(n), dtype=float)
        p1_ramp = pd.Series(pd.NaT, index=range(n))
    else:
        p1_idx = p1.set_index(COL_ROUTE)
        p1_tt = route_key.map(p1_idx[COL_P1_TT])
        p1_ramp = pd.to_datetime(route_key.map(p1_idx[COL_P1_RAMPUP]), errors="coerce")

    matched_p1 = (
        want.to_numpy()
        & p1_tt.notna().to_numpy()
        & period_dt.notna().to_numpy()
        & p1_ramp.notna().to_numpy()
        & (period_dt >= p1_ramp).to_numpy()
    )

    p2_vals = pd.to_numeric(
        route_key.map(lambda r: p2_new_tt.get(r) if p2_new_tt else np.nan),
        errors="coerce",
    )
    matched_p2 = (~matched_p1) & p2_vals.notna().to_numpy()
    matched_p3 = (~matched_p1) & (~matched_p2)

    if matched_p1.any():
        tt_out[matched_p1] = p1_tt.to_numpy(dtype=float)[matched_p1]
    if matched_p2.any():
        tt_out[matched_p2] = p2_vals.to_numpy(dtype=float)[matched_p2]
    if matched_p3.any():
        want_p3 = want.to_numpy()[matched_p3]
        dist_p3 = dist.iloc[np.where(matched_p3)[0]]
        tt_p3 = np.empty(int(matched_p3.sum()), dtype=float)
        mask_norm = ~want_p3
        mask_expr = want_p3
        if mask_norm.any():
            tt_p3[mask_norm] = _normal_tt_from_distance(
                dist_p3.iloc[np.where(mask_norm)[0]], min_tt=min_tt, min_dist=min_dist
            )
        if mask_expr.any():
            tt_p3[mask_expr] = _express_tt_from_distance(
                dist_p3.iloc[np.where(mask_expr)[0]]
            )
        tt_out[matched_p3] = tt_p3

    stats = {
        "n_p1": int(matched_p1.sum()),
        "n_p2": int(matched_p2.sum()),
        "n_p3": int(matched_p3.sum()),
    }
    return tt_out, stats


def apply_manual_express_overrides(
    routes: pd.DataFrame,
    overrides: Mapping[str, bool],
    *,
    p1_express: pd.DataFrame | None = None,
    p2_new_tt: Mapping[str, float] | None = None,
    min_tt: float = CONST_MIN_TT_TIME,
    min_dist: float = CONST_MIN_DIST_TT_TIME,
) -> tuple[pd.DataFrame, dict]:
    """
    Parte do Outbound padrão e altera SOMENTE rotas cujo override diverge do selo.
    TT das linhas alteradas: P1 → P2 → P3 (P3 só sem P1/P2).

    Retorna (dataframe_patchado, stats).
    """
    empty_stats = {
        "n_rows": 0,
        "n_overrides": len(overrides),
        "n_changed": 0,
        "n_to_normal": 0,
        "n_to_express": 0,
        "n_p1": 0,
        "n_p2": 0,
        "n_p3": 0,
        "changed_routes": [],
    }
    if routes is None or routes.empty:
        return routes.copy() if routes is not None else pd.DataFrame(), empty_stats

    required = [
        COL_ROUTE,
        COL_LH_EXPRESS,
        COL_TT_WITH_EXPRESS,
        COL_TT_FINAL,
        COL_DISTANCE,
        COL_QUEUE,
    ]
    missing = [c for c in required if c not in routes.columns]
    if missing:
        raise ValueError(f"Outbound base sem colunas obrigatórias: {missing}")

    p1_express = normalize_p1_express_df(p1_express) if p1_express is not None else normalize_p1_express_df(
        pd.DataFrame()
    )
    p2_new_tt = dict(p2_new_tt) if p2_new_tt else {}

    out = routes.copy()
    current = _as_bool_series(out[COL_LH_EXPRESS])
    desired = out[COL_ROUTE].map(lambda r: overrides.get(str(r).strip()) if pd.notna(r) else None)

    mask_in_list = desired.notna()
    mask_diff = mask_in_list & current.notna() & (desired != current)
    mask_diff = mask_diff | (mask_in_list & current.isna())

    n_to_normal = 0
    n_to_express = 0
    n_p1 = n_p2 = n_p3 = 0
    changed_routes: list[str] = []

    if mask_diff.any():
        mask_to_normal = mask_diff & (desired == False)  # noqa: E712
        mask_to_express = mask_diff & (desired == True)  # noqa: E712
        n_to_normal = int(mask_to_normal.sum())
        n_to_express = int(mask_to_express.sum())

        _set_express_on_mask(out, mask_to_normal, False)
        _set_express_on_mask(out, mask_to_express, True)

        if COL_PERIOD in out.columns:
            periods = out.loc[mask_diff, COL_PERIOD]
        else:
            periods = pd.Series(pd.NaT, index=out.index[mask_diff])

        tt_vals, pr_stats = _resolve_tt_for_rows(
            out.loc[mask_diff, COL_ROUTE],
            periods,
            desired.loc[mask_diff].astype(bool),
            out.loc[mask_diff, COL_DISTANCE],
            p1_express,
            p2_new_tt,
            min_tt=min_tt,
            min_dist=min_dist,
        )
        n_p1, n_p2, n_p3 = pr_stats["n_p1"], pr_stats["n_p2"], pr_stats["n_p3"]
        _set_numeric_on_mask(out, mask_diff, COL_TT_WITH_EXPRESS, tt_vals)

        queue = pd.to_numeric(out.loc[mask_diff, COL_QUEUE], errors="coerce").fillna(0.0)
        travel = pd.to_numeric(out.loc[mask_diff, COL_TT_WITH_EXPRESS], errors="coerce").fillna(0.0)
        _set_numeric_on_mask(
            out,
            mask_diff,
            COL_TT_FINAL,
            queue.to_numpy(dtype=float) + travel.to_numpy(dtype=float),
        )

        changed_routes = sorted({str(r) for r in out.loc[mask_diff, COL_ROUTE].tolist()})

    stats = {
        "n_rows": int(len(out)),
        "n_overrides": int(len(overrides)),
        "n_changed": int(mask_diff.sum()),
        "n_to_normal": n_to_normal,
        "n_to_express": n_to_express,
        "n_p1": n_p1,
        "n_p2": n_p2,
        "n_p3": n_p3,
        "changed_routes": changed_routes,
    }
    return out, stats


def assert_non_override_rows_identical(
    base: pd.DataFrame,
    patched: pd.DataFrame,
    overrides: Mapping[str, bool],
    value_cols: list[str] | None = None,
) -> None:
    """Garante que nenhuma coluna de valor mudou fora das rotas override."""
    if value_cols is None:
        value_cols = [
            COL_TT_FINAL,
            COL_TT_WITH_EXPRESS,
            COL_LH_EXPRESS,
            COL_DISTANCE,
            COL_QUEUE,
            "ADO",
            "TT Calc.",
        ]
    value_cols = [c for c in value_cols if c in base.columns and c in patched.columns]

    override_routes = set(overrides.keys())
    mask_keep = ~base[COL_ROUTE].astype(str).str.strip().isin(override_routes)
    left = base.loc[mask_keep, [COL_ROUTE] + value_cols].reset_index(drop=True)
    right = patched.loc[mask_keep, [COL_ROUTE] + value_cols].reset_index(drop=True)
    if len(left) != len(right):
        raise AssertionError(
            f"Linhas fora do override divergiram em quantidade: base={len(left)} patched={len(right)}"
        )
    for col in value_cols:
        a = left[col]
        b = right[col]
        if col == COL_LH_EXPRESS:
            if not (_as_bool_series(a).fillna(-1).eq(_as_bool_series(b).fillna(-1)).all()):
                raise AssertionError(f"Coluna {col} alterada em rota fora do override.")
            continue
        a_num = pd.to_numeric(a, errors="coerce")
        b_num = pd.to_numeric(b, errors="coerce")
        if a_num.notna().any() or b_num.notna().any():
            both_num = a_num.notna() & b_num.notna()
            if both_num.any() and not np.allclose(
                a_num[both_num].to_numpy(dtype=float),
                b_num[both_num].to_numpy(dtype=float),
                rtol=0,
                atol=0,
                equal_nan=True,
            ):
                bad = left.loc[both_num & (a_num != b_num), COL_ROUTE].head(5).tolist()
                raise AssertionError(f"Coluna {col} alterada fora do override. Exemplos: {bad}")
            rest = ~both_num
            if rest.any() and not a.astype(str)[rest].eq(b.astype(str)[rest]).all():
                raise AssertionError(f"Coluna {col} (não-numérica) alterada fora do override.")
        else:
            if not a.astype(str).eq(b.astype(str)).all():
                raise AssertionError(f"Coluna {col} alterada fora do override.")
