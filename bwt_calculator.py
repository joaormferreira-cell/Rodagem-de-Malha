#terceiro arquivo - Adaptado para processamento de um único mês

import pandas as pd
import numpy as np
import os
import sys
import requests
from requests_toolbelt import MultipartEncoder
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta

# Adiciona o diretório pai ao sys.path para permitir importações dos módulos na raiz
PARENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

import warnings
warnings.simplefilter(action='ignore')

from connection_with_path import GmailEntry
from transit_time_lib import compute_dist_time, compute_dist_time_express_routes
from hive_lib import get_df_demand, insert_df_into_hive, get_df_from_dataservice
from station_geo_lib import STATION_NAMES_API, STATION_NAMES_VERSION, build_station_state_lookup, add_estado_regional


credential_path = os.path.join(PARENT_DIR, 'credential', 'jards.json')
conn = GmailEntry(None, None, None, credential_path)

READ_FROM_HIVE = True
PRINT_HIVE_E2E = False
PRINT_SHEET_BWT_E2E = True
PRINT_1ST_SOC_SHEET = True
PRINT_SUMMARY_SHEET = True

# Filtro de períodos na aba "Network BWT output" (só afeta essa exportação).
# "normal"  -> mês seguinte + novembro (padrão de produção)
# "jun_nov" -> junho + novembro (ajuste temporário; voltar para "normal" depois)
BWT_OUTPUT_PERIOD_FILTER = "normal"

#--------------- Definitions PATHS --------------------
# network input
GSHEET_NETWORK_INPUT ='1S54tFjLI2sT8loUSCnexEGp_Z9ryKD1p8MugmhT5P34' # FY 2026 mensal - saída da query automations
RANGE_NETWORK_INPUT = 'Network Input!A1:U' 

# gsheets output
GSHEET_PRINT_OUTPUT = '1iReXhzuORpc7cTBGo5C1MrvUmILYu3x_ZzjnM3fDGfw'  # Output automations (original)
# GSHEET_PRINT_OUTPUT = '1hLHJCMx_3fpZdfWeVs9pjn_fvkdlc5ktsqiMSqei82g'  # Teste
RANGE_PRINT_OUTPUT = 'Network BWT output!A'
RANGE_PRINT_OUTPUT_CLEAR = "A10:AR"

RANGE_OUTPUT_SUMMARY_WRITE = 'raw_bwt!A'
RANGE_OUTPUT_SUMMARY_CLEAR = "A2:BP"
RANGE_OUTPUT_1stSOC_WRITE = "raw_data_1st_SOC!A"
RANGE_OUTPUT_1stSOC_CLEAR = "A2:AU"


# sheets from targets
GSHEET_TARGET_INPUT = '1mSxSQkhZdQWIkQmDpBRmYCAN7K-Kc1YdvEV7Z6feNY0' # [Default] automations (TEST COPY - Outbound)
# gsheet station list with Region 

GSHEET_STATION_LIST = '1hZSIsOUFpf5oQ7hw6bckUvq3_tZiPCCSeBOLyIstyqI'
RANGE_STATION_LIST = "Base!A2:B"
RANGE_SPX_INFO = "SPX_info!A1:I"

# 1.0 SELLER Paid to Dropoff
RANGE_TARGET_PAID_2DROPOFF = "[T] 1.0 APT (Paid to Pickup or dropoff)!D3:AA"
# 2.0 FM Dropoff to Pickup
RANGE_TARGET_DROPOFF_2PICKUP = '[T] 2.0 FM Dropoff to Pickup!D3:AA'
# 2.1 FM Pickup to SOC_FMH Received
RANGE_TARGET_PICKUP_2RECEIVED = '[T] 2.1 FM Pickup to SOC_FMH Received!A3:AA'
# 3.0.1 FMH Received to Packed
RANGE_TARGET_FMH_RCVD_2PACKED = '[T] 3.0.1 FMH Received to Packed!A3:E'
# 3.0.2 FMH Packed to Transporting
RANGE_TARGET_FMH_PCKD_2TRANS = '[T] 3.0.2 FMH Packed to Transporting!A3:E'
# 3.1 FBS Processing
RANGE_TARGET_FBS_PROCESSING = "[T] 3.1 FBS Processing!A3:AA"
# 4.0 SOC Received to Packed
RANGE_TARGET_SOC_RECEIVED_2PCKD = '[T] 4.0 SOC Received to Packed!A3:AA'
# 4.1 TT SOC Packed to Transporting to SOC
RANGE_TARGET_SOC_PCKD_TO_TRNSPTDING_TO_SOC = '[T] 4.1 TT and SOC Packed to Transporting to SOC!A3:P'
# 4.2 SOC Packed to Transporting 
RANGE_TARGET_SOC_PCKD_TO_TRNSPTING = '[T] 4.2 SOC Packed to LH Transporting!A3:AA'
# 4.9 LMH LH Arrived to Transported
RANGE_TARGET_LM_ARRIVED_2TRANSPORTED = '[T] 4.9 LMH LH Arrived to Transported!A3:AA'
# 5.0 LMH Transported to Received
RANGE_TARGET_LM_TRANS_2RCVD = '[T] 5.0 LMH LH Transported to Received!A3:AA'
# 5.1.0 LMH Received to Delivering
RANGE_TARGET_LM_RCVD_2DLVRING = '[T] 5.1.0 LMH Received to Delivering!A3:AA'
# 5.1.1 LMH Received to LH transporting to XPT
RANGE_TARGET_LM_RCVD_2XPT = '[T] 5.1.1 LMH Received to LH transporting to XPT!A3:AA'
# 5.9 XPT LH Arrived to XPT Received
RANGE_TARGET_XPT_ARRIVED_2RCVD = '[T] 5.9 XPT LH Arrived to XPT Received!A3:AA'
# 6.0 XPT Received to Delivering
RANGE_TARGET_XPT_RCVD_2DLVRING = '[T] 6.0 XPT Received to Delivering!A3:AA'
# 7.0 LMH Delivering to 1st
RANGE_TARGET_LMH_DLVRING_2_1ST = '[T] 7.0 LMH Delivering to 1st!A3:AA'
# 7.1 XPT Delivering to 1st
RANGE_TARGET_XPT_DLVRING_2_1ST = '[T] 7.1 XPT Delivering to 1st!A3:AA'
# Air LH
RANGE_RECEIVED_2DEPARTURE_AIRLH = "[T] 8. Airport Received to Flight Departure!A3:AA"
RANGE_ARRIVED_2OB_AIRLH = "[T] 8. Airport Received to Flight Departure!A3:AA"


# --------------- CONSTANTS -----------------------------
COL_PERIOD_NETWORK = 'period_start'
COLS_DISTANCES_NW = ["FMH-SOC","SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT"]
COL_EXCLUDE_OUT = ["period_end", "SOC3", "SOC4"] 
COL_ERRO_NW = "ERRO"
COL_ADO_NW = "ADO"
COL_PATH_NW = "E2E Path"

COLS_NW_STATIONS = ["FMH", "SOC1", 'SOC2', 'SOC3', 'SOC4', 'LMH', 'XPT']
COL_ORIGIN_NW = "ORIGIN"
COL_DEST_NW = "DESTINATION"

COL_CODE_TARGETS = 'code'

COL_FMH_TGT_VALUE = "Target Received to Transporting"
COL_FMH_TGT_PERIOD = "period_start"

COL_PERIOD_NAME_TT = 'period_start'
COL_ORIGIN_TT = 'Origin'
COL_DEST_TT = 'Dest'
COL_ROUTE_TT = 'Route'
COL_TT_TT = 'TTFinal'

COL_OUTBOUND_TT = 'Final Pck-LHTr'

# SPX Info
COL_ZIPCODE_SPX = "zipcode"
COL_CODE_SPX = "station_code"
COL_ORIGIN_BR_SPM = "origin_spm"
COL_DEST_BR_SPM = "dest_spm"
COL_CODE_STATION_LIST = "Code"
COL_SUBREG_STATION_LIST = "SubRegion"
CONST_SUBREG_SPM = "SAO"
CONST_SPM = "SPM"
CONST_SPI = "SPI"

pref = 3

AIRPORT = "Airport"
SOC_AIRPORT_PCKD2RCVD = 4 

