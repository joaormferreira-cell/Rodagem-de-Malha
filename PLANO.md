# PLANO — Nova ferramenta de Rodagem de Malha (BWT)

Versão 1 · Nov/12/2026 · Status: **Fase 1 em andamento** (módulo de rotas pronto e validado)

---

## 1. Objetivo em uma frase

Reconstruir a rodagem de malha numa ferramenta **única, enxuta e rastreável**. Ela usa as **mesmas planilhas e APIs de entrada** e gera **as mesmas saídas** do processo atual, com números idênticos. Cada número do resultado passa a mostrar de onde veio.

## 2. Princípios (como um time sênior faria)

1. **Primeiro paridade, depois melhoria.** A ferramenta nova tem que dar exatamente os mesmos números da atual antes de qualquer mudança de regra. Toda mudança de regra é uma decisão separada e aprovada.
2. **Separar o cálculo da conexão.** As contas ficam em funções puras, que não sabem se o dado veio do Google, da API ou de um CSV. Isso permite testar tudo no computador, sem risco.
3. **Uma fonte de verdade para premissas.** Velocidades, 750 km, 4h, 12h, IDs de planilha e datas fixas ficam num arquivo de configuração, e não espalhados pelo código.
4. **Seguro por padrão.** O modo padrão nunca grava em produção. Gravar exige pedir explicitamente e mostra antes quais abas serão tocadas.
5. **Rastreabilidade.** Cada linha de saída diz qual regra e qual fonte gerou o número (P1, P2 ou P3; distância cadastrada ou calculada; meta da estação ou média).
6. **Validar a entrada antes de calcular.** Planilha com coluna faltando, rota duplicada ou estação sem cadastro gera um erro claro no início, e não um erro estranho no meio do processo.
7. **Rodar com um comando**, nas 4 etapas, sem depender de copiar dados entre planilhas no meio do caminho.

---

## 3. O que temos hoje (ponto de partida)

### 3.1 Processo atual (do Jards)
| Item | Situação |
|---|---|
| Código | 4 scripts + 5 bibliotecas, ~4.600 linhas |
| Como roda | Manual, um script por vez, na ordem 1 → 2 → (3) → 4 |
| Etapa 1 (malha) | **Não roda hoje**: o token na linha 864 está vazio |
| Ligação entre etapas | Via Hive e via cópia de aba entre planilhas (não documentada) |
| Testes | Nenhum |
| Rastreabilidade | Nenhuma: o resultado não diz de onde veio cada número |
| Etapa 4 | Grava em **append**: rodar 2x duplica linhas |

### 3.2 O que já construímos
| Entregável | Onde | Para que serve |
|---|---|---|
| Mapa do processo | `MAPA.md` | Fluxo, riscos, código morto, pontos obscuros |
| Regras de negócio | `CLAUDE.md` | Regras P1/P2/P3, distância, outbound, fila |
| Simulador local | `teste_local/` | Roda o código atual com CSV, sem internet, e gera o **gabarito** |
| Dados de exemplo | `teste_local/dados_exemplo/` | 8 caminhos inventados que cobrem os casos especiais |
| **Módulo de rotas (novo)** | `nova_ferramenta/rotas.py` | Etapa 2 reescrita do zero |
| Validação do módulo | `nova_ferramenta/validar_rotas.py` | **12 de 12 rotas iguais ao atual, nas 23 colunas** |

### 3.3 O que tem de inútil no código atual (vai sair)
| O que | Onde | Por que sai |
|---|---|---|
| Consulta direta ao Presto (`get_df_demand`) | `hive_lib.py` | Importada nos 4 scripts e nunca chamada |
| `get_df_demand_params` | `hive_lib.py` | É de outro projeto (`portal_bwt`) |
| 5 funções de escrita e leitura nunca usadas | `connection_with_path.py` | `clean_whole_sheet`, `clean_in_sheets`, `print_in_sheets_bach`, `get_last_empty_row`, `print_values_in_sheets` |
| `compute_unloading_queue_time` | etapa 2 | Nunca chamada. Por isso as colunas Queue e Unloading da aba [I] 1.0 são lidas e nunca usadas |
| Leitura de rede pela planilha `1S54tF…` | etapas 1, 2, 4 | Ramo `READ_FROM_HIVE = False`, desligado |
| Escrita na planilha `1e0Ntm…` | etapa 1 | `PRINT_SHEETS = False`, desligado |
| Leitura em dobro da planilha de expressas | etapa 2 | Lê a mesma aba 2x |
| ~12 funções quase iguais de "buscar meta da estação" | etapa 4 | Viram 1 função genérica + 1 tabela de configuração |
| Regra P1/P2/P3 duplicada | etapa 2 e `manual_express_lib.py` | Vira 1 função só |
| Imports sem uso, constantes sem uso, estado global | vários | Limpeza |

