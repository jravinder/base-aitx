-- UPPER BOUND. Battery arbitrage value by month and zone (perfect foresight, DAM, 30% floor), with
-- the RTM 15-minute equivalent for comparison.
with da as (
    select load_zone, strftime(local_date, '%Y-%m') as month, count(*) as days,
           sum(value_usd_floor30) as dam_value_usd, max(value_usd_floor30) as best_day_usd
    from {{ ref('mart_market__battery_value_daily') }} group by all
), rt as (
    select load_zone, strftime(local_date, '%Y-%m') as month, sum(cash_usd) as rtm_value_usd
    from {{ ref('int_market__battery_dispatch_rt') }} where reserve_floor_pct = 30 group by all
)
select da.*, rt.rtm_value_usd
from da left join rt using (load_zone, month)
order by load_zone, month
