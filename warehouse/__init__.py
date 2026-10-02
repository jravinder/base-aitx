"""ERCOT market + Base fleet telemetry warehouse (DuckDB). Entry point: python3 -m warehouse.build"""
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WH = os.path.join(ROOT, "data", "warehouse")          # generated, gitignored
RAW = os.path.join(WH, "raw")
DB = os.path.join(WH, "base.duckdb")
ZIPS = os.path.join(ROOT, "data", "ercot", "raw")      # ERCOT public archive zips, as downloaded
DBT = os.path.join(os.path.dirname(__file__), "dbt")
