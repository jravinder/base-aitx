"""Austin Auxiliary Power permit market view (issue #54, track 1).

Aggregate SoQL ($group) queries only, via the _get helper in house/permits.py.
Writes data/market.json for web/market.html.

Base Power rows: contractor_company_name='Base Power', work_class='Auxiliary
Power', issue_date in 2026 or later. Base-named permits before 2026 are a name
collision (a different company) and are not counted as Base.

Run from the repo root: python3 -m house.market
"""

import json
import re
import statistics
import time
from datetime import date

from house.permits import _get, SLEEP_SECONDS

AUX = "work_class='Auxiliary Power'"
BASE = "contractor_company_name='Base Power' AND issue_date >= '2026-01-01'"
OUT = "data/market.json"

# Dated events drawn on web/market.html. Source: docs/GAPS.md row 1
# (Austin Energy release; Base sells Backup Only in Austin Energy territory).
EVENTS = [{"date": "2026-07-15", "label": "Base Backup Only launch"}]

# Display-name rule: Base Power by name; every other contractor by rank
# ("Installer 1" = most 2026 permits). The public feed has the real names.


def q(params):
    rows = _get(params)
    time.sleep(SLEEP_SECONDS)
    return rows


def display(name, rank):
    return name if name == "Base Power" else f"Installer {rank}"


def monthly():
    def by_month(where):
        rows = q({"$select": "date_trunc_ym(issue_date) as m, count(*) as n",
                  "$where": where, "$group": "m", "$order": "m", "$limit": 500})
        return {r["m"][:7]: int(r["n"]) for r in rows if r.get("m")}
    where = f"{AUX} AND issue_date >= '2024-01-01'"
    all_ = by_month(where)
    base = by_month(f"{where} AND {BASE}")
    months = sorted(all_)
    return [{"month": m, "base": base.get(m, 0), "others": all_[m] - base.get(m, 0)} for m in months]


def classify(descs):
    text = " ".join(descs).lower()
    has_gen = "generator" in text
    has_bat = re.search(r"batter|powerwall|storage|ess\b", text) is not None
    has_solar = re.search(r"solar|\bpv\b|photovoltaic", text) is not None
    if has_bat and has_solar:
        return "solar-plus-battery"
    if has_bat:
        return "battery"
    if has_gen:
        return "generator"
    if has_solar:
        return "solar only"
    return "other"


def contractors():
    rows = q({"$select": "contractor_company_name as c, count(*) as n",
              "$where": f"{AUX} AND issue_date >= '2026-01-01' AND contractor_company_name IS NOT NULL",
              "$group": "c", "$order": "n DESC", "$limit": 10})
    out = []
    rank = 0
    for r in rows:
        name = r["c"]
        if name != "Base Power":
            rank += 1
        esc = name.replace("'", "''")
        samples = q({"$select": "description, count(*) as n",
                     "$where": f"{AUX} AND issue_date >= '2026-01-01' AND contractor_company_name='{esc}'",
                     "$group": "description", "$order": "n DESC", "$limit": 5})
        descs = [s.get("description", "") for s in samples]
        out.append({"contractor": display(name, rank), "permits_2026": int(r["n"]), "type": classify(descs)})
    return out


