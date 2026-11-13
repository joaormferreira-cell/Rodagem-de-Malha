"""
BWT por caminho (etapa 4): soma o tempo de cada etapa do pacote, do pagamento até a 1ª tentativa de entrega.

Cada etapa vem de uma de três fontes:
  - META por estação: aba [T] da planilha de metas (ex.: SOC-SP1 leva 3h de Received a Packed).
    Estação sem meta → média das metas do mês.
  - TEMPO DE ROTA: TTFinal das rotas (etapas 2 e 3).
  - VALOR ÚNICO: uma meta só para todos (etapas 1.0 e 2.0 do seller/FM).
Etapa que não existe no caminho (ex.: não tem SOC2) vale 0.
"""
import numpy as np
import pandas as pd

from ..configuracao import premissas
from .estados import estado_e_regional, tabela_estados
from .tempo_viagem import tt_normal

AEROPORTO = "Airport"

# (coluna, o que é, de onde vem) — na ordem do caminho do pacote
COMPONENTES = [
    ("bwt_apt_paid_to_dropoff", "Seller: pago → entregue no ponto/coletado", "[T] 1.0 (valor único; FBS = 0)"),
    ("bwt_dropoff_to_pickup", "First mile: dropoff → coleta", "[T] 2.0 (valor único; FBS = 0)"),
    ("bwt_pickup_to_received", "First mile: coleta → recebido no FMH/SOC", "[T] 2.1 por FMH (ou SOC1)"),
    ("bwt_fbs_processing", "FBS: processamento", "[T] 3.1 por FBS"),
    ("bwt_fmh_received_to_packed", "FMH: recebido → embalado", "[T] 3.0.1 por FMH"),
    ("bwt_fmh_packed_to_transporting", "FMH: embalado → saindo", "[T] 3.0.2 por FMH"),
    ("bwt_lh_fmh_to_soc", "Viagem FMH → SOC1", "TTFinal da rota"),
    ("bwt_lh_fbs_to_soc", "Viagem FBS → SOC1", "TTFinal da rota"),
    ("bwt_lh_fmh_to_lmh_arrived", "Viagem FMH → HUB (sem SOC)", "TTFinal da rota"),
    ("bwt_lh_fbs_to_lmh_arrived", "Viagem FBS → HUB (sem SOC)", "TTFinal da rota"),
    ("bwt_soc1_received_to_packed", "SOC1: recebido → embalado (0 se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc1_received_to_packed_full", "SOC1: recebido → embalado (mesmo se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc1_packed_to_transporting", "SOC1: embalado → saindo", "[T] 4.2 por SOC"),
    ("bwt_lh_soc1_to_soc2", "Viagem SOC1 → SOC2", "TTFinal da rota"),
    ("bwt_soc2_received_to_packed", "SOC2: recebido → embalado (0 se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc2_received_to_packed_full", "SOC2: recebido → embalado (mesmo se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc2_packed_to_transporting", "SOC2: embalado → saindo", "[T] 4.2 por SOC"),
    ("bwt_lh_soc2_to_soc3", "Viagem SOC2 → SOC3", "TTFinal da rota"),
    ("bwt_soc3_received_to_packed", "SOC3: recebido → embalado (0 se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc3_received_to_packed_full", "SOC3: recebido → embalado (mesmo se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc3_packed_to_transporting", "SOC3: embalado → saindo", "[T] 4.2 por SOC"),
    ("bwt_lh_soc3_to_soc4", "Viagem SOC3 → SOC4", "TTFinal da rota"),
    ("bwt_soc4_received_to_packed", "SOC4: recebido → embalado (0 se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc4_received_to_packed_full", "SOC4: recebido → embalado (mesmo se cross-dock)", "[T] 4.0 por SOC"),
    ("bwt_soc4_packed_to_transporting", "SOC4: embalado → saindo", "[T] 4.2 por SOC"),
    ("bwt_lh_soc_to_lmh", "Viagem último SOC → HUB", "TTFinal da rota"),
    ("bwt_lh_soc_to_xpt_arrived", "Viagem último SOC → XPT (sem HUB)", "TTFinal da rota"),
    ("bwt_lh_xpt_arrived_to_xpt_received", "XPT: chegou → recebido", "[T] 5.9 por XPT"),
    ("bwt_lh_arrived_to_transported", "HUB: chegou → descarregado", "[T] 4.9 por HUB"),
    ("bwt_lh_transported_to_lmh_received", "HUB: descarregado → recebido", "[T] 5.0 por HUB"),
    ("bwt_lmh_received_to_LH_xpt_or_delivering", "HUB: recebido → saindo p/ XPT ou p/ entrega", "[T] 5.1.1 / 5.1.0 por HUB"),
    ("bwt_lmh_transporting_to_xpt_arrived", "Viagem HUB → XPT", "TTFinal da rota (senão cálculo por km)"),
    ("bwt_lh_lmh_transported_to_xpt_to_delivering", "XPT: recebido → saindo p/ entrega", "[T] 6.0 por XPT"),
    ("bwt_hub_delivering_to_1st_attempt", "Entrega pelo HUB: saiu → 1ª tentativa", "[T] 7.0 por HUB"),
    ("bwt_xpt_delivering_to_1st_attempt", "Entrega pelo XPT: saiu → 1ª tentativa", "[T] 7.1 por XPT"),
]
COLUNAS_BWT = [c for c, _, _ in COMPONENTES]
# "_full" = recebido→embalado contando o SOC mesmo quando é cross-dock (total XD)
TROCA_FULL = {f"bwt_soc{i}_received_to_packed": f"bwt_soc{i}_received_to_packed_full" for i in range(1, 5)}
COLUNAS_OPERACIONAL = [c for c in COLUNAS_BWT if c not in TROCA_FULL.values()]
COLUNAS_TOTAL_XD = [TROCA_FULL.get(c, c) for c in COLUNAS_OPERACIONAL]
ESTACOES = ["FMH", "SOC1", "SOC2", "SOC3", "SOC4", "LMH", "XPT"]
DISTANCIAS = ["FMH-SOC", "SOC1-SOC2", "SOC2-SOC3", "SOC3-SOC4", "SOC-HUB", "FMH-HUB", "HUB-XPT", "SOC-XPT"]
COLUNAS_SAIDA = (["period_start", "ORIGIN", "DESTINATION", "E2E Path", "ADO", "FMH", "SOC1", "SOC2", "LMH", "XPT",
                  "bwt_total_hours", "bwt_total_hours_XD", "bounces"] + COLUNAS_BWT + ["estado", "regional"])
