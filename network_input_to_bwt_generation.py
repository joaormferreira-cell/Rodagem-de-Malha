#primeiro arquivo - Adaptado para processamento de um único mês
import pandas as pd
import numpy as np
import os
import sys
from datetime import datetime

# Adiciona o diretório pai ao sys.path para permitir importações dos módulos na raiz
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from connection_with_path import GmailEntry
from hive_lib import get_df_demand, insert_df_into_hive, get_df_from_dataservice


credential_path = os.path.join(PARENT_DIR, 'credential', 'jards.json')
conn = GmailEntry(None, None, None, credential_path)

# -------------- Definitions paths ----------------
# # network input
GSHEET_SCOPE_NETWORK_INPUT = "1S54tFjLI2sT8loUSCnexEGp_Z9ryKD1p8MugmhT5P34" # FY 2026 maio- saída da query automations
GSHEET_RANGE_NETWORK_INPUT = "Base" # FY 2026

# # gsheets output
GSHEET_SCOPE_PRINT_OUTPUT = '1e0NtmrB8jtn-PICUejjg8iNGcWX0O9sAVSctkLh0T1s'  # BWT Model - saída do código automations
GSHEET_RANGE_PRINT_OUTPUT_WRITE = 'Network Input!A' 
GSHEET_RANGE_PRINT_OUTPUT_CLEAR = "A1:W"

# sheets from distances inputs
GSHEET_SCOPE_DISTANCES_INPUT = '1-XOdOIY0Ik4cBmyb4YdpCKKmEXQJW1iLOS8-rFjhkwQ' 
GSHEET_RANGE_DISTANCES_INPUT = '0.0 Distances Available!A1:I'

# sheets from lat and lons
GSHEET_SCOPE_LAT_LON = '1j_-RWpY8l51uRoghLLfBbI10YCUM6DmbjHxJUzsaz2I' 
GSHEET_RANGE_LAT_LON_BASE_STATIONS = "0.0 Station List Historical!A1:D"
GSHEET_SCOPE_LAT_LON_NEW_OPS = '1hZSIsOUFpf5oQ7hw6bckUvq3_tZiPCCSeBOLyIstyqI'
GSHEET_RANGE_LAT_LON_BASE_STATIONS_NEW_OPS = 'Base!A2:G'

# Relatorio de paths afetados por falta de distancia/lat-long (2 abas no Sheets)
# Nomes EXATOS das abas a criar no arquivo (sem "!A" no nome da aba):
SHEET_TAB_LAT_LON_RESUMO = "Resumo_lat_lon"
SHEET_TAB_LAT_LON_DETAIL = "Paths_afetados"
PRINT_LAT_LON_REPORT_SHEETS = True
GSHEET_LAT_LON_REPORT = "1B2CFDdLbv8OERES43rI-9M4c_2rksLyRtjpIhWFHySI"
RANGE_LAT_LON_REPORT_RESUMO_WRITE = f"{SHEET_TAB_LAT_LON_RESUMO}!A"
RANGE_LAT_LON_REPORT_RESUMO_CLEAR = "A1:Z100"
RANGE_LAT_LON_REPORT_DETAIL_WRITE = f"{SHEET_TAB_LAT_LON_DETAIL}!A"
RANGE_LAT_LON_REPORT_DETAIL_CLEAR = "A1:K5000"
LAT_LON_REPORT_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{GSHEET_LAT_LON_REPORT}"

# -------------- CONSTANTS ------------------------
PRINT_SHEETS = False
PRINT_HIVE = True
READ_FROM_HIVE = True
# False = usa só "Station List Historical" para lat/long e cadastro de operações.
# True  = concatena também "Network Station List (Base)" (planilha GSHEET_SCOPE_LAT_LON_NEW_OPS),
#         útil quando há operações novas na Base que ainda não estão no Historical.
# Como ativar: USE_NEW_OPS_LAT_LON_DEFAULT = True  OU  variável de ambiente USE_NEW_OPS_LAT_LON=1
USE_NEW_OPS_LAT_LON_DEFAULT = True
USE_NEW_OPS_LAT_LON = os.environ.get("USE_NEW_OPS_LAT_LON", str(USE_NEW_OPS_LAT_LON_DEFAULT)).strip().lower() in ("1", "true", "yes")

CONST_EARTH_R = 6371.0
CONST_MULTIPLIER_DIST_HAVERSINE = 1.4
CONST_CROSSDOCK = "(XD)"
CONST_3PL = "3PL"

CONST_PRINT_WITHOUT_STATION_BREAK = False

CONST_FM = "FMH"
CONST_SOC = "SOC"
CONST_FBS = "FBS"
CONST_LMH = "HUB"
CONST_XPT = "XPT"

# Network input
COL_PERIOD_NW = 'period_start'
COL_PERIOD_END_NW = "period_end"
COL_ORIGIN_NW = "origin"
COL_DEST_NW = "destination"
COL_PATH_NW = "path"
COL_ADO_NW = "forecast_ado"
COL_FM_NW = "FMH"
COLS_SOCS_NW = ["SOC1", "SOC2", "SOC3", "SOC4"]
COL_LMH_NW = "LMH"
COL_XPT_NW = "XPT"

COL_ADO_OUT = "ADO"
COL_ORIGIN_OUT = "ORIGIN"
COL_DEST_OUT = "DESTINATION"
COL_PATH_OUT = "E2E Path"

COL_ERRO_OUT = "ERRO"
COL_TRECHOS_SEM_DIST = "trechos_sem_distancia"