**(Hipótese)** A ferramenta nova deve ficar com ~1.200 a 1.500 linhas, contra as ~4.600 de hoje.

---

## 4. Inventário: o que entra e o que sai

### 4.1 Entradas (só as colunas que de fato são usadas)
| # | Fonte | Aba / API | Colunas usadas | Usado em |
|---|---|---|---|---|
| E1 | API Data Service | `brbi_opslgc.demanda_bwt_` | period_start, period_end, origin, destination, path, forecast_ado | Malha |
| E2 | Sheets `1-XOdO…` | 0.0 Distances Available (A1:I) | origin, destini, distance_km, route | Malha |
| E3 | Sheets `1j_-RW…` | 0.0 Station List Historical (A1:D) | station_code, latitude, longitude | Malha |
| E4 | Sheets `1hZSIs…` | Base (A2:G) | Code, SubRegion, Lat, Lon | Malha + BWT |
| E5 | Sheets `1hZSIs…` | SPX_info (A1:I) | station_code, zipcode | BWT |
| E6 | API Data Service | `brbi_opslgc.station_names_malha` | station_code, state_name, status | BWT |
| E7 | Sheets `197nob…` | Implemented routes (B4:AA500) | Rota atualizada com movings, Transit time atualizado, Status, Data da última alteração, Data de ramp-up | Rotas + Ajuste |
| E8 | Sheets `1mwx37…` | ABA ROTAS (A1:Q) | ORIGEM, DESTINO, TT HRS, STATUS DA ROTA | Rotas + Ajuste |
| E9 | Sheets `1VaLP4…` | [O] 0. Routes SPRs (A1:G) | route_code, route_type, origin_station_code, destination_considered, carreta/truck/others_cap | Rotas |
| E10 | Sheets `1VaLP4…` | [I] 1.0 SOC Unloading and Loading Time (A3:I) | Sites, **Loading** (só essa coluna é usada) | Rotas |
| E11 | Sheets `1VaLP4…` | [I] 2. Air Line Haul TT (A3:B) | Route, TT (hours) | Rotas |
| E12 | Sheets `1HdplQ…` | [T] 4.1 SOC Arrived to Received (A3:AA) | code + colunas de mês | Rotas |
| E13 | Sheets `1HdplQ…` | express_route_mngmt (A1:B) | Route, flag expressa | Ajuste |
| E14 | Sheets `1mSxSQ…` | 16 abas de metas `[T] 1.0` a `[T] 8.` | code + colunas de mês (3.0.x: code, period_start, Target…) | BWT |

### 4.2 Saídas (mantidas iguais, para não quebrar quem usa)
| # | Destino | Aba / Tabela | Conteúdo |
|---|---|---|---|
| S1 | Hive (DataHub) | tabela da network | Malha com distâncias (**só se alguém consumir; ver decisão D3**) |
| S2 | Sheets `1B2CFD…` | Resumo_lat_lon, Paths_afetados | Caminhos com erro de distância ou cadastro |
| S3 | Sheets `1HdplQ…` | [T] 4.1 TT and SOC Packed to Transporting to SOC | Uma linha por rota (23 colunas) |
| S4 | Sheets `1HdplQ…` | raw_LhExpress_markup | Rota + selo expressa |
| S5 | Sheets `1iReXh…` | Network BWT output | BWT por caminho |
| S6 | Sheets `1iReXh…` | raw_bwt | BWT agregado ponderado por ADO |
| S7 | Sheets `1iReXh…` | raw_data_1st_SOC | BWT até o 1º SOC |

### 4.3 Saídas novas (rastreabilidade, em arquivo à parte, sem mexer nas abas atuais)
| # | Conteúdo | Para que serve |
|---|---|---|
| N1 | **Rotas com origem de cada número**: fonte_tt (P1/P2/P3/aéreo/fixo), fonte_capacidade (rota/estação/média), fonte_distancia (cadastro/inverso/Haversine), fonte_fila (SOC/média/padrão) | Responder "por que essa rota deu X horas?" |
| N2 | **BWT aberto por componente**, com a fonte de cada meta (da estação ou média) | Responder "de onde vem o BWT desse caminho?" |
| N3 | **Relatório de qualidade da entrada**: estações sem cadastro, rotas sem distância, duplicidades, meses faltando | Saber o que corrigir nas planilhas |
| N4 | **Registro da rodagem**: data, mês, premissas usadas, linhas lidas por aba | Auditoria e comparação entre rodagens |

### 4.4 Análise das planilhas By Step e Initiatives (Nov/12)