GRUPO_RESUMO = ["period_start", "spx_flag", "fbs_flag", "cb_flag", "origin_spm", "dest_spm"]
COLUNAS_RESUMO = (GRUPO_RESUMO + ["ADO", "bwt", "bwt_xd"] + COLUNAS_BWT + [c + "_ado_n" for c in COLUNAS_BWT])
ETAPAS_1O_SOC = ["bwt_apt_paid_to_dropoff", "bwt_dropoff_to_pickup", "bwt_pickup_to_received",
                 "bwt_fmh_received_to_packed", "bwt_fmh_packed_to_transporting", "bwt_lh_fmh_to_soc",
                 "bwt_soc1_received_to_packed", "bwt_soc1_packed_to_transporting"]
GRUPO_1O_SOC = ["period_start", "spx_flag", "origin_spm", "dest_spm", "fbs_flag", "cb_flag"]
COLUNAS_1O_SOC = GRUPO_1O_SOC + ["ADO", "BWTxADO_1st_SOC"]


# ---------------- Ajudantes ----------------
def como_planilha(df):
    """Valores como ficam depois de gravados no Hive/Sheets e lidos de volta (tudo texto; vazio = '')."""
    def _v(v):
        if v is None:
            return ""
        if isinstance(v, (bool, np.bool_)):
            return "TRUE" if v else "FALSE"
        if isinstance(v, float):
            return "" if v != v else (str(int(v)) if v.is_integer() else repr(v))
        return str(v)
    return df.apply(lambda col: col.map(_v))


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _vazio(s):
    return s.isna() | (s == "")


def _sem_xd(s):
    return s.str.replace("(XD)", "", regex=False)


def _sem_x(s):
    return s.str.replace("-X$", "", regex=True)


def _tipo(s):
    return s.str.split("-").str[0]


def _por_codigo(meta, coluna):
    """Meta → {código da estação: horas} (primeira linha de cada código vale)."""
    return _num(meta.drop_duplicates("code").set_index("code")[coluna])


def _meta_do_mes(meta, mes):
    return _num(meta[mes]) if mes in meta.columns else pd.Series(np.nan, index=meta.index)


