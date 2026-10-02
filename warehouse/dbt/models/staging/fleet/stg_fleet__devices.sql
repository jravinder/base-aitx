-- SIMULATION. One row per Base battery (warehouse/fleet_sim.py).
select device_id, serial, load_zone, reserve_floor_pct, capacity_kwh, power_kw, installed_on
from {{ source('fleet', 'devices') }}