| Planilha | O que é | Granularidade | Papel na ferramenta |
|---|---|---|---|
| **V2 BWT by Step** (`1KQq_O…`) | **Realizado** de BWT por etapa (horas + pedidos), mês, semana e dia. Fonte: query `joao_bwt_by_step_mece` (dono: João Pedro), atualização diária ~11h | Canal × rota macro (BR-BR, SP>RJ…) × etapa (códigos 1.01, 3.05, 4.xx…) | **Comparação "meta × realizado"**, não input de cálculo |
| **Initiatives BWT** (`1Ug8Qi…`) | Planejamento: KPIs por time, metas Nov/26 e Nov/27 por leg, lista de iniciativas com impacto em horas por etapa | Etapa / leg / time | **Consome o output da rodagem** e pode alimentar **cenários** |

O que vi nas abas:
- `Initiatives > Network` traz, por mês, "Avg time step / % Share / BWT" de cada componente `bwt_*` (`bwt_apt_paid_to_dropoff`, `bwt_lh_fmh_to_soc`…). A fonte declarada é "2. BWT Output". Ou seja, **ela consome a saída da etapa 4** (formato do `raw_bwt`). **(H)** "2. BWT Output" é a planilha `1iReXh…`.
- `Initiatives > Nov26-27` compara realizado (Aug–Oct) com meta (Nov/26, Nov/27) por leg.
- `Initiatives > BWT Initiatives (list)` tem o impacto de cada iniciativa em horas por etapa (ex.: "Reduce Leftover LMH to 10%" = −0,217h).
- `By Step > Assumptions` já documenta premissas, checagens e tolerâncias. É o mesmo padrão que a ferramenta nova deve seguir.

**Conclusões**
1. **By Step e Initiatives não substituem os inputs de cálculo.** A rodagem precisa de dados por estação e por rota (distâncias, lat/lon, capacidade dos veículos, metas por estação, expressas). As duas planilhas são agregadas por etapa e rota macro e não têm esses dados.
2. **A By Step é o par natural do output.** A rodagem gera a **meta** por etapa; a By Step tem o **realizado** na mesma lógica de etapas. A ferramenta nova deve gerar uma visão por etapa **com os mesmos códigos da By Step**. Assim, meta × realizado fica lado a lado, sem trabalho manual.
3. **A Initiatives é consumidora e futura fonte de cenários.** Ela lê a saída por componente. No futuro, a lista de iniciativas (impacto em horas por etapa) pode virar input de cenário: "BWT Nov/27 se as iniciativas X, Y e Z forem entregues".
4. **Input único: sim, mas consolidado pela ferramenta.** As 14 fontes têm donos diferentes e não dá para mover os dados de lugar. A proposta é a ferramenta ter uma etapa de **coleta** que lê as 14 fontes, guarda só as colunas usadas (seção 4.1) e grava **um único pacote de entrada** por rodagem (um arquivo, ou uma planilha "Inputs Rodagem" com uma aba por fonte). Todo o cálculo lê só desse pacote, que serve também como foto auditável do que foi usado.

### 4.5 Saídas novas para conectar com By Step e Initiatives
| # | Saída | Para quem |
|---|---|---|
| N5 | **Meta por etapa no layout da By Step**: Family, Code, Area, Type, KPI × mês, em horas e pedidos | Comparar meta × realizado direto com a By Step |
| N6 | **Componentes do BWT no layout da Initiatives > Network**: Avg time step, % Share e BWT por `bwt_*` e por mês | Substituir a cópia manual de "2. BWT Output" |
| N7 | *(Futuro)* **Cenários com iniciativas**: meta recalculada aplicando os impactos da lista de iniciativas | Planejamento Nov/27 |

Para isso é preciso uma **tabela de-para**: componente `bwt_*` da rodagem → código da By Step (ex.: `bwt_apt_paid_to_dropoff` → 1.01 "APT (Paid to Pickup or Dropoff)"; `bwt_lh_fmh_to_soc` → 4.xx). Ela fica em `config/de_para_by_step.yaml` e é validada com você.

### 4.6 Inputs padronizados (pensando em quem preenche)

**Problema hoje:** cada área preenche num formato diferente. Tem aba com o cabeçalho na linha 3, outra na linha 4 começando na coluna B, meses como colunas, nomes em inglês e português, e "status" escrito de 5 jeitos. As metas estão em 16 abas com layouts parecidos mas não iguais.

**Proposta:** 14 fontes viram **6 modelos padrão** (+ a API de demanda, que continua igual). Todos seguem as mesmas regras:
- **Uma linha por informação** (formato longo): mês e etapa são colunas, não abas.
- Cabeçalho sempre na **linha 1**, colunas sempre na mesma ordem, nomes em português e sem acento.
- **Listas suspensas** para etapa, status, tipo de estação e mês (não dá para digitar errado).
- Toda linha tem **responsavel** e **atualizado_em**, para saber quem mexeu e quando.
- A ferramenta valida o modelo e devolve **a linha exata e o motivo** do erro.