def _com_codigo(meta):
    """Tira as linhas sem estação na 1ª coluna (como o processo atual)."""
    return meta[~_vazio(meta.iloc[:, 0])] if not meta.empty else meta


# ---------------- Etapas ----------------
def _seller_e_first_mile(c, metas, mes, p):
    fbs = c["FMH"].str[:3] == "FBS"
    for col, meta in [("bwt_apt_paid_to_dropoff", metas["meta_1_0"]), ("bwt_dropoff_to_pickup", metas["meta_2_0"])]:
        c[col] = np.where(fbs, 0, float(meta[mes].loc[0]))   # valor único: 1ª linha da aba

    m = metas["meta_2_1"]
    media = _meta_do_mes(m[m["code"].str[:len(p["fmh_fora_da_media"])] != p["fmh_fora_da_media"]], mes).mean()
    estacao = np.where(_vazio(c["FMH"]), _sem_x(_sem_xd(c["SOC1"])), _sem_x(_sem_xd(c["FMH"])))
    valor = pd.Series(estacao, index=c.index).map(_por_codigo(m, mes))
    c["bwt_pickup_to_received"] = np.where(fbs, 0, valor.fillna(media))

    m = metas["meta_3_1"]
    valor = c["FMH"].map(_por_codigo(m, mes))
    c["bwt_fbs_processing"] = np.where(fbs, valor.fillna(_meta_do_mes(m, mes).mean()), 0)


def _fmh(c, meta_mes, coluna, p):
    """FMH recebido→embalado / embalado→saindo. Média sem FMH-PHP e sem FBS."""
    fora = p["fmh_fora_da_media"]
    na_media = (meta_mes["code"].str[:len(fora)] != fora) & (meta_mes["code"].str[:3] != "FBS")
    media = _num(meta_mes.loc[na_media, "Target Received to Transporting"]).mean()
    valor = c["FMH"].map(_por_codigo(meta_mes, "Target Received to Transporting"))
    c[coluna] = np.where((c["FMH"].str[:3] == "FBS") | _vazio(c["FMH"]), 0.0, valor.fillna(media))


def _primeira_viagem(c, tt):
    """FMH/FBS → SOC1 ou → HUB direto. Rota fora da lista de rotas fica vazia."""
    fbs = c["FMH"].str[:3] == "FBS"
    sem_fmh = _vazio(c["FMH"])
    para_soc = (_sem_xd(c["FMH"]) + ">" + _sem_xd(c["SOC1"])).map(tt)
    para_hub = (_sem_xd(c["FMH"]) + ">" + _sem_xd(c["LMH"])).map(tt)
    tem_soc = c["SOC1"] != ""
    c["bwt_lh_fmh_to_soc"] = np.where(fbs | sem_fmh | (c["SOC1"] == ""), 0.0, para_soc)
    c["bwt_lh_fbs_to_soc"] = np.where(~fbs | sem_fmh | (c["SOC1"] == ""), 0.0, para_soc)
    c["bwt_lh_fmh_to_lmh_arrived"] = np.where(tem_soc | fbs | sem_fmh | _vazio(c["LMH"]), 0.0, para_hub)
    c["bwt_lh_fbs_to_lmh_arrived"] = np.where(tem_soc | ~fbs | sem_fmh | (c["LMH"] == ""), 0.0, para_hub)


