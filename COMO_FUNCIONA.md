# Como funciona a Rodagem de Malha 2.0

Guia em linguagem simples, para entender e explicar a ferramenta sem ler código.

## Em uma frase
A ferramenta pega **os caminhos que os pacotes fazem** (ex.: FMH → SOC São Paulo → SOC Rio → HUB Rio), calcula **quanto tempo cada trecho leva** e, no fim, **o prazo total de entrega** (BWT).

## O que tem na pasta
| O quê | Para que serve |
|---|---|
| `RODAR.bat` | **O que você usa no dia a dia:** dois cliques e sai o Excel. |
| `dados_reais/` | Os dados que você baixa (Inputs Rodagem, distâncias, demanda, estações, realizado da By Step, real por rota, Initiatives). `pronto/` é montada sozinha a cada rodada. Só no seu PC. |
| `saida/` | O resultado: `Rodagem de Malha AAAA-MM-DD.xlsx` + arquivos de apoio (são refeitos a cada rodada). |
| `consultas/` | As 2 consultas do Data Studio da rotina semanal. |
| `malha/` | **A ferramenta nova** (Rodagem 2.0): o cálculo, as checagens e o Excel. |
| `99. Old/` | **O software antigo** (do Jards), ainda o oficial: os 4 scripts dos passos 1 a 4 (`network_input_to_bwt_generation.py`, `outobund_by_soc_tt_by_routes.py`, `outobund_by_soc_tt_by_routes_manual_express.py`, `bwt_calculator.py`), as peças que eles usam e o `MAPA.md` (mapa técnico). Gravam no Sheets/Hive. Para rodar: `python "99. Old/bwt_calculator.py"` (da pasta do projeto). |
| `apps_script/` | Botão **Rodagem → Atualizar resultado** da planilha de saída (ver `COMO_INSTALAR.md`). |
| `teste_local/` | `preparar_dados_reais.py` (o RODAR.bat usa), dados de exemplo e o simulador que roda o software antigo sem internet para comparar. |
| `tests/` | Testes automáticos. |
| `COMO_FUNCIONA.md` (este), `CLAUDE.md` | Guia simples · instruções para o Claude. |
| `__pycache__/`, `.pytest_cache/` | O Python cria sozinho. Pode ignorar. |

## Como rodar
**Jeito simples:** dois cliques em `RODAR.bat` (prepara os dados de `dados_reais`, calcula, confere e abre o Excel).

**O que sai (pasta `saida`):**
- `Rodagem de Malha AAAA-MM-DD.xlsx`: Leia-me, Resumo, Rodagem x Initiatives x Real (se houver `dados_reais/initiatives.csv`: aba Nov26-27 da Initiatives), Ponte do BWT (se houver o realizado da By Step; mês em andamento e último mês fechado), Onde atacar (se houver o realizado da By Step e o real por rota), Regra x Real (se houver o real por rota: a meta erra sempre para o mesmo lado em algum tipo de rota ou regra? Só compara, não muda a meta), Simulador de iniciativas (se houver a aba Nov26-27; com fórmulas: ligar e desligar cada iniciativa), Simulador de malha (com fórmulas: mudar a fila de um SOC, a viagem de uma rota ou virar a rota expressa e ver a meta de BWT mudar), Meta x Realizado (se houver o realizado da By Step), Meta By Step, Rotas, Rotas meta x real (se houver o real por rota: `consultas/lh_real_por_rota.sql`), Checagens
- `BWT por caminho - todos os meses.csv`: o detalhe de cada caminho
- `planilha\*.csv`: para o botão **Rodagem → Atualizar resultado** da planilha de saída (ver `apps_script/COMO_INSTALAR.md`)

**Pelo terminal** do VS Code, na pasta do projeto:

| Comando | O que faz |
|---|---|
| `python -m malha rodar` | Calcula tudo e salva os resultados na pasta `saida/` (Excel para abrir, Parquet para volume grande) |
| `python -m malha comparar` | Roda a ferramenta nova **e** o processo atual com os mesmos dados e diz se deu igual |
| `python -m pytest tests -q` | Roda os testes automáticos (igualdade com o processo atual + teste com 100 mil caminhos) |

Por padrão usa os dados de exemplo (`teste_local/dados_exemplo`). Para outros dados: `--dados <pasta>`.

## As partes (cada uma é um arquivo, com uma função clara)

```
malha/
  config/premissas.toml   ← TODOS os números de negócio (750 km, 4h, velocidades...). Mudou a regra? Muda aqui.
  config/fontes.toml      ← de qual planilha e aba vem cada input
  leitura.py              ← lê os inputs
  calculo/
    distancias.py         ← distância de cada trecho
    malha.py              ← ETAPA 1: monta os caminhos
    tempo_viagem.py       ← fórmula de tempo de viagem por km
    rotas.py              ← ETAPA 2: veículos, espera e tempo de cada rota
  pipeline.py             ← junta as etapas na ordem
  comparar.py             ← confere contra o processo atual
```