columns_bwt = ["bwt_apt_paid_to_dropoff", "bwt_dropoff_to_pickup", 'bwt_pickup_to_received','bwt_fbs_processing', 'bwt_fmh_received_to_packed', 'bwt_fmh_packed_to_transporting',
               "bwt_lh_fmh_to_soc", "bwt_lh_fbs_to_soc", "bwt_lh_fmh_to_lmh_arrived", "bwt_lh_fbs_to_lmh_arrived",
               "bwt_soc1_received_to_packed", "bwt_soc1_received_to_packed_full", 'bwt_soc1_packed_to_transporting', 'bwt_lh_soc1_to_soc2',
               'bwt_soc2_received_to_packed', "bwt_soc2_received_to_packed_full", 'bwt_soc2_packed_to_transporting', 'bwt_lh_soc2_to_soc3',
               'bwt_soc3_received_to_packed', "bwt_soc3_received_to_packed_full", 'bwt_soc3_packed_to_transporting', 'bwt_lh_soc3_to_soc4',
               'bwt_soc4_received_to_packed', "bwt_soc4_received_to_packed_full", 'bwt_soc4_packed_to_transporting',
               'bwt_lh_soc_to_lmh', 'bwt_lh_soc_to_xpt_arrived', 'bwt_lh_xpt_arrived_to_xpt_received', 'bwt_lh_arrived_to_transported',
               'bwt_lh_transported_to_lmh_received', 'bwt_lmh_received_to_LH_xpt_or_delivering', 'bwt_lmh_transporting_to_xpt_arrived', 'bwt_lh_lmh_transported_to_xpt_to_delivering',
               'bwt_hub_delivering_to_1st_attempt', 'bwt_xpt_delivering_to_1st_attempt']

SOC_RCVD_TO_FULL = {
    "bwt_soc1_received_to_packed": "bwt_soc1_received_to_packed_full",
    "bwt_soc2_received_to_packed": "bwt_soc2_received_to_packed_full",
    "bwt_soc3_received_to_packed": "bwt_soc3_received_to_packed_full",
    "bwt_soc4_received_to_packed": "bwt_soc4_received_to_packed_full",
}
columns_bwt_operational = [c for c in columns_bwt if c not in SOC_RCVD_TO_FULL.values()]
columns_bwt_xd_total = [SOC_RCVD_TO_FULL.get(c, c) for c in columns_bwt_operational]

def is_cb_origin(origin_series):
    return (
        (origin_series.str[:7] == "FMH-VCP")
        | (origin_series.str[:7] == "FMH-GIG")
        | (origin_series.str[:7] == "FMH-GRU")
    )

# --------------- FUNCTIONS COMPUTE BWT ---------------------

# 1. seller processing - bwt paid to dropoff 
def bwt_paid_2dropoff(network, target):
    station_lvl = "FMH"
    bwt = [float(target[0]) if fmh[0:pref] != 'FBS' else 0 for fmh in network[station_lvl]]
    network["bwt_apt_paid_to_dropoff"] = bwt
    return network

# 2.0 FM Dropoff to Pickup
def bwt_dropoff_2pickup(network, target):
    station_lvl = "FMH"
    bwt = [float(target[0]) if fmh[0:pref] != 'FBS' else 0 for fmh in network[station_lvl]]
    network["bwt_dropoff_to_pickup"] = bwt
    return network

# 2.1 FM Pickup to SOC_FMH Received
def bwt_pickup_2rcvd(network, targets, month_period):
    station_lvl1 = "FMH"
    station_lvl2 = "SOC1"
    station_exclud_avg = "FMH-PHP"
    avg_tgt = targets[targets[COL_CODE_TARGETS].str[0:len(station_exclud_avg)]!=station_exclud_avg][month_period].astype(float).mean()
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")

    # Columns whether to use FMH or SOC1
    network['station_to_map'] = np.where(
        network[station_lvl1].isna() | (network[station_lvl1] == ""),
        network[station_lvl2].str.replace('(XD)', '', regex=False).str.replace('-X$', '', regex=True),
        network[station_lvl1].str.replace('(XD)', '', regex=False).str.replace('-X$', '', regex=True)
    )
    # create bwt with targets
    bwt = network['station_to_map'].map(mapping_series)
    # create final bwt with avg for missing values or 0 for FBS
    final_bwt = np.where(
        network[station_lvl1].str[:pref] == 'FBS',
        0,
        np.where(bwt.isna(), avg_tgt, bwt)
    )
    network["bwt_pickup_to_received"] = final_bwt
    # Remove aux column
    del network['station_to_map']

    return network

# 2.2 Processing FBS
def bwt_fbs_processing(network, targets, month_period):
    station_lvl1 = "FMH"
    avg_tgt = targets[month_period].astype(float).mean()
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")

    # create bwt with targets
    bwt = network[station_lvl1].map(mapping_series)
    # create final bwt with avg for missing values or 0 for FBS
    final_bwt = np.where(
        network[station_lvl1].str[:pref] == 'FBS',
        np.where(bwt.isna(), avg_tgt, bwt),
        0
    )
    network["bwt_fbs_processing"] = final_bwt

    return network

# 3.0.1 / 3.0.2 FMH Received to Packed / Packed to Transporting
def _bwt_fmh_target(network, targets, output_col):
    station_lvl1 = "FMH"
    station_exclud_avg = "FMH-PHP"
    avg_tgt = targets[(targets[COL_CODE_TARGETS].str[0:len(station_exclud_avg)]!=station_exclud_avg) &
                      (targets[COL_CODE_TARGETS].str[0:pref]!="FBS")][COL_FMH_TGT_VALUE].astype(float).mean()

    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[COL_FMH_TGT_VALUE], errors="coerce")

    bwt = network[station_lvl1].map(mapping_series)
    mask_no_fmh = ((network[station_lvl1].isna()) | (network[station_lvl1] == ""))
    final_bwt = np.where(
        (network[station_lvl1].str[:pref] == 'FBS') | mask_no_fmh,
        0.0,
        np.where(bwt.isna(), avg_tgt, bwt)
    )
    network[output_col] = final_bwt

    return network

def bwt_fmh_rcvd_2packed(network, targets):
    return _bwt_fmh_target(network, targets, "bwt_fmh_received_to_packed")

def bwt_fmh_pckd_2trans(network, targets):
    return _bwt_fmh_target(network, targets, "bwt_fmh_packed_to_transporting")

# 4.0.1 Transit time LH FMH to SOC
def bwt_lh_fmh_2soc(network, targets, month_period):
    station_lvl1 = "FMH"
    station_lvl2 = "SOC1"
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")

    # Map with route to SOC1
    fmh_route_soc1 = np.array(network[station_lvl1].str.replace('(XD)', '', regex=False) + ">" + network[station_lvl2].str.replace('(XD)', '', regex=False))
 
    # create bwt with route TT times
    bwt = pd.Series(fmh_route_soc1).map(mapping_series)
    mask_no_fmh = ((network[station_lvl1].isna()) | (network[station_lvl1] == "") | (network[station_lvl2] == ""))
    
    # zero bwt where fmh is null and LMH is null
    final_bwt = np.where(
        (network[station_lvl1].str[:pref] == 'FBS') | mask_no_fmh,
        0.0,
        bwt)
    
    network["bwt_lh_fmh_to_soc"] = final_bwt
    return network

# 4.0.2 Transit time LH FMH to LMH
def bwt_lh_fmh_2lmh(network, targets, month_period):
    station_lvl1 = "FMH"
    station_lvl2 = "LMH"
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")

    # Map with route to LMH
    fmh_route_lmh = np.array(network[station_lvl1].str.replace('(XD)', '', regex=False) + ">" + network[station_lvl2].str.replace('(XD)', '', regex=False))
 
    # create bwt with route TT times
    bwt = pd.Series(fmh_route_lmh).map(mapping_series)
    mask_no_fmh = ((network[station_lvl1].isna()) | 
                   (network[station_lvl1] == "") | 
                   (network[station_lvl2] == "") | 
                   (network[station_lvl2].isna()))
    
    # zero bwt where fmh is null and LMH is null
    final_bwt = np.where(
        (network["SOC1"] != "") | (network[station_lvl1].str[:pref] == 'FBS') | mask_no_fmh,
        0.0,
        bwt)
    
    network["bwt_lh_fmh_to_lmh_arrived"] = final_bwt
    return network