def by_zip():
    where = f"{AUX} AND {BASE}"
    rows = q({"$select": "original_zip as z, status_current as s, count(*) as n, "
                         "median(date_diff_d(issue_date, applieddate)) as md",
              "$where": where, "$group": "z, s", "$limit": 1000})
    tot = q({"$select": "original_zip as z, count(*) as n, median(date_diff_d(issue_date, applieddate)) as md",
             "$where": where, "$group": "z", "$limit": 1000})
    demo = {r["zip"]: r for r in json.load(open("data/demographics.json"))["rows"]}
    zips = {}
    for r in tot:
        z = r.get("z") or "unknown"
        zips[z] = {"zip": z, "count": int(r["n"]), "final": 0, "active": 0, "other": 0,
                   "median_days_applied_to_issued": float(r["md"]) if r.get("md") else None}
    for r in rows:
        z = r.get("z") or "unknown"
        s = (r.get("s") or "").lower()
        key = s if s in ("final", "active") else "other"
        zips[z][key] += int(r["n"])
    for z in zips.values():
        z["final_rate"] = round(z["final"] / z["count"], 3)
        d = demo.get(z["zip"])
        z["owner_occupied"] = d["owner_occupied"] if d else None
        z["per_1000_owner_occupied"] = round(1000 * z["count"] / d["owner_occupied"], 2) if d and d["owner_occupied"] else None
    return sorted(zips.values(), key=lambda z: (z["per_1000_owner_occupied"] is None, -(z["per_1000_owner_occupied"] or 0), -z["count"]))


def base_totals():
    where = f"{AUX} AND {BASE}"
    st = q({"$select": "status_current as s, count(*) as n", "$where": where, "$group": "s"})
    md = q({"$select": "median(date_diff_d(issue_date, applieddate)) as md", "$where": where})
    counts = {(r.get("s") or "none").lower(): int(r["n"]) for r in st}
    total = sum(counts.values())
    return {"total": total, "by_status": counts,
            "final_rate": round(counts.get("final", 0) / total, 3) if total else None,
            "median_days_applied_to_issued": float(md[0]["md"]) if md and md[0].get("md") else None}


def annual():
    rows = q({"$select": "date_trunc_y(issue_date) as y, count(*) as n",
              "$where": f"{AUX} AND issue_date >= '2013-01-01'", "$group": "y", "$order": "y"})
    return [{"year": int(r["y"][:4]), "total": int(r["n"])} for r in rows if r.get("y")]


# Lookalike rule for "market next": zips where Base sells (territory status is
# not not_served), median home value at least $600,000, at least 5,000
# owner-occupied homes, and fewer than 1 Base permit per 1,000 of them.
LOOKALIKE = {"min_home_value": 600000, "min_owner_occupied": 5000, "max_base_per_1000": 1.0}


def lookalikes(zips):
    from house.territory import lookup
    per = {z["zip"]: z["per_1000_owner_occupied"] or 0 for z in zips}
    cnt = {z["zip"]: z["count"] for z in zips}
    out = []
    for r in json.load(open("data/demographics.json"))["rows"]:
        st = lookup(r["zip"]).get("status")
        if (st and st != "not_served" and (r["median_home_value"] or 0) >= LOOKALIKE["min_home_value"]
                and r["owner_occupied"] >= LOOKALIKE["min_owner_occupied"]
                and per.get(r["zip"], 0) < LOOKALIKE["max_base_per_1000"]):
            out.append({"zip": r["zip"], "territory": st, "owner_occupied": r["owner_occupied"],
                        "median_home_value": r["median_home_value"], "base_permits": cnt.get(r["zip"], 0),
                        "per_1000_owner_occupied": per.get(r["zip"], 0)})
    return {"rule": LOOKALIKE, "zips": sorted(out, key=lambda z: -z["owner_occupied"])}


def main():
    data = {
        "source": "City of Austin Issued Construction Permits, Socrata 3syk-w9eu (aggregate queries)",
        "fetched_at": date.today().isoformat(),
        "base_rule": "contractor 'Base Power', work class Auxiliary Power, issued 2026 or later",
        "monthly": monthly(),
        "contractors_2026": contractors(),
        "base_totals": base_totals(),
        "base_by_zip": by_zip(),
        "annual": annual(),
        "events": EVENTS,
    }
    data["lookalikes"] = lookalikes(data["base_by_zip"])
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"wrote {OUT}: {data['base_totals']}")
    for m in data["monthly"][-4:]:
        print(m)
    for z in data["base_by_zip"][:5]:
        print(z)
    for c in data["contractors_2026"]:
        print(c)


if __name__ == "__main__":
    main()
