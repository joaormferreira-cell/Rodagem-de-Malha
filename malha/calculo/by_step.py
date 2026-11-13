"""
Meta no formato da By Step: mês × canal × rota macro × KPI → bwt_n (horas × pedidos) e bwt_d (pedidos).
Mesmo formato da base do realizado (dev_brbi_opslgc.joao_bwt_by_step_mece), para comparar meta × realizado.

Como cada tempo da meta vira um KPI (onde começa e termina cada KPI vem do cálculo diário da By Step):
  - viagem que chega num SOC termina no "received" (inclui fila), igual ao TTFinal da meta;
  - viagem que chega no HUB/XPT termina no "arrive"; o HUB chegou→recebido é o M41 (= metas 4.9 + 5.0);
  - SOC3 e SOC4 da meta caem no M30/M31 (a By Step junta "SOC3 em diante");
  - estação aeroporto no lugar de um SOC vira M36 (recebido→saída do aeroporto).
Média de um KPI = bwt_n ÷ bwt_d, contando só quem passou pela etapa (tempo > 0), como no realizado.
"""
import unicodedata

import numpy as np
import pandas as pd

SOCS = ["SOC1", "SOC2", "SOC3", "SOC4"]
CANAIS = {"spx_flag": "SPX D2D", "fbs_flag": "SPX Fulfillment"}

KPI = {
    "M01": "M01 APT (Paid to Pickup or Dropoff)", "M07": "M07 FM: Dropoff to Pickup",
    "M09": "M09 FM: Pickup to SOC", "M10": "M10 FM: Pickup to FMH", "M11": "M11 FM: Pickup to LMH",
    "M05+M06": "M05+M06 FBS: Paid to Departure",
    "M13": "M13 LH FBS-SOC", "M15": "M15 LH FBS-LMH", "M17": "M17 LH FBS-Airport",
    "M18": "M18 FMH: Received to Packed", "M19": "M19 FMH: Packed to Departure",
    "M20": "M20 LH FMH-SOC", "M21": "M21 LH FMH-LMH", "M99a": "M99 LH FMH-Airport",
    "M24": "M24 SOC1: Received to Packed", "M25": "M25 SOC1: Packed to Departure",
    "M26": "M26 LH1 (SOC1-SOC2)",
    "M27": "M27 SOC2: Received to Packed", "M28": "M28 SOC2: Packed to Departure",
    "M29": "M29 LH2 (SOC2+-SOC)",
    "M30": "M30 SOC3: Received to Packed", "M31": "M31 SOC3: Packed to Departure",
    "M32": "M32 LH SOC-LMH", "M33": "M33 LH SOC-XPT", "M35": "M35 LH SOC-Airport",
    "M36": "M36 Airport: Received to Departure", "M37": "M37 Airport: Connection (Airport-Airport)",
    "M38": "M38 LH Airport-SOC", "M39": "M39 LH Airport-LMH", "M40": "M40 LH Airport-XPT",
    "M41": "M41 LMH: LH Transported to Received", "M42": "M42 LMH: Received to Departure",
    "M43": "M43 LH LMH-XPT", "M48": "M48 XPT: LH Arrived to Received", "M49": "M49 XPT: Received to Departure",
    "M62": "M62 LMH Delivering to 1st", "M63": "M63 XPT Delivering to 1st",
}
TOTAL = "FLOW BWT TOT"

# ---------- rota macro (mesma regra da query da By Step, aplicada às cidades das estações) ----------
_SPM = {"aruja", "barueri", "caieiras", "cajamar", "carapicuiba", "cotia", "diadema", "embu das artes",
        "ferraz de vasconcelos", "poa", "francisco morato", "franco da rocha", "guarulhos", "itapevi",
        "itaquaquecetuba", "jandira", "mairipora", "maua", "mogi das cruzes", "osasco", "santana de parnaiba",
        "santo andre", "sao bernardo do campo", "sao caetano do sul", "sao paulo", "suzano central", "suzano",
        "taboao da serra"}