COLS_STATIONS_NW = [COL_FM_NW] + COLS_SOCS_NW + [COL_LMH_NW, COL_XPT_NW]
COLS_DISTANCES_NW = ["FMH-SOC","SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT"]
COLS_OUT_NW = [COL_PERIOD_NW, COL_PERIOD_END_NW, COL_ORIGIN_OUT, COL_DEST_OUT, COL_PATH_OUT, COL_ADO_OUT] + COLS_STATIONS_NW + COLS_DISTANCES_NW + [COL_ERRO_OUT]
COLS_OUT_REDUCED = [COL_PERIOD_NW, COL_ORIGIN_OUT, COL_DEST_OUT, COL_PATH_OUT, COL_ADO_OUT] + COLS_DISTANCES_NW + [COL_ERRO_OUT]

# Aux network columns
COL_LIST_STATIONS_NW = "list_stations"
COL_LIST_DISTANCES_NW = "list_distances"

from_station_to_distance = {('FMH', 'SOC1'):'FMH-SOC', ('FMH', 'LMH'):'FMH-HUB', 
                            ('SOC1', 'SOC2'):'SOC1-SOC2', ('SOC2', 'SOC3'):'SOC2-SOC3', ('SOC3', 'SOC4'):'SOC3-SOC4', 
                            ('SOC1', 'FMH'):'SOC1-SOC2', ('SOC2', 'FMH'):'SOC2-SOC3', ('SOC3', 'FMH'):'SOC3-SOC4',
                            ('SOC1', 'LMH'):'SOC-HUB', ('SOC2', 'LMH'):'SOC-HUB', ('SOC3', 'LMH'):'SOC-HUB', ('SOC4', 'LMH'):'SOC-HUB', 
                            ('SOC1', 'XPT'):'SOC-XPT', ('SOC2', 'XPT'):'SOC-XPT', ('SOC3', 'XPT'):'SOC-XPT', ('SOC4', 'XPT'):'SOC-XPT',
                            ('LMH', 'XPT'):'HUB-XPT'}
# Distances
COL_DISTANCE_DIST = "distance_km"
COL_ORIGIN_DIST = "origin"
COL_ROUTE_TYPE_DIST = "route_type"
COL_DEST_DIST = "destini"
COL_ROUTE_DIST = "route"

COL_ROUTE_INV_DIST = "route_inv"

# Lat Lon Base
COL_STATION_BASE = "station_code"
COL_STATION_TYPE_BASE = "station_type"
COL_LAT_BASE = "latitude"
COL_LON_BASE = "longitude"

# ----------------- Load inputs ------------------------
if READ_FROM_HIVE:
    # Usando o Service ID e credenciais fornecidos para a nova API no DataSuite
    service_id = 'brbi_opslgc.demanda_bwt_'
    app_key = os.environ.get('APP_KEY')
    app_secret = os.environ.get('APP_SECRET')
    
    print(f"Buscando dados via Data Service API: {service_id}")
    df_networks = get_df_from_dataservice(
        api_abbr=service_id, 
        version='x0lsfvvqjz38wfs3',
        app_key=app_key, 
        app_secret=app_secret
    )

    # Verificação e rename de colunas caso venham em minúsculo ou com nomes diferentes
    cols_rename = {
        'forecast_ado': COL_ADO_NW,
        'origin': COL_ORIGIN_NW,
        'destination': COL_DEST_NW,
        'path': COL_PATH_NW,
        'period_start': COL_PERIOD_NW,
        'ADO': COL_ADO_NW,  # Compatibilidade com hive_lib upper case
        'ORIGIN': COL_ORIGIN_NW,
        'DESTINATION': COL_DEST_NW,
        'E2E Path': COL_PATH_NW
    }
    df_networks = df_networks.rename(columns=cols_rename)
    
    if not df_networks.empty:
        print(f"Sucesso! {len(df_networks)} linhas carregadas da API.")
    else:
        print("Aviso: Nenhum dado retornado pela API.")
else:
    df_networks = conn.get_sheets(scopes=GSHEET_SCOPE_NETWORK_INPUT, sh_name=GSHEET_RANGE_NETWORK_INPUT)

df_lat_lon_station_base = conn.get_sheets(scopes=GSHEET_SCOPE_LAT_LON, sh_name=GSHEET_RANGE_LAT_LON_BASE_STATIONS)
if USE_NEW_OPS_LAT_LON:
    df_lat_lon_station_base_new_ops = conn.get_sheets(scopes=GSHEET_SCOPE_LAT_LON_NEW_OPS, sh_name=GSHEET_RANGE_LAT_LON_BASE_STATIONS_NEW_OPS)
    df_lat_lon_station_base_new_ops = df_lat_lon_station_base_new_ops.rename(columns={
        "CODE": "Code",
    })
    df_lat_lon_station_base_new_ops = df_lat_lon_station_base_new_ops[["Code", "Lat", "Lon"]]
    df_lat_lon_station_base_new_ops = df_lat_lon_station_base_new_ops.rename(columns={
        "Code": "station_code",
        "Lat": "latitude",
        "Lon": "longitude"
    })
else:
    print("Aviso: Network Station List (Base) desabilitado; usando apenas Station List Historical.")
    df_lat_lon_station_base_new_ops = pd.DataFrame(columns=["station_code", "latitude", "longitude"])
df_lat_lon_station_base = df_lat_lon_station_base[["station_code", "latitude", "longitude"]]
df_lat_lon_station_base = pd.concat([df_lat_lon_station_base, df_lat_lon_station_base_new_ops])  
df_distances = conn.get_sheets(scopes=GSHEET_SCOPE_DISTANCES_INPUT, sh_name=GSHEET_RANGE_DISTANCES_INPUT)

#------------------ Treat and clean inputs -------------
# convert to numeric
df_networks[COL_ADO_NW] = pd.to_numeric(df_networks[COL_ADO_NW], errors="coerce")

# DELETE 3PL IN DESTINATION
df_networks = df_networks[~(df_networks[COL_DEST_NW]==CONST_3PL)]

# convert to datetime
df_networks[COL_PERIOD_NW] = pd.to_datetime(df_networks[COL_PERIOD_NW]).dt.normalize()

