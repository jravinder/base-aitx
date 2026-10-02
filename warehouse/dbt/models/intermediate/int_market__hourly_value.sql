-- Each hour's share of the battery's arbitrage value (perfect-foresight dispatch, so an UPPER BOUND).
-- A day's value is attributed to its discharge hours: discharge kW x (price - the day's charging cost
-- per kWh discharged). The hours of a day sum exactly to that day's cash.
with d as (
    select * from {{ ref('int_market__battery_dispatch') }}
), day_cost as (
    select load_zone, reserve_floor_pct, local_date,
           sum(charge_kw * price_usd_mwh) / nullif(sum(discharge_kw), 0) as charge_cost_per_kw_out
    from d group by all
)
select
    d.load_zone, d.reserve_floor_pct, d.interval_start_utc, d.local_date, d.price_usd_mwh,
    d.charge_kw, d.discharge_kw, d.cash_usd,
    coalesce(d.discharge_kw * (d.price_usd_mwh - c.charge_cost_per_kw_out) / 1000.0, 0) as value_usd
from d join day_cost c using (load_zone, reserve_floor_pct, local_date)
