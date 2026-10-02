-- Lorenz-style curve: cumulative share of arbitrage value (UPPER BOUND, 30% floor) vs share of hours,
-- hours sorted by price, high to low.
with v as (
    select h.*, p.period
    from {{ ref('int_market__hourly_value') }} h
    join {{ ref('int_market__periods') }} p on h.local_date between p.start_date and p.end_date
    where h.reserve_floor_pct = 30
), r as (
    select load_zone, period,
           row_number() over w as rk,
           count(*) over (partition by load_zone, period) as n,
           sum(value_usd) over w / sum(value_usd) over (partition by load_zone, period) as cum_share
    from v
    window w as (partition by load_zone, period order by price_usd_mwh desc, interval_start_utc
                 rows between unbounded preceding and current row)
), pts as (
    select unnest([0.001, 0.002, 0.005, 0.01, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]) as share_of_hours
)
select load_zone, period, share_of_hours, cum_share as share_of_value
from r join pts on r.rk = greatest(1, ceil(r.n * pts.share_of_hours))
order by load_zone, period, share_of_hours