# get distances that are in the inverse way
df_distances_inv = df_distances[[COL_ORIGIN_DIST, COL_DEST_DIST, COL_DISTANCE_DIST]].rename(
    columns={COL_ORIGIN_DIST:COL_DEST_DIST, COL_DEST_DIST:COL_ORIGIN_DIST})
# create route inv
df_distances_inv[COL_ROUTE_DIST] = df_distances_inv[COL_ORIGIN_DIST] + ">" + df_distances_inv[COL_DEST_DIST]
df_distances = pd.concat([df_distances[[COL_ORIGIN_DIST, COL_DEST_DIST, COL_DISTANCE_DIST, COL_ROUTE_DIST]], df_distances_inv[[COL_ORIGIN_DIST, COL_DEST_DIST, COL_DISTANCE_DIST, COL_ROUTE_DIST]]])
# drop duplicates
df_distances = df_distances.drop_duplicates(subset=[COL_ROUTE_DIST], keep='first').reset_index(drop=True)
# convert to numeric 
df_distances[COL_DISTANCE_DIST] = pd.to_numeric(df_distances[COL_DISTANCE_DIST], errors="coerce")

# convert to dict
dict_distances = df_distances.set_index(COL_ROUTE_DIST)[COL_DISTANCE_DIST].to_dict()

# clean lat lon
df_lat_lon_station_base = df_lat_lon_station_base[(df_lat_lon_station_base[COL_STATION_BASE]!="") & (~(df_lat_lon_station_base[COL_STATION_BASE].isna()))]
df_lat_lon_station_base = df_lat_lon_station_base.drop_duplicates(subset=[COL_STATION_BASE], keep='first').reset_index(drop=True)
# convert to numeric 
df_lat_lon_station_base[COL_LAT_BASE] = pd.to_numeric(df_lat_lon_station_base[COL_LAT_BASE], errors="coerce")
df_lat_lon_station_base[COL_LON_BASE] = pd.to_numeric(df_lat_lon_station_base[COL_LON_BASE], errors="coerce")

# convert to dict
dict_lat = df_lat_lon_station_base.set_index(COL_STATION_BASE)[COL_LAT_BASE].to_dict()
dict_lon = df_lat_lon_station_base.set_index(COL_STATION_BASE)[COL_LON_BASE].to_dict()
known_stations = set(df_lat_lon_station_base[COL_STATION_BASE].tolist())
# --------------- Functions ---------------------------

def _station_exists(code, known_stations):
    return code in known_stations


def _station_missing_lat_lon(code, dict_lat, dict_lon):
    if code not in dict_lat or code not in dict_lon:
        return True
    la, lo = dict_lat[code], dict_lon[code]
    if la == "" or lo == "":
        return True
    if pd.isna(la) or pd.isna(lo):
        return True
    return False


def _codes_from_path(path):
    codes = []
    for raw in str(path).split(">"):
        code = raw.replace(CONST_CROSSDOCK, "").strip()
        if code:
            codes.append(code)
    return codes


def classify_stations_from_paths(df, path_col, known_stations, dict_lat, dict_lon):
    """
    Classifica estações dos paths em:
    - missing_operations: código inexistente na base de estações (erro crítico).
    - missing_lat_lon: código existe, mas sem latitude/longitude válidas (aviso).
    """
    missing_operations = set()
    missing_lat_lon = set()
    if df.empty or path_col not in df.columns:
        return sorted(missing_operations), sorted(missing_lat_lon)
    for path in df[path_col].dropna().unique():
        for code in _codes_from_path(path):
            if not _station_exists(code, known_stations):
                missing_operations.add(code)
            elif _station_missing_lat_lon(code, dict_lat, dict_lon):
                missing_lat_lon.add(code)
    return sorted(missing_operations), sorted(missing_lat_lon)


def compute_distance_haversine_advanced(lat1, lon1, lat2, lon2):
    # 1. Convert to radians
    for coord in (lat1, lon1, lat2, lon2):
        if coord == "" or pd.isna(coord):
            return -1
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    # 2. Compute coordiante diffs
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    # 3. Aplica a fórmula de Haversine
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
    c = 2 * np.arcsin(np.sqrt(a))
    distance = CONST_EARTH_R * c
    final_distance = distance * CONST_MULTIPLIER_DIST_HAVERSINE 
    return final_distance

def _missing_codes_for_failed_routes(distances, routes_wo_xd, dict_lat, dict_lon):
    missing_codes = set()
    for dist, route in zip(distances, routes_wo_xd):
        if dist != -1:
            continue
        parts = route.split(">")
        if len(parts) >= 2:
            o, d = parts[0], parts[1]
            if _station_missing_lat_lon(o, dict_lat, dict_lon):
                missing_codes.add(o)
            if _station_missing_lat_lon(d, dict_lat, dict_lon):
                missing_codes.add(d)
    return missing_codes


def create_list_stations_distances(list_stations, dict_distances, dict_lat, dict_lon, lat_lon_report=None):
    """
    Return a list with distances for each line of a data frame, the distance is either from a data base or Distance Haversine Advanced.
    Trechos sem distância cadastrada e sem lat/lon recebem -1 (linha marcada como inválida downstream).
    """
    routes_wo_xd = [list_stations[i].replace(CONST_CROSSDOCK, '') + ">" + list_stations[i+1].replace(CONST_CROSSDOCK, '')
                    for i in range(len(list_stations)-1)]
    distances = [dict_distances.get(route, "") for route in routes_wo_xd]
    if "" in distances:
        distances = [compute_distance_haversine_advanced(dict_lat.get(route.split(">")[0], ""),
                                                         dict_lon.get(route.split(">")[0], ""),
                                                         dict_lat.get(route.split(">")[1], ""),
                                                         dict_lon.get(route.split(">")[1], ""))
                     if dist == "" else dist
                     for dist, route in zip(distances, routes_wo_xd)]
        if -1 in distances and lat_lon_report is not None:
            missing_codes = _missing_codes_for_failed_routes(distances, routes_wo_xd, dict_lat, dict_lon)
            lat_lon_report["affected_path_count"] += 1
            lat_lon_report["stations_causing_distance_failure"].update(missing_codes)
    return distances

