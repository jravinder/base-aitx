{#- DuckDB SQL macros used by the staging models. dbt runs this on-run-start; warehouse/runner.py
    executes the same body before the first model. -#}
{% macro duckdb_macros() %}
-- ERCOT publishes local (America/Chicago) hour-ending labels. On the fall-back day the 01:00-02:00
-- hour happens twice; the second one carries Repeated Hour Flag = Y (CST). DuckDB/ICU resolves an
-- ambiguous local time to the later (CST) instant, so a first-occurrence (CDT) interval is moved back
-- one hour. Spring-forward days simply have no HE03 rows.
create or replace macro chicago_to_utc(ts_local, repeated) as
  timezone('UTC', timezone('America/Chicago', ts_local))
  - case when not repeated
          and timezone('UTC', timezone('America/Chicago', ts_local))
            - timezone('UTC', timezone('America/Chicago', ts_local - interval 1 hour)) = interval 2 hour
         then interval 1 hour else interval 0 hour end;
create or replace macro utc_to_chicago(ts_utc) as
  timezone('America/Chicago', timezone('UTC', ts_utc))::timestamp;
{% endmacro %}