| Modelo | Colunas | Substitui | Quem preenche *(H)* |
|---|---|---|---|
| **M1 Metas por estação** | mes · etapa · estacao · horas · responsavel · atualizado_em | 16 abas `[T]` da `1mSxSQ…` + [T] 4.1 Arrived to Received + [I] 1.0 Loading | Cada área dona da etapa (FM, FMH, SOC, LMH, XPT) |
| **M2 Tempos de rota** | rota · tipo (expressa oficial / new TT / aérea / ajuste manual / fixo) · tt_horas · selo_expressa · status · vale_de · vale_ate · responsavel · atualizado_em | Implemented routes, ABA ROTAS, Air LH, express_route_mngmt, TT fixo de 47h no código | Line Haul / Expressas |
| **M3 Estações** | estacao · tipo · latitude · longitude · subregiao · cep · estado · status | Station List Historical, Base, SPX_info, API station_names | Cadastro / Network planning |
| **M4 Distâncias** | origem · destino · km · fonte | 0.0 Distances Available | Network planning |
| **M5 Capacidade de veículos** | rota *ou* (estacao_origem + tipo_rota) · carreta · truck · outros | [O] 0. Routes SPRs | Line Haul |
| **M6 Premissas** | parametro · valor · unidade · descricao | Valores escritos no código (750 km, 4h, 12h, velocidades, descansos) | Dono do modelo (você) |

Exemplo de M1, o mesmo formato para todas as áreas:
```
mes      | etapa                          | estacao   | horas | responsavel | atualizado_em
2026-11  | SOC Received to Packed         | SOC-SP1   | 3.0   | ana.soc     | 2026-11-05
2026-11  | LMH Received to Delivering     | HUB-SP-02 | 8.0   | bruno.lmh   | 2026-11-04
2026-11  | APT (Paid to Pickup/Dropoff)   | (todas)   | 18.0  | carla.fm    | 2026-11-03
```

**Transição sem atrito**
1. **Primeiro:** a ferramenta lê as planilhas de hoje e **converte sozinha** para os 6 modelos. Ninguém muda nada no dia 1, e os números continuam iguais.
2. **Depois:** cria a planilha "Inputs Rodagem" com os 6 modelos (abas com validação) e migra **uma área por vez**. Cada área passa a preencher direto no modelo.
3. **No fim:** as abas antigas viram só leitura e saem de uso.

### 4.7 Output mais claro (mesmos números)
| Hoje | Ferramenta nova |
|---|---|
| Colunas com nomes técnicos (`bwt_lh_soc1_to_soc2`, `Final Pck-LHTr`) | Mesmas abas de hoje mantidas **+** uma versão legível com nomes de negócio e unidade (h) |
| Resultado espalhado em 3 planilhas | Um **resumo da rodagem**: BWT total, por etapa (layout By Step), top rotas e caminhos que mais pesam, alertas |
| Sem explicação do número | Cada rota e caminho com a **fonte** (seção 4.3) |
| Erro de dado descoberto depois | **Relatório de qualidade** antes do cálculo |

---

## 5. Arquitetura da ferramenta nova

### 5.1 Fluxo
```
  LER            VALIDAR           CALCULAR                          CONFERIR         GRAVAR
  (adaptadores)  (contratos)       (funções puras)                   (checagens)      (adaptadores)
  Sheets  ─┐                       1. Malha (caminhos + distâncias)
  API     ─┼─► tabelas ─► entradas ─► 2. Rotas (veículos, TT, fila)  ─► saídas ok? ─► Sheets / Hive
  CSV     ─┘   em memória   ok?       3. Ajuste manual de expressas                    ou Excel local
                                      4. BWT por caminho
```
As 4 etapas rodam **em memória, em sequência**. A etapa 4 usa o resultado da etapa 2 direto, sem passar pela cópia entre planilhas nem pelo Hive. Isso elimina 2 dos 3 pontos obscuros do processo atual.