def stations_distances_to_columns(station_list, distances_list):
    dict_pos_df = {}
    allocation = []

    # Get stations types
    stations_type_list = [item[:3] for item in station_list]

    n_allocated = 0
    max_allocated = len(stations_type_list)

    # 1) Try FMH
    if ((stations_type_list[0]==CONST_FM) | (stations_type_list[0]==CONST_FBS)):
        # allocate
        dict_pos_df[COL_FM_NW] = station_list[0]
        # keep alocation value
        allocation.append(COL_FM_NW)
        # mark that first station was allocated
        n_allocated = n_allocated + 1

    # 2) Loop for stations not allocated yet
    n_soc = 0
    for i in range(n_allocated, max_allocated):
        # check if LMH 
        if (stations_type_list[i] == CONST_LMH):
            # allocate
            dict_pos_df[COL_LMH_NW] = station_list[i]
            # keep alocation value
            allocation.append(COL_LMH_NW)

        # check if XPT 
        elif (stations_type_list[i] == COL_XPT_NW):
            if allocation[i-1] != CONST_FM:
                # allocate
                dict_pos_df[COL_XPT_NW] = station_list[i]
                # keep alocation value
                allocation.append(COL_XPT_NW)
            else:
                # allocate erro FMH->XPT
                dict_pos_df[COL_ERRO_OUT] = station_list[i]
                # keep alocation value
                allocation.append(COL_ERRO_OUT)
                # print("ERROR: Route {station_list}")
        elif n_soc < len(COLS_SOCS_NW):
            # allocate
            dict_pos_df[COLS_SOCS_NW[n_soc]] = station_list[i]
            # keep alocation value
            allocation.append(COLS_SOCS_NW[n_soc])
        else:
            # allocate erro: too many SOCs
            dict_pos_df[COL_ERRO_OUT] = station_list[i]
            # keep alocation value
            allocation.append(COL_ERRO_OUT)
            # print("ERROR: Route {station_list}")
        n_soc = n_soc + 1

    # 3) Map distances to columns the allocation station values
    dict_pos_distances = {from_station_to_distance.get((allocation[i],allocation[i+1]),COL_ERRO_OUT):distances_list[i] 
                          for i in range(len(allocation)-1)}
    dict_pos_df.update(dict_pos_distances)

    return dict_pos_df


LAT_LON_ERROR_PREFIX = "sem distancia/lat-lon: "
ERRO_TIPO_LAT_LON = "lat_lon"
ERRO_TIPO_MAPEAMENTO = "mapeamento"
ERRO_TIPO_ESTRUTURA = "estrutura"


def _parse_erro_operacoes(erro_msg):
    text = str(erro_msg).strip()
    if text.startswith(LAT_LON_ERROR_PREFIX):
        return text[len(LAT_LON_ERROR_PREFIX):]
    return text


def _is_distance_lat_lon_error(erro_msg):
    return str(erro_msg).strip().startswith(LAT_LON_ERROR_PREFIX)


def _classify_path_erro(erro_msg):
    text = str(erro_msg).strip()
    if not text:
        return None, ""
    if text.startswith(LAT_LON_ERROR_PREFIX):
        return ERRO_TIPO_LAT_LON, (
            "Trecho sem distancia cadastrada e sem lat/lon valido para calcular via Haversine."
        )
    try:
        float(text)
        return ERRO_TIPO_MAPEAMENTO, (
            "Path com estrutura nao suportada pelo modelo de colunas BWT "
            "(ex: mais de 4 SOCs, FMH no meio do path, transicao entre estacoes nao mapeada). "
            f"O valor numerico em ERRO ({text}) e uma distancia calculada que nao coube em nenhuma coluna de saida."
        )
    except ValueError:
        return ERRO_TIPO_ESTRUTURA, (
            f"Erro de alocacao de estacao no path (ex: FMH direto para XPT, excesso de SOCs): {text}"
        )


def _count_soc_in_path(path):
    return sum(1 for code in _codes_from_path(path) if str(code).startswith(CONST_SOC))


def _count_paths_by_error_type(network_output):
    counts = {ERRO_TIPO_LAT_LON: 0, ERRO_TIPO_MAPEAMENTO: 0, ERRO_TIPO_ESTRUTURA: 0}
    for erro in network_output[COL_ERRO_OUT].astype(str).str.strip():
        if not erro:
            continue
        tipo, _ = _classify_path_erro(erro)
        if tipo:
            counts[tipo] += 1
    return counts


