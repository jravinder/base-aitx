-- Measured. DAM price by local day x local hour of day for the three zones. On the 25-hour fall-back
-- day the two 01:00 hours are averaged; on the 23-hour spring day hour 2 is absent.
select local_date, hour_of_day,
       avg(aen) as aen, avg(north) as north, avg(houston) as houston,
       avg(load_ercot_mw) as load_ercot_mw
from {{ ref('int_market__zone_hourly') }}
group by all
order by local_date, hour_of_day
