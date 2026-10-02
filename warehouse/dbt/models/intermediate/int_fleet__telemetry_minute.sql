-- One row per device per minute: clock-corrected, deduplicated (first delivery wins), values outside
-- physical ranges set to null and flagged. SOC 0-100 %, temperature -30..80 C, power |kW| <= 15.
with t as (
    select
        t.*,
        d.load_zone,
        d.reserve_floor_pct,
        c.is_skewed,
        date_trunc('minute',
            t.device_ts_utc
            + case when c.is_skewed then to_milliseconds(cast(round(c.clock_offset_s * 1000) as bigint)) else interval 0 second end
            + interval 30 second)                          as minute_utc
    from {{ ref('stg_fleet__telemetry') }} t
    join {{ ref('stg_fleet__devices') }} d using (device_id)
    join {{ ref('int_fleet__device_clock') }} c using (device_id)
)
select
    device_id,
    minute_utc,
    load_zone,
    reserve_floor_pct,
    case when soc_pct between 0 and 100 then soc_pct end   as soc_pct,
    case when temp_c between -30 and 80 then temp_c end    as temp_c,
    case when abs(kw) <= 15 then kw end                    as kw,
    not (soc_pct between 0 and 100)                        as soc_out_of_range,
    not (temp_c between -30 and 80)                        as temp_out_of_range,
    not (abs(kw) <= 15)                                    as kw_out_of_range,
    online,
    grid_ok,
    is_skewed                                              as clock_corrected,
    received_at_utc
from t
qualify row_number() over (partition by device_id, minute_utc order by received_at_utc) = 1
