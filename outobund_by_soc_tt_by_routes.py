#segundo arquivo - Adaptado para processamento de um único mês

import pandas as pd
import numpy as np
from datetime import date
import os
import sys

# Adiciona o diretório pai ao sys.path para permitir importações dos módulos na raiz
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from connection_with_path import GmailEntry
from transit_time_lib import compute_dist_time, compute_dist_time_express_routes
from hive_lib import get_df_demand, insert_df_into_hive, get_df_from_dataservice

import warnings
warnings.simplefilter(action='ignore')


credential_path = os.path.join(PARENT_DIR, 'credential', 'jards.json')
conn = GmailEntry(None, None, None, credential_path)

#--------------- Definitions PATHS --------------------
READ_FROM_HIVE = True

# network input
GSHEET_NETWORK_INPUT ='1S54tFjLI2sT8loUSCnexEGp_Z9ryKD1p8MugmhT5P34'  # FY 2026 mensal maio- saída da query automations
RANGE_NETWORK_INPUT = 'Network Input!A1:U' 

GSHEET_OTHER_INPUTS = '1VaLP441cLIrkW_Vwl6MDT_i_FLfVi2I9i-lVLePbGVQ'
RANGE_VEHICLES_CAP = '[O] 0. Routes SPRs!A1:G'
RANGE_QUEUE_UNLOADING = '[I] 1.0 SOC Unloading and Loading Time!A3:I'

# sheets from targets
GSHEET_PRINT_OUTPUT = '1HdplQWZuaSrEYQLNWQYA0gc5rCqXaLCt-aaLJ2xD3FE' # New Automations (TEST COPY)
 #GSHEET_PRINT_OUTPUT = '1roEOW4tOvUODUWCUnH86wXMBTr47okUZoFYSPxQB4Fg'
# SOC TT Line Haul and Outbound
RANGE_PRINT_OUTPUT = '[T] 4.1 TT and SOC Packed to Transporting to SOC!A'
RANGE_PRINT_OUTPUT_CLEAR = "A3:W"

# Express Markup summary
RANGE_EXPRESS_MARKUP_WRITE = 'raw_LhExpress_markup!A'
RANGE_EXPRESS_MARKUP_CLEAR = "A2:B"

# Range Arrived to Received
RANGE_ARRIVED2RECEIVED = "[T] 4.1 SOC Arrived to Received!A3:AA"

# Air LH
RANGE_AIRLH = "[I] 2. Air Line Haul TT!A3:B"

# Express Routes
GSHEET_ACTUAL_EXPRESS_ROUTES_INPUT = '197nob2_mCQy1fA-1ETkDH8hs6EW-YYLJx1F2egxW5uQ'
# TODO: range/colunas da planilha de express podem mudar de novo — revisar se o sheet for alterado
RANGE_ACTUAL_EXPRESS_ROUTES = 'Implemented routes!B4:AA500'
GSHEET_BID_ROUTES_INPUT = '1WCmyPTHv6YVi8wtKCdLxnT5v1saZA0fvDM1ojXhN8AU'
RANGE_BID_EXPRESS_ROUTES = 'RFQ!C5:C100'

# --- NOVO TRANSIT TIME CORRIGIDO ---
GSHEET_NEW_TT_CORRIGIDO = '1mwx37vJIDwk2eOMLZ_LTYqoTHq-3qui2zbOL9vkE6pE'
RANGE_NEW_TT_CORRIGIDO = 'ABA ROTAS!A1:Q'

# --------------- CONSTANTS -----------------------------
# Min values to be Express Route
CONST_MIN_DIST_EXPRESS = 750 # km
CONST_MIN_ADO_EXPRESS = 0 # ADO
# Min Outbound value for stations not in the same place
CONST_MIN_OUTBOUND_TIME = 4 # hours
CONST_MIN_TT_TIME = 1 # hours
# minimal distances to consider TT time (probably same place)
CONST_MIN_DIST_TT_TIME = 3 # km
AIRPORT = "Airport"

CONST_QUEUE_UNLOADING_HUB_XPT = 2 # hours

# --------------- COLUMNS ----------------------------

CONST_CROSSDOCK = "(XD)"
COL_PERIOD_NETWORK = 'period_start'
COL_PATH_NW = "E2E Path"
COLS_NW_STATIONS = ["FMH", "SOC1", 'SOC2', 'SOC3', 'SOC4', 'LMH', 'XPT']
from_to_station_distance = {('FMH', 'SOC1'):'FMH-SOC', ('FMH', 'LMH'):'FMH-HUB', 
                            ('SOC1', 'SOC2'):'SOC1-SOC2', ('SOC2', 'SOC3'):'SOC2-SOC3', ('SOC3', 'SOC4'):'SOC3-SOC4', 
                            ('SOC1', 'LMH'):'SOC-HUB', ('SOC2', 'LMH'):'SOC-HUB', ('SOC3', 'LMH'):'SOC-HUB', ('SOC4', 'LMH'):'SOC-HUB', 
                            ('SOC1', 'XPT'):'SOC-XPT', ('SOC2', 'XPT'):'SOC-XPT', ('SOC3', 'XPT'):'SOC-XPT', ('SOC4', 'XPT'):'SOC-XPT',
                            ('LMH', 'XPT'):'HUB-XPT'}
COLS_DISTANCES_NW = ["FMH-SOC","SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT"]
COL_ERRO_NW = "ERRO"
COL_ADO_NETWORK = 'ADO'

COL_CODE_AIRPORT = "Route"
COL_TT_AIRPORT = "TT (hours)"

COL_ORIGIN_OUT = 'Origin'
COL_DEST_OUT = 'Dest'
COL_ROUTE_OUT = 'Route'
COL_TT_FINAL_OUT = 'TTFinal'
COL_RAW_OUTBOUND_OUT = 'Raw Pck-LHTr'
COL_OUTBOUND_OUT = 'Pck-LHTr'
COL_FINAL_OUTBOUND_OUT = 'Final Pck-LHTr'
COL_DISTANCE_OUT = 'Distance'
COL_ADO_OUT = 'ADO'
COL_LH_EXPRES = 'LHExpress Ident.'
COL_TT_WITH_EXPRESS = 'TT with Express'
COL_TT_CALC_OUT = 'TT Calc.'
COL_LMH_RCVD_2LHM_DLVRING_LH_TRNSPTING = 'LMHRec-LMHDelivering or LH Transporting'
COL_ROUTE_TYPE_OUT = 'route_type'
COL_N_CARRETA_OUT = "N Carretas"
COL_N_TRUCK_OUT = "N Truck"
COL_N_OTHER_OUT = "N Others"
COL_TOTAL_VEHICLES_OUT = "Total Vehicles"

COMPUTE_PCKD_TRNSPTING = ["SOC-SOC"]