_GRUPOS = {
    ("sao paulo", "SP Metro"): _SPM,
    ("sao paulo", "SP Interior"): {"campinas", "ribeirao preto", "limeira", "bauru", "sumare", "sococaba", "sorocaba",
                                   "braganca paulista", "marilia", "presidente prudente", "varzea paulista",
                                   "sao jose do rio preto", "aracatuba", "piracicaba", "araraquara", "sao carlos",
                                   "franca", "jau", "mogi mirim", "itapeva", "leme", "votuporanga", "botucatu",
                                   "jundiai", "tatui", "itapetininga", "assis", "barretos"},
    ("rio de janeiro", "RJ Metro"): {"bangu", "barra", "campo grande", "duque de caxias", "ilha", "niteroi",
                                     "rio de janeiro", "santa cruz"},
    ("minas gerais", "MG Metro"): {"barreiro", "belo horizonte", "betim", "brumadinho", "caete", "centro sul",
                                   "contagem", "ibirite", "igarape", "juatuba", "lagoa santa", "mateus leme",
                                   "nova lima", "pampulha", "pedro leopoldo", "ribeirao das neves", "sabara",
                                   "santa luzia", "sarzedo", "venda nova", "vespasiano"},
}
_CAPITAIS = {("sao paulo", "sao paulo"): "SP Capital", ("rio de janeiro", "rio de janeiro"): "RJ Capital",
             ("minas gerais", "belo horizonte"): "MG Capital"}
_UF = {"acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
       "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
       "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
       "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
       "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP",
       "sergipe": "SE", "tocantins": "TO"}
_REGIAO = {**dict.fromkeys(["espirito santo", "minas gerais", "rio de janeiro", "sao paulo"], "Sudeste"),
           **dict.fromkeys(["alagoas", "bahia", "ceara", "maranhao", "paraiba", "pernambuco", "piaui",
                            "rio grande do norte", "sergipe"], "Nordeste"),
           **dict.fromkeys(["acre", "amapa", "amazonas", "para", "rondonia", "roraima", "tocantins"], "Norte"),
           **dict.fromkeys(["distrito federal", "goias", "mato grosso", "mato grosso do sul"], "Centro-oeste"),
           **dict.fromkeys(["parana", "rio grande do sul", "santa catarina"], "Sul")}
_OD = {"SP>SP", "SP>MG", "SP>RJ", "MG>MG", "MG>SP", "RJ>MG", "RJ>RJ", "RJ>SP", "SP>AM", "SP>BA", "SP>CE",
       "SP>PR", "SP>RS"}
_UF_OD = {"AM", "BA", "CE", "MG", "PR", "RJ", "RS", "SP"}
_METRO_CRUZADO = {"RJ Metro>SP Metro", "RJ Metro>MG Metro", "MG Metro>SP Metro"}
_CAPITAL_PAR = {"SP Capital>SP Capital", "RJ Capital>RJ Capital", "MG Capital>MG Capital",
                "MG Capital>SP Capital", "RJ Capital>MG Capital", "RJ Capital>SP Capital"}


