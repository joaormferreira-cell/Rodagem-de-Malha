"""
Estado (UF) e regional de cada caminho, a partir do XPT ou do HUB final.
Regra do processo atual:
  1. XPT preenchido e com estado na lista de estações → usa esse estado;
  2. senão, HUB (LMH) preenchido → estado da lista; se não achar, tira a UF do código (HUB-LSP-01 → SP);
  3. senão, fica vazio.
"""
import re
import unicodedata

import pandas as pd

UF_POR_ESTADO = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM", "bahia": "BA", "ceara": "CE",
    "distrito federal": "DF", "espirito santo": "ES", "goias": "GO", "maranhao": "MA", "mato grosso": "MT",
    "mato grosso do sul": "MS", "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ", "rio grande do norte": "RN",
    "rio grande do sul": "RS", "rondonia": "RO", "roraima": "RR", "santa catarina": "SC",
    "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO",
}
REGIONAL_POR_UF = {
    **dict.fromkeys(["AC", "AP", "AM", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
}
_UF_NO_CODIGO_DO_HUB = re.compile(r"^HUB-L([A-Z]{2})", re.IGNORECASE)


def _sem_acento(texto):
    texto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def _limpo(codigo):
    if codigo is None or (isinstance(codigo, float) and pd.isna(codigo)):
        return ""
    return str(codigo).strip().replace("(XD)", "")


def tabela_estados(estacoes):
    """Lista de estações (API station_names_malha) → {código: nome do estado}; ativa (status maior) primeiro."""
    df = estacoes.copy()
    df["station_code"] = df["station_code"].astype(str).str.strip()
    df["state_name"] = df["state_name"].astype(str).str.strip()
    if "status" in df.columns:
        df["status"] = pd.to_numeric(df["status"], errors="coerce").fillna(0)
        df = df.sort_values(["station_code", "status"], ascending=[True, False])
    return df.drop_duplicates("station_code").set_index("station_code")["state_name"].to_dict()


def _uf_da_lista(codigo, estados):
    nome = estados.get(_limpo(codigo), "")
    if not nome or nome.lower() == "nan":
        return ""
    return UF_POR_ESTADO.get(_sem_acento(nome), "")


def _uf(xpt, lmh, estados):
    if _limpo(xpt):
        uf = _uf_da_lista(xpt, estados)
        if uf:
            return uf
    if _limpo(lmh):
        uf = _uf_da_lista(lmh, estados)
        if uf:
            return uf
        m = _UF_NO_CODIGO_DO_HUB.match(_limpo(lmh))
        return m.group(1).upper() if m and m.group(1).upper() in REGIONAL_POR_UF else ""
    return ""


def estado_e_regional(caminhos, estados):
    """Devolve (estado, regional) por linha. Calcula uma vez por par XPT/HUB."""
    pares = caminhos[["XPT", "LMH"]].astype(object).where(caminhos[["XPT", "LMH"]].notna(), None)
    chave = list(zip(pares["XPT"], pares["LMH"]))
    cache = {par: _uf(par[0], par[1], estados) for par in set(chave)}
    estado = pd.Series([cache[par] for par in chave], index=caminhos.index)
    sem = (estado == "").sum()
    if sem:
        print(f"Estado/regional não resolvido para {sem} linha(s).")
    return estado, estado.map(lambda uf: REGIONAL_POR_UF.get(uf, "") if uf else "")