def _soc(c, est, prox, metas, mes, fmh_rcvd, fmh_pckd):
    """
    SOC recebido→embalado e embalado→saindo.
    Estação aeroporto usa a meta de aeroporto ÷ 2. Cross-dock (XD) não tem recebido→embalado
    (a coluna _full tem o valor mesmo assim).
    """
    aero = metas["meta_8"]
    aero_mes = _meta_do_mes(aero, mes) / 2
    aero_por_codigo = pd.Series(aero_mes.to_numpy(), index=aero["code"]).loc[~aero["code"].duplicated().to_numpy()]
    media_aero = aero_mes.mean()
    preenchida = ~_vazio(c[est])
    tipo = _tipo(c[est])

    # recebido → embalado
    m = metas["meta_4_0"]
    por_codigo = pd.concat([_por_codigo(m, mes), _por_codigo(fmh_rcvd, "Target Received to Transporting")])
    media = _meta_do_mes(m, mes).mean()
    aero_valor = c[est].map(aero_por_codigo).fillna(media_aero)   # mesma meta antes/depois do voo
    valor = c[est].map(por_codigo)
    xd = c[est].str.contains("(XD)", regex=False)
    c[f"bwt_{est.lower()}_received_to_packed"] = np.where(
        ~xd & preenchida, np.where(tipo == AEROPORTO, aero_valor, valor.fillna(media)), 0)
    sem = _sem_xd(c[est])
    aero_full = sem.map(aero_por_codigo).fillna(media_aero)
    valor_full = sem.map(por_codigo)
    c[f"bwt_{est.lower()}_received_to_packed_full"] = np.where(
        preenchida, np.where(_tipo(sem) == AEROPORTO, aero_full, valor_full.fillna(media)), 0)

    # embalado → saindo
    m = metas["meta_4_2"]
    por_codigo = pd.concat([_por_codigo(m, mes), _por_codigo(fmh_pckd, "Target Received to Transporting")])
    media = _meta_do_mes(m, mes).mean()
    valor = sem.map(por_codigo)
    c[f"bwt_{est.lower()}_packed_to_transporting"] = np.where(
        preenchida, np.where(tipo == AEROPORTO, aero_full, valor.fillna(media)), 0)


def _viagem_entre_socs(c, est, prox, tt):
    rota = (_sem_xd(c[est]) + ">" + _sem_xd(c[prox])).map(tt)
    c[f"bwt_lh_{est.lower()}_to_{prox.lower()}"] = np.where(_vazio(c[est]) | _vazio(c[prox]), 0, rota)


def _ultimo_soc_ao_destino(c, tt):
    """Viagem do último SOC até o HUB, ou até o XPT quando não tem HUB."""
    c[ESTACOES] = c[ESTACOES].fillna("")
    ultimo = _sem_xd(c["SOC1"])
    for est in ["SOC2", "SOC3", "SOC4"]:
        ultimo = np.where(c[est] == "", ultimo, _sem_xd(c[est]))
    hub = np.where(c["LMH"] == "", "", _sem_xd(c["LMH"]))
    xpt = np.where((c["LMH"] != "") | (c["XPT"] == ""), "", _sem_xd(c["XPT"]))
    sem_soc = c["SOC1"] == ""
    for destino, coluna in [(hub, "bwt_lh_soc_to_lmh"), (xpt, "bwt_lh_soc_to_xpt_arrived")]:
        valor = pd.Series(pd.Series(ultimo) + ">" + pd.Series(destino)).map(tt).to_numpy()
        c[coluna] = np.where(sem_soc.to_numpy() | (destino == ""), 0, valor)


def _meta_na_estacao(c, meta, mes, est, coluna):
    """Meta da estação (HUB ou XPT); estação sem meta = média; sem a estação no caminho = 0."""
    valor = _sem_x(c[est]).map(_por_codigo(meta, mes))
    c[coluna] = np.where(_vazio(c[est]), 0, valor.fillna(_meta_do_mes(meta, mes).mean()))


def _last_mile(c, metas, mes, tt):
    _meta_na_estacao(c, metas["meta_5_9"], mes, "XPT", "bwt_lh_xpt_arrived_to_xpt_received")
    _meta_na_estacao(c, metas["meta_4_9"], mes, "LMH", "bwt_lh_arrived_to_transported")
    _meta_na_estacao(c, metas["meta_5_0"], mes, "LMH", "bwt_lh_transported_to_lmh_received")

    # HUB recebido → saindo para o XPT (se tem XPT) ou para a entrega
    hub = _sem_x(c["LMH"])
    p_xpt, p_ent = metas["meta_5_1_1"], metas["meta_5_1_0"]
    para_xpt = hub.map(_por_codigo(p_xpt, mes)).fillna(_meta_do_mes(p_xpt, mes).mean())
    para_ent = hub.map(_por_codigo(p_ent, mes)).fillna(_meta_do_mes(p_ent, mes).mean())
    c["bwt_lmh_received_to_LH_xpt_or_delivering"] = np.where(
        _vazio(c["LMH"]), 0.0, np.where(_vazio(c["XPT"]), para_ent, para_xpt))

    # viagem HUB → XPT: TTFinal da rota; se não tiver, cálculo por km (mínimo 1h abaixo de 3 km)
    km = _num(c["HUB-XPT"]).fillna(0.0)
    da_rota = (_sem_xd(c["LMH"]) + ">" + _sem_xd(c["XPT"])).map(tt)
    por_km = np.where((km > 0) & (km < 3.0), 1.0, tt_normal(km))
    por_km = np.where(km <= 0, 0.0, por_km)
    c["bwt_lmh_transporting_to_xpt_arrived"] = np.where((km > 0) & da_rota.notnull(), da_rota, por_km)

    _meta_na_estacao(c, metas["meta_6_0"], mes, "XPT", "bwt_lh_lmh_transported_to_xpt_to_delivering")

    # entrega: pelo XPT se tem XPT, senão pelo HUB (sem a estação = média)
    tem_xpt = (c["XPT"] != "") & c["XPT"].notnull()
    for meta, est, coluna in [(metas["meta_7_0"], "LMH", "bwt_hub_delivering_to_1st_attempt"),
                              (metas["meta_7_1"], "XPT", "bwt_xpt_delivering_to_1st_attempt")]:
        c[coluna] = _sem_x(c[est]).map(_por_codigo(meta, mes)).fillna(_meta_do_mes(meta, mes).mean()).to_numpy()
    c.loc[tem_xpt, "bwt_hub_delivering_to_1st_attempt"] = 0.0
    c.loc[~tem_xpt, "bwt_xpt_delivering_to_1st_attempt"] = 0.0


