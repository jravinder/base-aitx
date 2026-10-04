-- How concentrated is a battery's value? Hours ranked by DAM price within zone and period; the share
-- of the period's arbitrage value (UPPER BOUND, 30% reserve floor) earned in the top 1% / 5% / 10%.
with v as (
    select h.*, p.period
    from {{ ref('int_market__hourly_value') }} h
    join {{ ref('int_market__periods') }} p on h.local_date between p.start_date and p.end_date
    where h.reserve_floor_pct = 30
), r as (
    select *, row_number() over (partition by load_zone, period order by price_usd_mwh desc, interval_start_utc) as rk,
              count(*) over (partition by load_zone, period) as n
    from v
)
select
    load_zone, period,
    any_value(n)                                                        as hours,
    sum(value_usd)                                                      as value_usd,
    sum(value_usd) filter (where rk <= ceil(n * 0.01)) / sum(value_usd) as top1pct_share,
    sum(value_usd) filter (where rk <= ceil(n * 0.05)) / sum(value_usd) as top5pct_share,
    sum(value_usd) filter (where rk <= ceil(n * 0.10)) / sum(value_usd) as top10pct_share,
    count(*) filter (where discharge_kw > 0.01)                         as hours_discharging,
    max(price_usd_mwh)                                                  as max_price,
    quantile_cont(price_usd_mwh, 0.5)                                   as median_price,
    count(*) filter (where price_usd_mwh >= 200)                        as hours_ge_200,
    count(*) filter (where price_usd_mwh >= 1000)                       as hours_ge_1000,
    count(*) filter (where price_usd_mwh < 0)                           as hours_negative
from r
group by all
order by period, load_zone