# 4.0.3 Transit time LH FBS to SOC
def bwt_lh_fbs_2soc(network, targets, month_period):
    station_lvl1 = "FMH"
    station_lvl2 = "SOC1"
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")

    # Map with route to SOC1
    fbs_route_soc1 = np.array(network[station_lvl1].str.replace('(XD)', '', regex=False) + ">" + network[station_lvl2].str.replace('(XD)', '', regex=False))
 
    # create bwt with route TT times
    bwt = pd.Series(fbs_route_soc1).map(mapping_series)
    mask_no_fmh = ((network[station_lvl1].isna()) | (network[station_lvl1] == "") | (network[station_lvl2] == ""))
    
    # zero bwt where fmh is null and LMH is null
    final_bwt = np.where(
        (network[station_lvl1].str[:pref] != 'FBS') | mask_no_fmh,
        0.0,
        bwt)
    
    network["bwt_lh_fbs_to_soc"] = final_bwt
    return network

# 4.0.4 Transit time LH FBS to LMH
def bwt_lh_fbs_2lmh(network, targets, month_period):
    station_lvl1 = "FMH"
    station_lvl2 = "LMH"
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")

    # Map with route to LMH
    fbs_route_lmh = np.array(network[station_lvl1].str.replace('(XD)', '', regex=False) + ">" + network[station_lvl2].str.replace('(XD)', '', regex=False))
 
    # create bwt with route TT times
    bwt = pd.Series(fbs_route_lmh).map(mapping_series)
    mask_no_fmh = ((network[station_lvl1].isna()) | (network[station_lvl1] == "") | (network[station_lvl2] == ""))
    
    # zero bwt where fmh is null and LMH is null
    final_bwt = np.where(
        (network["SOC1"] != "") | (network[station_lvl1].str[:pref] != 'FBS') | mask_no_fmh,
        0.0,
        bwt)
    
    network["bwt_lh_fbs_to_lmh_arrived"] = final_bwt
    return network

# 4.1.1 Compute SOC Received to Packed 
def bwt_soc_rcvd_2pckd(network, targets, target_fmh_rcvd_2packed, target_rcvd2flight, target_flight2ob, month_period, station_lvl1, station_lvl2):
    avg_tgt = pd.to_numeric(targets[month_period], errors='coerce').mean()
    # pass flight targets to numeric
    target_rcvd2flight[month_period] = pd.to_numeric(target_rcvd2flight[month_period], errors='coerce')
    target_flight2ob[month_period] = pd.to_numeric(target_flight2ob[month_period], errors='coerce')
    aux_r2f = target_rcvd2flight.copy()
    aux_f2ob = target_flight2ob.copy()
    aux_r2f[month_period] = aux_r2f[month_period] / 2
    aux_f2ob[month_period] = aux_f2ob[month_period] / 2
    # get avg for flights
    avg_rcvd2flight = aux_r2f[month_period].mean()
    avg_flight2ob = aux_f2ob[month_period].mean()

    # Creating series mapping targets for SOCs
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")
    # Creating series mapping targets for FMHs
    mapping_series_fmh = pd.to_numeric(target_fmh_rcvd_2packed.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[COL_FMH_TGT_VALUE], errors='coerce')
    # Received to flight
    mapping_series_r2f = aux_r2f.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period]
    mapping_series_f2ob = aux_f2ob.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period]
    bwt_r2f = network[station_lvl1].map(mapping_series_r2f).fillna(avg_rcvd2flight)
    bwt_f2ob = network[station_lvl1].map(mapping_series_f2ob).fillna(avg_flight2ob)
    aux_st_type = network[station_lvl2].str.split("-").str[0]
    # get bwt for flight before ou after flight
    bwt_airport = np.where(
        aux_st_type == AIRPORT,
        bwt_r2f,
        bwt_f2ob
    )
    
    # Concatenate two series in one to do mapping
    mapping_series = pd.concat([mapping_series, mapping_series_fmh])

    # Create aux indicating for station with cross dock
    xd_aux = np.where(
        network[station_lvl1].str.contains('(XD)', regex=False),
        1,
        0
    )
    # create bwt with targets
    bwt = network[station_lvl1].map(mapping_series)

    # create final bwt idetifying cross-dock and putting avg to mising values
    aux_st_type = network[station_lvl1].str.split("-").str[0]
    final_bwt = np.where(
        (xd_aux != 1) & (network[station_lvl1] != "") & (~network[station_lvl1].isna()),
        np.where(
            (aux_st_type == AIRPORT),
            bwt_airport,
            np.where(bwt.isna(), avg_tgt, bwt)
        ),
        0
    )
    network["bwt_" + station_lvl1.lower() + "_received_to_packed"] = final_bwt

    station_for_map = network[station_lvl1].str.replace('(XD)', '', regex=False)
    bwt_r2f_full = station_for_map.map(mapping_series_r2f).fillna(avg_rcvd2flight)
    bwt_f2ob_full = station_for_map.map(mapping_series_f2ob).fillna(avg_flight2ob)
    bwt_airport_full = np.where(
        aux_st_type == AIRPORT,
        bwt_r2f_full,
        bwt_f2ob_full
    )
    bwt_full = station_for_map.map(mapping_series)
    aux_st_type_full = station_for_map.str.split("-").str[0]
    final_bwt_full = np.where(
        (network[station_lvl1] != "") & (~network[station_lvl1].isna()),
        np.where(
            (aux_st_type_full == AIRPORT),
            bwt_airport_full,
            np.where(bwt_full.isna(), avg_tgt, bwt_full)
        ),
        0
    )
    network["bwt_" + station_lvl1.lower() + "_received_to_packed_full"] = final_bwt_full
    return network

# 4.1.2 Compute SOC Packed to LH Transporting 
def bwt_soc_pckd_2trans(network, targets, target_fmh_pckd_2trans, target_rcvd2flight, target_flight2ob, month_period, station_lvl1, station_lvl2):
    avg_tgt = pd.to_numeric(targets[month_period], errors='coerce').mean()
    # pass flight targets to numeric
    target_rcvd2flight[month_period] = pd.to_numeric(target_rcvd2flight[month_period], errors='coerce')
    target_flight2ob[month_period] = pd.to_numeric(target_flight2ob[month_period], errors='coerce')
    aux_r2f = target_rcvd2flight.copy()
    aux_f2ob = target_flight2ob.copy()
    aux_r2f[month_period] = aux_r2f[month_period] / 2
    aux_f2ob[month_period] = aux_f2ob[month_period] / 2
    # get avg for flights
    avg_rcvd2flight = aux_r2f[month_period].mean()
    avg_flight2ob = aux_f2ob[month_period].mean()

    # Creating series mapping targets for SOCs
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")
    # Creating series mapping targets for FMHs
    mapping_series_fmh = pd.to_numeric(target_fmh_pckd_2trans.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[COL_FMH_TGT_VALUE], errors='coerce')
    # Received to flight
    mapping_series_r2f = aux_r2f.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period]
    mapping_series_f2ob = aux_f2ob.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period]
    bwt_r2f = network[station_lvl1].str.replace('(XD)', '', regex=False).map(mapping_series_r2f).fillna(avg_rcvd2flight)
    bwt_f2ob = network[station_lvl1].str.replace('(XD)', '', regex=False).map(mapping_series_f2ob).fillna(avg_flight2ob)
    aux_st_type = network[station_lvl2].str.split("-").str[0]
    # get bwt for flight before ou after flight
    bwt_airport = np.where(
        aux_st_type == AIRPORT,
        bwt_r2f,
        bwt_f2ob
    )
    
    # Concatenate two series in one to do mapping
    mapping_series = pd.concat([mapping_series, mapping_series_fmh])

    # create bwt with targets
    bwt = network[station_lvl1].str.replace('(XD)', '', regex=False).map(mapping_series)

    # create final bwt idetifying cross-dock and putting avg to mising values
    aux_st_type = network[station_lvl1].str.split("-").str[0]
    final_bwt = np.where(
        (network[station_lvl1] != "") & (~network[station_lvl1].isna()),
        np.where(
            (aux_st_type == AIRPORT),
            bwt_airport,
            np.where(bwt.isna(), avg_tgt, bwt)
        ),
        0
    )
    network["bwt_" + station_lvl1.lower() + "_packed_to_transporting"] = final_bwt
    return network

