-- SIMULATION. SOC distribution across the fleet per local day (device-day means), and devices that
-- spent any hour under their reserve floor.
with dev_day as (
    select utc_to_chicago(minute_utc)::date as local_date, device_id,
           avg(soc_pct) as soc_pct, min(soc_pct) as soc_min,
           any_value(reserve_floor_pct) as floor_pct, bool_or(not grid_ok) as had_outage
    from {{ ref('int_fleet__telemetry_minute') }}
    group by all
)
select local_date,
       count(*)                                               as devices,
       quantile_cont(soc_pct, 0.10)                           as soc_p10,
       quantile_cont(soc_pct, 0.50)                           as soc_p50,
       quantile_cont(soc_pct, 0.90)                           as soc_p90,
       count(*) filter (where soc_min < floor_pct - 0.5)      as devices_below_reserve,
       count(*) filter (where had_outage)                     as devices_with_outage
from dev_day
group by all
order by local_date
