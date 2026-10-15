import re
import unicodedata

import pandas as pd

STATION_NAMES_API = "brbi_opslgc.station_names_malha"
STATION_NAMES_VERSION = "eymaywo48upoxm5j"

COL_STATION_CODE = "station_code"
COL_STATE_NAME = "state_name"
COL_STATUS = "status"
COL_XPT = "XPT"
COL_LMH = "LMH"
COL_ESTADO = "estado"
COL_REGIONAL = "regional"

STATION_PRIORITY_COLS = [COL_XPT, COL_LMH]
HUB_UF_PATTERN = re.compile(r"^HUB-L([A-Z]{2})", re.IGNORECASE)

STATE_NAME_TO_UF = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "distrito federal": "DF",
    "espirito santo": "ES",
    "goias": "GO",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "para": "PA",
    "paraiba": "PB",
    "parana": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}

UF_TO_REGIONAL = {
    "AC": "Norte",
    "AP": "Norte",
    "AM": "Norte",
    "PA": "Norte",
    "RO": "Norte",
    "RR": "Norte",
    "TO": "Norte",
    "AL": "Nordeste",
    "BA": "Nordeste",
    "CE": "Nordeste",
    "MA": "Nordeste",
    "PB": "Nordeste",
    "PE": "Nordeste",
    "PI": "Nordeste",
    "RN": "Nordeste",
    "SE": "Nordeste",
    "DF": "Centro-oeste",
    "GO": "Centro-oeste",
    "MS": "Centro-oeste",
    "MT": "Centro-oeste",
    "ES": "Sudeste",
    "MG": "Sudeste",
    "RJ": "Sudeste",
    "SP": "Sudeste",
    "PR": "Sul",
    "RS": "Sul",
    "SC": "Sul",
}


def normalize_state_name(name):
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def state_name_to_uf(state_name):
    normalized = normalize_state_name(state_name)
    if not normalized:
        return ""
    return STATE_NAME_TO_UF.get(normalized, "")


def uf_to_regional(uf):
    if not uf:
        return ""
    return UF_TO_REGIONAL.get(uf, "")


def _clean_station_code(code):
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    text = str(code).strip()
    if not text:
        return ""
    return text.replace("(XD)", "")


def _is_filled(code):
    return bool(_clean_station_code(code))


def build_station_state_lookup(df_stations):
    df = df_stations.copy()
    df[COL_STATION_CODE] = df[COL_STATION_CODE].astype(str).str.strip()
    df[COL_STATE_NAME] = df[COL_STATE_NAME].astype(str).str.strip()
    if COL_STATUS in df.columns:
        df[COL_STATUS] = pd.to_numeric(df[COL_STATUS], errors="coerce").fillna(0)
        df = df.sort_values(by=[COL_STATION_CODE, COL_STATUS], ascending=[True, False])
    df = df.drop_duplicates(subset=[COL_STATION_CODE], keep="first")
    return df.set_index(COL_STATION_CODE)[COL_STATE_NAME]


def _valid_state_name(state_name):
    if state_name is None or (isinstance(state_name, float) and pd.isna(state_name)):
        return ""
    text = str(state_name).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def _lookup_uf_from_api(station_lookup, code):
    cleaned = _clean_station_code(code)
    if not cleaned:
        return ""
    state_name = _valid_state_name(station_lookup.get(cleaned, ""))
    if not state_name:
        return ""
    return state_name_to_uf(state_name)


def extract_uf_from_hub_code(code):
    cleaned = _clean_station_code(code)
    if not cleaned:
        return ""
    match = HUB_UF_PATTERN.match(cleaned)
    if not match:
        return ""
    uf = match.group(1).upper()
    if uf in UF_TO_REGIONAL:
        return uf
    return ""


def _resolve_uf_for_row(row, station_lookup):
    xpt_code = row.get(COL_XPT, "")
    lmh_code = row.get(COL_LMH, "")

    if _is_filled(xpt_code):
        uf = _lookup_uf_from_api(station_lookup, xpt_code)
        if uf:
            return uf

    if _is_filled(lmh_code):
        uf = _lookup_uf_from_api(station_lookup, lmh_code)
        if uf:
            return uf
        return extract_uf_from_hub_code(lmh_code)

    return ""


def add_estado_regional(df, station_lookup):
    result = df.copy()
    result[COL_ESTADO] = result.apply(lambda row: _resolve_uf_for_row(row, station_lookup), axis=1)
    result[COL_REGIONAL] = result[COL_ESTADO].map(uf_to_regional)

    missing_mask = result[COL_ESTADO] == ""
    if missing_mask.any():
        print(f"Estado/regional não resolvido para {missing_mask.sum()} linha(s).")

    return result
