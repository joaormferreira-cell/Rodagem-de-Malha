"""
Simulador local do Google Sheets, do Data Service e do Hive.

- Leituras de planilha vêm de CSV em  dados_<tipo>/<pasta da planilha>/<nome da aba>.csv
- Leituras da API (Data Service) vêm de CSV em  dados_<tipo>/api/<nome>.csv
- Gravações NÃO saem do computador: viram arquivos Excel na pasta saida/.
- Toda conexão de rede é bloqueada enquanto o teste roda.

As "planilhas simuladas" ficam em memória: o que uma etapa grava, a etapa seguinte lê.
"""
import csv
import io
import re
import socket
import sys
import types
from pathlib import Path

import pandas as pd

PASTA_TESTE = Path(__file__).resolve().parent
PASTA_REPO = PASTA_TESTE.parent
PASTA_ANTIGO = PASTA_REPO / "99. Old"   # software antigo (scripts originais)

# planilha (ID do Google) -> pasta com os CSV das abas
PASTAS_PLANILHAS = {
    "1-XOdOIY0Ik4cBmyb4YdpCKKmEXQJW1iLOS8-rFjhkwQ": "distancias_1-XOdO",
    "1j_-RWpY8l51uRoghLLfBbI10YCUM6DmbjHxJUzsaz2I": "estacoes_historico_1j_-RW",
    "1hZSIsOUFpf5oQ7hw6bckUvq3_tZiPCCSeBOLyIstyqI": "estacoes_base_1hZSIs",
    "1B2CFDdLbv8OERES43rI-9M4c_2rksLyRtjpIhWFHySI": "relatorio_latlon_1B2CFD",
    "1e0NtmrB8jtn-PICUejjg8iNGcWX0O9sAVSctkLh0T1s": "bwt_model_1e0Ntm",
    "1S54tFjLI2sT8loUSCnexEGp_Z9ryKD1p8MugmhT5P34": "network_input_1S54tF",
    "1VaLP441cLIrkW_Vwl6MDT_i_FLfVi2I9i-lVLePbGVQ": "outros_inputs_1VaLP4",
    "1HdplQWZuaSrEYQLNWQYA0gc5rCqXaLCt-aaLJ2xD3FE": "automations_1HdplQ",
    "197nob2_mCQy1fA-1ETkDH8hs6EW-YYLJx1F2egxW5uQ": "expressas_197nob",
    "1mwx37vJIDwk2eOMLZ_LTYqoTHq-3qui2zbOL9vkE6pE": "new_tt_1mwx37",
    "1mSxSQkhZdQWIkQmDpBRmYCAN7K-Kc1YdvEV7Z6feNY0": "metas_1mSxSQ",
    "1iReXhzuORpc7cTBGo5C1MrvUmILYu3x_ZzjnM3fDGfw": "bwt_output_1iReXh",
}

# planilhas onde os scripts só gravam (não precisam de CSV de entrada)
PLANILHAS_SO_SAIDA = {
    "1B2CFDdLbv8OERES43rI-9M4c_2rksLyRtjpIhWFHySI",
    "1e0NtmrB8jtn-PICUejjg8iNGcWX0O9sAVSctkLh0T1s",
    "1iReXhzuORpc7cTBGo5C1MrvUmILYu3x_ZzjnM3fDGfw",
}

# API do Data Service -> arquivo em dados_<tipo>/api/
ARQUIVOS_API = {
    "brbi_opslgc.demanda_bwt_": "demanda_bwt.csv",
    "brbi_opslgc.get_bwt_network_jards": "network_bwt.csv",
    "brbi_opslgc.station_names_malha": "station_names.csv",
}
# o que a etapa 1 sobe no Hive é o que a API get_bwt_network_jards devolve depois
API_ALIMENTADA_PELO_HIVE = "brbi_opslgc.get_bwt_network_jards"

_RANGE_RE = re.compile(r"^([A-Za-z]+)(\d+):([A-Za-z]+)(\d*)$")
_CELULA_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


class FaltaArquivo(FileNotFoundError):
    pass


def link_planilha(planilha_id):
    return f"https://docs.google.com/spreadsheets/d/{planilha_id}"


def pasta_da_planilha(planilha_id):
    return PASTAS_PLANILHAS.get(planilha_id, planilha_id)


