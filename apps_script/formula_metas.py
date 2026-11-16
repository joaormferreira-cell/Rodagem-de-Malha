"""
Gera a fórmula da aba METAS da planilha Inputs Rodagem.
A fórmula lê as abas [T] (espelho das planilhas originais) e monta a tabela única:
    etapa | codigo_by_step | estacao | mes | horas | aba_origem
Uso: python apps_script/formula_metas.py  → imprime a fórmula (colar em METAS!A2).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from malha.configuracao import fontes  # noqa: E402
from malha.padronizar import METAS  # noqa: E402

NUM = r"^-?\d+(\.\d+)?$"
MES = r"^\d{4}-\d{2}-01$"


def _bloco(chave):
    etapa, codigo, formato, aba_curta = METAS[chave]
    aba = fontes()["planilhas"][chave]["aba"].replace("'", "''")
    r = f"'{aba}'!"
    rotulo = f'"{etapa}"&"|"&"{codigo}"&"|"'
    if formato == "fmh":   # já é uma linha por FMH × mês: A = mês, B = FMH, E = horas
        k = f'{r}B4:B&"|"&{r}A4:A&"|"&{r}E4:E'
        filtro = f'({r}B4:B<>"")*REGEXMATCH({r}E4:E&"","{NUM}")'
        corpo = f'FILTER({rotulo}&{k}&"|{aba_curta}",{filtro})'
    elif formato == "valor_unico":   # 1ª linha de dados, cabeçalho a partir de D3
        k = f'TOCOL(IF(REGEXMATCH({r}D3:AA3&"","{MES}")*REGEXMATCH({r}D4:AA4&"","{NUM}"),' \
            f'"TODAS|"&{r}D3:AA3&"|"&{r}D4:AA4,NA()),2)'
        corpo = f'{rotulo}&{k}&"|{aba_curta}"'
    else:   # uma coluna por mês, cabeçalho na linha 3, estação na coluna A
        k = f'TOCOL(IF(REGEXMATCH({r}A3:AA3&"","{MES}")*({r}A4:A<>"")*REGEXMATCH({r}A4:AA&"","{NUM}"),' \
            f'{r}A4:A&"|"&{r}A3:AA3&"|"&{r}A4:AA,NA()),2)'
        corpo = f'{rotulo}&{k}&"|{aba_curta}"'
    return corpo


def formula():
    blocos = ";".join(_bloco(c) for c in METAS)
    return f"=ARRAYFORMULA(IFERROR(SPLIT({{{blocos}}},\"|\",FALSE,FALSE)))"


if __name__ == "__main__":
    print(formula())