# 4.2.0 LH inter SOC n>n+1
def bwt_lh_soc_to_soc(network, targets, month_period, station_lvl1, station_lvl2):
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")
    # Map route to next station available
    route_soc1_soc2 = network[station_lvl1].str.replace('(XD)', '', regex=False) + ">" + network[station_lvl2].str.replace('(XD)', '', regex=False)
    
    # create bwt with route outbound times
    bwt = pd.Series(route_soc1_soc2).map(mapping_series)
    # zero bwt where soc1 or soc2 is null
    final_bwt = np.where(
        (network[station_lvl1].isna()) | (network[station_lvl1] == "") | (network[station_lvl2].isna()) | (network[station_lvl2] == ""),
        0,
        bwt
    )

    network["bwt_lh_" + station_lvl1.lower() + "_to_" + station_lvl2.lower()] = final_bwt
    return network

# 4.4 Transit time LH SOC to LMH or XPT
def bwt_lh_soc_to_lmh_xpt(network, targets, lmh_or_xpt_dest="LMH", name_column=None):
    station_lvl1 = "SOC1"
    station_lvl2 = "SOC2"
    station_lvl3 = "SOC3"
    station_lvl4 = "SOC4"
    station_cols = ["FMH", station_lvl1, station_lvl2, station_lvl3, station_lvl4, "LMH", "XPT"]
    network[station_cols] = network[station_cols].fillna("")

    station_lvl5 = lmh_or_xpt_dest 
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")

    # Map last soc available
    last_soc = np.where(
        (network[station_lvl4].isna()) | (network[station_lvl4] == ""),
        np.where(
            network[station_lvl3].isna() | (network[station_lvl3] == ""),
            np.where(
                network[station_lvl2].isna() | (network[station_lvl2] == ""),
                network[station_lvl1].str.replace('(XD)', '', regex=False),
                network[station_lvl2].str.replace('(XD)', '', regex=False)
            ),    
            network[station_lvl3].str.replace('(XD)', '', regex=False)),
        network[station_lvl4].str.replace('(XD)', '', regex=False)
    )
    # Map LMH or XPT available
    if station_lvl5 == "LMH":
        lmh_xpt_available = np.where(
            (network[station_lvl5].isna()) | (network[station_lvl5] == ""),
            "",
            network[station_lvl5].str.replace('(XD)', '', regex=False)
        )
    else:
        lmh_xpt_available = np.where(
            (network["LMH"]!="") | (network[station_lvl5] == ""), 
            "",
            network[station_lvl5].str.replace('(XD)', '', regex=False) # if LMH is empty and XPT not empty
        )
        
    # route soc>lmh or xpt
    route_soc_station = last_soc + ">" + lmh_xpt_available

    # create bwt with route outbound times
    bwt = pd.Series(route_soc_station).map(mapping_series)

    # mask where start soc is null
    mask_first_soc_null = ((network[station_lvl1].isna()) | (network[station_lvl1] == ""))
    # mask where there is no lmh or xpt
    mask_no_lm_xpt = lmh_xpt_available == "" 

    final_bwt = np.where(
        mask_first_soc_null | mask_no_lm_xpt,
        0,
        bwt
    )

    if name_column is None:
        name_column = "bwt_lh_soc_to_" + lmh_or_xpt_dest.lower()
    network[name_column] = final_bwt
    return network

# 5.0 LMH Transported to Received
def bwt_LH_transported_2lmh_rcvd(network, targets, month_period, station_lvl1, name_column):
    avg_tgt = pd.to_numeric(targets[month_period], errors='coerce').mean()
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")

    # create bwt with targets
    bwt = network[station_lvl1].str.replace('-X$', '', regex=True).map(mapping_series)
    # create final bwt with avg for missing values or 0 for missing station
    final_bwt = np.where(
        (network[station_lvl1].isna()) | (network[station_lvl1] == ''),
        0,
        np.where(bwt.isna(), avg_tgt, bwt)
    )
    network[name_column] = final_bwt
    return network

# 5.1 LMH Received to LH Transporting to XPT or delivering 
def bwt_lm_rcvd_2xpt_dlvring(network, targets_xpt, targets_dlvring, month_period):  
    station_lvl1 = "LMH"
    station_lvl2 = "XPT"
    # Creating series mapping targets
    mapping_series_xpt = pd.to_numeric(targets_xpt.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")
    mapping_series_dlvring = pd.to_numeric(targets_dlvring.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")

    # create bwt with targets
    bwt_xpt = network[station_lvl1].str.replace('-X$', '', regex=True).map(mapping_series_xpt)
    bwt_dlvring = network[station_lvl1].str.replace('-X$', '', regex=True).map(mapping_series_dlvring)
    # pass to numeric 
    bwt_xpt = pd.to_numeric(bwt_xpt, errors='coerce')
    bwt_dlvring = pd.to_numeric(bwt_dlvring, errors='coerce')
    avg_tgt_xpt = pd.to_numeric(targets_xpt[month_period], errors='coerce').mean()
    avg_tgt_dlvring = pd.to_numeric(targets_dlvring[month_period], errors='coerce').mean()
    # create final bwt with avg for missing values or 0 for missing LMH
    final_bwt = np.where(
        (network[station_lvl1].isna()) | (network[station_lvl1] == ''),
        0.0,
        np.where((network[station_lvl2].isna()) | (network[station_lvl2] == ''),
                 np.where(bwt_dlvring.isna(), avg_tgt_dlvring, bwt_dlvring), 
                 np.where(bwt_xpt.isna(), avg_tgt_xpt, bwt_xpt)
                 )
    )
    network["bwt_lmh_received_to_LH_xpt_or_delivering"] = final_bwt
    return network

# 6.0 LMH LH transporting to LH transported (traveling)
def bwt_lmh_transporting_2transported(network, targets, distances, name_column):  
    distances = pd.to_numeric(distances, errors='coerce').fillna(0.0)
    
    # 1. Try to map with TTFinal from targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_ROUTE_TT]).set_index(COL_ROUTE_TT)[COL_TT_TT], errors="coerce")
    route_lmh_xpt = network["LMH"].str.replace('(XD)', '', regex=False) + ">" + network["XPT"].str.replace('(XD)', '', regex=False)
    # Ensure mapping uses the correct index
    bwt_mapped = pd.Series(route_lmh_xpt.values, index=network.index).map(mapping_series)
    
    # 2. Fallback calculation (Consistency with network simulation logic)
    bwt_calc = compute_dist_time(distances)
    # Min TT = 1h if distance < 3km (but > 0)
    bwt_calc = np.where((distances > 0) & (distances < 3.0), 1.0, bwt_calc)

    bwt_fallback = bwt_calc
    # Ensure 0 if distance is 0 or negative
    bwt_fallback = np.where(distances <= 0, 0.0, bwt_fallback)
    
    # 3. Final BWT: Mapped value or Fallback
    # We use the mapped value only if distance > 0, to avoid mapping non-existent legs
    final_bwt = np.where((distances > 0) & bwt_mapped.notnull(), bwt_mapped, bwt_fallback)
    
    network[name_column] = final_bwt
    return network


# 7.0 Delivering to Delivered
def bwt_delivering_2delivered(network, targets, month_period, station_lvl1, name_column):
    avg_tgt = pd.to_numeric(targets[month_period], errors='coerce').mean()
    
    # Creating series mapping targets
    mapping_series = pd.to_numeric(targets.drop_duplicates(subset=[COL_CODE_TARGETS]).set_index(COL_CODE_TARGETS)[month_period], errors="coerce")

    # create bwt with targets
    bwt = network[station_lvl1].str.replace('-X$', '', regex=True).map(mapping_series)
    # create final bwt with avg for missing values or 0 for missing station
    final_bwt = np.where(bwt.isna(), avg_tgt, bwt)
    network[name_column] = final_bwt
    return network

# -------------- Load inputs ---------------------
# Load networks
if READ_FROM_HIVE:
    # Usando o Data Service ID configurado no DataSuite com credenciais do .env
    service_id = 'brbi_opslgc.get_bwt_network_jards'
    app_key = os.environ.get('APP_KEY')
    app_secret = os.environ.get('APP_SECRET')
    
    print(f"Buscando dados via Data Service API: {service_id}")
    df_networks = get_df_from_dataservice(
        api_abbr=service_id, 
        app_key=app_key, 
        app_secret=app_secret
    )
else:
    df_networks = conn.get_sheets(scopes=GSHEET_NETWORK_INPUT, sh_name=RANGE_NETWORK_INPUT)

df_networks[COL_PERIOD_NETWORK] = df_networks[COL_PERIOD_NETWORK].astype(str).str[0:10]

df_station_uf = conn.get_sheets(scopes=GSHEET_STATION_LIST, sh_name=RANGE_STATION_LIST)
df_station_cep = conn.get_sheets(scopes=GSHEET_STATION_LIST, sh_name=RANGE_SPX_INFO)

app_key = os.environ.get('APP_KEY')
app_secret = os.environ.get('APP_SECRET')
print(f"Buscando dados via Data Service API: {STATION_NAMES_API}")
df_station_names = get_df_from_dataservice(
    api_abbr=STATION_NAMES_API,
    version=STATION_NAMES_VERSION,
    app_key=app_key,
    app_secret=app_secret,
)
station_state_lookup = build_station_state_lookup(df_station_names)

network_columns_without_bwt = df_networks.columns

# --------- Targets -----------
# 1.0 SELLER Paid to Dropoff
df_tgt_apt_paid_2dropoff = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_PAID_2DROPOFF)
# 2.0 FM Dropoff to Pickup 
df_tgt_dropoff_2pickup = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_DROPOFF_2PICKUP)
# 2.1 FM Pickup to SOC_FMH Received
df_tgt_pickup_2rcvd = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_PICKUP_2RECEIVED)
# 3.0.1 FMH Received to Packed
df_tgt_fmh_rcvd_2packed = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_FMH_RCVD_2PACKED)
# 3.0.2 FMH Packed to Transporting
df_tgt_fmh_pckd_2trans = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_FMH_PCKD_2TRANS)
# 3.1 FBS Received to Transporting
df_tgt_fbs_processing = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_FBS_PROCESSING)
# 4.0 SOC Received to Packed
df_tgt_soc_rcvd_2pckd = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_SOC_RECEIVED_2PCKD)
# 4.1 SOC Packed to Transporting to SOC
df_tgt_tt_and_soc_pckd_2trnspting_soc = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_SOC_PCKD_TO_TRNSPTDING_TO_SOC)
# 4.2 SOC Packed to Transporting
df_tgt_soc_pckd2trans = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_SOC_PCKD_TO_TRNSPTING)
# 4.9 LMH LH Arrived to Transported
df_tgt_lm_arrived_2transported = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_LM_ARRIVED_2TRANSPORTED)
# 5.0 LMH Transported to Received
df_tgt_lm_trans_2rcvd = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_LM_TRANS_2RCVD)
# 5.1.0 LMH Received to Delivering
df_tgt_lm_rcvd_2dlvring = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_LM_RCVD_2DLVRING)
# 5.1.1 LMH Received to LH transporting to XPT
df_tgt_lm_rcvd_2transporting_xpt = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_LM_RCVD_2XPT)
# 5.9 XPT LH Arrived to XPT Received
df_tgt_xpt_arrived_2rcvd = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_XPT_ARRIVED_2RCVD)
# 6.0 XPT Received to Delivering
df_tgt_lmh_lh_trnsprtd_2xpt_dlvring = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_XPT_RCVD_2DLVRING)
# 7.0 LMH Delivering to 1st
df_tgt_lmh_dlvring_2_1st = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_LMH_DLVRING_2_1ST)
# 7.1 XPT Delivering to 1st
df_tgt_xpt_dlvring_2_1st = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_TARGET_XPT_DLVRING_2_1ST)
# Combine both
df_tgt_dlvring_2dlvd = pd.concat([df_tgt_lmh_dlvring_2_1st, df_tgt_xpt_dlvring_2_1st], ignore_index=True)
# 8.1 Air LH Rcvd to Flight
df_tgt_flight_arr_2ob = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_RECEIVED_2DEPARTURE_AIRLH)
# 8.2 Air LH Rcvd to Flight
df_tgt_rcvd_2flight = conn.get_sheets(scopes=GSHEET_TARGET_INPUT, sh_name=RANGE_ARRIVED_2OB_AIRLH)

