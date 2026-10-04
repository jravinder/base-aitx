-- The earlier CSV (grid/ercot_archive.py), long form, only to reconcile against stg_ercot__dam_spp.
with src as (select * from {{ source('ercot', 'dam_legacy_csv') }}),
long as (unpivot src on aen, north, houston into name zone value price)
select
    'LZ_' || upper(zone)        as settlement_point,
    cast("date" as date)        as local_date,
    cast(he as integer)         as hour_ending,
    cast(price as double)       as price_usd_mwh
from long
