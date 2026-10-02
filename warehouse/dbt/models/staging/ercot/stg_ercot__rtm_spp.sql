-- RTM 15-minute settlement point prices. Load zones are published twice: type LZ (the zone price)
-- and LZEW (energy-weighted, used for settlement of some loads); both are kept, keyed by type.
with src as (
    select * from {{ source('ercot', 'rtm_spp') }}
), typed as (
    select
        settlement_point_name                                   as settlement_point,
        settlement_point_type,
        strptime(delivery_date, '%m/%d/%Y')::date               as local_date,
        delivery_hour::integer                                  as hour_ending,
        delivery_interval::integer                              as interval_in_hour,
        repeated_hour_flag = 'Y'                                as is_repeated_hour,
        settlement_point_price                                  as price_usd_mwh,
        _source_file
    from src
)
select
    settlement_point,
    settlement_point_type,
    chicago_to_utc(local_date + to_hours(hour_ending - 1) + to_minutes((interval_in_hour - 1) * 15), is_repeated_hour) as interval_start_utc,
    local_date + to_hours(hour_ending - 1) + to_minutes((interval_in_hour - 1) * 15)                                    as interval_start_local,
    local_date,
    hour_ending,
    interval_in_hour,
    hour_ending - 1 as hour_of_day,
    is_repeated_hour,
    price_usd_mwh,
    _source_file
from typed