# Filter nulls and na
df_tgt_apt_paid_2dropoff = df_tgt_apt_paid_2dropoff.loc[~((df_tgt_apt_paid_2dropoff.iloc[:,0].isna()) | (df_tgt_apt_paid_2dropoff.iloc[:,0]==""))]
df_tgt_dropoff_2pickup = df_tgt_dropoff_2pickup.loc[~((df_tgt_dropoff_2pickup.iloc[:,0].isna()) | (df_tgt_dropoff_2pickup.iloc[:,0]==""))]
df_tgt_pickup_2rcvd = df_tgt_pickup_2rcvd.loc[~((df_tgt_pickup_2rcvd.iloc[:,0].isna()) | (df_tgt_pickup_2rcvd.iloc[:,0]==""))]
df_tgt_fmh_rcvd_2packed = df_tgt_fmh_rcvd_2packed.loc[~((df_tgt_fmh_rcvd_2packed.iloc[:,0].isna()) | (df_tgt_fmh_rcvd_2packed.iloc[:,0]==""))]
df_tgt_fmh_pckd_2trans = df_tgt_fmh_pckd_2trans.loc[~((df_tgt_fmh_pckd_2trans.iloc[:,0].isna()) | (df_tgt_fmh_pckd_2trans.iloc[:,0]==""))]
df_tgt_fbs_processing = df_tgt_fbs_processing.loc[~((df_tgt_fbs_processing.iloc[:,0].isna()) | (df_tgt_fbs_processing.iloc[:,0]==""))]
df_tgt_soc_rcvd_2pckd = df_tgt_soc_rcvd_2pckd.loc[~((df_tgt_soc_rcvd_2pckd.iloc[:,0].isna()) | (df_tgt_soc_rcvd_2pckd.iloc[:,0]==""))]
df_tgt_lm_arrived_2transported = df_tgt_lm_arrived_2transported.loc[~((df_tgt_lm_arrived_2transported.iloc[:,0].isna()) | (df_tgt_lm_arrived_2transported.iloc[:,0]==""))]
df_tgt_lm_trans_2rcvd = df_tgt_lm_trans_2rcvd.loc[~((df_tgt_lm_trans_2rcvd.iloc[:,0].isna()) | (df_tgt_lm_trans_2rcvd.iloc[:,0]==""))]
df_tgt_lm_rcvd_2dlvring = df_tgt_lm_rcvd_2dlvring.loc[~((df_tgt_lm_rcvd_2dlvring.iloc[:,0].isna()) | (df_tgt_lm_rcvd_2dlvring.iloc[:,0]==""))]
df_tgt_lm_rcvd_2transporting_xpt = df_tgt_lm_rcvd_2transporting_xpt.loc[~((df_tgt_lm_rcvd_2transporting_xpt.iloc[:,0].isna()) | (df_tgt_lm_rcvd_2transporting_xpt.iloc[:,0]==""))]
df_tgt_xpt_arrived_2rcvd = df_tgt_xpt_arrived_2rcvd.loc[~((df_tgt_xpt_arrived_2rcvd.iloc[:,0].isna()) | (df_tgt_xpt_arrived_2rcvd.iloc[:,0]==""))]
df_tgt_lmh_lh_trnsprtd_2xpt_dlvring = df_tgt_lmh_lh_trnsprtd_2xpt_dlvring.loc[~((df_tgt_lmh_lh_trnsprtd_2xpt_dlvring.iloc[:,0].isna()) | (df_tgt_lmh_lh_trnsprtd_2xpt_dlvring.iloc[:,0]==""))]
df_tgt_dlvring_2dlvd = df_tgt_dlvring_2dlvd.loc[~((df_tgt_dlvring_2dlvd.iloc[:,0].isna()) | (df_tgt_dlvring_2dlvd.iloc[:,0]==""))]

# --------------- Treat Inputs -----------------------------
# keep only without error
if COL_ERRO_NW in df_networks.columns:
    df_networks[COL_ERRO_NW] = df_networks[COL_ERRO_NW].fillna("")
    df_networks = df_networks[df_networks[COL_ERRO_NW] == ""]

# delete routes with distance = -1
df_networks = df_networks[~((df_networks[COLS_DISTANCES_NW] == "-1").any(axis=1))]
df_networks.reset_index(inplace=True, drop=True)