COL_VEHICLE_CARRETA = 'carreta_cap'
COL_VEHICLE_TRUCK = 'truck_cap'
COL_VEHICLE_OTHERS = 'others_cap'
COL_VEHICLE_ROUTE = 'route_code' 
COL_VEHICLE_ROUTE_TYPE = "route_type"
COL_VEHICLE_DESTINATION = 'origin_station_code'
COL_VEHICLE_ORIGIN = "destination_considered"

VEHICLES = [COL_VEHICLE_CARRETA, COL_VEHICLE_TRUCK, COL_VEHICLE_OTHERS]

COL_QUEUE = 'Queue'
COL_UNLOADING = 'Unloading'
COL_QUEUE_UNLOADING_LOADING_CODE = "Sites" 
LINE_OTHER_QUEUE_UNLD = 'Other'
COLS_TT_QUEUE_UNLOADING = "TT Queue and Unloading"
COL_LOADING = 'Loading'

COLS_OUTPUT = [COL_PERIOD_NETWORK, COL_ROUTE_OUT, COL_ORIGIN_OUT, COL_DEST_OUT, COL_ROUTE_TYPE_OUT, COL_ADO_OUT, COL_DISTANCE_OUT,
            COL_FINAL_OUTBOUND_OUT, COL_OUTBOUND_OUT, COL_RAW_OUTBOUND_OUT, COL_LOADING, 
            COL_TT_FINAL_OUT, COL_LH_EXPRES, COL_TT_CALC_OUT, COL_TT_WITH_EXPRESS, COLS_TT_QUEUE_UNLOADING,
            COL_TOTAL_VEHICLES_OUT, COL_N_CARRETA_OUT, COL_N_TRUCK_OUT, COL_N_OTHER_OUT, COL_VEHICLE_CARRETA, COL_VEHICLE_TRUCK, COL_VEHICLE_OTHERS]

# Cols Target Arrived to Received
COL_CODE_ARR2RCVD = "code"

df_express_routes_date_all = pd.DataFrame(columns=["Route", "period_start", "period_start_express"])

# ----------------- AUX Functions ---------------------------
def is_cb_origin(origin_series):
    return (
        (origin_series.str[:7] == "FMH-VCP")
        | (origin_series.str[:7] == "FMH-GIG")
        | (origin_series.str[:7] == "FMH-GRU")
    )

def get_valid_stations(row):
    """
    Retorna uma lista com os nomes das estações preenchidas em um caminho.
    """
    valid_stations = [
        station for station in COLS_NW_STATIONS
        if pd.notna(row[station]) and row[station] != ""
    ]
    
    return valid_stations

def get_routes_with_distances(row):
    """
    Return a list with dicts with routes as keys and distances as values 
    """
    routes_distances = {(row[row['valid_stations_list'][i]].replace(CONST_CROSSDOCK, ''), 
                        row[row['valid_stations_list'][i+1]].replace(CONST_CROSSDOCK, '')): row[from_to_station_distance[(row['valid_stations_list'][i], row['valid_stations_list'][i+1])]] 
                        for i in range(len(row['valid_stations_list'])-1)}
    return routes_distances

def compute_routes_with_distances(network, period):
    global df_express_routes_date_all
    """
    Decomposes paths in different lines for each route in each path with distances
    """
    network['valid_stations_list'] = network.apply(get_valid_stations, axis=1)
    network['routes_dists_dicts'] = network.apply(get_routes_with_distances, axis=1)
    # make lists with tuples using routes and distances
    network['routes_dists_list'] = network['routes_dists_dicts'].apply(lambda x: list(x.items()) if isinstance(x, dict) else [])
    # Explode all routes to have one route for line 
    network_exploded = network.explode('routes_dists_list').reset_index(drop=True)
    # make distance and route separate columns
    network_exploded[[COL_ROUTE_OUT, COL_DISTANCE_OUT]] = pd.DataFrame(
        network_exploded['routes_dists_list'].tolist(),
        index=network_exploded.index
    )
    # get routes unique and drop same routes with different distances
    routes_dists_df = network_exploded.groupby(COL_ROUTE_OUT)[COL_DISTANCE_OUT].first().reset_index()

    # Sum ADO from same routes
    routes_ado_df = network_exploded.groupby(COL_ROUTE_OUT)[COL_ADO_NETWORK].sum().reset_index()
    # Join routes to ADO and rearange
    merged_df = routes_dists_df.merge(routes_ado_df, how = 'left', on=COL_ROUTE_OUT)
    merged_df[COL_PERIOD_NETWORK] = period
    merged_df[COL_ORIGIN_OUT] = merged_df[COL_ROUTE_OUT].str[0]
    merged_df[COL_DEST_OUT] = merged_df[COL_ROUTE_OUT].str[1]
    # create route column and route type column
    merged_df[COL_ROUTE_OUT] = merged_df[COL_ROUTE_OUT].str[0] + '>' + merged_df[COL_ROUTE_OUT].str[1]
    merged_df[COL_ROUTE_TYPE_OUT] = merged_df[COL_ORIGIN_OUT].str[0:3] + "-" + merged_df[COL_DEST_OUT].str[0:3]

    # transform distance to numeric
    merged_df[COL_DISTANCE_OUT] = pd.to_numeric(merged_df[COL_DISTANCE_OUT], errors='coerce')
    # output columns
    merged_df = merged_df[[COL_PERIOD_NETWORK, COL_ROUTE_OUT, COL_ORIGIN_OUT, COL_DEST_OUT, COL_ROUTE_TYPE_OUT, COL_ADO_NETWORK, COL_DISTANCE_OUT]]
    df_express_routes_date = merged_df.groupby(["Route"]).agg({"period_start": "min"}).reset_index()
    df_express_routes_date["period_start_express"] = pd.to_datetime(df_express_routes_date["period_start"])+pd.DateOffset(months=3)
    df_express_routes_date_all = pd.concat([df_express_routes_date, df_express_routes_date_all])
    df_express_routes_date_all = df_express_routes_date_all.groupby(["Route"]).agg({"period_start_express": "min"}).reset_index()
    merged_df = merged_df.merge(df_express_routes_date_all, how="left", on = ["Route"])
    return merged_df

