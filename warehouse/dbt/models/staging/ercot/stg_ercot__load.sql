-- ERCOT native load, hourly, one row per weather zone. The repeated fall-back hour is the row whose
-- label ends in ' DST' (it follows the first 02:00 row, so it is the second, CST, occurrence).
with src as (
    select * from {{ source('ercot', 'native_load') }}
), typed as (
    select
        strptime(split_part(datetime, ' ', 1), '%m/%d/%Y')::date                  as local_date,
        cast(split_part(split_part(datetime, ' ', 2), ':', 1) as integer)         as hour_ending,
        datetime like '% DST'                                                      as is_repeated_hour,
        cast(SCENT as double) as scent, cast(NCENT as double) as ncent,
        cast(COAST as double) as coast, cast(ERCOT as double) as ercot
    from src
), long as (
    unpivot typed on scent, ncent, coast, ercot into name weather_zone value load_mw
)
select
    upper(weather_zone)                                                           as weather_zone,
    chicago_to_utc(local_date + to_hours(hour_ending - 1), is_repeated_hour)     as interval_start_utc,
    local_date + to_hours(hour_ending - 1)                                       as interval_start_local,
    local_date,
    hour_ending,
    hour_ending - 1 as hour_of_day,
    is_repeated_hour,
    load_mw
from long