def separar_aba(sh_name):
    aba, celulas = sh_name.rsplit("!", 1) if "!" in sh_name else (sh_name, "")
    aba = aba.strip()
    if aba.startswith("'") and aba.endswith("'"):
        aba = aba[1:-1].replace("''", "'")
    return aba, celulas.strip()


def col_para_numero(letras):
    n = 0
    for c in letras.upper():
        n = n * 26 + (ord(c) - ord("A") + 1)
    return n


def ler_grade(caminho):
    """CSV inteiro da aba como grade de textos (linha 1 do CSV = linha 1 da aba)."""
    dados = caminho.read_bytes()
    try:
        texto = dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = dados.decode("latin-1")
    inicio = "\n".join(texto.splitlines()[:10])
    sep = ";" if inicio.count(";") > inicio.count(",") else ","
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=sep)]


def celula(grade, linha, coluna):
    """linha e coluna começam em 1, como na planilha."""
    if linha - 1 < len(grade) and coluna - 1 < len(grade[linha - 1]):
        return grade[linha - 1][coluna - 1]
    return ""


def valor_como_no_sheets(v):
    """Como o Google Sheets mostra um valor gravado com valueInputOption=RAW."""
    if v is None:
        return ""
    if isinstance(v, bool) or type(v).__name__ == "bool_":
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        if v != v:  # NaN
            return ""
        return str(int(v)) if v.is_integer() else repr(v)
    return str(v)


class PlanilhaFalsa:
    """Imita service.spreadsheets() da API do Google só para o batchGet por coluna."""

    def __init__(self, grade):
        self.grade = grade
        self._ranges = []

    def values(self):
        return self

    def batchGet(self, spreadsheetId, ranges, majorDimension):
        self._ranges = ranges
        return self

    def execute(self):
        saida = []
        for rng in self._ranges:
            m = _RANGE_RE.match(rng.rsplit("!", 1)[1])
            col, r1, r2 = col_para_numero(m.group(1)), int(m.group(2)), int(m.group(4))
            valores = [celula(self.grade, r, col) for r in range(r1, r2 + 1)]
            while valores and valores[-1] == "":
                valores.pop()
            saida.append({"values": [[v] if v != "" else [] for v in valores]})
        return {"valueRanges": saida}


