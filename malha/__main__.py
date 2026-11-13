"""
Comandos:
  python -m malha rodar     --dados teste_local/dados_exemplo   calcula e salva os resultados em saida/
  python -m malha comparar  --dados teste_local/dados_exemplo   confere se dá igual ao processo atual
"""
import argparse
import sys

from .comparar import comparar
from .pipeline import rodar


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m malha")
    parser.add_argument("comando", choices=["rodar", "comparar"])
    parser.add_argument("--dados", default="teste_local/dados_exemplo", help="pasta com os CSV de entrada")
    parser.add_argument("--saida", default="saida", help="pasta onde salvar os resultados")
    args = parser.parse_args()
    if args.comando == "rodar":
        try:
            rodar(args.dados, args.saida)
        except FileNotFoundError as erro:   # input faltando: mensagem simples, sem detalhe técnico
            sys.exit(f"\nFALTA UM INPUT\n{erro}")
    else:
        sys.exit(0 if comparar(args.dados) else 1)


if __name__ == "__main__":
    main()
