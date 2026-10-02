-- SIMULATION. Every RT 15-minute interval in the fleet window, per zone: the real ERCOT price and
-- how much of the zone's fleet could answer it (online, grid up, SOC above the member's floor).
with q as (
    select time_bucket(interval 15 minute, minute_utc) as interval_start_utc, load_zone, device_id,
           avg(soc_pct) as soc_pct, any_value(reserve_floor_pct) as floor_pct,
           bool_and(online) as online, bool_and(grid_ok) as grid_ok, avg(kw) as kw
    from {{ ref('int_fleet__telemetry_minute') }}
    group by all
), z as (
    select interval_start_utc, load_zone,
           count(*)                                                                         as reporting,
           count(*) filter (where online and grid_ok and soc_pct > floor_pct + 1)            as available,
           sum(case when online and grid_ok then greatest(soc_pct - floor_pct, 0) / 100.0 * 39.2 else 0 end) as kwh_above_reserve,
           sum(greatest(kw, 0))                                                             as kw_discharging
    from q group by all
), fleet as (
    select load_zone, count(*) as devices from {{ ref('stg_fleet__devices') }} group by all
), p as (
    select interval_start_utc, settlement_point as load_zone, price_usd_mwh
    from {{ ref('stg_ercot__rtm_spp') }}
    where settlement_point_type = 'LZ'
      and interval_start_utc between (select min(minute_utc) from {{ ref('int_fleet__telemetry_minute') }})
                                 and (select max(minute_utc) from {{ ref('int_fleet__telemetry_minute') }})
)
select p.interval_start_utc, p.load_zone, p.price_usd_mwh, p.price_usd_mwh >= 250 as is_spike,
       fleet.devices, coalesce(z.reporting, 0) as reporting, coalesce(z.available, 0) as available,
       coalesce(z.kwh_above_reserve, 0) as kwh_above_reserve, coalesce(z.kw_discharging, 0) as kw_discharging,
       coalesce(z.available, 0) / fleet.devices::double as available_share
from p join fleet using (load_zone)
left join z using (interval_start_utc, load_zone)
order by p.interval_start_utc, p.load_zone
