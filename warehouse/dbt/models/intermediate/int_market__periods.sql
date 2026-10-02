-- Reporting periods, anchored on the last full DAM day in the warehouse.
with last as (select max(local_date) as d from {{ ref('int_market__zone_hourly') }})
select '2025' as period, date '2025-01-01' as start_date, date '2025-12-31' as end_date from last
union all select '2026 YTD', date '2026-01-01', d from last
union all select 'last 365 days', d - 364, d from last
