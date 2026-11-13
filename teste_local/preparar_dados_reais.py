"""
Monta a pasta de dados reais no mesmo formato de dados_exemplo, a partir de:
  dados_reais/Inputs Rodagem.xlsx          (planilha consolidada, baixada como Excel)
  dados_reais/0.0 Distances Available.csv  (aba de distâncias, baixada como CSV)
  dados_reais/demanda_bwt.csv              (export da tabela dev_brbi_opslgc.joao_malha_demanda_bwt)
  dados_reais/station_names.csv            (export da tabela dev_brbi_opslgc.joao_malha_station_names)
Saída: dados_reais/pronto/  → usar com  python -m malha rodar --dados dados_reais/pronto

Uso: python teste_local/preparar_dados_reais.py
"""
import csv
import shutil
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ORIGEM = RAIZ / "dados_reais"
DESTINO = ORIGEM / "pronto"
MODELO = RAIZ / "teste_local" / "dados_exemplo"   # define quais abas existem e em qual pasta ficam


def nome_no_excel(aba):
    """O Excel não aceita [ ] no nome da aba e corta em 31 caracteres."""
    return aba.replace("[", "").replace("]", "")[:31]


def salvar_grade(df, arquivo):
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with open(arquivo, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(df.fillna("").astype(str).values.tolist())


def main():
    excel = pd.read_excel(ORIGEM / "Inputs Rodagem.xlsx", sheet_name=None, header=None, dtype=str)
    faltando = []
    for modelo in sorted(MODELO.glob("*/*.csv")):
        pasta, aba = modelo.parent.name, modelo.stem
        if pasta == "api":
            continue
        destino = DESTINO / pasta / modelo.name
        if aba == "0.0 Distances Available":
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ORIGEM / "0.0 Distances Available.csv", destino)
            continue
        grade = excel.get(nome_no_excel(aba))
        if grade is None or grade.iloc[0, 0] == "#REF!":
            faltando.append(f"{pasta}/{aba}")
            continue
        salvar_grade(grade, destino)

    api = DESTINO / "api"
    api.mkdir(parents=True, exist_ok=True)
    demanda = pd.read_csv(ORIGEM / "demanda_bwt.csv", dtype=str, keep_default_na=False)
    if "period_end" not in demanda.columns:   # a tabela não traz; é o último dia do mês
        fim = pd.to_datetime(demanda["period_start"]) + pd.offsets.MonthEnd(0)
        demanda.insert(1, "period_end", fim.dt.strftime("%Y-%m-%d"))
    demanda.to_csv(api / "demanda_bwt.csv", index=False)
    shutil.copyfile(ORIGEM / "station_names.csv", api / "station_names.csv")

    print(f"Pronto: {DESTINO}")
    print(f"  demanda: {len(demanda)} linhas | meses: {sorted(demanda['period_start'].unique())}")
    if faltando:
        print("  FALTANDO (sem acesso ou aba vazia):")
        for f in faltando:
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