def print_lat_lon_report_summary(network_output, lat_lon_report, lat_lon_report_exported):
    """
    Resumo legivel no terminal: o que falhou, por que e como corrigir.
    """
    counts = _count_paths_by_error_type(network_output)
    n_lat_lon = counts[ERRO_TIPO_LAT_LON]
    n_mapeamento = counts[ERRO_TIPO_MAPEAMENTO]
    n_estrutura = counts[ERRO_TIPO_ESTRUTURA]
    n_total = n_lat_lon + n_mapeamento + n_estrutura
    all_stations_without_coords = sorted(
        lat_lon_report["stations_without_coords"] | lat_lon_report["stations_causing_distance_failure"]
    )
    station_sources = (
        "Station List Historical + Network Station List (Base)"
        if USE_NEW_OPS_LAT_LON
        else "Station List Historical"
    )

    print("\n" + "=" * 72)
    print("DIAGNOSTICO DE PATHS COM ERRO")
    print("=" * 72)

    if n_total == 0 and not all_stations_without_coords:
        print("Nenhum path com ERRO neste run.")
        print("=" * 72)
        return

    print(f"Total de paths com ERRO: {n_total}")
    if n_lat_lon:
        print(f"  - lat/lon (falta distancia ou coordenadas): {n_lat_lon}")
    if n_mapeamento:
        print(f"  - mapeamento (estrutura do path nao suportada): {n_mapeamento}")
    if n_estrutura:
        print(f"  - estrutura (alocacao invalida de estacoes): {n_estrutura}")
    print()

    if all_stations_without_coords or n_lat_lon > 0:
        print("-" * 72)
        print("TIPO: lat/lon — trecho sem distancia cadastrada e sem coordenadas")
        print("-" * 72)
        if all_stations_without_coords:
            print(f"Operacoes sem coordenadas validas em '{station_sources}':")
            for code in all_stations_without_coords:
                print(f"  - {code}")
            print(f"Total: {len(all_stations_without_coords)} operacao(oes)")
        print(f"Paths E2E afetados: {n_lat_lon}")
        if n_lat_lon > 0:
            mask = network_output[COL_ERRO_OUT].astype(str).str.strip().apply(_is_distance_lat_lon_error)
            ado_afetado = pd.to_numeric(
                network_output.loc[mask, COL_ADO_OUT], errors="coerce"
            ).fillna(0.0).sum()
            print(f"ADO total dos paths afetados: {ado_afetado:,.2f}")

        print("\nCOMO CORRIGIR (escolha UMA das opcoes por trecho):")
        print("  Opcao A - Cadastrar distancia do trecho:")
        print("    Planilha: 0.0 Distances Available")
        print(f"    ID: {GSHEET_SCOPE_DISTANCES_INPUT}")
        print("    Colunas: origin | destini | distance_km (trecho no formato ORIGEM>DESTINO)")
        print("  Opcao B - Cadastrar lat/lon da operacao:")
        print(f"    Planilha: {station_sources}")
        print(f"    Historical ID: {GSHEET_SCOPE_LAT_LON}")
        if USE_NEW_OPS_LAT_LON:
            print(f"    New Ops (Base) ID: {GSHEET_SCOPE_LAT_LON_NEW_OPS}")
        print("  Depois de corrigir, rode este script novamente.\n")

    if n_mapeamento > 0:
        print("-" * 72)
        print("TIPO: mapeamento — estrutura do path nao cabe no modelo BWT")
        print("-" * 72)
        print(
            "O modelo de saida suporta: FMH + ate 4 SOCs (SOC1..SOC4) + HUB + XPT.\n"
            "Paths com mais de 4 SOCs, FMH no meio (ex: crossdock), ou transicoes\n"
            "nao previstas fazem a distancia calculada ir para a coluna ERRO como numero.\n"
            "Isso NAO e problema de lat/lon nem de distancia faltando — a distancia foi\n"
            "calculada, mas o script nao sabe em qual coluna de saida coloca-la."
        )
        mapeamento_mask = network_output[COL_ERRO_OUT].astype(str).str.strip().apply(
            lambda x: _classify_path_erro(x)[0] == ERRO_TIPO_MAPEAMENTO
        )
        df_map = network_output.loc[mapeamento_mask, [COL_PATH_OUT, COL_ADO_OUT]].copy()
        df_map["n_socs"] = df_map[COL_PATH_OUT].map(_count_soc_in_path)
        soc_dist = df_map["n_socs"].value_counts().sort_index()
        print("\nDistribuicao de SOCs nos paths com erro de mapeamento:")
        for n_soc, qtd in soc_dist.items():
            flag = " <- acima do limite de 4" if n_soc > len(COLS_SOCS_NW) else ""
            print(f"  - {int(n_soc)} SOC(s): {int(qtd)} path(s){flag}")
        print(f"\nPaths E2E afetados: {n_mapeamento}")
        ado_map = pd.to_numeric(df_map[COL_ADO_OUT], errors="coerce").fillna(0.0).sum()
        print(f"ADO total dos paths afetados: {ado_map:,.2f}")
        print("\nCOMO CORRIGIR:")
        print("  - Revisar/simplificar o path E2E na base de Network Input")
        print(f"    Planilha ID: {GSHEET_SCOPE_NETWORK_INPUT}")
        print("  - Ou expandir o modelo no codigo (mais SOCs / transicoes extras)")
        print("  - Cadastrar lat/lon ou distancia NAO resolve este tipo de erro.\n")
        sample = network_output.loc[mapeamento_mask, [COL_PATH_OUT, COL_ERRO_OUT]].drop_duplicates().head(5)
        if not sample.empty:
            print("Amostra de paths com erro de mapeamento:")
            for _, row in sample.iterrows():
                n_soc = _count_soc_in_path(row[COL_PATH_OUT])
                print(
                    f"  - [{n_soc} SOCs] {row[COL_PATH_OUT]} | ERRO={row[COL_ERRO_OUT]} (distancia nao alocada)"
                )

    if n_estrutura > 0:
        print("-" * 72)
        print("TIPO: estrutura — alocacao invalida de estacoes no path")
        print("-" * 72)
        print(f"Paths afetados: {n_estrutura}")
        print("Exemplos: FMH conectado direto a XPT, sequencia de estacoes invalida.")
        print("Correcao: revisar o path E2E na base de Network Input.")
        estrutura_mask = network_output[COL_ERRO_OUT].astype(str).str.strip().apply(
            lambda x: _classify_path_erro(x)[0] == ERRO_TIPO_ESTRUTURA
        )
        sample = network_output.loc[estrutura_mask, [COL_PATH_OUT, COL_ERRO_OUT]].drop_duplicates().head(5)
        if not sample.empty:
            print("Amostra:")
            for _, row in sample.iterrows():
                print(f"  - path: {row[COL_PATH_OUT]} | ERRO: {row[COL_ERRO_OUT]}")

    if lat_lon_report_exported and n_total > 0:
        print("-" * 72)
        print("DETALHAMENTO EXPORTADO (Google Sheets):")
        print(f"  URL: {LAT_LON_REPORT_SHEET_URL}")
        print(f'  Aba "{SHEET_TAB_LAT_LON_RESUMO}": resumo por tipo de erro e metricas')
        print(f'  Aba "{SHEET_TAB_LAT_LON_DETAIL}": lista dos {n_total} paths com ERRO')
    elif n_total > 0:
        print("AVISO: exportacao para Google Sheets falhou — veja mensagem de AVISO acima.")

    print("=" * 72 + "\n")