def compute_routes_vehicles_SPRs(routes, routes_spr):
    """
    Computes SPRs for specific vehicles for specific routes.
    Keep values for historical data or keep avg from all SOCs/FMHs 
    """
    for vehicle_type in VEHICLES:        
        routes_combinations = routes_spr[COL_VEHICLE_ROUTE_TYPE].unique()
        # compute avg for routes types (FMH-SOC, SOC-SOC, etc)
        routes_avg = {route_type:routes_spr[routes_spr[COL_VEHICLE_ROUTE_TYPE] == route_type][vehicle_type].mean() for route_type in routes_combinations}
        # create map column with avgs
        column_avg = routes[COL_ROUTE_TYPE_OUT].map(routes_avg)
        # get hist data for routes with available info
        routes_hist_spr = routes.merge(routes_spr, how = 'left', left_on = [COL_ROUTE_OUT], right_on = [COL_VEHICLE_ROUTE]).set_index(routes.index)[vehicle_type]
        # get hist data for stations with available info 
        stations_hist_spr = routes.merge(routes_spr, how = 'left', left_on = [COL_ORIGIN_OUT, COL_ROUTE_TYPE_OUT], right_on = [COL_VEHICLE_ORIGIN, COL_VEHICLE_DESTINATION]).set_index(routes.index)[vehicle_type]
        # compute best source of data available for each route hist_route > hist_station > avg
        final_spr = np.where((routes_hist_spr.isna()) | (routes_hist_spr == ""),
                            np.where((stations_hist_spr.isna()) | (stations_hist_spr == ""), 
                                    column_avg, 
                                    stations_hist_spr
                                    ),
                             routes_hist_spr)
        routes[vehicle_type] = final_spr
    
    return routes

