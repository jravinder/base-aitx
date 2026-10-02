-- UPPER BOUND. Perfect-foresight DAM arbitrage value of one Base battery per local day and zone,
-- at a 0% and a 30% reserve floor, with the day's peak price.
select load_zone, local_date,
       sum(cash_usd) filter (where reserve_floor_pct = 30) as value_usd_floor30,
       sum(cash_usd) filter (where reserve_floor_pct = 0)  as value_usd_floor0,
       max(price_usd_mwh)                                   as peak_price_usd_mwh,
       count(*) filter (where reserve_floor_pct = 30)       as hours
from {{ ref('int_market__battery_dispatch') }}
where reserve_floor_pct in (0, 30)
group by all
order by load_zone, local_date
