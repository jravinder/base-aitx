-- UPPER BOUND. The cost of the backup reserve: annual arbitrage value at each reserve floor (0-50%)
-- and what it gives up against a 0% floor.
with v as (
    select d.load_zone, p.period, d.reserve_floor_pct, sum(d.cash_usd) as value_usd, count(distinct d.local_date) as days
    from {{ ref('int_market__battery_dispatch') }} d
    join {{ ref('int_market__periods') }} p on d.local_date between p.start_date and p.end_date
    group by all
)
select v.*,
       first(value_usd) over w                      as value_usd_floor0,
       first(value_usd) over w - value_usd          as reserve_cost_usd,
       1 - value_usd / first(value_usd) over w      as reserve_cost_share,
       39.2 * reserve_floor_pct / 100.0             as reserve_kwh
from v
window w as (partition by load_zone, period order by reserve_floor_pct)
order by load_zone, period, reserve_floor_pct
