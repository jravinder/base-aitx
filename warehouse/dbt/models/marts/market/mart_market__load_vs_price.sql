-- Measured. Do the highest-load hours and the highest-price hours line up? Per calendar year of
-- overlapping data: the 100 highest ERCOT-load hours vs the 100 highest LZ_AEN DAM-price hours,
-- by local hour of day, plus their overlap and the hourly correlation.
with h as (
    select *, extract(year from local_date)::integer as yr
    from {{ ref('int_market__zone_hourly') }}
    where load_ercot_mw is not null and aen is not null
), r as (
    select *, row_number() over (partition by yr order by load_ercot_mw desc) as load_rank,
              row_number() over (partition by yr order by aen desc)           as price_rank
    from h
), by_hour as (
    select yr, hour_of_day,
           count(*) filter (where load_rank <= 100)  as top_load_hours,
           count(*) filter (where price_rank <= 100) as top_price_hours
    from r group by all
), summary as (
    select yr,
           count(*)                                                 as hours,
           min(local_date)                                          as first_day,
           max(local_date)                                          as last_day,
           count(*) filter (where load_rank <= 100 and price_rank <= 100) as overlap_top100,
           corr(load_ercot_mw, aen)                                 as corr_load_price,
           max(load_ercot_mw)                                       as peak_load_mw,
           count(distinct month(local_date)) filter (where load_rank <= 100)  as top_load_months,
           count(distinct month(local_date)) filter (where price_rank <= 100) as top_price_months
    from r group by all
)
select b.*, s.hours, s.first_day, s.last_day, s.overlap_top100, s.corr_load_price, s.peak_load_mw, s.top_load_months, s.top_price_months
from by_hour b join summary s using (yr)
order by yr, hour_of_day
