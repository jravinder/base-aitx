-- DAM settlement point prices, one row per settlement point per delivery hour, typed, UTC + local.
-- Hour ending (HE01..HE24, local) becomes interval_start_local = date + (HE - 1) h.
with src as (
    select * from {{ source('ercot', 'dam_spp') }}
), typed as (
    select
        settlement_point,
        strptime(delivery_date, '%m/%d/%Y')::date              as local_date,
        cast(split_part(hour_ending, ':', 1) as integer)       as hour_ending,
        repeated_hour_flag = 'Y'                               as is_repeated_hour,
        settlement_point_price                                 as price_usd_mwh,
        _source_file
    from src
)
select
    settlement_point,
    case when settlement_point like 'LZ\_%' escape '\' then 'load_zone' else 'hub' end as point_type,
    chicago_to_utc(local_date + to_hours(hour_ending - 1), is_repeated_hour)            as interval_start_utc,
    local_date + to_hours(hour_ending - 1)                                              as interval_start_local,
    local_date,
    hour_ending,
    hour_ending - 1                                                                     as hour_of_day,
    is_repeated_hour,
    price_usd_mwh,
    _source_file
from typed