def plan_vehicles_vec(orders, cap_C=None, cap_T=None, cap_O=None,
                      min_orders=0, frac_round_up=0.7, min_remainder=1000):
    """
    orders         : array-like/Series com ADO (ex.: df['L'])
    cap_C, cap_T, cap_O : capacidades por veículo (ex.: df['AI'], df['AJ'], df['AK'])
    min_orders     : ADO mínimo para considerar 
    frac_round_up  : limiar de fração p/ arredondar p/ cima no tipo principal 
    min_remainder  : sobra mínima que NÃO justifica abrir outro veículo 

    Retorna:
      labels (Series de strings) e opcionalmente breakdown (DataFrame com colunas C, T, O)
    """
    # --- Prepare arrays ---
    orders = np.asarray(orders, dtype=float)
    n = orders.shape[0]
    labels = np.full(n, "-", dtype=object)
    nC = np.zeros(n, dtype=int)
    nT = np.zeros(n, dtype=int)
    nO = np.zeros(n, dtype=int)
    # get valid routes 
    valid = (~np.isnan(orders)) & (orders > 0) & (orders >= min_orders)

    # ---------- Try to alocate Carreta ----------
    # Candidates that are not decided and valid
    undecided = (labels == "-") & valid & (~np.isnan(cap_C)) & (cap_C > 0) & (orders > cap_C)
    # get only undecided and valid data
    o = orders[undecided]
    c = cap_C[undecided]
    # get how many full vehicles are filled 
    full = (o // c).astype(int)
    # get the rest 
    rest  = o - full * c
    # get how much from the vehicle is the rest
    frac = np.divide(rest, c, out=np.zeros_like(rest), where=c>0)

    # 1) Orders fill exactly the vehicle
    m_exact = undecided.copy()
    m_exact[undecided] = (rest == 0).astype(bool)
    m_exact = m_exact.astype(bool)
    if np.any(m_exact[undecided]):
        nC[m_exact] = full[rest==0]
        labels[m_exact] = 1

    # Update masks
    undecided = (labels == "-") & valid & (~np.isnan(cap_C)) & (cap_C > 0) & (orders > cap_C)
    sel = undecided.copy()
    o, c = orders[sel], cap_C[sel]
    full = (o // c).astype(int)
    rest  = o - full * c
    frac = np.divide(rest, c, out=np.zeros_like(rest), where=c>0)

    # 2) Rest is enough to fill another Carreta
    m_up = sel.copy()
    m_up[sel] = (frac > frac_round_up)
    m_up = m_up.astype(bool)
    if np.any(m_up[sel]):
        nC[m_up] = full[frac>frac_round_up] + 1
        labels[m_up] = 1

    # update mask
    undecided = (labels == "-") & valid & (~np.isnan(cap_C)) & (cap_C > 0) & (orders > cap_C)
    # 3) Rest is not enough to fill another Carreta
    sel = undecided.copy()
    o, c = orders[sel], cap_C[sel]
    full = (o // c).astype(int)
    rest  = o - full * c
    m_small = sel.copy()
    m_small[sel] = (rest < min_remainder) & (rest > 0)
    m_small = m_small.astype(bool)
    if np.any(m_small[sel]):
        nC[m_small] = full[(rest < min_remainder) & (rest > 0)]
        labels[m_small] = 1

    # Update mask
    undecided = (labels == "-") & valid & (~np.isnan(cap_C)) & (cap_C > 0) & (orders > cap_C)
    # 4) Fill completed carretas and the rest in a truck 
    sel = undecided.copy()
    o, c = orders[sel], cap_C[sel]
    full = (o // c).astype(int)
    nC[undecided] = full
    nT[undecided] = 1
    labels[undecided] = 1

    # ------------------- Try to allocate Truck -------------------- 
    # Candidates that are not decided and valid
    undecided = (labels == "-") & valid & (~np.isnan(cap_T)) & (cap_T > 0) & (orders > cap_T)
    # get only undecided and valid data
    o = orders[undecided]
    c = cap_T[undecided]
    # get how many full vehicles are filled 
    full = (o // c).astype(int)
    # get the rest 
    rest  = o - full * c
    # get how much from the vehicle is the rest
    frac = np.divide(rest, c, out=np.zeros_like(rest), where=c>0)
    # 1) Orders fill exactly the vehicle
    m_exact = undecided.copy()
    m_exact[undecided] = (rest == 0)
    m_exact = m_exact.astype(bool)
    if np.any(m_exact[undecided]):
        nT[m_exact] = full[rest==0]
        labels[m_exact] = 1

    # Update masks
    undecided = (labels == "-") & valid & (~np.isnan(cap_T)) & (cap_T > 0) & (orders > cap_T)
    sel = undecided.copy()
    o, c = orders[sel], cap_T[sel]
    full = (o // c).astype(int)
    rest  = o - full * c
    frac = np.divide(rest, c, out=np.zeros_like(rest), where=c>0)
    # 2) Rest is enough to fill another Truck
    m_up = sel.copy()
    m_up[sel] = (frac > frac_round_up)
    m_up = m_up.astype(bool)
    if np.any(m_up[sel]):
        nT[m_up] = full[frac>frac_round_up] + 1
        labels[m_up] = 1

    # update mask
    undecided = (labels == "-") & valid & (~np.isnan(cap_T)) & (cap_T > 0) & (orders > cap_T)
    # 3) Rest is not enough to fill another vehicle
    sel = undecided.copy()
    o, c = orders[sel], cap_T[sel]
    full = (o // c).astype(int)
    rest  = o - full * c
    m_small = sel.copy()
    m_small[sel] = (rest < min_remainder) & (rest > 0)
    m_small = m_small.astype(bool)
    if np.any(m_small[sel]):
        nT[m_small] = full[(rest < min_remainder) & (rest > 0)]
        labels[m_small] = 1

    # Update mask
    undecided = (labels == "-") & valid & (~np.isnan(cap_T)) & (cap_T > 0) & (orders > cap_T)
    # 4) Fill completed Trucks and the rest in other 
    sel = undecided.copy()
    o, c = orders[sel], cap_T[sel]
    full = (o // c).astype(int)
    nT[undecided] = full
    nO[undecided] = 1
    labels[undecided] = 1

    # ------------- Fall Back in Truck -------------------- 
    # Update mask
    undecided = (labels == "-") & valid  
    nT[undecided] = 1
    labels[undecided] = 1

    # --------- Put orders >= min_orders in Other vehicle --------------
    valid = (~np.isnan(orders)) & (orders > 0) 
    undecided = (labels == "-") & valid  
    nO[undecided] = 1
    labels[undecided] = 1

    return pd.DataFrame({COL_N_CARRETA_OUT: nC, COL_N_TRUCK_OUT: nT, COL_N_OTHER_OUT: nO})

def compute_unloading_queue_time(routes, targets_unld_queue):
    # compute avg queue 
    avg_soc_queue = targets_unld_queue[targets_unld_queue[COL_QUEUE_UNLOADING_LOADING_CODE]!= LINE_OTHER_QUEUE_UNLD][COL_QUEUE].mean()
    avg_other_queue = targets_unld_queue[targets_unld_queue[COL_QUEUE_UNLOADING_LOADING_CODE] == LINE_OTHER_QUEUE_UNLD][COL_QUEUE].mean()
    # compute avg unloading  
    avg_soc_unloading = targets_unld_queue[targets_unld_queue[COL_QUEUE_UNLOADING_LOADING_CODE]!= LINE_OTHER_QUEUE_UNLD][COL_UNLOADING].mean()
    avg_other_unloading = targets_unld_queue[targets_unld_queue[COL_QUEUE_UNLOADING_LOADING_CODE] == LINE_OTHER_QUEUE_UNLD][COL_UNLOADING].mean()
    # sum values and create mapping series
    target_total_soc = targets_unld_queue.set_index(COL_QUEUE_UNLOADING_LOADING_CODE)
    target_total_soc["sum_queue_unload"] = target_total_soc[COL_UNLOADING] + target_total_soc[COL_QUEUE] 
    target_total_soc = target_total_soc["sum_queue_unload"]
    # map to destinis
    bwt_socs_mapped = routes[COL_DEST_OUT].map(target_total_soc)

    final_bwt = np.where(
        routes[COL_DEST_OUT].str[:3] == "SOC",
        np.where(
            bwt_socs_mapped.isna(),
            avg_soc_queue + avg_soc_unloading,
            bwt_socs_mapped
        ),
        avg_other_queue + avg_other_unloading
    )
    return final_bwt

def compute_arrived2received(routes, arr2rcvd, month):
    # compute avg queue 
    avg_arr2rcvd = arr2rcvd[month].apply(pd.to_numeric, errors='coerce').mean()
    avg_other_queue = CONST_QUEUE_UNLOADING_HUB_XPT 
    # sum values and create mapping series
    target_total_soc = arr2rcvd.set_index(COL_CODE_ARR2RCVD)[month]
    # map to destinis
    bwt_socs_mapped = routes[COL_DEST_OUT].map(target_total_soc)

    final_bwt = np.where(
        routes[COL_DEST_OUT].str[:3] == "SOC",
        np.where(
            bwt_socs_mapped.isna(),
            avg_arr2rcvd,
            bwt_socs_mapped
        ),
        avg_other_queue
    )
    return final_bwt

def compute_loading_time(routes, targets_loading):
    avg_soc_loading = targets_loading[targets_loading[COL_QUEUE_UNLOADING_LOADING_CODE]!= LINE_OTHER_QUEUE_UNLD][COL_LOADING].mean()
    avg_other_loading = targets_loading[targets_loading[COL_QUEUE_UNLOADING_LOADING_CODE] == LINE_OTHER_QUEUE_UNLD][COL_LOADING].mean()
    # Create mapping series
    target_total = (targets_loading).set_index(COL_QUEUE_UNLOADING_LOADING_CODE)[COL_LOADING]
    # map to origins
    bwt_socs_mapped = routes[COL_ORIGIN_OUT].map(target_total)

    final_bwt = np.where(
        routes[COL_ORIGIN_OUT].str[:3] == "SOC",
        np.where(
            bwt_socs_mapped.isna(),
            avg_soc_loading,
            bwt_socs_mapped
        ),
        avg_other_loading
    )
    return final_bwt

def compute_airlh(routes, df_airlh):
    mask_origin = routes[COL_ORIGIN_OUT].str.split("-").str[0] == AIRPORT
    mask_dest = routes[COL_DEST_OUT].str.split("-").str[0] == AIRPORT
    mask_airlh = mask_origin & mask_dest
    # create mapping series
    map_serie = df_airlh.drop_duplicates(subset=[COL_CODE_AIRPORT], keep="first").set_index(COL_CODE_AIRPORT)[COL_TT_AIRPORT]
    # Put in routes
    routes.loc[mask_airlh, COL_TT_FINAL_OUT] = routes.loc[mask_airlh, COL_ROUTE_OUT].map(map_serie)
    # erase other times
    cols_erase = [COL_TT_WITH_EXPRESS, COL_TT_CALC_OUT, COLS_TT_QUEUE_UNLOADING]
    routes.loc[mask_airlh, cols_erase] = np.nan
    routes.loc[mask_airlh, COL_LH_EXPRES] = False
    return routes
# -------------- Load inputs ------------------
# Load networks
if READ_FROM_HIVE:
    # Usando o Data Service ID configurado no DataSuite com credenciais do .env
    service_id = 'brbi_opslgc.get_bwt_network_jards'
    app_key = os.environ.get('APP_KEY')
    app_secret = os.environ.get('APP_SECRET')
    
    print(f"Buscando dados via Data Service API: {service_id}")
    
    # Chamada ajustada para a assinatura da hive_lib local (api_abbr em vez de service_id)
    df_networks = get_df_from_dataservice(
        api_abbr=service_id, 
        app_key=app_key, 
        app_secret=app_secret
    )
    
    # Renomear colunas vindo do Hive (minúsculas) para o padrão do script
    cols_rename_query = {col.lower().replace("-","_"):col for col in COLS_DISTANCES_NW}
    cols_rename_query = cols_rename_query | {col.lower():col for col in COLS_NW_STATIONS + [COL_ERRO_NW, COL_ADO_NETWORK]}
    cols_rename_query = cols_rename_query | {COL_PATH_NW.lower().replace(" ","_"): COL_PATH_NW}
    df_networks = df_networks.rename(columns=cols_rename_query)
    
    print(f"Total de linhas carregadas: {len(df_networks)}")
    if not df_networks.empty and 'period_start' in df_networks.columns:
        print(f"Meses detectados: {df_networks['period_start'].unique()}")
else:
    df_networks = conn.get_sheets(scopes=GSHEET_NETWORK_INPUT, sh_name=RANGE_NETWORK_INPUT)

df_networks[COL_PERIOD_NETWORK] = df_networks[COL_PERIOD_NETWORK].astype(str).str[0:10]

df_networks[COL_ADO_NETWORK] = pd.to_numeric(df_networks[COL_ADO_NETWORK], errors='coerce')

def parse_transit_time_to_hours(series, column_name):
    """
    Parse transit time values like HH:MM, HHH:MM, HH:MM:SS(.mmm) into hours.
    Keeps strict validation and raises an explicit error for invalid formats.
    """
    tt_as_text = series.astype(str).str.strip()
    parts = tt_as_text.str.split(":", n=2, expand=True)

    hours = pd.to_numeric(parts[0], errors="coerce")
    minutes = pd.to_numeric(parts[1], errors="coerce")

    invalid_mask = hours.isna() | minutes.isna()
    if invalid_mask.any():
        bad_samples = [
            f"row {int(idx) + 5}: {repr(series.loc[idx])}"
            for idx in series.index[invalid_mask][:10]
        ]
        raise ValueError(
            f"Invalid transit time format in '{column_name}'. "
            f"Expected HH:MM or HH:MM:SS(.mmm). Samples: {bad_samples}"
        )

    return hours + (minutes / 60.0)

def non_empty_mask(series):
    return series.notna() & series.astype(str).str.strip().ne("")

# Express routes
df_express_routes = conn.get_sheets(scopes=GSHEET_ACTUAL_EXPRESS_ROUTES_INPUT, sh_name=RANGE_ACTUAL_EXPRESS_ROUTES)
df_express_routes = df_express_routes[["Rota atualizada com movings", "Transit time atualizado", "Status", "Data da última alteração"]]
df_express_routes = df_express_routes[df_express_routes["Status"]!="Expressa inativa"]
df_express_routes = df_express_routes[df_express_routes["Status"]!="Inativa"]
df_express_routes = df_express_routes[~df_express_routes["Status"].str.contains("Expressa a ativar", na=False)] 
df_express_routes["Route"] = df_express_routes["Rota atualizada com movings"].str.replace("|",">")
mask_route = non_empty_mask(df_express_routes["Rota atualizada com movings"])
mask_status = non_empty_mask(df_express_routes["Status"])
mask_tt = non_empty_mask(df_express_routes["Transit time atualizado"])
mask_all_blank = ~mask_route & ~mask_status & ~mask_tt
df_express_routes = df_express_routes[~mask_all_blank]
mask_route = non_empty_mask(df_express_routes["Rota atualizada com movings"])
mask_status = non_empty_mask(df_express_routes["Status"])
mask_tt = non_empty_mask(df_express_routes["Transit time atualizado"])
mask_missing_tt = (mask_route | mask_status) & ~mask_tt
if mask_missing_tt.any():
    missing_rows = [int(idx) + 5 for idx in df_express_routes.index[mask_missing_tt][:10]]
    routes_preview = (
        df_express_routes.loc[mask_missing_tt, "Rota atualizada com movings"]
        .astype(str).head(10).tolist()
    )
    print(
        f"WARNING: Skipping active express routes without transit time. "
        f"Sheet rows: {missing_rows}. Routes: {routes_preview}"
    )
    df_express_routes = df_express_routes[~mask_missing_tt]
df_express_routes["TT"] = parse_transit_time_to_hours(
    df_express_routes["Transit time atualizado"], "Transit time atualizado"
)
df_express_routes["period_rampup_express"] = pd.to_datetime(df_express_routes["Data da última alteração"], format="%d/%b/%y")
df_express_routes = df_express_routes[["Route", "TT", "period_rampup_express"]]

df_express_routes_old = conn.get_sheets(scopes=GSHEET_ACTUAL_EXPRESS_ROUTES_INPUT, sh_name=RANGE_ACTUAL_EXPRESS_ROUTES)
# TODO: "Data de ramp-up" (col J) substituiu temporariamente "Data final de ramp-up" — pode voltar a mudar
df_express_routes_old = df_express_routes_old[
    ["Rota atualizada com movings", "Transit time atualizado", "Data de ramp-up"]
]
df_express_routes_old["Route"] = df_express_routes_old["Rota atualizada com movings"].str.replace("|", ">")
mask_route_old = non_empty_mask(df_express_routes_old["Rota atualizada com movings"])
mask_rampup_old = non_empty_mask(df_express_routes_old["Data de ramp-up"])
mask_tt_old = non_empty_mask(df_express_routes_old["Transit time atualizado"])
mask_all_blank_old = ~mask_route_old & ~mask_rampup_old & ~mask_tt_old
df_express_routes_old = df_express_routes_old[~mask_all_blank_old]
mask_route_old = non_empty_mask(df_express_routes_old["Rota atualizada com movings"])
mask_rampup_old = non_empty_mask(df_express_routes_old["Data de ramp-up"])
mask_tt_old = non_empty_mask(df_express_routes_old["Transit time atualizado"])
mask_missing_tt_old = (mask_route_old | mask_rampup_old) & ~mask_tt_old
if mask_missing_tt_old.any():
    missing_rows_old = [int(idx) + 5 for idx in df_express_routes_old.index[mask_missing_tt_old][:10]]
    routes_preview_old = (
        df_express_routes_old.loc[mask_missing_tt_old, "Rota atualizada com movings"]
        .astype(str).head(10).tolist()
    )
    print(
        f"WARNING: Skipping historical express routes without transit time. "
        f"Sheet rows: {missing_rows_old}. Routes: {routes_preview_old}"
    )
    df_express_routes_old = df_express_routes_old[~mask_missing_tt_old]
df_express_routes_old["TT"] = parse_transit_time_to_hours(
    df_express_routes_old["Transit time atualizado"], "Transit time atualizado"
)
df_express_routes_old["period_rampup_express"] = pd.to_datetime(df_express_routes_old["Data de ramp-up"], format="%d/%b/%y")
df_express_routes_old = df_express_routes_old[["Route", "TT", "period_rampup_express"]]

df_express_routes = pd.concat([df_express_routes, df_express_routes_old], axis=0)
df_express_routes = df_express_routes.groupby(["Route", "TT"])["period_rampup_express"].min().reset_index()

# --- INÍCIO DO CÓDIGO COMENTADO (leitura BID/RFQ legada) ---
# df_express_routes_bid = conn.get_sheets(scopes=GSHEET_BID_ROUTES_INPUT, sh_name=RANGE_BID_EXPRESS_ROUTES)
# df_express_routes_bid = df_express_routes_bid["ROTA"].str.split("|", expand=True) 
# df_express_routes_bid["Route"] = df_express_routes_bid[0] + ">" + df_express_routes_bid[1]
# df_express_routes_bid["period_start_express_bid"] = pd.to_datetime(date.today().strftime("%Y-%m-%d"))+pd.DateOffset(months=3)
# df_express_routes_bid = df_express_routes_bid.drop(df_express_routes_bid.columns[0:2], axis=1)
# --- FIM DO CÓDIGO COMENTADO (leitura BID/RFQ legada) ---

# load vehicles capacities per route
df_vehicles_cap = conn.get_sheets(scopes=GSHEET_OTHER_INPUTS, sh_name=RANGE_VEHICLES_CAP)
df_vehicles_cap[COL_VEHICLE_CARRETA] = pd.to_numeric(df_vehicles_cap[COL_VEHICLE_CARRETA], errors='coerce')
df_vehicles_cap[COL_VEHICLE_TRUCK] = pd.to_numeric(df_vehicles_cap[COL_VEHICLE_TRUCK], errors='coerce')
df_vehicles_cap[COL_VEHICLE_OTHERS] = pd.to_numeric(df_vehicles_cap[COL_VEHICLE_OTHERS], errors='coerce')

# load Queue and unloading time 
df_queue_unloading_loading = conn.get_sheets(scopes=GSHEET_OTHER_INPUTS, sh_name=RANGE_QUEUE_UNLOADING)
df_queue_unloading_loading[COL_QUEUE] = pd.to_numeric(df_queue_unloading_loading[COL_QUEUE], errors="coerce")
df_queue_unloading_loading[COL_UNLOADING] = pd.to_numeric(df_queue_unloading_loading[COL_UNLOADING], errors="coerce") 
df_queue_unloading_loading[COL_LOADING] = pd.to_numeric(df_queue_unloading_loading[COL_LOADING], errors="coerce") 

# load arrived to received for SOCs
df_arrived2received = conn.get_sheets(scopes=GSHEET_PRINT_OUTPUT, sh_name=RANGE_ARRIVED2RECEIVED)

# Select the column names first to avoid slicing issues
COL_ARRIVED2RECEIVED_ADO_AUX = df_arrived2received.columns[3:]

# Apply the numeric conversion directly to those columns
df_arrived2received[COL_ARRIVED2RECEIVED_ADO_AUX] = df_arrived2received[COL_ARRIVED2RECEIVED_ADO_AUX].apply(pd.to_numeric, errors='coerce')

# load targets for Airports
df_airlh = conn.get_sheets(scopes=GSHEET_OTHER_INPUTS, sh_name=RANGE_AIRLH)
df_airlh[COL_TT_AIRPORT] = pd.to_numeric(df_airlh[COL_TT_AIRPORT], errors="coerce")

# --- INÍCIO DO CÓDIGO COMENTADO (leitura antiga de df_new_tt_corrigido) ---
# print("Loading New Transit Time source...")
# df_new_tt_corrigido = conn.get_sheets(scopes=GSHEET_NEW_TT_CORRIGIDO, sh_name=RANGE_NEW_TT_CORRIGIDO)
# # Convert TT HRS (HH:MM:SS) to float hours
# def convert_tt_to_hours(tt_str):
#     try:
#         if not tt_str or tt_str == "": return np.nan
#         parts = tt_str.split(':')
#         if len(parts) == 3:
#             return float(parts[0]) + float(parts[1])/60 + float(parts[2])/3600
#         elif len(parts) == 2:
#             return float(parts[0]) + float(parts[1])/60
#         return float(tt_str)
#     except:
#         return np.nan
#
# df_new_tt_corrigido["Route"] = df_new_tt_corrigido["ORIGEM"].astype(str) + ">" + df_new_tt_corrigido["DESTINO"].astype(str)
# df_new_tt_corrigido["TT_Hours"] = df_new_tt_corrigido["TT HRS"].apply(convert_tt_to_hours)
# dict_new_tt = df_new_tt_corrigido.dropna(subset=["TT_Hours"]).set_index("Route")["TT_Hours"].to_dict()
# --- FIM DO CÓDIGO COMENTADO (leitura antiga de df_new_tt_corrigido) ---

# --- INÍCIO DO NOVO CÓDIGO (leitura de df_new_tt_corrigido com limpeza de DESTINO e filtro de STATUS) ---
print("Loading New Transit Time source (v2 - cleaned)...")
df_new_tt_corrigido = conn.get_sheets(scopes=GSHEET_NEW_TT_CORRIGIDO, sh_name=RANGE_NEW_TT_CORRIGIDO)

# Convert TT HRS (HH:MM:SS) to float hours
def convert_tt_to_hours(tt_str):
    try:
        if not tt_str or tt_str == "": return np.nan
        parts = str(tt_str).split(':')
        if len(parts) == 3:
            return float(parts[0]) + float(parts[1])/60 + float(parts[2])/3600
        elif len(parts) == 2:
            return float(parts[0]) + float(parts[1])/60
        return float(tt_str)
    except:
        return np.nan

# Filtrar apenas rotas ATIVA ou A INICIAR
if 'STATUS DA ROTA' in df_new_tt_corrigido.columns:
    df_new_tt_corrigido = df_new_tt_corrigido[
        df_new_tt_corrigido['STATUS DA ROTA'].astype(str).str.upper().str.strip().isin(['ATIVA', 'A INICIAR'])
    ].copy()
    print(f"  Filtered new TT routes: {len(df_new_tt_corrigido)} rows with STATUS 'ATIVA' or 'A INICIAR'")
else:
    print("  WARNING: Column 'STATUS DA ROTA' not found in New TT sheet. Using all rows.")

# Limpeza de DESTINO: split por '|' e pegar apenas a última parte (destino final)
df_new_tt_corrigido['DESTINO_LIMPO'] = (
    df_new_tt_corrigido['DESTINO'].astype(str)
    .str.split('|').str[-1]
    .str.strip()
)

# Construir chave Route: ORIGEM > DESTINO_LIMPO
df_new_tt_corrigido['Route'] = (
    df_new_tt_corrigido['ORIGEM'].astype(str).str.strip()
    + '>'
    + df_new_tt_corrigido['DESTINO_LIMPO']
)

# Converter TT HRS para float
df_new_tt_corrigido['TT_Hours'] = df_new_tt_corrigido['TT HRS'].apply(convert_tt_to_hours)

# Criar dicionário de mapeamento Route -> TT_Hours (Prioridade 2)
dict_new_tt = (
    df_new_tt_corrigido
    .dropna(subset=['TT_Hours'])
    .drop_duplicates(subset=['Route'], keep='first')
    .set_index('Route')['TT_Hours']
    .to_dict()
)
print(f"  New TT dictionary loaded with {len(dict_new_tt)} routes.")
# --- FIM DO NOVO CÓDIGO (leitura de df_new_tt_corrigido) ---

# --------------- Treat Inputs -----------------------------
# keep only without error
if COL_ERRO_NW in df_networks.columns:
    df_networks[COL_ERRO_NW] = df_networks[COL_ERRO_NW].fillna("")
    df_networks = df_networks[df_networks[COL_ERRO_NW] == ""]

# delete routes with distance = -1 (linhas invalidas sem distancia/lat-lon)
if not df_networks.empty:
    invalid_dist_mask = (df_networks[COLS_DISTANCES_NW] == "-1").any(axis=1)
    n_invalid = int(invalid_dist_mask.sum())
    if n_invalid > 0:
        print(f"AVISO: Removendo {n_invalid} linha(s) com distancia invalida (-1).")
        df_networks = df_networks[~invalid_dist_mask]

rows_before = len(df_networks)
origin_col = "ORIGIN" if "ORIGIN" in df_networks.columns else "FMH"
if origin_col in df_networks.columns:
    cb_mask = is_cb_origin(df_networks[origin_col].astype(str))
    df_networks = df_networks[~cb_mask].copy()
    print(f"Excluídas {rows_before - len(df_networks)} linhas de ORIGIN CB (FMH-VCP-*, FMH-GRU-*, FMH-GIG-*)")

df_networks.reset_index(inplace=True, drop=True)

# -------------- Compute Out bound and TT by routes ---------
periods_network = np.unique(df_networks[COL_PERIOD_NETWORK])
dict_networks = {period:df_networks.loc[df_networks[COL_PERIOD_NETWORK] == period] for period in periods_network}
dict_routes = {}

# loop for all networks
for period in periods_network:
    month_period = period[:8] + "01"
    # ----------------OUTBOUND -----------------------
    # Get routes with ADO and Distances
    print("Processing routes for period: " + period)
    routes = compute_routes_with_distances(dict_networks[period], period)

    if routes[routes[COL_DISTANCE_OUT].isna()].shape[0] > 0:
        print('--------------------------------------------------')
        print(f"ATTENTION: There are {routes[routes[COL_DISTANCE_OUT].isna()].shape[0]} routes WITHOUT DISTANCE")
        print('--------------------------------------------------')
        routes = routes[~routes["Distance"].isna()]  
        #raise
    # Compute SPR from routes
    routes = compute_routes_vehicles_SPRs(routes, df_vehicles_cap)
    
    # Compute vehicles for each route 
    vehicles_routes = plan_vehicles_vec(routes[COL_ADO_OUT] , routes[COL_VEHICLE_CARRETA], routes[COL_VEHICLE_TRUCK], routes[COL_VEHICLE_OTHERS])
    vehicles_routes["Total Vehicles"] = vehicles_routes.sum(axis=1)
    
    # concat tables from routes and vehicles
    routes = pd.concat([routes, vehicles_routes], axis = 1)
    
    # ------------ SOC-SOC Pckd-Transporting -------------------------------
    # compute loading time
    routes[COL_LOADING] = compute_loading_time(routes, df_queue_unloading_loading)

    # compute time Outbound SOC-SOC [12h avg divided by the number of vehicles]
    routes[COL_RAW_OUTBOUND_OUT] = 12/routes[COL_TOTAL_VEHICLES_OUT]
    # treat vehicles = 0
    routes.loc[routes[COL_TOTAL_VEHICLES_OUT]==0, COL_RAW_OUTBOUND_OUT] = 12
    routes[COL_OUTBOUND_OUT] =  routes[COL_RAW_OUTBOUND_OUT]
    
    # for outbound time smaller than minimum value, consider minimum value
    routes.loc[routes[COL_OUTBOUND_OUT] < CONST_MIN_OUTBOUND_TIME ,COL_OUTBOUND_OUT] = CONST_MIN_OUTBOUND_TIME

    # Final Pckd-Transporting
    routes[COL_FINAL_OUTBOUND_OUT] = routes[COL_LOADING] + routes[COL_OUTBOUND_OUT]

    # erase routes types which are no inter SOC [logic dont apply] 
    routes.loc[(~routes[COL_ROUTE_TYPE_OUT].isin(COMPUTE_PCKD_TRNSPTING)),[COL_FINAL_OUTBOUND_OUT, COL_OUTBOUND_OUT, COL_RAW_OUTBOUND_OUT, COL_LOADING,]] = np.nan

    # Inicializar colunas de resultado
    routes[COL_LH_EXPRES] = False
    routes[COL_TT_CALC_OUT] = np.nan
    routes[COL_TT_WITH_EXPRESS] = np.nan

    # Converter period_start para datetime para comparação
    period_start_dt = pd.to_datetime(routes[COL_PERIOD_NETWORK].iloc[0])

    # ---- PRIORIDADE 1: Merge com Planilha Oficial de Expressas ----
    routes = routes.merge(
        df_express_routes[['Route', 'TT', 'period_rampup_express']],
        how='left',
        on='Route'
    )

    # Máscara: rota existe na planilha E mês simulado >= data de ativação
    mask_p1 = (
        routes['TT'].notnull()
        & (period_start_dt >= routes['period_rampup_express'])
    )

    # Aplicar Prioridade 1: selo Express = True, TT oficial
    routes.loc[mask_p1, COL_LH_EXPRES] = True
    routes.loc[mask_p1, COL_TT_WITH_EXPRESS] = routes.loc[mask_p1, 'TT']

    # Flag para controle de prioridade
    routes['_matched_p1'] = mask_p1

    # Limpar colunas temporárias do merge
    routes = routes.drop(columns=['TT', 'period_rampup_express'], errors='ignore')

    # ---- PRIORIDADE 2: Planilha de Novas Rotas (dict_new_tt) ----
    # Só aplica onde NÃO houve match na Prioridade 1
    routes['_tt_new_route'] = routes[COL_ROUTE_OUT].map(dict_new_tt)
    mask_p2 = (~routes['_matched_p1']) & (routes['_tt_new_route'].notnull())

    # Aplicar Prioridade 2: usa TT da planilha, NÃO altera selo de Expressa
    routes.loc[mask_p2, COL_TT_WITH_EXPRESS] = routes.loc[mask_p2, '_tt_new_route']

    # Flag para controle
    routes['_matched_p2'] = mask_p2

    # ---- REGRA GLOBAL DE SELO POR DISTÂNCIA ----
    # Aplica-se para qualquer rota que ainda não seja Expressa Oficial (P1),
    # mantendo as travas de negócio originais (exclui 3PL e XPT).
    mask_express_dist = (
        (~routes['_matched_p1'])
        & (~routes[COL_ORIGIN_OUT].astype(str).str.contains('3PL', na=False))
        & (~routes[COL_DEST_OUT].astype(str).str.contains('XPT', na=False))
        & (routes[COL_DISTANCE_OUT] >= CONST_MIN_DIST_EXPRESS)
    )
    routes.loc[mask_express_dist, COL_LH_EXPRES] = True

    # ---- PRIORIDADE 3: Cálculo Matemático baseado em distância ----
    # Só calcula a matemática de tempo se NÃO achou TT na P1 e NÃO achou na P2
    mask_p3 = (~routes['_matched_p1']) & (~routes['_matched_p2'])

    # Calcular TT base via distância
    routes.loc[mask_p3, COL_TT_CALC_OUT] = compute_dist_time(routes.loc[mask_p3, COL_DISTANCE_OUT])
    routes.loc[mask_p3 & (routes[COL_DISTANCE_OUT] < CONST_MIN_DIST_TT_TIME), COL_TT_CALC_OUT] = CONST_MIN_TT_TIME

    # Se caiu na P3 E tem o selo de expressa (ganho pela regra global acima) -> usa matemática rápida
    mask_p3_express = mask_p3 & routes[COL_LH_EXPRES]
    if mask_p3_express.any():
        routes.loc[mask_p3_express, COL_TT_WITH_EXPRESS] = compute_dist_time_express_routes(
            routes.loc[mask_p3_express, COL_DISTANCE_OUT]
        )

    # Se caiu na P3 Normal -> Usa matemática normal
    mask_p3_normal = mask_p3 & (~routes[COL_LH_EXPRES])
    routes.loc[mask_p3_normal, COL_TT_WITH_EXPRESS] = routes.loc[mask_p3_normal, COL_TT_CALC_OUT]

    # Preencher COL_TT_CALC_OUT para histórico em todas as rotas (auditoria)
    routes.loc[~mask_p3, COL_TT_CALC_OUT] = compute_dist_time(routes.loc[~mask_p3, COL_DISTANCE_OUT])
    routes.loc[(~mask_p3) & (routes[COL_DISTANCE_OUT] < CONST_MIN_DIST_TT_TIME), COL_TT_CALC_OUT] = CONST_MIN_TT_TIME

    # Limpeza final
    routes = routes.drop(columns=['_matched_p1', '_matched_p2', '_tt_new_route', 'period_start_express'], errors='ignore')

    print(f"  TT Priorities applied - P1(Express): {mask_p1.sum()}, P2(New TT): {mask_p2.sum()}, P3(Distance): {mask_p3.sum()} (Express by dist: {mask_p3_express.sum()})")

    # ---- Queue/Unloading Time (mantido da lógica original) ----
    df_arrived2received = df_arrived2received.dropna()

    # Unloading and Queue time for destini
    if month_period in df_arrived2received.columns:
        routes[COLS_TT_QUEUE_UNLOADING] = compute_arrived2received(routes, df_arrived2received[[COL_CODE_ARR2RCVD, month_period]], month_period)
    else:
        print(f"AVISO: {month_period} não encontrado em df_arrived2received. Usando 0.")
        routes[COLS_TT_QUEUE_UNLOADING] = 0

    # XPT and direct FMH/FBS/SOC to HUB routes: no queue time, only travel TT
    mask_no_queue_routes = routes[COL_ROUTE_TYPE_OUT].isin(["HUB-XPT", "SOC-XPT", "FBS-HUB", "FMH-HUB", "SOC-HUB"])
    routes.loc[mask_no_queue_routes, COLS_TT_QUEUE_UNLOADING] = 0

    # Zero Unloading and queue time for routes same place (only min value for TT) 
    routes.loc[routes[COL_DISTANCE_OUT] < CONST_MIN_DIST_TT_TIME, COLS_TT_QUEUE_UNLOADING] = 0

    # TT Final = Queue/Unloading + TT with Express
    routes[COL_TT_FINAL_OUT] = routes[COLS_TT_QUEUE_UNLOADING].astype(float) + routes[COL_TT_WITH_EXPRESS]
    # --- FIM DO NOVO CÓDIGO (Hierarquia de 3 Prioridades) ---

    # compute Air LH
    routes = compute_airlh(routes, df_airlh)
    
    # [TEMP TO ADJUST] Put Fixed time to AirLH SOC-SP6>HUB-LAM-02 = 47 hours. 
    mask_airlh = routes[COL_ROUTE_OUT] == ("SOC-SP6>HUB-LAM-02") 
    routes.loc[mask_airlh, COL_TT_FINAL_OUT] = 47 
    routes.loc[mask_airlh, COL_LH_EXPRES] = False
    routes.loc[mask_airlh, [COL_TT_WITH_EXPRESS, COLS_TT_QUEUE_UNLOADING, COL_TT_CALC_OUT]] = np.nan

    # keep result
    dict_routes[period] = routes

print("Gathering results")
if dict_routes:
    # routes
    routes_output = pd.concat([dict_routes[period] for period in periods_network])
    routes_output.reset_index(inplace=True, drop= True)
    routes_output = routes_output.fillna("")

    # ------------ Clean sheets before writing -----------------------
    print("Cleaning sheets")
    # clean routes
    conn.clean_specific_range(
        sheet_id=GSHEET_PRINT_OUTPUT,
        sheet_name=RANGE_PRINT_OUTPUT.split("!")[0],
        range_to_clear = RANGE_PRINT_OUTPUT_CLEAR
    )
    # clean express markup
    conn.clean_specific_range(
        sheet_id=GSHEET_PRINT_OUTPUT,
        sheet_name='raw_LhExpress_markup',
        range_to_clear = RANGE_EXPRESS_MARKUP_CLEAR
    )

    # ----------- print Results -----------
    print('Writing result to sheets')
    ### Using 50k batchs
    batch_size = 50000
    print_line_buffer = 2
    num_batches = int(routes_output.shape[0]/batch_size)+1
    for i in range(num_batches):
        add_line_title = 1 if i > 0 else 0
        sh_range = RANGE_PRINT_OUTPUT + str(1 + i*batch_size + print_line_buffer + add_line_title) 
        print(f"Escrevendo batch {i+1} de {num_batches} no Google Sheets...")
        try:
            conn.print_in_sheets(scopes=GSHEET_PRINT_OUTPUT, sh_name=sh_range,
                                 df=routes_output.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT], print_columns=True if i == 0 else False)
        except Exception:
            print('print in sheets failed, trying again.')
            conn.print_in_sheets(scopes=GSHEET_PRINT_OUTPUT, sh_name=sh_range,
                                 df=routes_output.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT], print_columns=False)

    # ----------- Print Express Markup Summary -----------
    print('Writing Express Markup summary to sheets')
    try:
        conn.print_in_sheets(
            scopes=GSHEET_PRINT_OUTPUT, 
            sh_name=RANGE_EXPRESS_MARKUP_WRITE + '1',
            df=routes_output[[COL_ROUTE_OUT, COL_LH_EXPRES]], 
            print_columns=True
        )
    except Exception as e:
        print(f"Error writing express markup summary: {e}")
else:
    print("Nenhum dado para processar.")
