-- Measured. Spike hours by zone, month and local hour of day. DAM counts hours; RTM counts 15-minute
-- intervals divided by 4, so both read as hours.
with dam as (
    select 'DAM' as market, settlement_point as load_zone, local_date, hour_of_day, price_usd_mwh, 1.0::double as hours
    from {{ ref('stg_ercot__dam_spp') }}
    where settlement_point in ('LZ_AEN', 'LZ_NORTH', 'LZ_HOUSTON')
), rtm as (
    select 'RTM', settlement_point, local_date, hour_of_day, price_usd_mwh, 0.25::double
    from {{ ref('stg_ercot__rtm_spp') }}
    where settlement_point_type = 'LZ' and settlement_point in ('LZ_AEN', 'LZ_NORTH', 'LZ_HOUSTON')
), u as (select * from dam union all select * from rtm)
select
    market, load_zone, strftime(local_date, '%Y-%m') as month, hour_of_day,
    sum(hours)                                          as hours,
    sum(hours) filter (where price_usd_mwh >= 100)      as hours_ge_100,
    sum(hours) filter (where price_usd_mwh >= 200)      as hours_ge_200,
    sum(hours) filter (where price_usd_mwh >= 500)      as hours_ge_500,
    sum(hours) filter (where price_usd_mwh >= 1000)     as hours_ge_1000,
    sum(hours) filter (where price_usd_mwh < 0)         as hours_negative
from u
group by all
order by market, load_zone, month, hour_of_day