def build_lat_lon_report_dfs(network_output, lat_lon_report):
    """
    Monta DataFrames para abas Resumo e Paths afetados (todos os tipos de ERRO).
    """
    mask_affected = network_output[COL_ERRO_OUT].astype(str).str.strip().ne("")
    df_affected = network_output.loc[mask_affected].copy()
    if df_affected.empty:
        return pd.DataFrame(), pd.DataFrame()

    df_affected[COL_ADO_OUT] = pd.to_numeric(df_affected[COL_ADO_OUT], errors="coerce").fillna(0.0)
    if COL_TRECHOS_SEM_DIST not in df_affected.columns:
        df_affected[COL_TRECHOS_SEM_DIST] = ""

    classified = df_affected[COL_ERRO_OUT].astype(str).str.strip().apply(_classify_path_erro)
    df_affected["tipo_erro"] = classified.map(lambda x: x[0])
    df_affected["descricao_erro"] = classified.map(lambda x: x[1])
    df_affected["n_socs"] = df_affected[COL_PATH_OUT].map(_count_soc_in_path)

    all_stations_without_coords = sorted(
        lat_lon_report["stations_without_coords"] | lat_lon_report["stations_causing_distance_failure"]
    )
    ado_total = float(df_affected[COL_ADO_OUT].sum())
    counts = _count_paths_by_error_type(df_affected)

    # --- Bloco 1: metricas gerais ---
    resumo_rows = [
        {"secao": "METRICAS GERAIS", "campo": "", "valor": ""},
        {"secao": "", "campo": "data_execucao", "valor": datetime.now().strftime("%Y-%m-%d %H:%M")},
        {"secao": "", "campo": "total_paths_com_erro", "valor": len(df_affected)},
        {"secao": "", "campo": "ado_total_afetado", "valor": ado_total},
        {"secao": "", "campo": "erros_lat_lon", "valor": counts[ERRO_TIPO_LAT_LON]},
        {"secao": "", "campo": "erros_mapeamento", "valor": counts[ERRO_TIPO_MAPEAMENTO]},
        {"secao": "", "campo": "erros_estrutura", "valor": counts[ERRO_TIPO_ESTRUTURA]},
        {"secao": "", "campo": "operacoes_sem_lat_long", "valor": ", ".join(all_stations_without_coords)},
        {"secao": "", "campo": "", "valor": ""},
    ]

    if counts[ERRO_TIPO_MAPEAMENTO] > 0:
        soc_dist = df_affected.loc[df_affected["tipo_erro"] == ERRO_TIPO_MAPEAMENTO, "n_socs"].value_counts().sort_index()
        resumo_rows.append({"secao": "MAPEAMENTO — SOCs por path (limite do modelo: 4)", "campo": "", "valor": ""})
        for n_soc, qtd in soc_dist.items():
            resumo_rows.append({
                "secao": "",
                "campo": f"{int(n_soc)} SOC(s)",
                "valor": f"qtd_paths={int(qtd)}",
            })
        resumo_rows.append({"secao": "", "campo": "", "valor": ""})

    # --- Bloco 2: trechos sem cadastro (somente lat_lon) ---
    leg_rows = []
    for _, row in df_affected.loc[df_affected["tipo_erro"] == ERRO_TIPO_LAT_LON].iterrows():
        ado = float(row[COL_ADO_OUT])
        for leg in str(row.get(COL_TRECHOS_SEM_DIST, "")).split(";"):
            leg = leg.strip()
            if leg:
                leg_rows.append({"trecho_sem_distancia": leg, "ado": ado})
    if leg_rows:
        df_legs = pd.DataFrame(leg_rows)
        df_legs_agg = (
            df_legs.groupby("trecho_sem_distancia", as_index=False)
            .agg(qtd_paths=("ado", "count"), ado_somado=("ado", "sum"))
            .sort_values("qtd_paths", ascending=False)
        )
        resumo_rows.append({"secao": "TRECHOS SEM CADASTRO (cadastrar em 0.0 Distances Available)", "campo": "", "valor": ""})
        for _, r in df_legs_agg.iterrows():
            resumo_rows.append({
                "secao": "",
                "campo": r["trecho_sem_distancia"],
                "valor": f"qtd_paths={int(r['qtd_paths'])} | ado_somado={r['ado_somado']:.2f}",
            })
        resumo_rows.append({"secao": "", "campo": "", "valor": ""})

    # --- Bloco 3: por operacao sem lat/long (somente lat_lon) ---
    op_rows = []
    for _, row in df_affected.loc[df_affected["tipo_erro"] == ERRO_TIPO_LAT_LON].iterrows():
        ado = float(row[COL_ADO_OUT])
        for code in _parse_erro_operacoes(row[COL_ERRO_OUT]).split(","):
            code = code.strip()
            if code:
                op_rows.append({"operacao": code, "ado": ado})
    if op_rows:
        df_ops = pd.DataFrame(op_rows)
        df_ops_agg = (
            df_ops.groupby("operacao", as_index=False)
            .agg(qtd_paths=("ado", "count"), ado_somado=("ado", "sum"))
            .sort_values("qtd_paths", ascending=False)
        )
        resumo_rows.append({"secao": "POR OPERACAO SEM LAT/LONG", "campo": "", "valor": ""})
        for _, r in df_ops_agg.iterrows():
            resumo_rows.append({
                "secao": "",
                "campo": r["operacao"],
                "valor": f"qtd_paths={int(r['qtd_paths'])} | ado_somado={r['ado_somado']:.2f}",
            })

    df_resumo = pd.DataFrame(resumo_rows)

    df_detail = df_affected[
        [
            COL_PERIOD_NW, COL_ORIGIN_OUT, COL_DEST_OUT, COL_PATH_OUT, COL_ADO_OUT,
            "tipo_erro", COL_ERRO_OUT, "descricao_erro", "n_socs", COL_TRECHOS_SEM_DIST,
        ]
    ].copy()
    df_detail = df_detail.rename(columns={
        COL_ERRO_OUT: "valor_erro",
        COL_TRECHOS_SEM_DIST: "trechos_sem_distancia",
    })
    df_detail = df_detail.fillna("")

    return df_resumo, df_detail