def _norm(texto):
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return ""
    texto = unicodedata.normalize("NFKD", str(texto).strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _grupo(estado, cidade):
    return next((g for (e, g), cidades in _GRUPOS.items() if e == estado and cidade in cidades), "")


def rotas_macro(estado_o, cidade_o, estado_d, cidade_d):
    """Lista de rotas macro de um par origem → destino (mesma regra da By Step)."""
    rotas = ["BR - BR"]
    if estado_o == estado_d == "sao paulo" and cidade_o in _SPM and cidade_d in _SPM:
        rotas.append("SPM - SPM")
    uf_o, uf_d = _UF.get(estado_o, ""), _UF.get(estado_d, "")
    if uf_o in _UF_OD and uf_d in _UF_OD and f"{uf_o}>{uf_d}" in _OD:
        rotas.append(f"{uf_o} > {uf_d}")
    g_o, g_d = _grupo(estado_o, cidade_o), _grupo(estado_d, cidade_d)
    cap_o, cap_d = _CAPITAIS.get((estado_o, cidade_o), ""), _CAPITAIS.get((estado_d, cidade_d), "")
    if estado_d in _REGIAO:
        rotas.append(f"BR>{_REGIAO[estado_d]}")
    if uf_d:
        rotas.append(f"BR>{uf_d} State")
    if g_d:
        rotas.append(f"BR>{g_d}")
    if not g_d or g_d == "SP Interior":
        rotas.append("BR>Not Metro")
    if g_o and g_o == g_d and g_d.endswith("Metro"):
        rotas.append(f"{g_o}>{g_d}")
    if f"{g_o}>{g_d}" in _METRO_CRUZADO:
        rotas.append(f"{g_o}>{g_d}")
    if cap_d:
        rotas.append(f"BR>{cap_d}")
    if f"{cap_o}>{cap_d}" in _CAPITAL_PAR:
        rotas.append(f"{cap_o}>{cap_d}")
    return rotas


def _geo_estacoes(spx_info):
    """Código da estação → (estado, cidade) normalizados (da aba SPX_info)."""
    df = spx_info.drop_duplicates("station_code")
    vazio = pd.Series("", index=df.index)
    estado, cidade = df.get("state_name", vazio), df.get("city_name", vazio)
    return {c: (_norm(e), _norm(m)) for c, e, m in zip(df["station_code"], estado, cidade)}


# ---------- tempo da meta → KPI ----------
def _tipo(s):
    return np.where(s.str.startswith("Airport"), "Airport", np.where(s == "", "", "SOC"))


def caminho_etapa(caminhos):
    """
    Caminho × KPI: uma linha por passagem (ex.: cada viagem entre SOCs é uma passagem).
    Colunas: period_start, E2E Path, canal, kpi, passagem, horas, ADO.
    """
    c = caminhos.copy()
    c["canal"] = np.where(c["fbs_flag"] == 1, CANAIS["fbs_flag"], CANAIS["spx_flag"])
    tipos = {s: _tipo(c[s].fillna("")) for s in SOCS}
    # posição do SOC contando só SOCs (aeroporto não conta), limitada a 3 como na By Step
    ordem, conta = {}, np.zeros(len(c), dtype=int)
    for s in SOCS:
        conta = conta + (tipos[s] == "SOC")
        ordem[s] = np.minimum(conta, 3)
    tem_fmh = c["FMH"].fillna("") != ""
    ultimo = np.full(len(c), "", dtype=object)
    for s in SOCS:
        ultimo = np.where(tipos[s] != "", tipos[s], ultimo)

    pecas = []

    def add(componentes, kpi, passagem):
        horas = sum(pd.to_numeric(c[x], errors="coerce").fillna(0.0).to_numpy() for x in componentes)
        kpi = np.broadcast_to(np.asarray(kpi, dtype=object), (len(c),))
        pecas.append(pd.DataFrame({"period_start": c["period_start"].to_numpy(), "E2E Path": c["E2E Path"].to_numpy(),
                                   "canal": c["canal"].to_numpy(), "kpi": kpi, "passagem": passagem,
                                   "horas": horas, "ADO": c["ADO"].to_numpy()}))

    add(["bwt_apt_paid_to_dropoff"], KPI["M01"], "seller")
    add(["bwt_dropoff_to_pickup"], KPI["M07"], "fm")
    add(["bwt_pickup_to_received"], np.where(tem_fmh, KPI["M10"],
                                             np.where(c["SOC1"].fillna("") != "", KPI["M09"], KPI["M11"])), "coleta")
    add(["bwt_fbs_processing"], KPI["M05+M06"], "fbs")
    add(["bwt_fmh_received_to_packed"], KPI["M18"], "fmh")
    add(["bwt_fmh_packed_to_transporting"], KPI["M19"], "fmh_saida")
    t1 = tipos["SOC1"]
    add(["bwt_lh_fmh_to_soc"], np.where(t1 == "Airport", KPI["M99a"], KPI["M20"]), "lh_origem")
    add(["bwt_lh_fbs_to_soc"], np.where(t1 == "Airport", KPI["M17"], KPI["M13"]), "lh_origem")
    add(["bwt_lh_fmh_to_lmh_arrived"], KPI["M21"], "lh_origem")
    add(["bwt_lh_fbs_to_lmh_arrived"], KPI["M15"], "lh_origem")

    for i, s in enumerate(SOCS, start=1):
        n = s.lower()
        aero = tipos[s] == "Airport"
        rec = np.select([aero, ordem[s] == 1, ordem[s] == 2], [KPI["M36"], KPI["M24"], KPI["M27"]], KPI["M30"])
        emb = np.select([aero, ordem[s] == 1, ordem[s] == 2], [KPI["M36"], KPI["M25"], KPI["M28"]], KPI["M31"])
        add([f"bwt_{n}_received_to_packed"], rec, f"{s}_recebido")
        add([f"bwt_{n}_packed_to_transporting"], emb, np.where(aero, f"{s}_recebido", f"{s}_saida"))
        if i < 4:
            prox = SOCS[i]
            a, b = tipos[s], tipos[prox]
            lh = np.select([(a == "SOC") & (b == "SOC") & (ordem[s] == 1), (a == "SOC") & (b == "SOC"),
                            (a == "SOC") & (b == "Airport"), (a == "Airport") & (b == "SOC")],
                           [KPI["M26"], KPI["M29"], KPI["M35"], KPI["M38"]], KPI["M37"])
            add([f"bwt_lh_{n}_to_{prox.lower()}"], lh, f"lh_{s}")
    add(["bwt_lh_soc_to_lmh"], np.where(ultimo == "Airport", KPI["M39"], KPI["M32"]), "lh_hub")
    add(["bwt_lh_soc_to_xpt_arrived"], np.where(ultimo == "Airport", KPI["M40"], KPI["M33"]), "lh_xpt")
    add(["bwt_lh_arrived_to_transported", "bwt_lh_transported_to_lmh_received"], KPI["M41"], "hub_chegada")
    add(["bwt_lmh_received_to_LH_xpt_or_delivering"], KPI["M42"], "hub_saida")
    add(["bwt_lmh_transporting_to_xpt_arrived"], KPI["M43"], "lh_hub_xpt")
    add(["bwt_lh_xpt_arrived_to_xpt_received"], KPI["M48"], "xpt_chegada")
    add(["bwt_lh_lmh_transported_to_xpt_to_delivering"], KPI["M49"], "xpt_saida")
    add(["bwt_hub_delivering_to_1st_attempt"], KPI["M62"], "entrega")
    add(["bwt_xpt_delivering_to_1st_attempt"], KPI["M63"], "entrega")

    longa = pd.concat(pecas, ignore_index=True)
    longa = longa.groupby(["period_start", "E2E Path", "canal", "kpi", "passagem"], as_index=False, sort=False) \
                 .agg(horas=("horas", "sum"), ADO=("ADO", "first"))
    return longa[longa["horas"] > 0].reset_index(drop=True)


def meta_by_step(caminhos, spx_info):
    """Mês × canal × rota macro × KPI, no formato da base da By Step (bwt_n = horas × pedidos, bwt_d = pedidos)."""
    geo = _geo_estacoes(spx_info)
    c = caminhos.copy()
    c["canal"] = np.where(c["fbs_flag"] == 1, CANAIS["fbs_flag"], CANAIS["spx_flag"])
    o = c["ORIGIN"].fillna("").str.replace("(XD)", "", regex=False).map(lambda x: geo.get(x, ("", "")))
    d = c["DESTINATION"].fillna("").str.replace("(XD)", "", regex=False).map(lambda x: geo.get(x, ("", "")))
    pares = pd.Series(list(zip(o, d)), index=c.index)
    c["rotas"] = pares.map({p: tuple(rotas_macro(p[0][0], p[0][1], p[1][0], p[1][1])) for p in set(pares)})
    sem_geo = (o.map(lambda x: x == ("", "")) | d.map(lambda x: x == ("", ""))).sum()
    if sem_geo:
        print(f"By Step: {sem_geo} caminho(s) com estação de origem/destino fora da SPX_info (só entram em BR - BR)")

    longa = caminho_etapa(c)
    longa["bwt_n"] = longa["horas"] * longa["ADO"]
    longa = longa.merge(c[["period_start", "E2E Path", "rotas"]], on=["period_start", "E2E Path"], how="left")
    por_kpi = longa.groupby(["period_start", "canal", "rotas", "kpi"], as_index=False) \
                   .agg(bwt_n=("bwt_n", "sum"), bwt_d=("ADO", "sum"))
    total = c.assign(bwt_n=c["bwt_total_hours"] * c["ADO"], kpi=TOTAL) \
             .groupby(["period_start", "canal", "rotas", "kpi"], as_index=False).agg(bwt_n=("bwt_n", "sum"),
                                                                                     bwt_d=("ADO", "sum"))
    tudo = pd.concat([por_kpi, total], ignore_index=True).explode("rotas").rename(columns={"rotas": "main_route"})
    saida = tudo.groupby(["period_start", "canal", "main_route", "kpi"], as_index=False)[["bwt_n", "bwt_d"]].sum()
    saida = saida.rename(columns={"period_start": "attempt_month", "canal": "spx_channel"})
    saida["media_h"] = saida["bwt_n"] / saida["bwt_d"]
    return saida.sort_values(["attempt_month", "spx_channel", "main_route", "kpi"]).reset_index(drop=True)
