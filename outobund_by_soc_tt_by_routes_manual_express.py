"""
Manual Express (month): NÃO recalcula o Outbound inteiro.

Fluxo:
  1) Lê a saída do Outbound padrão em "[T] 4.1 ..."
  2) Lê overrides em express_route_mngmt
  3) Carrega lookups P1 (planilha oficial) e P2 (New TT)
  4) Altera SOMENTE rotas da lista cujo selo diverge:
       selo forçado + TT por P1 → P2 → P3 (P3 só sem P1/P2)
  5) Regrava a aba [T] 4.1

Tudo que não está na lista permanece idêntico ao padrão.
"""
import os
import sys

import pandas as pd

PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MONTH_DIR = os.path.abspath(os.path.dirname(__file__))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)
if MONTH_DIR not in sys.path:
    sys.path.insert(0, MONTH_DIR)

from connection_with_path import GmailEntry
from manual_express_lib import (
    build_p2_new_tt_dict,
    apply_manual_express_overrides,
    assert_non_override_rows_identical,
    load_overrides_from_mngmt_df,
    normalize_p1_express_df,
    parse_express_flag,
)

import warnings

warnings.simplefilter(action="ignore")

credential_path = os.path.join(PARENT_DIR, "credential", "jards.json")
conn = GmailEntry(None, None, None, credential_path)

# --------------- PATHS --------------------
GSHEET_PRINT_OUTPUT = "1HdplQWZuaSrEYQLNWQYA0gc5rCqXaLCt-aaLJ2xD3FE"
RANGE_BASE_OUTBOUND = "[T] 4.1 TT and SOC Packed to Transporting to SOC!A3:W"
RANGE_PRINT_OUTPUT = "[T] 4.1 TT and SOC Packed to Transporting to SOC!A"
RANGE_PRINT_OUTPUT_CLEAR = "A3:W"
RANGE_EXPRESS_MNGMT = "express_route_mngmt!A1:B"

GSHEET_ACTUAL_EXPRESS_ROUTES_INPUT = "197nob2_mCQy1fA-1ETkDH8hs6EW-YYLJx1F2egxW5uQ"
RANGE_ACTUAL_EXPRESS_ROUTES = "Implemented routes!B4:AA500"

GSHEET_NEW_TT_CORRIGIDO = "1mwx37vJIDwk2eOMLZ_LTYqoTHq-3qui2zbOL9vkE6pE"
RANGE_NEW_TT_CORRIGIDO = "ABA ROTAS!A1:Q"

COL_PERIOD = "period_start"
COL_ROUTE = "Route"
COL_LH_EXPRESS = "LHExpress Ident."
COL_TT_FINAL = "TTFinal"
COL_TT_WITH_EXPRESS = "TT with Express"
COL_DISTANCE = "Distance"
COL_QUEUE = "TT Queue and Unloading"

COLS_OUTPUT = [
    "period_start",
    "Route",
    "Origin",
    "Dest",
    "route_type",
    "ADO",
    "Distance",
    "Final Pck-LHTr",
    "Pck-LHTr",
    "Raw Pck-LHTr",
    "Loading",
    "TTFinal",
    "LHExpress Ident.",
    "TT Calc.",
    "TT with Express",
    "TT Queue and Unloading",
    "Total Vehicles",
    "N Carretas",
    "N Truck",
    "N Others",
    "carreta_cap",
    "truck_cap",
    "others_cap",
]