def export_lat_lon_report_to_sheets(conn, df_resumo, df_detail):
    """Limpa e reescreve as abas do relatorio a cada execucao. Retorna True se exportou com sucesso."""
    print(f"Limpando abas do relatorio lat/lon ({SHEET_TAB_LAT_LON_RESUMO}, {SHEET_TAB_LAT_LON_DETAIL})...")
    conn.clean_specific_range(
        sheet_id=GSHEET_LAT_LON_REPORT,
        sheet_name=SHEET_TAB_LAT_LON_RESUMO,
        range_to_clear=RANGE_LAT_LON_REPORT_RESUMO_CLEAR,
    )
    conn.clean_specific_range(
        sheet_id=GSHEET_LAT_LON_REPORT,
        sheet_name=SHEET_TAB_LAT_LON_DETAIL,
        range_to_clear=RANGE_LAT_LON_REPORT_DETAIL_CLEAR,
    )

    wrote_any = False
    if df_resumo is not None and not df_resumo.empty:
        print(f'Escrevendo aba "{SHEET_TAB_LAT_LON_RESUMO}"...')
        conn.print_in_sheets(
            scopes=GSHEET_LAT_LON_REPORT,
            sh_name=RANGE_LAT_LON_REPORT_RESUMO_WRITE + "1",
            df=df_resumo,
            print_columns=True,
        )
        wrote_any = True

    if df_detail is not None and not df_detail.empty:
        print(f'Escrevendo aba "{SHEET_TAB_LAT_LON_DETAIL}" ({len(df_detail)} linhas)...')
        batch_size = 50000
        num_batches = int(df_detail.shape[0] / batch_size) + 1
        for i in range(num_batches):
            sh_range = RANGE_LAT_LON_REPORT_DETAIL_WRITE + str(1 + i * batch_size)
            chunk = df_detail.iloc[i * batch_size : (i + 1) * batch_size]
            conn.print_in_sheets(
                scopes=GSHEET_LAT_LON_REPORT,
                sh_name=sh_range,
                df=chunk,
                print_columns=(i == 0),
            )
        wrote_any = True

    return wrote_any


# ----------- Compute Network format with distances and ADO -----------------
# periods_network = np.unique(df_networks[COL_PERIOD_NW])
# Get unique dates
unique_dates = df_networks[COL_PERIOD_NW].unique()
unique_dates_series = pd.Series(unique_dates)

# get min date for each month
first_dates_by_month = unique_dates_series.groupby(
    [unique_dates_series.dt.year, unique_dates_series.dt.month]
).min()

dict_networks = {period:df_networks.loc[df_networks[COL_PERIOD_NW] == period] for period in first_dates_by_month}

missing_operations, missing_lat_lon_warn = classify_stations_from_paths(
    df_networks, COL_PATH_NW, known_stations, dict_lat, dict_lon
)
if missing_operations:
    station_sources = "Station List Historical / Network Station List (Base)" if USE_NEW_OPS_LAT_LON else "Station List Historical"
    msg = (
        f"ERROR: The following station(s) are missing from {station_sources}:\n"
        + "\n".join(f"  - {code}" for code in missing_operations)
        + f"\n\nTotal: {len(missing_operations)} station(s). Add them to the spreadsheet(s) and run again."
    )
    print(msg)
    raise ValueError(msg)

lat_lon_report = {
    "stations_without_coords": set(missing_lat_lon_warn),
    "stations_causing_distance_failure": set(),
    "affected_path_count": 0,
}
if missing_lat_lon_warn:
    station_sources = "Station List Historical / Network Station List (Base)" if USE_NEW_OPS_LAT_LON else "Station List Historical"
    print(
        "AVISO: As operacoes abaixo existem em "
        f"{station_sources}, mas nao possuem latitude/longitude validas. "
        "O processamento continuara; rotas sem distancia cadastrada para esses trechos serao ignoradas.\n"
        + "\n".join(f"  - {code}" for code in missing_lat_lon_warn)
    )

