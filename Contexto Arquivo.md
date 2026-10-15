# Rodagem de Malha — pipeline BWT (SPX BR)

Scripts Python que pegam a demanda da malha (paths E2E + ADO), calculam distâncias, transit time (TT) e outbound por rota e, no fim, o BWT (Buyer Waiting Time) por path. Leem e gravam em Google Sheets e no Hive / Data Service da Shopee.

## Ambiente

```
<pasta-pai>/                    # hoje: Desktop\Rodagem de Malha (é o PARENT_DIR dos scripts)
├── credential/jards.json       # OAuth Google (o token.json é gerado aqui). Fica FORA do repo.
└── Rodagem-de-Malha/           # este repositório
    ├── .env                    # APP_KEY, APP_SECRET (carregado pelo hive_lib.py). Nunca commitar.
    ├── CLAUDE.md
    └── *.py
```

- Rodar da raiz do repo: `python <script>.py`.
- Os scripts executam direto ao rodar (não têm `main()`), exceto `outobund_by_soc_tt_by_routes_manual_express.py`.
- Precisa da intranet Shopee (Data Service usa `Env.INTRANET`) e do SDK interno `dataservice`.
- Libs: pandas, numpy, google-api-python-client, google-auth-oauthlib, python-dotenv, requests, requests-toolbelt, pyhive.

## Ordem do pipeline

**1. `network_input_to_bwt_generation.py`**: monta a network com distâncias.
- Lê: API `brbi_opslgc.demanda_bwt_`; distâncias `1-XOdO…` (`0.0 Distances Available`); lat/lon `1j_-RW…` (Station List Historical) + `1hZSIs…` (Base).
- Grava: **Hive** via DataHub (`PRINT_HIVE = True`); relatório de erros em `1B2CFD…` (`Resumo_lat_lon`, `Paths_afetados`, limpa e reescreve). `PRINT_SHEETS = False`.

**2. `outobund_by_soc_tt_by_routes.py`**: outbound, veículos e TT por rota.
- Lê: API `brbi_opslgc.get_bwt_network_jards`; expressas oficiais `197nob…`; New TT `1mwx37…`; SPRs, fila/descarga e Air LH `1VaLP4…`; Arrived→Received em `1HdplQ…`.
- Grava: `1HdplQ…` → `[T] 4.1 TT and SOC Packed to Transporting to SOC` e `raw_LhExpress_markup` (limpa e reescreve).

**3. `outobund_by_soc_tt_by_routes_manual_express.py`** (opcional): override manual de selo expressa.
- Lê: `[T] 4.1` e `express_route_mngmt` em `1HdplQ…`; P1 `197nob…`; P2 `1mwx37…`.
- Grava: regrava `[T] 4.1` em `1HdplQ…`. Só altera as rotas da lista e confere que o resto ficou idêntico.

**4. `bwt_calculator.py`**: BWT por path.
- Lê: API `get_bwt_network_jards`; targets `[T] *` em `1mSxSQ…`; estações `1hZSIs…` + API `brbi_opslgc.station_names_malha`.
- Grava: `1iReXhz…` (output **original**) → `Network BWT output`, `raw_bwt`, `raw_data_1st_SOC`, em modo **append**.

Bibliotecas de apoio:
- `transit_time_lib.py`: TT por distância (normal e expressa).
- `manual_express_lib.py`: lógica do override manual (usada no passo 3).
- `station_geo_lib.py`: estado e regional a partir de XPT/LMH.
- `hive_lib.py`: leitura via Data Service API e upload pro Hive (DataHub).
- `connection_with_path.py`: classe `GmailEntry`, leitura e escrita no Google Sheets.

## Regras de negócio principais

- Path suportado: FMH/FBS + até 4 SOCs + LMH (HUB) + XPT. O que não cabe vai para a coluna `ERRO`.
- Distância: base cadastrada (vale nos dois sentidos) → senão Haversine × 1,4 → senão `-1` (linha descartada depois).
- TT por rota: **P1** planilha oficial de expressas (se mês ≥ ramp-up) → **P2** New TT (status ATIVA / A INICIAR) → **P3** fórmula por km.
- Selo expressa: rota em P1, ou distância ≥ 750 km (exceto origem 3PL e destino XPT).
- `TTFinal` = fila/descarga do destino (Arrived→Received) + TT. Sem fila para HUB-XPT, SOC-XPT, FBS/FMH/SOC-HUB e rotas < 3 km.
- Outbound SOC-SOC: 12h ÷ nº de veículos (mínimo 4h) + loading.
- Origens CB (`FMH-VCP`, `FMH-GIG`, `FMH-GRU`) são excluídas.

## Regras para o Claude

- **Nunca rodar um script que grava em Sheets ou Hive sem perguntar antes.** Dizer quais planilhas e abas serão tocadas.
- Para testar: desligar as flags de escrita (`PRINT_HIVE`, `PRINT_SHEET_BWT_E2E`, `PRINT_SUMMARY_SHEET`, `PRINT_1ST_SOC_SHEET`) ou apontar para cópia de teste (`bwt_calculator.py` tem `1hLHJC…` comentado como "Teste").
- `bwt_calculator.py` grava em append: rodar duas vezes duplica linhas.
- Nunca abrir, imprimir, commitar ou colar o conteúdo de `credential/`, `token.json`, `.env` ou tokens de ingestão.
- Mudanças mínimas e só no escopo pedido. Não refatorar o que não foi pedido.
- A lógica P1/P2/P3 existe em dois lugares (`outobund_by_soc_tt_by_routes.py` e `manual_express_lib.py` + `_load_p1_express`). Mudou em um, checar o outro.
- Ao propor mudança de regra, dizer qual coluna/aba de saída muda.
- Responder em português, direto.

## Pontos em aberto

- `network_input_to_bwt_generation.py:864`: `ingestion_token = ` está vazio (erro de sintaxe). Repor localmente, sem commitar o token.
- `bwt_calculator.py:101-102`: `RANGE_RECEIVED_2DEPARTURE_AIRLH` e `RANGE_ARRIVED_2OB_AIRLH` apontam para a mesma aba (`[T] 8. Airport Received to Flight Departure`). Confirmar se Arrived→OB deveria ler outra aba.
- `outobund_by_soc_tt_by_routes_manual_express.py:178`: o bloco antigo do P1 só é lido se existirem as colunas `Data de ramp-up` **e** `Data final de ramp-up`. O outbound padrão só exige `Data de ramp-up`. Se a coluna "final" não existir na planilha, o P1 do manual diverge do padrão.
- `[T] 4.1` é gravada em `1HdplQ…` (passos 2 e 3), mas o `bwt_calculator.py` lê de `1mSxSQ…`. Confirmar como uma chega na outra.
- Valores fixos no código: novembro/2026 no filtro do output (`bwt_calculator.py:921`); TT fixo de 47h para `SOC-SP6>HUB-LAM-02` (`outobund_by_soc_tt_by_routes.py:884`, marcado [TEMP]).
