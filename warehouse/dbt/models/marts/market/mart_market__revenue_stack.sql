-- UPPER BOUND. Energy + ancillary services co-optimised (capacity payments only) by zone, period and
-- reserve floor, next to energy-only arbitrage at the same floor.
with s as (
    select r.load_zone, p.period, r.reserve_floor_pct, r.service, sum(r.usd) as usd, sum(r.mw_h) as mw_h
    from {{ ref('int_market__revenue_stack') }} r
    join {{ ref('int_market__periods') }} p on r.local_date between p.start_date and p.end_date
    group by all
), e as (
    select load_zone, period, reserve_floor_pct, value_usd as energy_only_usd
    from {{ ref('mart_market__reserve_cost') }}
)
select s.*, sum(s.usd) over (partition by s.load_zone, s.period, s.reserve_floor_pct) as stack_total_usd, e.energy_only_usd
from s join e using (load_zone, period, reserve_floor_pct)
order by load_zone, period, reserve_floor_pct, service