def _normalize_base(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if COL_PERIOD in out.columns:
        out[COL_PERIOD] = out[COL_PERIOD].astype(str).str[:10]
    if COL_ROUTE in out.columns:
        out = out[out[COL_ROUTE].astype(str).str.strip().ne("")].copy()
        out = out[out[COL_ROUTE].astype(str).str.lower().ne("route")].copy()
    out.reset_index(drop=True, inplace=True)
    return out


def _prepare_for_sheets_write(df: pd.DataFrame) -> pd.DataFrame:
    """
    print_in_sheets usa valueInputOption=RAW:
      - str \"FALSE\" / \"0\" → célula TEXTO ('FALSE / '0)
      - bool False / float 0 → tipo nativo (igual ao Outbound padrão)
    """
    out = df.copy()
    numeric_cols = [
        "ADO",
        COL_DISTANCE,
        "Final Pck-LHTr",
        "Pck-LHTr",
        "Raw Pck-LHTr",
        "Loading",
        COL_TT_FINAL,
        "TT Calc.",
        COL_TT_WITH_EXPRESS,
        COL_QUEUE,
        "Total Vehicles",
        "N Carretas",
        "N Truck",
        "N Others",
        "carreta_cap",
        "truck_cap",
        "others_cap",
    ]
    for col in numeric_cols:
        if col not in out.columns:
            continue
        num = pd.to_numeric(out[col], errors="coerce")
        # mantém vazio onde não há número (Sheets fica em branco, não 'nan')
        out[col] = num.where(num.notna(), other="")

    if COL_LH_EXPRESS in out.columns:
        flags = out[COL_LH_EXPRESS].map(parse_express_flag)
        # bool nativo; vazio se ilegível
        out[COL_LH_EXPRESS] = flags.where(flags.notna(), other="")

    # NaN restantes → "" (evita gravar "nan" como texto)
    out = out.where(pd.notna(out), other="")
    return out


def _non_empty(series: pd.Series) -> pd.Series:
    return series.notna() & series.astype(str).str.strip().ne("")


def _tt_hhmm_to_hours(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    parts = text.str.split(":", n=2, expand=True)
    hours = pd.to_numeric(parts[0], errors="coerce")
    minutes = pd.to_numeric(parts[1], errors="coerce")
    return hours + (minutes / 60.0)


def _load_p1_express() -> pd.DataFrame:
    """Planilha oficial Implemented routes (Prioridade 1) — mesmo critério do Outbound."""
    raw = conn.get_sheets(
        scopes=GSHEET_ACTUAL_EXPRESS_ROUTES_INPUT, sh_name=RANGE_ACTUAL_EXPRESS_ROUTES
    )
    cur = raw[
        ["Rota atualizada com movings", "Transit time atualizado", "Status", "Data da última alteração"]
    ].copy()
    cur = cur[cur["Status"] != "Expressa inativa"]
    cur = cur[cur["Status"] != "Inativa"]
    cur = cur[~cur["Status"].astype(str).str.contains("Expressa a ativar", na=False)]
    cur["Route"] = cur["Rota atualizada com movings"].astype(str).str.replace("|", ">", regex=False)
    cur = cur[_non_empty(cur["Rota atualizada com movings"]) & _non_empty(cur["Transit time atualizado"])]
    cur["TT"] = _tt_hhmm_to_hours(cur["Transit time atualizado"])
    cur["period_rampup_express"] = pd.to_datetime(
        cur["Data da última alteração"], format="%d/%b/%y", errors="coerce"
    )
    cur = cur[["Route", "TT", "period_rampup_express"]]

    old = raw.copy()
    # Bloco antigo usa Data de ramp-up quando disponível
    if "Data de ramp-up" in old.columns and "Data final de ramp-up" in old.columns:
        old = old[
            [
                "Rota atualizada com movings",
                "Transit time atualizado",
                "Data de ramp-up",
                "Data final de ramp-up",
            ]
        ].copy()
        old["Route"] = old["Rota atualizada com movings"].astype(str).str.replace("|", ">", regex=False)
        old = old[_non_empty(old["Rota atualizada com movings"]) & _non_empty(old["Transit time atualizado"])]
        old["TT"] = _tt_hhmm_to_hours(old["Transit time atualizado"])
        old["period_rampup_express"] = pd.to_datetime(
            old["Data de ramp-up"], format="%d/%b/%y", errors="coerce"
        )
        old = old[["Route", "TT", "period_rampup_express"]]
        cur = pd.concat([cur, old], axis=0)

    cur = cur.groupby(["Route", "TT"], as_index=False)["period_rampup_express"].min()
    return normalize_p1_express_df(cur)


def main() -> None:
    print("Carregando Outbound padrão (base) de", RANGE_BASE_OUTBOUND)
    base = conn.get_sheets(scopes=GSHEET_PRINT_OUTPUT, sh_name=RANGE_BASE_OUTBOUND)
    base = _normalize_base(base)
    print(f"  {len(base)} linhas / {base[COL_ROUTE].nunique()} rotas únicas")

    required = [COL_ROUTE, COL_LH_EXPRESS, COL_TT_WITH_EXPRESS, COL_TT_FINAL, COL_DISTANCE, COL_QUEUE]
    missing = [c for c in required if c not in base.columns]
    if missing:
        raise SystemExit(f"Base [T] 4.1 sem colunas: {missing}. Rode o Outbound padrão antes.")

    print("Carregando overrides de", RANGE_EXPRESS_MNGMT)
    mngmt = conn.get_sheets(scopes=GSHEET_PRINT_OUTPUT, sh_name=RANGE_EXPRESS_MNGMT)
    overrides = load_overrides_from_mngmt_df(mngmt)
    print(f"  {len(overrides)} rotas na lista com flag válido")
    if overrides:
        n_false = sum(1 for v in overrides.values() if v is False)
        n_true = sum(1 for v in overrides.values() if v is True)
        print(f"  force_normal(FALSE)={n_false}  force_express(TRUE)={n_true}")

    print("Carregando P1 (Implemented routes) e P2 (New TT)...")
    p1_express = _load_p1_express()
    df_new_tt = conn.get_sheets(scopes=GSHEET_NEW_TT_CORRIGIDO, sh_name=RANGE_NEW_TT_CORRIGIDO)
    p2_new_tt = build_p2_new_tt_dict(df_new_tt)
    print(f"  P1 routes={len(p1_express)}  P2 routes={len(p2_new_tt)}")

    patched, stats = apply_manual_express_overrides(
        base,
        overrides,
        p1_express=p1_express,
        p2_new_tt=p2_new_tt,
    )
    print(
        f"Override aplicado: changed={stats['n_changed']} "
        f"(to_normal={stats['n_to_normal']}, to_express={stats['n_to_express']}; "
        f"TT P1={stats['n_p1']} P2={stats['n_p2']} P3={stats['n_p3']})"
    )
    if stats["changed_routes"]:
        sample = stats["changed_routes"][:15]
        more = "" if len(stats["changed_routes"]) <= 15 else f" ... (+{len(stats['changed_routes']) - 15})"
        print(f"  Rotas alteradas: {sample}{more}")

    assert_non_override_rows_identical(base, patched, overrides)
    print("OK: linhas fora da lista idênticas à base.")

    write_cols = [c for c in COLS_OUTPUT if c in patched.columns]
    if not write_cols:
        write_cols = list(patched.columns)
    routes_output = _prepare_for_sheets_write(patched[write_cols])

    print("Limpando destino e gravando resultado...")
    conn.clean_specific_range(
        sheet_id=GSHEET_PRINT_OUTPUT,
        sheet_name=RANGE_PRINT_OUTPUT.split("!")[0],
        range_to_clear=RANGE_PRINT_OUTPUT_CLEAR,
    )

    batch_size = 50000
    print_line_buffer = 2
    num_batches = int(routes_output.shape[0] / batch_size) + 1
    for i in range(num_batches):
        add_line_title = 1 if i > 0 else 0
        sh_range = RANGE_PRINT_OUTPUT + str(1 + i * batch_size + print_line_buffer + add_line_title)
        print(f"Escrevendo batch {i + 1} de {num_batches}...")
        try:
            conn.print_in_sheets(
                scopes=GSHEET_PRINT_OUTPUT,
                sh_name=sh_range,
                df=routes_output.iloc[i * batch_size : (i + 1) * batch_size],
                print_columns=(i == 0),
            )
        except Exception:
            print("print in sheets failed, trying again.")
            conn.print_in_sheets(
                scopes=GSHEET_PRINT_OUTPUT,
                sh_name=sh_range,
                df=routes_output.iloc[i * batch_size : (i + 1) * batch_size],
                print_columns=False,
            )

    print("Concluído.")


if __name__ == "__main__":
    main()