### 5.2 Estrutura de pastas
```
malha/                       pacote da ferramenta nova (o código atual fica intacto até a virada)
  config/
    premissas.yaml           velocidades, descansos, 750 km, 4h, 12h, 0,7, 1000, fila padrão 2h, TT fixos
    fontes.yaml              IDs de planilha, abas, ranges, APIs, destinos de gravação
    componentes_bwt.yaml     tabela dos ~35 componentes do BWT (qual meta, qual estação, regra se faltar)
  leitura/                   sheets.py · dataservice.py · csv_local.py   (mesma interface)
  gravacao/                  sheets.py · hive.py · excel_local.py         (mesma interface)
  validacao/                 entradas.py (contratos) · saidas.py (checagens)
  calculo/
    distancias.py            cadastro nos 2 sentidos → Haversine × 1,4 → erro
    malha.py                 caminho → FMH / SOC1-4 / LMH / XPT + distâncias        (etapa 1)
    tempo_viagem.py          fórmulas normal e expressa
    rotas.py                 veículos, outbound, P1/P2/P3, fila                       (etapa 2) ✅
    ajuste_expressas.py      override manual, reaproveitando P1/P2/P3 de rotas.py    (etapa 3)
    bwt.py                   motor genérico guiado por componentes_bwt.yaml          (etapa 4)
  pipeline.py                ler → validar → calcular → conferir → gravar
  rastreabilidade.py         saídas N1-N4
  __main__.py                linha de comando
tests/
  unit/                      teste de cada regra isolada (ex.: 2.650 km → 40h)
  paridade/                  ferramenta nova × processo atual, coluna a coluna
dados_exemplo/               os CSV do teste_local
```

### 5.3 Como vai rodar
```
python -m malha rodar --mes 2026-11 --modo teste       # lê CSV, grava Excel local (padrão)
python -m malha rodar --mes 2026-11 --modo sombra      # lê planilhas reais, grava numa CÓPIA
python -m malha rodar --mes 2026-11 --modo producao    # grava nas abas reais; lista as abas e pede confirmação
python -m malha validar-entradas --mes 2026-11         # só confere as planilhas, não calcula
python -m malha comparar --mes 2026-11                 # ferramenta nova × processo atual
```

### 5.4 Etapa 4 guiada por tabela (a maior simplificação)
Hoje existem ~12 funções quase iguais, uma por componente. Na ferramenta nova, cada componente vira uma linha de configuração:
```yaml
- coluna: bwt_soc1_received_to_packed
  tipo: meta_estacao                     # busca a meta da estação no mês
  estacao: SOC1
  aba: "[T] 4.0 SOC Received to Packed"
  se_faltar: media                       # sem meta da estação → média das estações
- coluna: bwt_lh_soc1_to_soc2
  tipo: tempo_rota                       # usa o TTFinal da rota calculada na etapa 2
  de: SOC1
  para: SOC2
```
As regras especiais (FBS zera etapas de FMH, crossdock (XD), aeroporto, caminho com ou sem XPT) viram regras nomeadas e testadas uma a uma. **(Hipótese)** cerca de 70% dos componentes cabem no padrão genérico.

---

## 6. Plano de execução (passo a passo)

Dias úteis a partir de Nov/12. **Atenção: Nov/20 é feriado em SP (Consciência Negra).**

| Fase | O que | Entregável | Critério de pronto | Prazo |
|---|---|---|---|---|
| **0. Fundação** | Estrutura de pastas, `premissas.yaml`, `fontes.yaml`, leitura CSV, mover `rotas.py` **vetorizado**, teste de carga com 100 mil caminhos sintéticos, gravação em Parquet | Esqueleto rodando com `python -m malha` | Rotas continua 12/12 igual; 100 mil caminhos em segundos | **Nov/13** |
| **1. Malha** | `distancias.py` + `malha.py` | Etapa 1 reescrita | 8/8 caminhos iguais ao atual, incluindo ERRO e Haversine | **Nov/13** |
| **2. Ajuste de expressas** | `ajuste_expressas.py` usando a mesma P1/P2/P3 | Etapa 3 reescrita | Mesmas rotas alteradas; resto idêntico | **Nov/16** |
| **3. BWT** | `componentes_bwt.yaml` + `bwt.py` | Etapa 4 reescrita | 6/6 caminhos iguais, nos ~35 componentes + agregados | **Nov/18** |
| **4. Pipeline único** | `pipeline.py`, linha de comando, 4 etapas em sequência | `python -m malha rodar` | Tudo igual ao gabarito em 1 comando | **Nov/19** |
| **5. Qualidade e rastreabilidade** | Contratos de entrada, checagens de saída, saídas N1–N4, testes unitários | Relatórios de rastreio | Toda linha com fonte; entrada ruim gera erro claro | **Nov/24** |
| **5b. Input único + visão By Step** | Etapa de coleta (pacote único de entrada), de-para `bwt_*` → códigos By Step, saídas N5 e N6 | Pacote de entrada + meta no layout By Step e Initiatives | De-para aprovado por você; N6 bate com a aba Network da Initiatives | **Nov/25** |
| **6. Dados reais (offline)** | Baixar as abas reais em CSV e rodar ferramenta nova × processo atual | Relatório de paridade real | 100% das linhas iguais, ou cada diferença explicada | **Nov/26** *(depende de D7)* |
| **7. Conexão real (sombra)** | Adaptadores Sheets e API com credenciais próprias, gravando numa cópia | Rodagem real sem risco | 2 rodagens seguidas iguais ao processo atual | **Dec/01** *(depende de A1, A2)* |
| **8. Virada** | Modo produção, desligar scripts antigos, manual de uso | Ferramenta oficial | Aprovação do gestor | **Dec/03** |
| **8b. Inputs padronizados** | Planilha "Inputs Rodagem" com os 6 modelos (M1–M6), validação, migração de uma área por vez | Áreas preenchendo no padrão | Rodagem lendo dos modelos dá o mesmo número que lendo das planilhas antigas | **Dec/04 → Dec/18** *(1 área por vez)* |
| 9. Melhorias de regra *(opcional)* | Corrigir as estranhezas da seção 9, uma por vez | Mudanças aprovadas | Cada mudança com antes × depois | A definir |