class Simulador:
    def __init__(self, pasta_dados, pasta_saida):
        self.pasta_dados = Path(pasta_dados)
        self.pasta_saida = Path(pasta_saida)
        self.planilhas = {}      # (planilha_id, aba) -> grade em memória
        self.api = {}            # api -> DataFrame em memória (alimentado pelo "Hive")
        self.gravadas = []       # (planilha_id, aba) gravadas na etapa atual
        self.hive = []           # uploads para o Hive na etapa atual
        self.etapa = ""

        sys.path.insert(0, str(PASTA_ANTIGO))
        import connection_with_path as cwp_real
        self.cwp_real = cwp_real

    # ---------- planilhas ----------
    def _arquivo_aba(self, planilha_id, aba):
        return self.pasta_dados / pasta_da_planilha(planilha_id) / f"{aba}.csv"

    def _grade(self, planilha_id, aba, obrigatoria=True):
        chave = (planilha_id, aba)
        if chave in self.planilhas:
            return self.planilhas[chave]
        arquivo = self._arquivo_aba(planilha_id, aba)
        if not arquivo.exists():
            if not obrigatoria:
                return []
            if planilha_id in PLANILHAS_SO_SAIDA:
                # a etapa 4 lê a própria aba de saída só para saber onde continuar gravando
                raise FaltaArquivo(f"[TESTE LOCAL] aba de saída '{aba}' sem CSV: considerada vazia (normal no teste)")
            raise FaltaArquivo(
                f"\n\nFALTA ARQUIVO: {arquivo}\n"
                f"  Planilha: {link_planilha(planilha_id)}\n"
                f"  Aba: '{aba}'\n"
                f"  Baixe essa aba como CSV e salve com esse nome nessa pasta.\n")
        return ler_grade(arquivo)

    def get_sheets(self, scopes, sh_name, **kwargs):
        aba, celulas = separar_aba(sh_name)
        origem = "memória (gravada por etapa anterior)" if (scopes, aba) in self.planilhas else "CSV"
        grade = self._grade(scopes, aba)
        print(f"[TESTE LOCAL] Lendo aba '{aba}' ({pasta_da_planilha(scopes)}) de {origem}")

        # mesma regra do connection_with_path.get_sheets para escolher o modo de leitura
        parsed = self.cwp_real._parse_sheet_rectangular_range(sh_name)
        usa_batch = (parsed is not None
                     and (parsed[3] - parsed[1] + 1) <= 80
                     and (parsed[4] - parsed[2] + 1) <= 50000)
        if usa_batch:
            titulo, i1, r1, i2, r2 = parsed
            return self.cwp_real.GmailEntry._batch_get_rectangular_to_dataframe(
                titulo, scopes, i1, r1, i2, r2, PlanilhaFalsa(grade))

        # modo ROWS: a API corta células vazias no fim de cada linha e linhas vazias no fim
        m = _RANGE_RE.match(celulas) if celulas else None
        if m:
            c1, r1, c2 = col_para_numero(m.group(1)), int(m.group(2)), col_para_numero(m.group(3))
            r2 = int(m.group(4)) if m.group(4) else len(grade)
        else:
            c1, r1, c2, r2 = 1, 1, max((len(l) for l in grade), default=0), len(grade)
        linhas = []
        for r in range(r1, r2 + 1):
            linha = [celula(grade, r, c) for c in range(c1, c2 + 1)]
            while linha and linha[-1] == "":
                linha.pop()
            linhas.append(linha)
        while linhas and not linhas[-1]:
            linhas.pop()
        return self.cwp_real.GmailEntry._sheet_values_to_dataframe(linhas)

    def _grade_para_escrita(self, planilha_id, aba):
        chave = (planilha_id, aba)
        if chave not in self.planilhas:
            self.planilhas[chave] = [list(l) for l in self._grade(planilha_id, aba, obrigatoria=False)]
        if chave not in self.gravadas:
            self.gravadas.append(chave)
        return self.planilhas[chave]

    def clean_specific_range(self, sheet_id, sheet_name, range_to_clear):
        aba, _ = separar_aba(sheet_name)
        print(f"[TESTE LOCAL] O script real APAGARIA {range_to_clear} da aba '{aba}' em {link_planilha(sheet_id)}")
        grade = self._grade_para_escrita(sheet_id, aba)
        m = _RANGE_RE.match(range_to_clear)
        c1, r1, c2 = col_para_numero(m.group(1)), int(m.group(2)), col_para_numero(m.group(3))
        r2 = int(m.group(4)) if m.group(4) else len(grade)
        for r in range(r1, min(r2, len(grade)) + 1):
            linha = grade[r - 1]
            for c in range(c1, min(c2, len(linha)) + 1):
                linha[c - 1] = ""

    def print_in_sheets(self, scopes, sh_name, df, print_columns=True):
        aba, celula_ini = separar_aba(sh_name)
        m = _CELULA_RE.match(celula_ini)
        c0, r0 = col_para_numero(m.group(1)), int(m.group(2))
        linhas = ([list(df.columns)] if print_columns else []) + df.values.tolist()
        print(f"[TESTE LOCAL] O script real GRAVARIA {len(df)} linha(s) na aba '{aba}' "
              f"a partir de {celula_ini} em {link_planilha(scopes)}")
        grade = self._grade_para_escrita(scopes, aba)
        for i, valores in enumerate(linhas):
            r = r0 + i
            while len(grade) < r:
                grade.append([])
            linha = grade[r - 1]
            while len(linha) < c0 - 1 + len(valores):
                linha.append("")
            for j, v in enumerate(valores):
                linha[c0 - 1 + j] = valor_como_no_sheets(v)

    # ---------- Data Service / Hive ----------
    def get_df_from_dataservice(self, api_abbr=None, version=None, app_key=None, app_secret=None, **kwargs):
        if api_abbr in self.api:
            print(f"[TESTE LOCAL] API '{api_abbr}': usando o que a etapa 1 subiu no Hive (memória)")
            return self.api[api_abbr].copy()
        arquivo = self.pasta_dados / "api" / ARQUIVOS_API.get(api_abbr, f"{api_abbr}.csv")
        if not arquivo.exists():
            raise FaltaArquivo(f"\n\nFALTA ARQUIVO da API '{api_abbr}': {arquivo}\n")
        print(f"[TESTE LOCAL] API '{api_abbr}': lendo {arquivo.name}")
        return pd.read_csv(arquivo, dtype=str, keep_default_na=False)

    def insert_df_into_hive(self, df, api_endpoint, ingestion_token):
        print(f"[TESTE LOCAL] O script real SUBIRIA {len(df)} linha(s) no Hive ({api_endpoint})")
        tabela = df.copy()
        self.hive.append(tabela)
        self.api[API_ALIMENTADA_PELO_HIVE] = tabela.apply(lambda col: col.map(valor_como_no_sheets))

    # ---------- execução de um script original ----------
    def rodar_script(self, nome_arquivo, etapa, ajustes_codigo=()):
        self.etapa = etapa
        self.gravadas = []
        self.hive = []
        sim = self

        class ConexaoFalsa:
            def __init__(self, *args, **kwargs):
                pass

            def get_sheets(self, scopes, sh_name, **kwargs):
                return sim.get_sheets(scopes, sh_name, **kwargs)

            def print_in_sheets(self, scopes, sh_name, df, print_columns=True):
                return sim.print_in_sheets(scopes, sh_name, df, print_columns)

            def clean_specific_range(self, sheet_id, sheet_name, range_to_clear):
                return sim.clean_specific_range(sheet_id, sheet_name, range_to_clear)

            def __getattr__(self, nome):
                raise RuntimeError(f"[TESTE LOCAL] '{nome}' não é simulado; o teste não conecta em nada.")

        def bloqueado(nome):
            def _f(*a, **k):
                raise RuntimeError(f"[TESTE LOCAL] '{nome}' bloqueado no teste.")
            return _f

        falso_cwp = types.ModuleType("connection_with_path")
        falso_cwp.GmailEntry = ConexaoFalsa
        falso_hive = types.ModuleType("hive_lib")
        falso_hive.get_df_from_dataservice = self.get_df_from_dataservice
        falso_hive.insert_df_into_hive = self.insert_df_into_hive
        falso_hive.get_df_demand = bloqueado("get_df_demand")
        falso_hive.get_df_demand_params = bloqueado("get_df_demand_params")
        sys.modules["connection_with_path"] = falso_cwp
        sys.modules["hive_lib"] = falso_hive

        caminho = PASTA_ANTIGO / nome_arquivo
        codigo = caminho.read_text(encoding="utf-8")
        for padrao, troca, motivo in ajustes_codigo:
            codigo, n = re.subn(padrao, troca, codigo)
            if n:
                print(f"[TESTE LOCAL] Ajuste só em memória (arquivo original intacto): {motivo}")

        contexto = {"__name__": "__main__", "__file__": str(caminho)}
        with _rede_bloqueada():
            exec(compile(codigo, str(caminho), "exec"), contexto)
        return contexto

    def salvar_gravacoes(self):
        """Salva em Excel como cada aba ficaria depois da etapa, e o que iria para o Hive."""
        pasta = self.pasta_saida / self.etapa
        arquivos = []
        for planilha_id, aba in self.gravadas:
            grade = self.planilhas[(planilha_id, aba)]
            largura = max((len(l) for l in grade), default=0)
            df = pd.DataFrame([l + [""] * (largura - len(l)) for l in grade])
            df = df.apply(lambda col: col.map(_numero_se_der))
            destino = pasta / pasta_da_planilha(planilha_id) / f"{aba}.xlsx"
            destino.parent.mkdir(parents=True, exist_ok=True)
            df.to_excel(destino, index=False, header=False)
            arquivos.append((destino, f"aba '{aba}' de {link_planilha(planilha_id)}"))
        for i, tabela in enumerate(self.hive, start=1):
            destino = pasta / "hive" / f"upload_hive_{i}.xlsx"
            destino.parent.mkdir(parents=True, exist_ok=True)
            tabela.to_excel(destino, index=False)
            arquivos.append((destino, "tabela no Hive (DataHub)"))
        return arquivos


def _numero_se_der(v):
    if not isinstance(v, str) or v == "":
        return v
    try:
        return int(v) if re.fullmatch(r"-?\d+", v) else float(v)
    except ValueError:
        return v


class _rede_bloqueada:
    """Impede qualquer conexão de rede enquanto o script original roda."""

    def __enter__(self):
        self._connect = socket.socket.connect
        self._create = socket.create_connection

        def proibido(*a, **k):
            raise ConnectionRefusedError("[TESTE LOCAL] Rede bloqueada durante o teste.")
        socket.socket.connect = proibido
        socket.create_connection = proibido
        return self

    def __exit__(self, *exc):
        socket.socket.connect = self._connect
        socket.create_connection = self._create
        return False