## Passo a passo do cálculo

### Etapa 1 — Montar a malha (`calculo/malha.py`)
1. Recebe a demanda: cada caminho e quantos pacotes por dia passam nele (ADO).
2. Tira caminhos com destino 3PL.
3. Para cada trecho do caminho, acha a distância:
   - se está **cadastrada** (planilha de distâncias), usa — vale nos dois sentidos;
   - senão, calcula pela **linha reta entre as estações × 1,4** (as estradas não são retas);
   - se a estação não tem localização, marca **-1** e o caminho vai para a lista de erros.
4. Coloca cada estação na sua coluna: FMH, SOC1 a SOC4, LMH (HUB), XPT.

### Etapa 2 — Calcular cada rota (`calculo/rotas.py`)
1. **Quebra** cada caminho nos seus trechos e **soma os pacotes** de todos os caminhos que passam no mesmo trecho.
2. **Veículos:** enche carretas; sobra pequena (< 1.000 pacotes) não abre veículo; sobra grande (> 70% de uma carreta) abre mais uma; o resto vai num truck.
3. **Espera para sair** (só SOC → SOC): 12h ÷ número de veículos, nunca menos de 4h, + tempo de carregar.
4. **Tempo de viagem**, nesta ordem de prioridade:
   1. rota na planilha oficial de **expressas** (já ativa no mês) → tempo oficial;
   2. rota na planilha **New TT** → tempo de lá;
   3. senão, **cálculo pela distância** (velocidade + paradas do motorista).
   Rotas de 750 km ou mais ganham o selo de expressa.
5. **Fila no destino:** tempo para descarregar no SOC de destino. Rotas que terminam em HUB ou XPT não têm fila.
6. **Tempo total da rota** = viagem + fila.

Cada rota diz **de onde veio o tempo de viagem** (coluna `fonte_tt`): Expressa oficial, New TT, Cálculo por km, Air LH ou Valor fixo.

### Etapa 3 — Ajuste manual de expressas (`calculo/ajuste_expressas.py`)
A lista `express_route_mngmt` diz quais rotas o time quer (ou não) como expressa. Só essas rotas mudam: troca o selo e recalcula o tempo de viagem. O resto fica igual.

### Etapa 4 — BWT por caminho (`calculo/bwt.py`)
Soma o tempo de **cada etapa do pacote**, do pagamento até a 1ª tentativa de entrega (35 etapas, lista completa em `COMPONENTES` no arquivo). Cada etapa vem de:
- **meta da estação** (abas [T] da planilha de metas) — estação sem meta usa a **média** do mês;
- **tempo da rota** (TTFinal das etapas 2 e 3) — para as viagens;
- etapa que o caminho não tem (ex.: não passa por SOC2) **vale 0**.

Saídas: BWT por caminho (`bwt_caminhos`), resumo por grupo × pacotes (`bwt_resumo` = aba raw_bwt) e até o 1º SOC (`bwt_1o_soc` = raw_data_1st_SOC).

## Como sabemos que está certo
Toda parte nova é comparada com o processo atual, **com os mesmos dados**, coluna por coluna (`python -m malha comparar`). Só avança quando dá igual.

| Parte | Resultado |
|---|---|
| Malha (etapa 1) | 8 de 8 caminhos iguais, 22 colunas |
| Rotas (etapa 2) | 12 de 12 rotas iguais, 23 colunas |
| Ajuste de expressas (etapa 3) | 12 de 12 rotas iguais, 23 colunas |
| BWT (etapa 4) | iguais nos dados de exemplo **e** em ~5.900 caminhos sorteados com todos os casos (aeroporto, cross-dock, FBS, XPT, sem HUB, 4 SOCs) |
| Volume | 100 mil caminhos, etapas 1 a 4, em ~14 segundos |

## Dados reais
1. Coloque em `dados_reais/`: `Inputs Rodagem.xlsx`, `0.0 Distances Available.csv`, `demanda_bwt.csv`, `station_names.csv`.
2. `python teste_local/preparar_dados_reais.py` → monta `dados_reais/pronto/`.
3. `python -m malha comparar --dados dados_reais/pronto`.

`dados_reais/` não vai para o GitHub (dados da empresa).

## Acompanhar o mês (toda semana)
As duas consultas pegam sozinhas **o mês atual até ontem**. Não precisa mudar data.
1. No Data Studio (Presto), rode `consultas/lh_real_por_rota.sql` e salve o CSV (todos os resultados) como `dados_reais/lh_real_mes_atual.csv`.
2. Rode `consultas/by_step_realizado.sql` e salve como `dados_reais/by_step_mes_atual.csv`.
3. Dois cliques no `RODAR.bat`. Ele junta o mês atual no histórico (`lh_real_por_rota.csv` e `by_step_realizado.csv`) e gera o Excel.

No Excel: **Ponte do BWT** (mês em andamento × meta, até o último dia com dado), **Onde atacar** e **Regra x Real**.
