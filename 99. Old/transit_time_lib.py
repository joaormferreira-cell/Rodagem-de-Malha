import numpy as np

def compute_dist_time(dist_km):
    """
    Primeiros 100km: Velocidade de 60km/h
    Após os primeiros 100km: Velocidade de 76km/h
    Descansos longos: 13h a cada 8 horas de direção (tempo_base)
    Descansos curtos: 1,5h a cada 5 horas de direção (tempo_base)
    """
    dist_km = np.array(dist_km, dtype=float)
    # tempo base em horas
    tempo_base = (np.minimum(dist_km, 100) / 60) + (np.maximum(dist_km - 100, 0) / 76)
    # descansos longos
    descansos_longos = np.floor(tempo_base / 8) * 13
    # descansos curtos
    descansos_curtos = np.floor(tempo_base / 5) * 1.5
    # tempo total
    tempo_total = tempo_base + descansos_longos + descansos_curtos

    # --------------  V2 ------------------------
    # dist_km = np.array(dist_km, dtype=float)
    # # Tempo base em horas dirigindo (primeiros 100km a 45 km/h, e o restante a 70 km/h)
    # tempo_base = (np.minimum(dist_km, 100) / 55) + (np.maximum(dist_km - 100, 0) / 75)

    # # cada ciclo em horas é de 10h30 dirigindo 
    # # Descansos longos a cada 12 horas de condução de trabalho do motorista (efetivamente 10h30 dirigindo)
    # descanso_longo = np.floor(tempo_base / 10.5) * 11
    # # Descansos curtos I (pausa de 0h30 após as primeiras 5h30 de cada ciclo)
    # descansos_curtos_1 = ((np.floor(tempo_base / 10.5) + np.floor( (tempo_base % 10.5) / 5.5) )) * 0.5
    # # Descansos curtos II (após o primeiro descanso curto, pausa de uma hora para almoçar)
    # descansos_curtos_2 = ((np.floor(tempo_base / 10.5) + np.floor( (tempo_base % 10.5) / 8) )) * 1
    # # Tempo total = Tempo base + descansos
    # tempo_total = tempo_base + descanso_longo + descansos_curtos_1 + descansos_curtos_2

    return tempo_total


def compute_dist_time_express_routes(dist_km):
    """
    Primeiros 100km: Velocidade de 65km/h
    Após os primeiros 100km: Velocidade de 70 - 75km/h
    Troca de motorista: 60 min apos 12 horas de deslocamento
    Descansos curtos I: 30 min apos 5:30 de percurso.
    Descansos curtos II: 60 min apos 8:00 de percurso (almoço)
    """
    dist_km = np.array(dist_km, dtype=float)
    # tempo base em horas
    tempo_base = (np.minimum(dist_km, 100) / 60) + (np.maximum(dist_km - 100, 0) / 76)
    # descansos longos
    troca_motorista = np.floor(tempo_base / 8) * 1
    # descansos curtos
    descansos_curtos = np.floor(tempo_base / 5) * 1.5
    # tempo total
    tempo_total = tempo_base + descansos_curtos + troca_motorista

    
    # --------------  V2 ------------------------
    # dist_km = np.array(dist_km, dtype=float)
    # # Tempo base em horas dirigindo (primeiros 100km a 45 km/h, e o restante a 65 km/h) 
    # tempo_base = (np.minimum(dist_km, 100) / 55) + (np.maximum(dist_km - 100, 0) / 75)

    # # cada ciclo em horas é de 10h30 dirigindo 
    # # Troca de motoristas a cada 12 horas de condução de trabalho do motorista (efetivamente 10h30 dirigindo)
    # troca_motorista = np.floor(tempo_base / 10.5) * 1
    # # Descansos curtos I (pausa de 0h30 após as primeiras 5h30 de cada ciclo)
    # descansos_curtos_1 = ((np.floor(tempo_base / 10.5) + np.floor( (tempo_base % 10.5) / 5.5) )) * 0.5
    # # Descansos curtos II (após o primeiro descanso curto, pausa de uma hora para almoçar )
    # descansos_curtos_2 = ((np.floor(tempo_base / 10.5) + np.floor( (tempo_base % 10.5) / 8) )) * 1
    # # Tempo total = Tempo base + descansos
    # tempo_total = tempo_base + troca_motorista + descansos_curtos_1 + descansos_curtos_2

    return tempo_total
