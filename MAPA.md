# MAPA — Rodagem de Malha (pipeline BWT, SPX BR)

Legenda: sem marca = **fato** (está no código) · **(H)** = hipótese minha. Não cobre `teste_local/` (simulador local, não faz parte do original).

## O que faz
Calcula o **BWT** (Buyer Waiting Time: horas da compra até a 1ª tentativa de entrega) de cada caminho logístico da malha (FMH/FBS → SOCs → HUB → XPT). Para isso monta os caminhos com distâncias, calcula tempo de viagem e de saída de cada rota e soma as metas de cada etapa operacional, gravando em Google Sheets e no Hive.

## Como rodar
- `python <script>.py` na raiz do repo. Sem argumentos de CLI; o código roda ao importar (exceto o passo 3, que tem `main()`).
- Arquivos: `../credential/jards.json` (OAuth Google; `token.json` é **criado** ao lado) e `.env` na raiz.
- Env vars: `APP_KEY`, `APP_SECRET` (Data Service); `HADOOP_USER_NAME`, `HADOOP_USER_RPCPASSWORD` (só Presto, não usado); opcionais `DATASERVICE_TIMEOUT_SECONDS`, `USE_NEW_OPS_LAT_LON`.
- Libs (sem requirements.txt): pandas, numpy, google-api-python-client, google-auth-oauthlib, python-dotenv, requests, requests-toolbelt, pyhive, `dataservice` (SDK interno Shopee). Exige intranet (`Env.INTRANET`).
- Sem cron, CI, Dockerfile ou testes no repo → disparo **manual**. Ordem pelos comentários do topo (`#primeiro/#segundo/#terceiro arquivo`).

## Entry points
| Arquivo:linha | Dispara |
|---|---|
| `network_input_to_bwt_generation.py:18` (cliente Google) e `:127` (leitura) | Passo 1 — malha + distâncias |
| `outobund_by_soc_tt_by_routes.py:23` e `:473` | Passo 2 — TT/outbound por rota |
| `outobund_by_soc_tt_by_routes_manual_express.py:283` → `main()` `:200` | Passo 3 (opcional) — override manual de expressas |
| `bwt_calculator.py:28` e `:662` | Passo 4 — BWT por caminho |

## Fluxo
1. **Passo 1** — In: API `brbi_opslgc.demanda_bwt_` (caminhos + ADO); Sheets `1-XOdO…` (distâncias), `1j_-RW…` + `1hZSIs…` (lat/lon). Etapas: remove destino 3PL → distância por trecho (cadastro nos 2 sentidos → senão Haversine×1,4 → senão `-1`) → distribui estações em FMH/SOC1-4/LMH/XPT. Out: **POST no DataHub/Hive** (`:866`); relatório de erros em `1B2CFD…` (abas `Resumo_lat_lon`, `Paths_afetados`).
2. **Passo 2** — In: API `get_bwt_network_jards`; Sheets `197nob…` (expressas), `1mwx37…` (New TT), `1VaLP4…` (SPR, carga, Air LH), `1HdplQ…` (Arrived→Received). Etapas: quebra caminhos em rotas → soma ADO → nº de veículos → outbound SOC-SOC (12h÷veículos, mín. 4h + loading) → TT por P1 expressa / P2 New TT / P3 fórmula km (`transit_time_lib.py`) → + fila destino. Out: `1HdplQ…` abas `[T] 4.1 TT and SOC Packed…` e `raw_LhExpress_markup`.
3. **Passo 3** — In: `[T] 4.1` e `express_route_mngmt` (`1HdplQ…`), P1, P2. Etapas: força selo das rotas listadas e recalcula TT (`manual_express_lib.py`); verifica que o resto ficou idêntico. Out: regrava `[T] 4.1`.
4. **Passo 4** — In: API `get_bwt_network_jards` e `station_names_malha`; 17 abas de metas em `1mSxSQ…`; `1hZSIs…` (`Base`, `SPX_info`). Etapas: ~35 componentes de tempo por caminho → soma `bwt_total_hours` → SPM/estado/regional → agregados por ADO. Out: `1iReXhz…` abas `Network BWT output`, `raw_bwt`, `raw_data_1st_SOC` (**append**).

## Dependências externas
Google Sheets API (OAuth, conta do `jards.json`) · Shopee Data Service (`dataservice` SDK, APP_KEY/SECRET, `endUser` fixo `jards.silva@shopee.com` em `hive_lib.py:119`) · DataHub ingestion (URL fixa em `network_input…:863`, token) · Presto (só em função não usada). Nenhuma credencial hard-coded encontrada.

## Riscos e efeitos colaterais
- **Apaga dados em Sheets** (`clean_specific_range`): passo 1 `A1:Z100`/`A1:K5000` no relatório; passos 2 e 3 `A3:W` de `[T] 4.1` e `A2:B` de `raw_LhExpress_markup`.
- **Passo 4 grava em append**: rodar 2× duplica linhas na planilha marcada como "original" (`:47`).
- **Passo 1 sobe para o Hive** via POST; erro de upload só é impresso, não interrompe (`hive_lib.py:87`).
- **Passo 1 não compila hoje**: `ingestion_token = ` vazio (`:864`).
- OAuth pode abrir navegador (`connection_with_path.py:164`) e grava `token.json` em disco. Nada de delete de arquivo, e-mail, subprocess ou API paga externa.

## Código morto / não usado — candidatos a remoção
Nada foi removido. Remover só depois de entender o processo inteiro.
`get_df_demand` (importado nos 4 scripts, nunca chamado) · `get_df_demand_params` (cita `portal_bwt/`, outro repo) · em `connection_with_path.py`: `clean_whole_sheet`, `clean_in_sheets`, `print_in_sheets_bach`, `get_last_empty_row`, `print_values_in_sheets` · passo 2: `compute_unloading_queue_time`, `CONST_MIN_ADO_EXPRESS`, `GSHEET_BID_*`, `date` · passo 4: `import requests`, `MultipartEncoder`, `PRINT_HIVE_E2E`, `COL_EXCLUDE_OUT` · passo 1: escrita em `1e0Ntm…` desligada (`PRINT_SHEETS=False`) · ramos `READ_FROM_HIVE=False` (Sheets `1S54tF…`) nos passos 1, 2 e 4.

## Pontos obscuros
- **(H)** A API `get_bwt_network_jards` lê a tabela que o passo 1 sobe no Hive. Nada no código liga as duas.
- O passo 2 grava `[T] 4.1` em `1HdplQ…`, mas o passo 4 lê de `1mSxSQ…`. Como uma chega na outra?
- DataHub: o upload acrescenta ou substitui a tabela?
- `bwt_calculator.py:101-102`: dois ranges aéreos apontam para a mesma aba.
- Passo 2 `:226`: o merge de SPR por estação usa `destination_considered` = origem e `origin_station_code` = tipo de rota. Nomes invertidos ou intencional?
- Passo 4 `:921`: novembro/2026 fixo + "próximo mês" dependente da data de execução. Passo 2 `:884`: TT fixo de 47h `[TEMP]`.
- Origem das premissas de velocidade e descanso em `transit_time_lib.py` (sem fonte; há uma "V2" comentada).
- `hive_lib.py`: renomes `soc4_hub` e alias `DEST` sem uso aparente.
