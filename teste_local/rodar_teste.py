"""
Teste local das 4 etapas do pipeline BWT, sem Google Sheets, sem API, sem Hive e sem internet.

Roda o código dos próprios scripts originais (não é cópia da lógica). Leituras vêm de CSV,
e tudo o que seria gravado vira arquivo Excel em saida/.

Uso:
    python rodar_teste.py                          (pergunta a etapa; usa dados de exemplo)
    python rodar_teste.py --etapa todas --dados exemplo
    python rodar_teste.py --etapa 2 --dados reais
"""
import argparse
import sys
import traceback

import pandas as pd

from simulador import PASTA_TESTE, FaltaArquivo, Simulador

ID_AUTOMATIONS = "1HdplQWZuaSrEYQLNWQYA0gc5rCqXaLCt-aaLJ2xD3FE"
ID_METAS = "1mSxSQkhZdQWIkQmDpBRmYCAN7K-Kc1YdvEV7Z6feNY0"
ABA_TT_ROTAS = "[T] 4.1 TT and SOC Packed to Transporting to SOC"

ETAPAS = {
    "1": dict(
        arquivo="network_input_to_bwt_generation.py",
        pasta="etapa_1_malha",
        titulo="ETAPA 1 - Monta a malha (caminhos + distâncias)",
        ajustes=[(r"ingestion_token =[ \t]*\n", "ingestion_token = None\n",
                  "linha 864 (token vazio, que impede o arquivo de rodar) preenchida com None")],
    ),
    "2": dict(
        arquivo="outobund_by_soc_tt_by_routes.py",
        pasta="etapa_2_tempo_por_rota",
        titulo="ETAPA 2 - Tempo e veículos de cada rota",
        ajustes=[],
    ),
    "3": dict(
        arquivo="outobund_by_soc_tt_by_routes_manual_express.py",
        pasta="etapa_3_ajuste_expressas",
        titulo="ETAPA 3 - Ajuste manual de rotas expressas (opcional)",
        ajustes=[],
    ),
    "4": dict(
        arquivo="bwt_calculator.py",
        pasta="etapa_4_bwt",
        titulo="ETAPA 4 - Prazo total de entrega (BWT) por caminho",
        ajustes=[],
    ),
}


def mostrar(df, colunas, titulo):
    colunas = [c for c in colunas if c in df.columns]
    tabela = df[colunas].copy()
    for c in colunas:
        numeros = pd.to_numeric(tabela[c], errors="coerce")
        if numeros.notna().all():
            tabela[c] = numeros.round(1)
    print(f"\n----- {titulo} -----")
    print(tabela.to_string(index=False))


def resumo(etapa, ctx):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 80)
    if etapa == "1" and "network_output" in ctx:
        mostrar(ctx["network_output"],
                ["E2E Path", "ADO", "FMH-SOC", "SOC1-SOC2", "SOC-HUB", "HUB-XPT", "ERRO"],
                "Caminhos com as distâncias de cada trecho (km)")
    elif etapa == "2" and "routes_output" in ctx:
        mostrar(ctx["routes_output"],
                ["Route", "route_type", "ADO", "Distance", "Total Vehicles", "Final Pck-LHTr",
                 "LHExpress Ident.", "TT with Express", "TT Queue and Unloading", "TTFinal"],
                "Uma linha por rota (tempos em horas)")
    elif etapa == "4" and "network_output" in ctx:
        mostrar(ctx["network_output"],
                ["E2E Path", "ADO", "bwt_total_hours", "bounces", "estado", "regional"],
                "Prazo total (BWT, em horas) de cada caminho")


def rodar_etapa(sim, etapa):
    cfg = ETAPAS[etapa]
    print("\n" + "=" * 78)
    print(f"{cfg['titulo']}   [{cfg['arquivo']}]")
    print("=" * 78)
    ctx = sim.rodar_script(cfg["arquivo"], cfg["pasta"], cfg["ajustes"])
    resumo(etapa, ctx)
    arquivos = sim.salvar_gravacoes()
    print("\nO que o script real gravaria (salvo aqui no seu computador, em Excel):")
    for caminho, destino_real in arquivos:
        print(f"  - {caminho.relative_to(PASTA_TESTE)}\n      (no real: {destino_real})")
    if not arquivos:
        print("  (nada)")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--etapa", choices=["1", "2", "3", "4", "todas"])
    parser.add_argument("--dados", choices=["exemplo", "reais"], default="exemplo")
    args = parser.parse_args()

    etapa = args.etapa
    if etapa is None:
        print("Qual etapa você quer testar?")
        print("  1 = Monta a malha            2 = Tempo de cada rota")
        print("  3 = Ajuste de expressas      4 = Prazo total (BWT)")
        print("  T = Todas, em sequência (uma alimenta a outra)")
        resposta = input("Digite 1, 2, 3, 4 ou T e aperte Enter: ").strip().lower()
        etapa = "todas" if resposta in ("t", "todas", "") else resposta
        if etapa not in ETAPAS and etapa != "todas":
            sys.exit("Opção inválida.")

    pasta_dados = PASTA_TESTE / f"dados_{args.dados}"
    pasta_saida = PASTA_TESTE / "saida" / args.dados
    sim = Simulador(pasta_dados, pasta_saida)
    print(f"Dados de entrada: {pasta_dados}")
    print("Internet bloqueada durante o teste. Nada é gravado em planilha nem no Hive.")

    try:
        if etapa == "todas":
            for e in ["1", "2", "3"]:
                rodar_etapa(sim, e)
            # a etapa 4 lê o [T] 4.1 de outra planilha (metas). Não está claro como o resultado
            # chega lá (ponto em aberto no CLAUDE.md); aqui supomos que é copiado.
            print(f"\n[TESTE LOCAL] SUPOSIÇÃO: a aba '{ABA_TT_ROTAS}' gravada nas etapas 2/3 (planilha "
                  f"1HdplQ…) é copiada para a planilha de metas (1mSxSQ…), de onde a etapa 4 lê.")
            sim.planilhas[(ID_METAS, ABA_TT_ROTAS)] = [list(l) for l in sim.planilhas[(ID_AUTOMATIONS, ABA_TT_ROTAS)]]
            rodar_etapa(sim, "4")
        else:
            rodar_etapa(sim, etapa)
    except FaltaArquivo as erro:
        print(erro)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        print("\nO teste parou com erro (veja acima). Nenhuma planilha real foi tocada.")
        sys.exit(1)

    print("\nTeste concluído. Nenhuma planilha real nem o Hive foram tocados.")


if __name__ == "__main__":
    main()
