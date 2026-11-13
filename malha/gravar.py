"""
Grava o resultado na planilha de saída (mesmo layout do processo atual), no modo SUBSTITUIR MÊS:
os meses calculados agora tomam o lugar dos mesmos meses que já estavam lá; os outros meses ficam.
Assim rodar duas vezes não duplica linhas (no processo atual, rodar 2x duplica).

Desligado por padrão: só grava se [saida].planilha estiver preenchida em config/fontes.toml.
Usa a mesma conexão do processo atual (connection_with_path.GmailEntry + credential/jards.json).
"""
from pathlib import Path

import pandas as pd

from .calculo.bwt import COLUNAS_1O_SOC, COLUNAS_RESUMO, COLUNAS_SAIDA
from .configuracao import fontes

RAIZ = Path(__file__).resolve().parents[1]
CREDENCIAL = RAIZ.parent / "credential" / "jards.json"
LOTE = 50_000

# aba: (linha do cabeçalho, colunas na ordem da planilha, de qual resultado vem)
ABAS = {
    "Network BWT output": (10, COLUNAS_SAIDA, "bwt_caminhos"),
    "raw_bwt": (2, COLUNAS_RESUMO, "bwt_resumo"),
    # atenção: na planilha o cabeçalho desta aba está em outra ordem, mas os dados sempre foram gravados assim
    "raw_data_1st_SOC": (2, COLUNAS_1O_SOC, "bwt_1o_soc"),
}


def _letra(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def plano_de_gravacao(resultados, existentes, meses_network):
    """
    Monta, para cada aba, as linhas finais (meses antigos que ficam + meses novos).
    existentes = {aba: DataFrame com o que está hoje na planilha, colunas na ordem da aba}.
    Separado da gravação para poder testar sem internet.
    """
    plano = {}
    for aba, (_, colunas, origem) in ABAS.items():
        novo = resultados[origem][colunas].copy()
        if aba == "Network BWT output":
            novo = novo[novo["period_start"].isin(meses_network)]
        meses_novos = set(novo["period_start"].astype(str).str[:10])
        antigo = existentes.get(aba, pd.DataFrame(columns=colunas))
        fica = antigo[~antigo.iloc[:, 0].astype(str).str[:10].isin(meses_novos)] if len(antigo) else antigo
        fica = fica.set_axis(colunas[:fica.shape[1]], axis=1) if len(fica) else fica
        plano[aba] = {"manter": len(fica), "novas": len(novo), "meses_substituidos": sorted(meses_novos),
                      "linhas": pd.concat([fica, novo.fillna("")], ignore_index=True)}
    return plano


def gravar(resultados, confirmar=False):
    """Lê o que está na planilha, troca os meses e regrava. Sem confirmar=True só mostra o plano."""
    cfg = fontes().get("saida", {})
    planilha = cfg.get("planilha", "")
    if not planilha:
        print("Gravação desligada ([saida].planilha vazio em config/fontes.toml).")
        return None
    if not CREDENCIAL.exists():
        raise FileNotFoundError(f"Sem a chave de acesso do Google: {CREDENCIAL}")

    import sys
    sys.path.insert(0, str(RAIZ))
    from connection_with_path import GmailEntry
    conn = GmailEntry(None, None, None, str(CREDENCIAL))

    existentes = {}
    for aba, (linha_cab, colunas, _) in ABAS.items():
        # lê a partir do cabeçalho (o get_sheets usa a 1ª linha lida como cabeçalho); colunas valem pela posição
        existentes[aba] = conn.get_sheets(scopes=planilha, sh_name=f"'{aba}'!A{linha_cab}:{_letra(len(colunas))}")
    plano = plano_de_gravacao(resultados, existentes, cfg.get("meses_network_output", []))
    for aba, p in plano.items():
        print(f"  {aba}: mantém {p['manter']} linhas, troca os meses {p['meses_substituidos']} ({p['novas']} linhas)")
    if not confirmar:
        print("Nada gravado (simulação). Para gravar: gravar(resultados, confirmar=True).")
        return plano

    for aba, p in plano.items():
        linha_cab, colunas, _ = ABAS[aba]
        conn.clean_specific_range(sheet_id=planilha, sheet_name=aba,
                                  range_to_clear=f"A{linha_cab + 1}:{_letra(len(colunas))}")
        linhas = p["linhas"]
        for i in range(0, len(linhas), LOTE):
            conn.print_in_sheets(scopes=planilha, sh_name=f"'{aba}'!A{linha_cab + 1 + i}",
                                 df=linhas.iloc[i:i + LOTE], print_columns=False)
        print(f"  {aba}: gravado ({len(linhas)} linhas)")
    return plano