def _bwt_do_mes(c, metas, periodo, tt, p):
    mes = periodo[:-2] + "01"
    fmh_rcvd = metas["meta_3_0_1"][metas["meta_3_0_1"]["period_start"] == mes][["code", "Target Received to Transporting"]]
    fmh_pckd = metas["meta_3_0_2"][metas["meta_3_0_2"]["period_start"] == mes][["code", "Target Received to Transporting"]]
    _seller_e_first_mile(c, metas, mes, p)
    _fmh(c, fmh_rcvd, "bwt_fmh_received_to_packed", p)
    _fmh(c, fmh_pckd, "bwt_fmh_packed_to_transporting", p)
    _primeira_viagem(c, tt)
    for est, prox in [("SOC1", "SOC2"), ("SOC2", "SOC3"), ("SOC3", "SOC4"), ("SOC4", "LMH")]:
        _soc(c, est, prox, metas, mes, fmh_rcvd, fmh_pckd)
        if prox != "LMH":
            _viagem_entre_socs(c, est, prox, tt)
    _ultimo_soc_ao_destino(c, tt)
    _last_mile(c, metas, mes, tt)
    return c


# ---------------- Preparação e resumo ----------------
def preparar_metas(metas):
    """Tira linhas sem estação e completa a meta de FMH vazia com a média (como o processo atual)."""
    # o processo atual não filtra estas abas (linha sem estação entra na média)
    sem_filtro = {"meta_4_2", "meta_7_0", "meta_7_1", "meta_8"}
    metas = {k: (v if k in sem_filtro else _com_codigo(v)).copy() for k, v in metas.items()}
    for k in ["meta_3_0_1", "meta_3_0_2"]:
        valor = _num(metas[k]["Target Received to Transporting"])
        metas[k]["Target Received to Transporting"] = valor.fillna(valor.mean())
    return metas


def _spm(subregiao, spx_info, p):
    """Estação em SP Metropolitana: CEP começando com 0 (SPX_info) ou SubRegion SAO (Base)."""
    # CEP vazio = Not SPM (o zipcode é a última coluna lida, então vazio chega como "sem valor" no processo atual)
    cep = spx_info["zipcode"].fillna("").astype(str)
    spm_cep = (cep != "") & cep.str.rjust(8, "0").str.startswith("0")
    por_cep = pd.DataFrame({"station_code": spx_info["station_code"],
                            "spm": np.where(spm_cep, "SPM", "Not SPM")})
    por_regiao = pd.DataFrame({"station_code": subregiao["Code"],
                               "spm": np.where(subregiao["SubRegion"].isin(p["regioes_spm"]), "SPM", "Not SPM")})
    tabela = pd.concat([por_cep, por_regiao]).drop_duplicates("station_code", keep="first")
    return tabela.set_index("station_code")["spm"]


def _flags(saida, p):
    fbs = saida["ORIGIN"].str[:3] == "FBS"
    cb = saida["ORIGIN"].str[:7].isin(p["origens_cb"])
    saida["fbs_flag"] = fbs.astype(int)
    saida["cb_flag"] = cb.astype(int)
    saida["spx_flag"] = (~(fbs | cb)).astype(int)
    return saida