---

## 7. 5W2H

| | Resposta |
|---|---|
| **What (o quê)** | Ferramenta nova de rodagem de malha: malha → rotas → ajuste de expressas → BWT, com as mesmas entradas e saídas, mais rastreabilidade |
| **Why (por quê)** | O processo atual tem ~4.600 linhas com muito código sem uso e lógica duplicada. A etapa 1 não roda, as etapas dependem de cópia manual, não há testes e o resultado não é explicável. Hoje ninguém consegue alterar uma regra com segurança |
| **Who (quem)** | **Você:** dono do projeto, decisões, acessos, validação de negócio. **Claude:** código, testes, documentação. **Gestor:** aprova mudança de comportamento e a virada. **TI / Data Suite:** acessos (APP_KEY, OAuth). **Quem consome as abas de saída:** avisar antes da virada |
| **Where (onde)** | Repositório `Rodagem-de-Malha`, pasta `malha/`. Roda no seu computador, na intranet Shopee |
| **When (quando)** | Nov/12 → Dec/03 a ferramenta oficial (seção 6); Dec/04 → Dec/18 a migração das áreas para os inputs padronizados. Paridade com exemplo até Nov/19; com dados reais até Nov/26 |
| **How (como)** | Reescrever etapa por etapa, sempre comparando com o gabarito do processo atual. Primeiro igualar os números, depois melhorar |
| **How much (quanto)** | Sem custo de software (Python e bibliotecas gratuitas). Custo em tempo: ~15 dias úteis. Dependência de acessos internos |

---

## 8. Decisões que você precisa tomar

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| D1 | A etapa 4 continua em **append**? | (a) append, como hoje · (b) substituir o mês que está sendo rodado | **(b)**: rodar 2x não duplica. Avisar quem usa a aba |
| D2 | Colunas de rastreio nas abas atuais ou à parte? | (a) colunas extras no fim · (b) arquivo / aba separada | **(b)**: não quebra quem lê as abas |
| D3 | Continua subindo a malha no Hive? | (a) sim · (b) não | Depende de alguém além da etapa 2/4 usar a tabela. Se ninguém usar → (b) |
| D4 | Onde grava na fase sombra? | Cópia das 3 planilhas de saída | Criar cópias com "TESTE" no nome |
| D5 | Valores fixos (Nov/2026 no filtro, 47h SOC-SP6>HUB-LAM-02) | Manter no `premissas.yaml` · remover | Manter, mas visível na configuração |
| D6 | Estranhezas da seção 9 | Preservar na paridade · corrigir depois | Preservar agora; corrigir na Fase 9 com aprovação |
| D7 | Dados reais da Fase 6 | Baixar CSV à mão · esperar os acessos | CSV à mão: não trava o projeto |
| D8 | Formato do input único | (a) arquivo local por rodagem · (b) planilha "Inputs Rodagem" no Google | **(a)** primeiro (rápido, auditável); **(b)** depois, se o time quiser ver no Sheets |
| D9 | Onde publicar N5 e N6 | (a) abas novas na By Step / Initiatives · (b) planilha de output própria | **(b)**, e By Step / Initiatives leem dela. Não mexer nas suas planilhas sem combinar |
| D10 | Quem é dono de cada modelo M1–M6 | Nomes por área | Definir com o gestor antes da Fase 8b |

## 9. Estranhezas do código atual (preservadas na paridade, candidatas a correção)

1. O SPR é cruzado por estação com nomes de coluna trocados (`destination_considered` = origem, `origin_station_code` = tipo de rota). Duplicidade nessa combinação **derruba** o script atual.
2. A etapa 4 lê "Received→Flight" e "Arrived→OB" da **mesma aba** (`[T] 8.`).
3. O ajuste manual (etapa 3) só lê o histórico de expressas se existir a coluna "Data final de ramp-up"; a etapa 2 não exige essa coluna.
4. A fila de rotas que não terminam em SOC é fixa em 2h; a aba [I] 1.0 tem Queue e Unloading, mas não são usadas.
5. Metas [T] 1.0 e 2.0 usam só o **primeiro valor** da coluna do mês, um número nacional e não por estação.
6. Premissas de velocidade e descanso sem fonte documentada (existe uma "V2" comentada com outros valores).

