-- Realizado do By Step do MÊS ATUAL (do dia 1 até o último dia calculado), para comparar com a meta na Rodagem de Malha.
-- Rodar no Data Studio (https://datasuite.shopee.io/studio), motor Presto. Não precisa mudar nada.
-- Depois: baixar o resultado em CSV (todos os resultados) e salvar como  dados_reais\by_step_mes_atual.csv
--     (o RODAR.bat junta esse mês no histórico dados_reais\by_step_realizado.csv)
-- A coluna ultimo_dia diz até que dia a tabela está calculada (aparece na aba Ponte do BWT).

select date_trunc('month', attempt_date) as attempt_month, spx_channel, main_route, kpi,
       sum(bwt_n) as bwt_n, sum(bwt_d) as bwt_d,
       max(attempt_date) as ultimo_dia
from dev_brbi_opslgc.joao_bwt_by_step_mece
where spx_channel in ('SPX D2D', 'SPX Fulfillment')
  and attempt_date >= date_trunc('month', current_date - interval '1' day)
group by 1, 2, 3, 4