def resumo(caminhos):
    """raw_bwt: horas × pacotes somadas por grupo (só conta pacote na etapa se a etapa tem tempo > 0)."""
    df = caminhos.copy()
    for col in COLUNAS_BWT:
        ado_etapa = np.where(df[col] > 0, df["ADO"], 0.0)
        df[col + "_ado_n"] = ado_etapa
        df[col] = df[col] * ado_etapa
    g = df.groupby(GRUPO_RESUMO, as_index=False)[["ADO"] + COLUNAS_BWT + [c + "_ado_n" for c in COLUNAS_BWT]].sum()
    g["bwt"] = g[COLUNAS_OPERACIONAL].sum(axis=1)
    g["bwt_xd"] = g[COLUNAS_TOTAL_XD].sum(axis=1)
    return g[COLUNAS_RESUMO]


def resumo_1o_soc(caminhos):
    """raw_data_1st_SOC: horas × pacotes até sair do 1º SOC (só caminhos com SOC)."""
    df = caminhos[~_vazio(caminhos["SOC1"])].copy()
    df["BWTxADO_1st_SOC"] = df[ETAPAS_1O_SOC].apply(_num).sum(axis=1).fillna(0) * df["ADO"]
    df["fbs_flag"] = df["fbs_flag"].astype(str)
    df["cb_flag"] = df["cb_flag"].astype(str)
    return df[COLUNAS_1O_SOC].groupby(GRUPO_1O_SOC, as_index=False).sum(numeric_only=True)


# ---------------- Execução ----------------
def calcular_bwt(malha, rotas, metas, subregiao, spx_info, lista_estacoes):
    """
    malha: saída da etapa 1; rotas: saída da etapa 3 ([T] 4.1).
    Devolve {"bwt_caminhos": BWT por caminho, "bwt_resumo": raw_bwt, "bwt_1o_soc": raw_data_1st_SOC}.
    """
    p = {**premissas()["bwt"], **premissas()["rotas"]}
    rede = como_planilha(malha)
    rede["period_start"] = rede["period_start"].str[:10]
    rede = rede[rede["ERRO"].fillna("") == ""] if "ERRO" in rede.columns else rede
    rede = rede[~(rede[DISTANCIAS] == "-1").any(axis=1)].reset_index(drop=True)
    rede["ADO"] = _num(rede["ADO"])
    tabela_rotas = como_planilha(rotas)
    metas = preparar_metas(metas)

    meses = []
    for periodo in sorted(rede["period_start"].unique()):
        c = rede[rede["period_start"] == periodo].copy()
        r = tabela_rotas[tabela_rotas["period_start"].str[:10] == periodo]
        tt = _num(r.drop_duplicates("Route").set_index("Route")["TTFinal"])
        meses.append(_bwt_do_mes(c, metas, periodo, tt, p))
    saida = pd.concat(meses, ignore_index=True)

    horas = saida[COLUNAS_BWT].apply(_num).fillna(0.0)
    saida["bwt_total_hours"] = horas[COLUNAS_OPERACIONAL].sum(axis=1)
    saida["bwt_total_hours_XD"] = horas[COLUNAS_TOTAL_XD].sum(axis=1)
    saida["bounces"] = (saida[["FMH", "SOC1", "SOC2", "LMH", "XPT"]].fillna("") != "").sum(axis=1)
    spm = _spm(subregiao, spx_info, p)
    saida["origin_spm"] = saida["ORIGIN"].map(spm).fillna("Not SPM")
    saida["dest_spm"] = saida["DESTINATION"].map(spm).fillna("Not SPM")
    saida["estado"], saida["regional"] = estado_e_regional(saida, tabela_estados(lista_estacoes))
    saida["period_start_aux"] = pd.to_datetime(saida["period_start"]).dt.strftime("%Y-%m-%d")
    antes = len(saida)
    saida = saida[~saida["ORIGIN"].str[:7].isin(p["origens_cb"])].reset_index(drop=True)
    print(f"BWT: {len(saida)} caminhos ({antes - len(saida)} de origem CB excluídos)")

    saida = _flags(saida, p)
    return {"bwt_caminhos": saida, "bwt_resumo": resumo(saida), "bwt_1o_soc": resumo_1o_soc(saida)}
