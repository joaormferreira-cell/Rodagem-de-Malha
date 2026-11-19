-- Tempo REAL de estrada por rota, para a aba "Rotas meta x real" da Rodagem de Malha.
-- Rodar no Data Studio (https://datasuite.shopee.io/studio), motor Presto.
-- Pega sozinha o MÊS ATUAL, do dia 1 até ontem (linha "PERÍODO"). Não precisa mudar nada.
--     Para outro período, troque a linha PERÍODO por datas fixas, ex.: between date '2026-10-01' and date '2026-10-31'
-- Depois: baixar o resultado em CSV (todos os resultados) e salvar como  dados_reais\lh_real_mes_atual.csv
--     (o RODAR.bat junta esse mês no histórico dados_reais\lh_real_por_rota.csv)
--
-- Regra igual à do By Step:
--   começa quando o pacote SAI da estação anterior;
--   termina quando é RECEBIDO no SOC/FMH (inclui fila) ou quando CHEGA no HUB/XPT.
-- Quebra do tempo: estrada = saiu → chegou;  fila = chegou → recebido (só quando o destino é SOC/FMH).
-- grass_date = dia da 1ª tentativa de entrega (mesmo critério do mês da By Step).

with est as (
  select cast(station_id as varchar) as id, max(station_code) as codigo
  from dev_brbi_opslgc.joao_malha_station_names
  group by 1
),
trechos as (
  select shipment_id, station_sequence,
         max(cast(date_trunc('month', grass_date) as varchar)) as mes,
         max(cast(previous_station_id as varchar)) as id_a,
         max(cast(actual_station_id as varchar)) as id_b,
         max(try_cast(actual_station_type as integer)) as tipo_b,
         min(try_cast(previous_transporting_datetime as timestamp)) as saiu_a,
         min(try_cast(previous_lharrived_datetime as timestamp)) as chegou_b,
         min(try_cast(received_datetime as timestamp)) as recebido_b
  from brbi_opslgc.da_log_spx_leadtime_all_miles_by_shipment_daily
  where grass_date between date_trunc('month', current_date - interval '1' day)
                       and current_date - interval '1' day   -- PERÍODO: mês atual até ontem
    and previous_station_id is not null
  group by 1, 2
),
horas as (
  select id_a, id_b, mes,
         date_diff('second', saiu_a,
                   case when tipo_b in (3, 12, 20) then chegou_b else recebido_b end) / 3600.0 as h,
         date_diff('second', saiu_a, chegou_b) / 3600.0 as h_estrada,
         case when tipo_b not in (3, 12, 20) then date_diff('second', chegou_b, recebido_b) / 3600.0 end as h_fila
  from trechos
  where id_a <> id_b
)
select ea.codigo || '>' || eb.codigo as rota,
       mes,
       count(*) as pacotes,
       round(avg(h), 2) as horas_media,
       round(approx_percentile(h, 0.5), 2) as horas_mediana,
       round(avg(case when h_estrada between 0 and 240 then h_estrada end), 2) as estrada_media,
       round(avg(case when h_fila between 0 and 240 then h_fila end), 2) as fila_media
from horas
join est ea on ea.id = horas.id_a
join est eb on eb.id = horas.id_b
where h > 0 and h <= 240
group by 1, 2
having count(*) >= 30
order by pacotes desc