for period in first_dates_by_month:
    # 0) Reset Index
    dict_networks[period].reset_index(inplace = True, drop = True)

    # 1) create list with stations for each period
    dict_networks[period][COL_LIST_STATIONS_NW] = dict_networks[period][COL_PATH_NW].str.split(">")

    # 2) Create a list with distances for routes
    list_distances = []
    for list_stations in dict_networks[period].loc[:, COL_LIST_STATIONS_NW].values:
        distance = create_list_stations_distances(
            list_stations, dict_distances, dict_lat, dict_lon, lat_lon_report=lat_lon_report
        )
        list_distances.append(distance)
    dict_networks[period][COL_LIST_DISTANCES_NW] = list_distances

    # 3) Put stations and distances in right columns
    list_pos_columns = []
    for line_list_stations, line_list_distances in dict_networks[period].loc[:, [COL_LIST_STATIONS_NW, COL_LIST_DISTANCES_NW]].values:
        dict_pos_cols_per_line = stations_distances_to_columns(line_list_stations, line_list_distances)
        if -1 in line_list_distances:
            routes_wo_xd = [
                line_list_stations[i].replace(CONST_CROSSDOCK, "")
                + ">"
                + line_list_stations[i + 1].replace(CONST_CROSSDOCK, "")
                for i in range(len(line_list_stations) - 1)
            ]
            failed_codes = _missing_codes_for_failed_routes(
                line_list_distances, routes_wo_xd, dict_lat, dict_lon
            )
            failed_legs = [routes_wo_xd[i] for i, d in enumerate(line_list_distances) if d == -1]
            dict_pos_cols_per_line[COL_TRECHOS_SEM_DIST] = "; ".join(failed_legs)
            dict_pos_cols_per_line[COL_ERRO_OUT] = (
                LAT_LON_ERROR_PREFIX + ", ".join(sorted(failed_codes))
            )
            for key, val in list(dict_pos_cols_per_line.items()):
                if val == -1:
                    dict_pos_cols_per_line[key] = "-1"
        list_pos_columns.append(dict_pos_cols_per_line)
    
    if list_pos_columns:
        # put ERRO column just to be sure 
        list_pos_columns[-1][COL_ERRO_OUT] = list_pos_columns[-1].get(COL_ERRO_OUT,"")
        # transform dict to data frame
        df_pos_columns = pd.DataFrame(list_pos_columns)
        # Append to Data Frame
        dict_networks[period] = pd.concat([dict_networks[period], df_pos_columns], axis = 1)  
    

# ------------ Treat to write to sheets ------------------
if not first_dates_by_month.empty:
    print("Gathering results")
    network_output = pd.concat([dict_networks[period] for period in first_dates_by_month])
    # convert date to string to print
    network_output[COL_PERIOD_NW] = network_output[COL_PERIOD_NW].astype(str)

    # fill na 
    network_output = network_output.fillna("")
    # rename some columns
    network_output = network_output.rename(columns={COL_PATH_NW:COL_PATH_OUT, COL_ADO_NW: COL_ADO_OUT, COL_ORIGIN_NW:COL_ORIGIN_OUT, COL_DEST_NW:COL_DEST_OUT})

    # Add OUTPUT columns if they do not exist
    for column in COLS_OUT_NW:
        # Se a coluna não existir no DataFrame
        if column not in network_output.columns:
            # Add columns with ""
            network_output[column] = ""

    # reset index
    network_output.reset_index(inplace=True, drop=True)

    if CONST_PRINT_WITHOUT_STATION_BREAK:
        COLS_OUT_NW = COLS_OUT_REDUCED

    # ------------ Clean sheets before writing -----------------------
    if PRINT_SHEETS:
        print("Cleaning sheets")
        # clean stations list
        conn.clean_specific_range(
            sheet_id=GSHEET_SCOPE_PRINT_OUTPUT,
            sheet_name=GSHEET_RANGE_PRINT_OUTPUT_WRITE.split("!")[0],
            range_to_clear = GSHEET_RANGE_PRINT_OUTPUT_CLEAR
        )

    # ----------- PRINT -----------------------
    if PRINT_SHEETS:
        print("Writing results to sheets")

        # Network output
        batch_size = 50000
        print_line_buffer = 0
        num_batches = int(network_output.shape[0]/batch_size)+1
        for i in range(num_batches):
            add_line_title = 1 if i > 0 else 0
            sh_range = GSHEET_RANGE_PRINT_OUTPUT_WRITE + str(1 + i*batch_size + print_line_buffer + add_line_title) 
            print(f"Escrevendo batch {i+1} de {num_batches} no Google Sheets...")
            try:
                conn.print_in_sheets(scopes=GSHEET_SCOPE_PRINT_OUTPUT, sh_name=sh_range,
                                    df=network_output.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUT_NW], print_columns=True if i == 0 else False)
            except Exception:
                print('print in sheets failed, trying again.')
                conn.print_in_sheets(scopes=GSHEET_SCOPE_PRINT_OUTPUT, sh_name=sh_range,
                                    df=network_output.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUT_NW], print_columns=False)

    # -------- PRINT HIVE -------------------

    if PRINT_HIVE:
        # https://datasuite.shopee.io/datahub/normal/ingestion/417309
        api_endpoint = 'https://datasuite.shopee.io/datahub/api/v1/usertoken/upload/csv/csv-cd1b372b-f63f-4d86-815c-fecef4dd2d3a'
        ingestion_token = 

        insert_df_into_hive(network_output[COLS_OUT_NW], api_endpoint, ingestion_token)

    lat_lon_report_exported = False
    if PRINT_LAT_LON_REPORT_SHEETS:
        df_resumo, df_detail = build_lat_lon_report_dfs(network_output, lat_lon_report)
        try:
            lat_lon_report_exported = export_lat_lon_report_to_sheets(conn, df_resumo, df_detail)
        except Exception as exc:
            print(f"AVISO: Falha ao exportar relatorio lat/lon para Sheets: {exc}")
            print(
                f"  Verifique se as abas existem com os nomes exatos: "
                f'"{SHEET_TAB_LAT_LON_RESUMO}" e "{SHEET_TAB_LAT_LON_DETAIL}" '
                f"(sem '!A' no nome da aba)."
            )

    n_total = sum(_count_paths_by_error_type(network_output).values())
    if PRINT_LAT_LON_REPORT_SHEETS:
        print_lat_lon_report_summary(network_output, lat_lon_report, lat_lon_report_exported)
    elif n_total > 0:
        print_lat_lon_report_summary(network_output, lat_lon_report, lat_lon_report_exported=False)
else:
    print("Nenhum dado para exportar.")
