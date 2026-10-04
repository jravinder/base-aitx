{{ config(materialized='view') }}
-- SIMULATION. Typed and renamed 1-minute telemetry, as delivered (duplicates and skew still present;
-- int_fleet__telemetry_minute corrects them). A view: 43M rows are read straight from Parquet.
select
    device_id,
    ts                                                   as device_ts_utc,
    received_at                                          as received_at_utc,
    date_diff('millisecond', ts, received_at) / 1000.0   as lag_s,
    soc_pct::double                                      as soc_pct,
    kw::double                                           as kw,
    temp_c::double                                       as temp_c,
    online,
    grid_ok,
    cast("day" as date)                                  as partition_day
from {{ source('fleet', 'telemetry') }}
