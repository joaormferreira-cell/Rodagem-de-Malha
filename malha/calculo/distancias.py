"""Distância de cada trecho: cadastro (vale nos dois sentidos) → linha reta × 1,4 → -1 (sem como calcular)."""
import numpy as np
import pandas as pd

from ..configuracao import premissas

SEM_DISTANCIA = -1


def tabela_distancias(cadastro):
    """{'ORIGEM>DESTINO': km}. O sentido cadastrado tem prioridade sobre o inverso."""
    ida = cadastro[["origin", "destini", "distance_km", "route"]]
    volta = ida.rename(columns={"origin": "destini", "destini": "origin"})
    volta = volta.assign(route=volta["origin"] + ">" + volta["destini"])
    todas = pd.concat([ida, volta]).drop_duplicates("route", keep="first")
    return dict(zip(todas["route"], pd.to_numeric(todas["distance_km"], errors="coerce")))


def tabela_coordenadas(historico, base):
    """Latitude e longitude por estação: Station List Historical primeiro, depois a Base (operações novas)."""
    base = base.rename(columns={"CODE": "Code"})
    novas = base[["Code", "Lat", "Lon"]].rename(columns={"Code": "station_code", "Lat": "latitude", "Lon": "longitude"})
    todas = pd.concat([historico[["station_code", "latitude", "longitude"]], novas])
    todas = todas[todas["station_code"].notna() & (todas["station_code"] != "")]
    todas = todas.drop_duplicates("station_code", keep="first")
    lat = dict(zip(todas["station_code"], pd.to_numeric(todas["latitude"], errors="coerce")))
    lon = dict(zip(todas["station_code"], pd.to_numeric(todas["longitude"], errors="coerce")))
    return lat, lon


def linha_reta_ajustada(lat1, lon1, lat2, lon2, p=None):
    """Haversine × multiplicador. -1 se faltar alguma coordenada."""
    p = p or premissas()["distancia"]
    if any(c is None or c == "" or pd.isna(c) for c in (lat1, lon1, lat2, lon2)):
        return SEM_DISTANCIA
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return p["raio_terra_km"] * 2 * np.arcsin(np.sqrt(a)) * p["multiplicador_haversine"]


def sem_coordenada(codigo, lat, lon):
    return codigo not in lat or codigo not in lon or pd.isna(lat[codigo]) or pd.isna(lon[codigo])
