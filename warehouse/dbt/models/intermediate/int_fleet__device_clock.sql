-- Device clock offset = the device's median (received - stamped) lag minus the fleet's median lag.
-- More than 30 s off is skew (device medians sit within ~0.1 s of the fleet otherwise); that device's timestamps are shifted by the offset downstream.
with per_device as (
    select device_id, median(lag_s) as median_lag_s, count(*) as readings
    from {{ ref('stg_fleet__telemetry') }}
    group by device_id
), fleet as (
    select median(median_lag_s) as fleet_lag_s from per_device
)
select
    device_id,
    readings,
    median_lag_s,
    median_lag_s - fleet_lag_s               as clock_offset_s,
    abs(median_lag_s - fleet_lag_s) > 30     as is_skewed
from per_device, fleet