# transform ADO to numeric
df_networks[COL_ADO_NW] = pd.to_numeric(df_networks[COL_ADO_NW], errors="coerce")
df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_VALUE] = pd.to_numeric(df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_VALUE], errors="coerce")
df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_VALUE] = df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_VALUE].fillna(df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_VALUE].mean())
df_tgt_fmh_pckd_2trans[COL_FMH_TGT_VALUE] = pd.to_numeric(df_tgt_fmh_pckd_2trans[COL_FMH_TGT_VALUE], errors="coerce")
df_tgt_fmh_pckd_2trans[COL_FMH_TGT_VALUE] = df_tgt_fmh_pckd_2trans[COL_FMH_TGT_VALUE].fillna(df_tgt_fmh_pckd_2trans[COL_FMH_TGT_VALUE].mean())

# ----------------- COMPUTE BWT ----------------------------
periods_network = np.unique(df_networks[COL_PERIOD_NETWORK])
dict_networks = {period:df_networks.loc[df_networks[COL_PERIOD_NETWORK] == period] for period in periods_network}

# loop for all networks
for period in periods_network:
    print("Processing BWT period: " + period)
    # take first day of month
    month_period = period[:-2] + '01'
    # get target for each month
    tgt_fmh_rcvd_2packed_period = df_tgt_fmh_rcvd_2packed[df_tgt_fmh_rcvd_2packed[COL_FMH_TGT_PERIOD]==month_period][[COL_CODE_TARGETS, COL_FMH_TGT_VALUE]]
    tgt_fmh_pckd_2trans_period = df_tgt_fmh_pckd_2trans[df_tgt_fmh_pckd_2trans[COL_FMH_TGT_PERIOD]==month_period][[COL_CODE_TARGETS, COL_FMH_TGT_VALUE]]
    tgt_transit_time = df_tgt_tt_and_soc_pckd_2trnspting_soc[df_tgt_tt_and_soc_pckd_2trnspting_soc[COL_PERIOD_NAME_TT]==period][[COL_ROUTE_TT, COL_TT_TT]]

    # 1. seller processing - bwt paid to dropoff
    dict_networks[period] = bwt_paid_2dropoff(dict_networks[period], df_tgt_apt_paid_2dropoff[month_period])
    # 2.0 FM Dropoff to Pickup
    dict_networks[period] = bwt_dropoff_2pickup(dict_networks[period], df_tgt_dropoff_2pickup[month_period])
    # 2.1 FM Pickup to SOC_FMH Received
    dict_networks[period] = bwt_pickup_2rcvd(dict_networks[period], df_tgt_pickup_2rcvd[[COL_CODE_TARGETS,month_period]], month_period)
    # 2.2 FBS Processing
    dict_networks[period] = bwt_fbs_processing(dict_networks[period], df_tgt_fbs_processing[[COL_CODE_TARGETS,month_period]], month_period)
    # 3.0.1 / 3.0.2 FMH Received to Packed / Packed to Transporting
    dict_networks[period] = bwt_fmh_rcvd_2packed(dict_networks[period], tgt_fmh_rcvd_2packed_period)
    dict_networks[period] = bwt_fmh_pckd_2trans(dict_networks[period], tgt_fmh_pckd_2trans_period)
    # 4.0.1 Transit time LH FMH to SOC
    dict_networks[period] = bwt_lh_fmh_2soc(dict_networks[period], tgt_transit_time, month_period)
    dict_networks[period] = bwt_lh_fbs_2soc(dict_networks[period], tgt_transit_time, month_period)
    dict_networks[period] = bwt_lh_fmh_2lmh(dict_networks[period], tgt_transit_time, month_period)
    dict_networks[period] = bwt_lh_fbs_2lmh(dict_networks[period], tgt_transit_time, month_period)
    
    # 4.0.1 SOC1 Received to Packed / Packed to Transporting
    dict_networks[period] = bwt_soc_rcvd_2pckd(dict_networks[period], df_tgt_soc_rcvd_2pckd[[COL_CODE_TARGETS,month_period]], tgt_fmh_rcvd_2packed_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC1", "SOC2")
    dict_networks[period] = bwt_soc_pckd_2trans(dict_networks[period], df_tgt_soc_pckd2trans[[COL_CODE_TARGETS,month_period]], tgt_fmh_pckd_2trans_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC1", "SOC2")
    # 4.1.0 LH inter SOC1>2 / SOC2 Rcvd-Pckd / Pckd-Trans
    dict_networks[period] = bwt_lh_soc_to_soc(dict_networks[period], tgt_transit_time, month_period, "SOC1", "SOC2")
    dict_networks[period] = bwt_soc_rcvd_2pckd(dict_networks[period], df_tgt_soc_rcvd_2pckd[[COL_CODE_TARGETS,month_period]], tgt_fmh_rcvd_2packed_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC2", "SOC3")
    dict_networks[period] = bwt_soc_pckd_2trans(dict_networks[period], df_tgt_soc_pckd2trans[[COL_CODE_TARGETS,month_period]], tgt_fmh_pckd_2trans_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC2", "SOC3")
    # 4.2.0 LH inter SOC2>3 / SOC3 Rcvd-Pckd / Pckd-Trans
    dict_networks[period] = bwt_lh_soc_to_soc(dict_networks[period], tgt_transit_time, month_period, "SOC2", "SOC3")
    dict_networks[period] = bwt_soc_rcvd_2pckd(dict_networks[period], df_tgt_soc_rcvd_2pckd[[COL_CODE_TARGETS,month_period]], tgt_fmh_rcvd_2packed_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC3", "SOC4")
    dict_networks[period] = bwt_soc_pckd_2trans(dict_networks[period], df_tgt_soc_pckd2trans[[COL_CODE_TARGETS,month_period]], tgt_fmh_pckd_2trans_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC3", "SOC4")
    # 4.3.0 LH inter SOC3>4 / SOC4 Rcvd-Pckd / Pckd-Trans
    dict_networks[period] = bwt_lh_soc_to_soc(dict_networks[period], tgt_transit_time, month_period, "SOC3", "SOC4")
    dict_networks[period] = bwt_soc_rcvd_2pckd(dict_networks[period], df_tgt_soc_rcvd_2pckd[[COL_CODE_TARGETS,month_period]], tgt_fmh_rcvd_2packed_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC4", "LMH")
    dict_networks[period] = bwt_soc_pckd_2trans(dict_networks[period], df_tgt_soc_pckd2trans[[COL_CODE_TARGETS,month_period]], tgt_fmh_pckd_2trans_period,
                                                df_tgt_rcvd_2flight[[COL_CODE_TARGETS,month_period]], df_tgt_flight_arr_2ob[[COL_CODE_TARGETS,month_period]],
                                                month_period, "SOC4", "LMH")
    
    # 4.4.1 LH SOC to LMH / XPT
    dict_networks[period] = bwt_lh_soc_to_lmh_xpt(dict_networks[period], tgt_transit_time, "LMH")
    dict_networks[period] = bwt_lh_soc_to_lmh_xpt(dict_networks[period], tgt_transit_time, "XPT", "bwt_lh_soc_to_xpt_arrived")
    # 5.9 XPT LH Arrived to XPT Received
    dict_networks[period] = bwt_LH_transported_2lmh_rcvd(
        dict_networks[period],
        df_tgt_xpt_arrived_2rcvd[[COL_CODE_TARGETS, month_period]],
        month_period,
        'XPT',
        "bwt_lh_xpt_arrived_to_xpt_received"
    )
    # 4.9 LMH LH Arrived to Transported
    dict_networks[period] = bwt_LH_transported_2lmh_rcvd(
        dict_networks[period],
        df_tgt_lm_arrived_2transported[[COL_CODE_TARGETS, month_period]],
        month_period,
        'LMH',
        "bwt_lh_arrived_to_transported",
    )
    # 5.0 LMH T-R / R-LH / Traveling
    dict_networks[period] = bwt_LH_transported_2lmh_rcvd(dict_networks[period], df_tgt_lm_trans_2rcvd[[COL_CODE_TARGETS,month_period]], month_period, 'LMH', "bwt_lh_transported_to_lmh_received")
    dict_networks[period] = bwt_lm_rcvd_2xpt_dlvring(dict_networks[period], df_tgt_lm_rcvd_2transporting_xpt[[COL_CODE_TARGETS,month_period]], df_tgt_lm_rcvd_2dlvring[[COL_CODE_TARGETS,month_period]], month_period)
    dict_networks[period] = bwt_lmh_transporting_2transported(dict_networks[period], tgt_transit_time, dict_networks[period]["HUB-XPT"], "bwt_lmh_transporting_to_xpt_arrived")
    # 6.1 LH-XPT / 7.0 D-D (Split HUB and XPT)
    dict_networks[period] = bwt_LH_transported_2lmh_rcvd(dict_networks[period], df_tgt_lmh_lh_trnsprtd_2xpt_dlvring[[COL_CODE_TARGETS,month_period]], month_period, 'XPT', "bwt_lh_lmh_transported_to_xpt_to_delivering")
    
    # Calculate HUB delivery (using LMH targets)
    dict_networks[period] = bwt_delivering_2delivered(dict_networks[period], df_tgt_lmh_dlvring_2_1st[[COL_CODE_TARGETS,month_period]], month_period, "LMH", 'bwt_hub_delivering_to_1st_attempt')
    # Calculate XPT delivery (using XPT targets)
    dict_networks[period] = bwt_delivering_2delivered(dict_networks[period], df_tgt_xpt_dlvring_2_1st[[COL_CODE_TARGETS,month_period]], month_period, "XPT", 'bwt_xpt_delivering_to_1st_attempt')
    
    # Apply masks based on XPT presence
    mask_has_xpt = (dict_networks[period]["XPT"] != "") & (dict_networks[period]["XPT"].notnull())
    dict_networks[period].loc[mask_has_xpt, "bwt_hub_delivering_to_1st_attempt"] = 0.0
    dict_networks[period].loc[~mask_has_xpt, "bwt_xpt_delivering_to_1st_attempt"] = 0.0

print("Gathering results")
if dict_networks:
    network_output = pd.concat([dict_networks[period] for period in periods_network])
    network_output.reset_index(inplace=True, drop= True)
    column_bwt_total_h = "bwt_total_hours"
    column_bwt_total_xd_h = "bwt_total_hours_XD"
    numeric_bwt = network_output[columns_bwt].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    network_output[column_bwt_total_h] = numeric_bwt[columns_bwt_operational].sum(axis=1)
    network_output[column_bwt_total_xd_h] = numeric_bwt[columns_bwt_xd_total].sum(axis=1)
    # Count bounces
    cols_bounces = ["FMH", "SOC1", "SOC2", "LMH", "XPT"]
    network_output['bounces'] = (network_output[cols_bounces].fillna('') != '').sum(axis=1)


    # --- SubRegion Info ---
    col_zip_spm = "zipcode_SPM"
    df_station_cep[COL_ZIPCODE_SPX] = df_station_cep[COL_ZIPCODE_SPX].astype(str).str.rjust(8, '0')
    df_station_cep[col_zip_spm] = "Not SPM"
    df_station_cep.loc[df_station_cep[COL_ZIPCODE_SPX].str.startswith('0'), col_zip_spm] = "SPM"
    df_station_cep = df_station_cep[[COL_CODE_SPX, col_zip_spm]]

    df_station_uf[col_zip_spm] = "Not SPM"
    df_station_uf.loc[df_station_uf[COL_SUBREG_STATION_LIST] == CONST_SUBREG_SPM, col_zip_spm] = "SPM"
    df_station_uf = df_station_uf[[COL_CODE_STATION_LIST, col_zip_spm]]
    df_station_uf = df_station_uf.rename(columns={COL_CODE_STATION_LIST:COL_CODE_SPX})

    df_subreg = pd.concat([df_station_cep, df_station_uf])
    df_subreg = df_subreg.drop_duplicates(subset=COL_CODE_SPX, keep="first").reset_index(drop=True)

    network_output = pd.merge(network_output, df_subreg, how="left", left_on=COL_ORIGIN_NW, right_on=COL_CODE_SPX)
    network_output = network_output.rename(columns={col_zip_spm:COL_ORIGIN_BR_SPM})
    network_output = network_output.drop(COL_CODE_SPX, axis=1)

    network_output = pd.merge(network_output, df_subreg, how="left", left_on=COL_DEST_NW, right_on=COL_CODE_SPX)
    network_output = network_output.rename(columns={col_zip_spm:COL_DEST_BR_SPM})
    network_output = network_output.drop(COL_CODE_SPX, axis=1)

    network_output[COL_ORIGIN_BR_SPM] = network_output[COL_ORIGIN_BR_SPM].fillna("Not SPM")
    network_output[COL_DEST_BR_SPM] = network_output[COL_DEST_BR_SPM].fillna("Not SPM")

    network_output = add_estado_regional(network_output, station_state_lookup)

    network_output["period_start_aux"] = pd.to_datetime(network_output["period_start"]).dt.strftime('%Y-%m-%d')

    rows_before = len(network_output)
    network_output = network_output[~is_cb_origin(network_output[COL_ORIGIN_NW])].copy()
    print(f"Excluídas {rows_before - len(network_output)} linhas de ORIGIN CB (FMH-VCP-*, FMH-GRU-*, FMH-GIG-*)")

    # --- Filtro exclusivo para a aba "Network BWT output" ---
    start_of_month = date.today().replace(day=1)
    next_month = (start_of_month + relativedelta(months=1)).strftime("%Y-%m-%d")
    june_month = datetime.strptime('2026-06-01', '%Y-%m-%d').date().strftime("%Y-%m-%d")
    november_month = datetime.strptime('2026-11-01', '%Y-%m-%d').date().strftime("%Y-%m-%d")

    if BWT_OUTPUT_PERIOD_FILTER == "jun_nov":
        periods_to_print = [june_month, november_month]
    else:
        periods_to_print = [next_month, november_month]

    print(f"Filtro Network BWT output ({BWT_OUTPUT_PERIOD_FILTER}): {periods_to_print}")
    network_output_print = network_output[
        network_output["period_start_aux"].isin(periods_to_print)
    ].copy()
    
    network_output_print = network_output_print.fillna("").reset_index(drop=True)
    # network_output mantém todos os meses, mas sem ORIGINs CB (filtradas acima)

    COLS_OUTPUT_BWT = ['period_start', 'ORIGIN', 'DESTINATION', 'E2E Path', 'ADO', 'FMH', 'SOC1', 'SOC2', 'LMH', 'XPT', column_bwt_total_h, column_bwt_total_xd_h, 'bounces'] + columns_bwt + ['estado', 'regional']

    if PRINT_SHEET_BWT_E2E:
        target_id = GSHEET_PRINT_OUTPUT
        # [APPEND MODE] Lê a coluna A para descobrir a última linha com dados
        # conn.clean_specific_range(sheet_id=target_id, sheet_name=RANGE_PRINT_OUTPUT.split("!")[0], range_to_clear = RANGE_PRINT_OUTPUT_CLEAR)
        print(f"Detectando última linha preenchida na aba: {RANGE_PRINT_OUTPUT.split('!')[0]}")
        col_a_range_bwt = f"'{RANGE_PRINT_OUTPUT.split('!')[0]}'!A10:A"
        try:
            existing_rows_bwt = conn.get_sheets(scopes=target_id, sh_name=col_a_range_bwt, timeout=300, retries=3)
            last_row_bwt = len(existing_rows_bwt) + 10 # +10 linhas do topo (vazias + cabeçalho)
            is_bwt_sheet_empty = False 
        except Exception as e:
            print(f"Erro ao ler linhas da aba base: {e}")
            last_row_bwt = 10 # Somente o topo ocupado
            is_bwt_sheet_empty = True
        
        print_line_buffer = max(last_row_bwt, 9)
        print(f"Iniciando escrita a partir da linha {print_line_buffer + 1} (última linha detectada: {last_row_bwt})")
        print(f"Writing BWT result to sheet {target_id}")
        batch_size = 50000
        num_batches = int(network_output_print.shape[0]/batch_size)+1
        for i in range(num_batches):
            # Só adiciona +1 no offset dos pacotes seguintes se o primeiro pacote imprimiu cabeçalho
            add_line_title = 1 if (i > 0 and is_bwt_sheet_empty) else 0
            sh_range = f"'{RANGE_PRINT_OUTPUT.split('!')[0]}'!A" + str(1 + i*batch_size + print_line_buffer + add_line_title) 
            
            print(f"Escrevendo batch {i+1} de {num_batches} no Google Sheets (BWT results)...")
            current_batch_header = is_bwt_sheet_empty if i == 0 else False
            try:
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                     df=network_output_print.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT_BWT], print_columns=current_batch_header)
            except Exception:
                print('print in sheets failed, trying again.')
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                     df=network_output_print.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT_BWT], print_columns=False)

    # ============= Summary to sheets ==============
    bwt_output = network_output.copy()

    prefix_ado = "_ado_n"
    COL_FBS_FLAG = "fbs_flag"
    COL_SPX_FLAG = "spx_flag"
    COL_CB_FLAG = "cb_flag"
    COL_BWT = "bwt"
    cols_group = [COL_PERIOD_NETWORK, COL_SPX_FLAG, COL_FBS_FLAG, COL_CB_FLAG, COL_ORIGIN_BR_SPM, COL_DEST_BR_SPM]

    # 1. Treat before printing 
    bwt_output[COL_FBS_FLAG] = 0
    mask_fbs = bwt_output[COL_ORIGIN_NW].str[:3] == "FBS"
    bwt_output.loc[mask_fbs, COL_FBS_FLAG] = 1

    bwt_output[COL_CB_FLAG] = 0
    mask_cb = is_cb_origin(bwt_output[COL_ORIGIN_NW])
    bwt_output.loc[mask_cb, COL_CB_FLAG] = 1

    bwt_output[COL_SPX_FLAG] = 1
    mask_not_spx = (mask_cb | mask_fbs)
    bwt_output.loc[mask_not_spx, COL_SPX_FLAG] = 0

    bwt_output[COL_ADO_NW] = pd.to_numeric(bwt_output[COL_ADO_NW],errors='coerce')
    bwt_output_copy = bwt_output.copy() 

    # 2. Get ADO with BWT > 0 by column
    columns_ado_phase = []
    for bwt_colum in columns_bwt:
        col_ado_phase = bwt_colum + prefix_ado
        columns_ado_phase.append(col_ado_phase)
        bwt_output[col_ado_phase] = 0.0
        mask = bwt_output[bwt_colum] > 0
        bwt_output.loc[mask, col_ado_phase] = pd.to_numeric(bwt_output[COL_ADO_NW],errors='coerce') 
        bwt_output[bwt_colum] = bwt_output[bwt_colum].multiply(bwt_output[col_ado_phase], axis = 0)

    bwt_grouped = bwt_output.groupby(by=cols_group, as_index=False).sum(numeric_only=True)
    bwt_grouped['bwt'] = bwt_grouped[columns_bwt_operational].sum(axis=1)
    bwt_grouped['bwt_xd'] = bwt_grouped[columns_bwt_xd_total].sum(axis=1)
    COLS_OUTPUT_SUMMARY = cols_group + [COL_ADO_NW] + [COL_BWT, 'bwt_xd'] + columns_bwt + columns_ado_phase
    bwt_grouped = bwt_grouped[COLS_OUTPUT_SUMMARY]

    # ------------- Print Summary (Append Mode) ------------------
    if PRINT_SUMMARY_SHEET:
        print('Writing BWT Summary result to sheets')
        target_id = GSHEET_PRINT_OUTPUT
        try:
            col_a_range_summary = f"'{RANGE_OUTPUT_SUMMARY_WRITE.split('!')[0]}'!A2:A"
            existing_summary = conn.get_sheets(scopes=target_id, sh_name=col_a_range_summary, timeout=300, retries=3)
            last_row_summary = len(existing_summary) + 2 # +2 linhas do topo (link + cabeçalho)
            is_empty_summary = False
        except Exception as e:
            print(f"Erro ao ler linhas da aba summary: {e}")
            last_row_summary = 1 
            is_empty_summary = True
            
        start_row_summary = max(last_row_summary, 1)

        batch_size = 50000
        num_batches = int(bwt_grouped.shape[0]/batch_size)+1
        for i in range(num_batches):
            add_line_title = 1 if (i > 0 and is_empty_summary) else 0
            sh_range = f"'{RANGE_OUTPUT_SUMMARY_WRITE.split('!')[0]}'!A" + str(start_row_summary + 1 + i*batch_size + add_line_title) 
            
            print(f"Escrevendo batch {i+1} de {num_batches} no Google Sheets (Summary)...")
            current_batch_header = is_empty_summary if i == 0 else False
            try:
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                    df=bwt_grouped.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT_SUMMARY], print_columns=current_batch_header)
            except Exception:
                print('print in sheets failed, trying again.')
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                    df=bwt_grouped.loc[i*batch_size:((i+1)*batch_size-1), COLS_OUTPUT_SUMMARY], print_columns=False)

    # --------- 1st SOC ------------------------
    COL_BWTxADO_1st_SOC = "BWTxADO_1st_SOC"
    COLS_BWT_1st_soc = ["bwt_apt_paid_to_dropoff", "bwt_dropoff_to_pickup", "bwt_pickup_to_received", "bwt_fmh_received_to_packed", "bwt_fmh_packed_to_transporting", "bwt_lh_fmh_to_soc", "bwt_soc1_received_to_packed", "bwt_soc1_packed_to_transporting"]

    mask_1st_soc = (bwt_output_copy["SOC1"] != "") & (~bwt_output_copy["SOC1"].isna())
    bwt_1stSOC = bwt_output_copy[mask_1st_soc].copy()

    bwt_1stSOC[COLS_BWT_1st_soc] = bwt_1stSOC[COLS_BWT_1st_soc].apply(pd.to_numeric, errors='coerce')  
    bwt_1stSOC[COL_ADO_NW] = pd.to_numeric(bwt_1stSOC[COL_ADO_NW], errors='coerce')  
    bwt_1stSOC[COL_BWTxADO_1st_SOC] = bwt_1stSOC[COLS_BWT_1st_soc].sum(axis=1).fillna(0) * bwt_1stSOC[COL_ADO_NW]

    cols_group_1stSOC = [COL_PERIOD_NETWORK, COL_SPX_FLAG, COL_ORIGIN_BR_SPM, COL_DEST_BR_SPM, COL_FBS_FLAG, COL_CB_FLAG]
    cols_keep_group_1stSOC = cols_group_1stSOC + [COL_ADO_NW, COL_BWTxADO_1st_SOC]
    bwt_1stSOC[COL_FBS_FLAG] = bwt_1stSOC[COL_FBS_FLAG].astype(str)
    bwt_1stSOC[COL_CB_FLAG] = bwt_1stSOC[COL_CB_FLAG].astype(str)
    bwt_1stSOC_grouped = bwt_1stSOC[cols_keep_group_1stSOC].groupby(by=cols_group_1stSOC, as_index=False).sum(numeric_only=True)

    # ------------- Print 1st SOC (Append Mode) ------------------
    if PRINT_1ST_SOC_SHEET:
        print('Writing BWT 1st SOC Summary result to sheets')
        target_id = GSHEET_PRINT_OUTPUT
        try:
            col_a_range_1stsoc = f"'{RANGE_OUTPUT_1stSOC_WRITE.split('!')[0]}'!A2:A"
            existing_1stsoc = conn.get_sheets(scopes=target_id, sh_name=col_a_range_1stsoc, timeout=300, retries=3)
            last_row_1stsoc = len(existing_1stsoc) + 2 # +2 linhas do topo (link + cabeçalho)
            is_empty_1stsoc = False
        except Exception as e:
            print(f"Erro ao ler linhas da aba 1st SOC: {e}")
            last_row_1stsoc = 1
            is_empty_1stsoc = True
            
        start_row_1stsoc = max(last_row_1stsoc, 1)

        batch_size = 50000
        num_batches = int(bwt_1stSOC_grouped.shape[0]/batch_size)+1
        for i in range(num_batches):
            add_line_title = 1 if (i > 0 and is_empty_1stsoc) else 0
            sh_range = f"'{RANGE_OUTPUT_1stSOC_WRITE.split('!')[0]}'!A" + str(start_row_1stsoc + 1 + i*batch_size + add_line_title) 
            
            print(f"Escrevendo batch {i+1} de {num_batches} no Google Sheets (1st SOC)...")
            current_batch_header = is_empty_1stsoc if i == 0 else False
            try:
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                    df=bwt_1stSOC_grouped.loc[i*batch_size:((i+1)*batch_size-1), cols_keep_group_1stSOC], print_columns=current_batch_header)
            except Exception:
                print('print in sheets failed, trying again.')
                conn.print_in_sheets(scopes=target_id, sh_name=sh_range,
                                    df=bwt_1stSOC_grouped.loc[i*batch_size:((i+1)*batch_size-1), cols_keep_group_1stSOC], print_columns=False)

else:
    print("Nenhum dado para exportar.")
