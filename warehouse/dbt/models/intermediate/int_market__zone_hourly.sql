-- One row per delivery hour: DAM price for the three load zones Base cares about, the weather-zone
-- load that matches each (Austin ~ SCENT, Dallas ~ NCENT, Houston ~ COAST), ERCOT total load, and
-- the five DAM ancillary service prices.
with dam as (
    select interval_start_utc,
           any_value(interval_start_local) as interval_start_local, any_value(local_date) as local_date,
           any_value(hour_ending) as hour_ending, any_value(hour_of_day) as hour_of_day,
           any_value(is_repeated_hour) as is_repeated_hour,
           max(price_usd_mwh) filter (where settlement_point = 'LZ_AEN')     as aen,
           max(price_usd_mwh) filter (where settlement_point = 'LZ_NORTH')   as north,
           max(price_usd_mwh) filter (where settlement_point = 'LZ_HOUSTON') as houston
    from {{ ref('stg_ercot__dam_spp') }}
    group by interval_start_utc
), ld as (
    select interval_start_utc,
           max(load_mw) filter (where weather_zone = 'SCENT') as load_scent_mw,
           max(load_mw) filter (where weather_zone = 'NCENT') as load_ncent_mw,
           max(load_mw) filter (where weather_zone = 'COAST') as load_coast_mw,
           max(load_mw) filter (where weather_zone = 'ERCOT') as load_ercot_mw
    from {{ ref('stg_ercot__load') }}
    group by interval_start_utc
), asp as (
    select interval_start_utc,
           max(price_usd_mw_h) filter (where service = 'regup') as regup,
           max(price_usd_mw_h) filter (where service = 'regdn') as regdn,
           max(price_usd_mw_h) filter (where service = 'rrs')   as rrs,
           max(price_usd_mw_h) filter (where service = 'ecrs')  as ecrs,
           max(price_usd_mw_h) filter (where service = 'nspin') as nspin
    from {{ ref('stg_ercot__as_prices') }}
    group by interval_start_utc
)
select dam.*, ld.load_scent_mw, ld.load_ncent_mw, ld.load_coast_mw, ld.load_ercot_mw,
       asp.regup, asp.regdn, asp.rrs, asp.ecrs, asp.nspin
from dam
left join ld using (interval_start_utc)
left join asp using (interval_start_utc)
order by interval_start_utc
