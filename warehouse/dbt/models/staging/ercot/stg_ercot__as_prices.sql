-- DAM ancillary service clearing prices (MCPC), unpivoted to one row per service per hour. $/MW per hour.
with src as (
    select
        strptime(delivery_date, '%m/%d/%Y')::date          as local_date,
        cast(split_part(hour_ending, ':', 1) as integer)   as hour_ending,
        repeated_hour_flag = 'Y'                           as is_repeated_hour,
        regup, regdn, rrs, ecrs, nspin,
        _source_file
    from {{ source('ercot', 'as_mcpc') }}
), long as (
    unpivot src on regup, regdn, rrs, ecrs, nspin into name service value price_usd_mw_h
)
select
    service,
    chicago_to_utc(local_date + to_hours(hour_ending - 1), is_repeated_hour) as interval_start_utc,
    local_date + to_hours(hour_ending - 1)                                   as interval_start_local,
    local_date,
    hour_ending,
    hour_ending - 1 as hour_of_day,
    is_repeated_hour,
    price_usd_mw_h,
    _source_file
from long