## 10. Acessos e dependências

| # | O que | Para quê | Situação |
|---|---|---|---|
| A1 | APP_KEY / APP_SECRET próprios no Data Suite | Ler as APIs E1 e E6 | **Falta**. Hoje são do Jards |
| A2 | Credencial Google própria (OAuth ou conta de serviço) | Ler e gravar Sheets | **Falta**. Hoje é o `jards.json` |
| A3 | SDK interno `dataservice` | Chamar o Data Service | **Falta** |
| A4 | Acesso de edição às planilhas de saída (ou às cópias) | Fases 7 e 8 | A verificar |
| A5 | Token de ingestão do DataHub | Só se D3 = (a) | Falta (linha 864 vazia) |

## 11. Riscos e como mitigar

| Risco | Impacto | Mitigação |
|---|---|---|
| Acessos (A1–A3) demorarem | Fases 7–8 atrasam | Fases 0–6 não dependem deles; pedir os acessos já |
| Dado real com formato diferente do exemplo (ex.: "10,5" com vírgula) | Diferenças na paridade | Fase 6 existe para isso; contratos de entrada pegam cedo |
| Alguém consome uma aba ou o Hive e não sabemos | Quebra na virada | Manter as saídas iguais (D2) e avisar antes da virada |
| Diferença de versão do pandas entre computadores | Números diferentes | Fixar versões num `requirements.txt` |
| Regra "estranha" ser intencional | Corrigir errado | Só corrigir na Fase 9, com aprovação |

## 12. Teste de estresse do desenho (Nov/12, com dados reais)

Medido nas planilhas reais, só com leitura. Cada achado muda o desenho **antes** de construir.

### 12.1 Volume: o detalhe NÃO cabe no Google Sheets
| Medida | Valor real |
|---|---|
| `Network BWT output` (`1iReXh…`) | **188.575 linhas × 50 colunas = 9,43 milhões de células** |
| Limite do Google Sheets | **10 milhões de células por arquivo** (soma de todas as abas) |
| Caminhos por mês | Set/26: 97.298 · Nov/26: 91.267 |
| Rotas na `[T] 4.1` | 23.615 linhas (2 meses) |

- ⚠️ **Risco no processo atual, agora:** a etapa 4 grava em append. A próxima rodagem (+~9 milhões de células) **passa do limite e falha**, a não ser que alguém limpe a aba antes. Vale avisar o gestor.
- A tabela "BWT por caminho e etapa" em formato longo daria ~95 mil caminhos × ~15 etapas ≈ **1,4 milhão de linhas por mês**. **Impossível no Sheets.**

**Mudança no desenho:**
- O **detalhe** (rotas, caminhos, caminho × etapa) vai para **tabela no Hive** (recomendado: é onde está o realizado da By Step, então meta × realizado viram um JOIN em SQL) **ou** para arquivo Parquet local (decisão D11).
- No **Sheets** ficam **só visões agregadas**: layout By Step (~100 códigos × filtros × meses), resumo, top rotas, qualidade dos dados. Isso dá milhares de linhas, não milhões.
- **Fim do append.** Cada rodagem ganha um `id_rodagem` (data + versão) e substitui o próprio mês. O histórico fica no Hive ou nos arquivos, não empilhado numa aba.

### 12.2 Formato do detalhe (para caber e agregar certo)
Mesmo padrão da By Step e do `raw_bwt`: **numerador e denominador** (`bwt_n = horas × pedidos`, `bwt_d = pedidos`). Assim qualquer agregação (por etapa, estado, canal) é Σn ÷ Σd, sem média de média.

Modelo em estrela (não repete o texto do caminho 35 vezes):
```
caminhos            id_rodagem · mes · id_caminho · caminho · origem · destino · canal · rota_macro · uf · regiao · pedidos_dia
caminho_etapa       id_rodagem · id_caminho · codigo_by_step · horas · bwt_n · bwt_d · fonte
rotas               id_rodagem · mes · rota · ... (colunas da seção "Rotas") · fonte_*
by_step_meta        id_rodagem · mes · canal · rota_macro · codigo_by_step · bwt_n · bwt_d     ← mesmo formato do raw_mece_month
```

### 12.3 De-para componentes da rodagem → códigos By Step
A By Step tem 98 códigos; a rodagem gera 35 componentes. O encaixe **não é 1 para 1**:

| Tipo | Exemplos | Tratamento |
|---|---|---|
| 1 → 1 | `bwt_apt_paid_to_dropoff` → 1.01 · `bwt_dropoff_to_pickup` → 3.01 · `bwt_soc1_received_to_packed` → 4.12 · `bwt_lh_soc_to_lmh` → 4.20 · `bwt_hub_delivering_to_1st_attempt` → 6.01 | Direto |
| 1 → vários (depende do caminho) | `bwt_pickup_to_received` → 3.03 (SOC) / 3.04 (FMH) / 3.05 (LMH) | Decide pela próxima estação do caminho |
| Vários → 1 | LMH 4.9 + 5.0 → 5.01 · LH SOC2→3 + SOC3→4 → 4.17 | Soma |
| Granularidade diferente | `bwt_fbs_processing` = 2.01 + 2.02 · fila no destino (dentro do TTFinal) = sub-etapas a/b/c da By Step | Comparar no **nível de lane** (LH + fila juntos), que é o que a própria By Step valida na linha 5 |
| Sem código na By Step | 4º SOC (`bwt_soc4_*`) · tempo de aeroporto embutido no SOC | Decisão D12 |
| Só existe no realizado | Fluxos reversos (LMH-SOC, XPT-SOC…), Pickup Point, Mobile HUB, FMH-FMH, No scan (7.01) | A meta **não modela** esses fluxos; marcar como "fora do modelo" na comparação |

**Consequência:** o BWT total da meta e o total realizado **não são comparáveis diretamente**, porque o realizado tem fluxos que a rodagem não simula. A comparação justa é **por etapa ou lane**, no mesmo recorte de canal e rota.

### 12.4 Filtros da By Step que a rodagem precisa produzir
- **Canal** (`spx_channel`): a rodagem cobre **SPX D2D + Fulfillment D2D**, sem CB. Own Flex, 3PL, BSC e XD não entram. É preciso o de-para `fbs_flag` → nome do canal na By Step.
- **Rota macro** (`main_route`): "BR - BR", "SPM - SPM", "SP > RJ", "BR>BA State", "SP Capital>SP Capital"… A rodagem tem UF, região e SPM, mas **não tem Capital / Metro / Interior**. O modelo **M3 Estações** precisa ganhar essa coluna, e é preciso a regra exata da query `joao_bwt_by_step_mece` (que é sua).

### 12.5 Outras descobertas
- **`1HdplQ…` ("1.1 BWT Target Inputs - Análise final") é cópia de `1mSxSQ…` ("1.1 BWT Target Inputs")**: as duas têm exatamente as mesmas 23 abas. A `[T] 4.1` da planilha principal tem dados de Ago/26 marcados "Source: Python Model". **(H)** O ID da planilha de saída é trocado à mão no código conforme o uso. Na ferramenta nova isso some: a etapa 4 usa o resultado da etapa 2 direto.
- **Inputs reais:** as abas de meta têm cabeçalho na linha 3, meses como `2025-01-01`, decimal com ponto e o **dono na célula A1** (ex.: "Source: Thadeu"). Isso ajuda a definir os donos dos modelos M1–M6 (D10).
- **Desempenho:** com ~95 mil caminhos, laço linha a linha (como na etapa 1 atual e no `quebrar_em_rotas` do módulo novo) fica lento. **Tudo precisa ser vetorizado**, e a Fase 0 inclui um teste com 100 mil caminhos sintéticos.
- **Cenários:** a Initiatives usa "2. BWT Output by step-**2027**". A ferramenta precisa de um parâmetro de **cenário** (Nov/26 base, Nov/27…) desde o início, para não ser adaptada depois.

### 12.6 Novas decisões
| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| D11 | Onde fica o detalhe (caminho × etapa) | (a) Hive · (b) Parquet local · (c) ambos | **(c)**: Parquet já na construção; Hive quando houver token de ingestão (A5 passa a ser necessário) |
| D12 | 4º SOC e aeroporto sem código na By Step | (a) somar no 3º SOC / SOC · (b) criar códigos novos | (b), marcados como "só meta" |
| D13 | Nível oficial de comparação meta × realizado | (a) código a código · (b) lane (LH + fila) e etapa-pai | **(b)**, que é como a By Step já confere |
| D14 | Regra de Capital / Metro / Interior | Copiar da query `joao_bwt_by_step_mece` | Usar exatamente a mesma regra da sua query |

## 13. Como medir o sucesso

| Indicador | Hoje | Meta |
|---|---|---|
| Paridade de números (exemplo) | Rotas 12/12 ✅ | 100% nas 4 etapas |
| Paridade de números (real) | — | 100%, ou diferença explicada |
| Comandos para rodar tudo | 4 scripts + cópia manual | 1 |
| Linhas de código | ~4.600 | ~1.500 *(hipótese)* |
| Linhas de saída com fonte rastreada | 0% | 100% |
| Testes automáticos | 0 | Cada regra de negócio com teste |
| Tempo de rodagem | A medir na Fase 6 | Menor que hoje |
| Rodar 2x duplica dados? | Sim (etapa 4) | Não (se D1 = b) |
