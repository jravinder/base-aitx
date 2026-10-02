"""A small dbt-compatible runner, so the warehouse builds with only duckdb + pyarrow installed.

It reads the dbt project in warehouse/dbt as-is: sources.yml (external locations), the SQL and
Python models (ref/source/config are the only Jinja used), the on-run-start DuckDB macros, and the
schema tests in schema.yml (not_null, unique, accepted_values, relationships, accepted_range,
unique_combination). `dbt build` on the same directory gives the same tables and runs the same tests.
"""
import glob
import importlib.util
import os
import re
import time
from graphlib import TopologicalSorter

import yaml

from . import DBT

REF = re.compile(r"\{\{\s*ref\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
SRC = re.compile(r"\{\{\s*source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}")
CFG = re.compile(r"\{\{\s*config\((.*?)\)\s*\}\}", re.S)
PYREF = re.compile(r"dbt\.ref\(\s*['\"](\w+)['\"]\s*\)")


def layer(path):
    for k in ("staging", "intermediate", "marts"):
        if f"/{k}/" in path:
            return k
    return "other"


class Project:
    def __init__(self, root=DBT):
        self.root = root
        self.sources = {}
        self.source_meta = {}
        for f in glob.glob(os.path.join(root, "models", "**", "*.yml"), recursive=True):
            y = yaml.safe_load(open(f)) or {}
            for s in y.get("sources", []):
                for t in s.get("tables", []):
                    self.sources[(s["name"], t["name"])] = t["meta"]["external_location"]
                    self.source_meta[(s["name"], t["name"])] = {
                        "loaded_at_field": t.get("loaded_at_field"),
                        "freshness": t["freshness"] if "freshness" in t else s.get("freshness")}
        self.models = {}
        for f in sorted(glob.glob(os.path.join(root, "models", "**", "*.sql"), recursive=True)
                        + glob.glob(os.path.join(root, "models", "**", "*.py"), recursive=True)):
            name = os.path.splitext(os.path.basename(f))[0]
            text = open(f).read()
            kind = "python" if f.endswith(".py") else "sql"
            refs = set((PYREF if kind == "python" else REF).findall(text))
            srcs = set(SRC.findall(text)) if kind == "sql" else set()
            mat = "table"
            m = CFG.search(text) if kind == "sql" else None
            if m and "view" in m.group(1):
                mat = "view"
            self.models[name] = {"path": f, "kind": kind, "text": text, "refs": refs, "sources": srcs,
                                 "materialized": mat, "layer": layer(f)}
        self.tests = self._tests()
        proj = yaml.safe_load(open(os.path.join(root, "dbt_project.yml")))
        self.on_run_start = proj.get("on-run-start", [])

    def order(self):
        return list(TopologicalSorter({n: m["refs"] for n, m in self.models.items()}).static_order())

    def render(self, name):
        sql = self.models[name]["text"]
        sql = CFG.sub("", sql)
        sql = REF.sub(lambda m: m.group(1), sql)
        return SRC.sub(lambda m: self.sources[(m.group(1), m.group(2))], sql)

    def macros(self):
        body = open(os.path.join(self.root, "macros", "duckdb_macros.sql")).read()
        return re.search(r"\{% macro duckdb_macros\(\) %\}(.*?)\{% endmacro %\}", body, re.S).group(1)

    def lineage(self):
        nodes = [{"id": f"source.{s}.{t}", "layer": "raw"} for s, t in self.sources]
        nodes += [{"id": n, "layer": m["layer"], "kind": m["kind"], "materialized": m["materialized"]}
                  for n, m in self.models.items()]
        edges = [[f"source.{s}.{t}", n] for n, m in self.models.items() for s, t in m["sources"]]
        edges += [[r, n] for n, m in self.models.items() for r in m["refs"]]
        return {"nodes": nodes, "edges": edges}

    # ---- schema tests ----
    def _tests(self):
        out = []
        for f in glob.glob(os.path.join(self.root, "models", "**", "schema.yml"), recursive=True):
            for mdl in (yaml.safe_load(open(f)) or {}).get("models", []):
                for t in mdl.get("data_tests", []):
                    out.append((mdl["name"], None, t))
                for col in mdl.get("columns", []):
                    for t in col.get("data_tests", []):
                        out.append((mdl["name"], col["name"], t))
        return out

    @staticmethod
    def test_sql(model, col, t):
        name, args = (t, {}) if isinstance(t, str) else next(iter(t.items()))
        args = (args or {}).get("arguments", args or {})
        if name == "not_null":
            return name, f"select * from {model} where {col} is null"
        if name == "unique":
            return name, f"select {col} from {model} where {col} is not null group by 1 having count(*) > 1"
        if name == "accepted_values":
            vals = ", ".join("'" + v + "'" for v in args["values"])
            return name, f"select * from {model} where {col} is not null and {col} not in ({vals})"
        if name == "relationships":
            to = re.sub(r"ref\(\s*['\"](\w+)['\"]\s*\)", r"\1", args["to"])
            return name, (f"select a.{col} from {model} a left join {to} b on a.{col} = b.{args['field']} "
                          f"where a.{col} is not null and b.{args['field']} is null")
        if name == "accepted_range":
            cond = []
            if args.get("min_value") is not None:
                cond.append(f"{col} < {args['min_value']}")
            if args.get("max_value") is not None:
                cond.append(f"{col} > {args['max_value']}")
            return name, f"select * from {model} where {col} is not null and ({' or '.join(cond)})"
        if name == "unique_combination":
            cols = ", ".join(args["combination_of_columns"])
            return name, f"select {cols}, count(*) n from {model} group by {cols} having count(*) > 1"
        raise ValueError(f"unknown test {name}")


class _Dbt:
    def __init__(self, con):
        self.con = con

    def ref(self, name):
        return self.con.table(name)

    def config(self, **kw):
        pass


def run_models(con, project, log=print):
    cwd = os.getcwd()
    os.chdir(project.root)              # source paths are relative to warehouse/dbt, as for dbt
    try:
        con.execute("set enable_progress_bar = false")
        con.execute(project.macros())
        stats = []
        for name in project.order():
            m = project.models[name]
            t = time.time()
            if m["kind"] == "sql":
                con.execute(f"create or replace {m['materialized']} {name} as (\n{project.render(name)}\n)")
            else:
                spec = importlib.util.spec_from_file_location(f"dbt_py_{name}", m["path"])
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                result = mod.model(_Dbt(con), con)
                con.register("__py_model_out", result)
                con.execute(f"create or replace table {name} as select * from __py_model_out")
                con.unregister("__py_model_out")
            rows = con.execute(f"select count(*) from {name}").fetchone()[0]
            s = {"model": name, "layer": m["layer"], "kind": m["kind"], "materialized": m["materialized"],
                 "rows": rows, "seconds": round(time.time() - t, 2)}
            stats.append(s)
            log(f"  {m['layer']:<12} {name:<40} {rows:>12,} rows {s['seconds']:>7.2f}s")
        return stats
    finally:
        os.chdir(cwd)


def run_tests(con, project):
    res = []
    cwd = os.getcwd()
    os.chdir(project.root)              # the telemetry view reads Parquet by a dbt-relative path
    try:
        for model, col, t in project.tests:
            name, sql = project.test_sql(model, col, t)
            failures = con.execute(f"select count(*) from ({sql})").fetchone()[0]
            res.append({"model": model, "column": col, "test": name, "failures": failures,
                        "status": "pass" if failures == 0 else "fail"})
    finally:
        os.chdir(cwd)
    return res
