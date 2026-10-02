-- SIMULATION. One row per device: coverage, longest gap, last report, clock offset, out-of-range
-- readings, and the longest stuck run of temperature and of SOC-while-moving-power.
with m as (
    select device_id, minute_utc, temp_c, soc_pct, kw, soc_out_of_range, temp_out_of_range, kw_out_of_range
    from {{ ref('int_fleet__telemetry_minute') }}
), flags as (
    select *,
        temp_c is not distinct from lag(temp_c) over w   as same_temp,
        soc_pct is not distinct from lag(soc_pct) over w as same_soc,
        date_diff('minute', lag(minute_utc) over w, minute_utc) as gap_min
    from m
    window w as (partition by device_id order by minute_utc)
), runs as (
    select *,
        sum(case when same_temp then 0 else 1 end) over w as t_run,
        sum(case when same_soc then 0 else 1 end) over w  as s_run
    from flags
    window w as (partition by device_id order by minute_utc rows unbounded preceding)
), t_stuck as (
    select device_id, max(n) as longest_same_temp_min from (
        select device_id, t_run, count(*) as n from runs where temp_c is not null group by all) group by all
), s_stuck as (
    select device_id, max(n) as longest_same_soc_moving_min from (
        select device_id, s_run, count(*) as n from runs
        where soc_pct is not null group by all having count(*) filter (where abs(kw) > 1) >= 30) group by all
), win as (
    select min(minute_utc) as first_min, max(minute_utc) as last_min from m
), agg as (
    select device_id,
           count(*)                                     as minutes_reported,
           max(minute_utc)                              as last_seen_utc,
           coalesce(max(gap_min), 0)                    as longest_gap_min,
           count(*) filter (where soc_out_of_range)     as soc_out_of_range,
           count(*) filter (where temp_out_of_range)    as temp_out_of_range,
           count(*) filter (where kw_out_of_range)      as kw_out_of_range
    from runs group by all
)
select
    d.device_id, d.serial, d.load_zone, d.reserve_floor_pct,
    coalesce(a.minutes_reported, 0)                                         as minutes_reported,
    date_diff('minute', win.first_min, win.last_min) + 1                    as minutes_expected,
    1 - coalesce(a.minutes_reported, 0) / (date_diff('minute', win.first_min, win.last_min) + 1)::double as missing_share,
    a.longest_gap_min,
    a.last_seen_utc,
    date_diff('minute', a.last_seen_utc, win.last_min)                      as minutes_since_last_seen,
    c.clock_offset_s,
    c.is_skewed,
    a.soc_out_of_range, a.temp_out_of_range, a.kw_out_of_range,
    coalesce(t.longest_same_temp_min, 0)                                    as longest_same_temp_min,
    coalesce(s.longest_same_soc_moving_min, 0)                              as longest_same_soc_moving_min
from {{ ref('stg_fleet__devices') }} d
cross join win
left join agg a using (device_id)
left join {{ ref('int_fleet__device_clock') }} c using (device_id)
left join t_stuck t using (device_id)
left join s_stuck s using (device_id)
order by d.device_id
