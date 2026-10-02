-- SIMULATION. Fleet by hour: devices reporting/online/islanded, net fleet power (MW, + = export),
-- mean SOC, devices under their own reserve floor, energy held above the floors, LZ_AEN RT price.
with dev_hour as (
    select date_trunc('hour', minute_utc) as hour_utc, device_id,
           any_value(reserve_floor_pct) as floor_pct,
           avg(kw) as kw, avg(soc_pct) as soc_pct,
           bool_and(online) as online, bool_or(not grid_ok) as grid_down
    from {{ ref('int_fleet__telemetry_minute') }}
    group by all
), rt as (
    select date_trunc('hour', interval_start_utc) as hour_utc, avg(price_usd_mwh) as rt_price_aen
    from {{ ref('stg_ercot__rtm_spp') }}
    where settlement_point = 'LZ_AEN' and settlement_point_type = 'LZ'
    group by all
)
select
    d.hour_utc,
    utc_to_chicago(d.hour_utc)                                                  as hour_local,
    count(*)                                                                    as devices_reporting,
    count(*) filter (where online)                                              as devices_online,
    count(*) filter (where grid_down)                                           as devices_grid_down,
    sum(kw) / 1000.0                                                            as fleet_mw,
    avg(soc_pct)                                                                as soc_mean_pct,
    count(*) filter (where soc_pct < floor_pct - 0.5)                           as devices_below_reserve,
    count(*) filter (where soc_pct < floor_pct - 0.5 and not grid_down)         as devices_below_reserve_grid_up,
    sum(greatest(soc_pct - floor_pct, 0) / 100.0 * 39.2)                        as kwh_above_reserve,
    any_value(rt.rt_price_aen)                                                  as rt_price_aen
from dev_hour d left join rt using (hour_utc)
group by d.hour_utc
order by d.hour_utc
