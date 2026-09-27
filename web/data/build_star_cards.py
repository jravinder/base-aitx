"""Build web/data/star_cards.json: backup permits filed by zip after each named storm.

Input:  data/storms.json (storm months), data/mirror/energy_permits.csv.gz (City of Austin permits),
        data/funnel.json (owner-occupied single-family homes per zip).
Output: web/data/star_cards.json. Run from the repo root: python3 web/data/build_star_cards.py
"""
import csv, gzip, json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATS = {"generator", "battery", "solar_battery"}
WINDOW = 3  # the storm month plus the next 2 months


def months_from(start, n):
    y, m = map(int, start.split("-"))
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


storms = json.loads((ROOT / "data/storms.json").read_text())["storms"]
funnel = json.loads((ROOT / "data/funnel.json").read_text())
owner = {r["zip"]: r["stages"][1]["count"] for r in funnel["rows"]}
windows = {s["name"]: set(months_from(s["month"], WINDOW)) for s in storms}

counts = {name: Counter() for name in windows}
with gzip.open(ROOT / "data/mirror/energy_permits.csv.gz", "rt") as fh:
    for r in csv.DictReader(fh):
        if r["category"] not in CATS or r["is_base"] == "1" or not r["applied_date"]:
            continue
        m = r["applied_date"][:7]
        for name, ms in windows.items():
            if m in ms:
                counts[name][r["zip"]] += 1

rows = []
for z in sorted(set().union(*counts.values()) | set(owner)):
    per = {name: counts[name][z] for name in windows}
    total = sum(per.values())
    homes = owner.get(z)
    rows.append({"zip": z, "storm_permits": total, "by_storm": per, "owner_sfd": homes,
                 "per_1000_homes": round(total / homes * 1000, 2) if homes else None})

out = {
    "built_from": ["data/storms.json", "data/mirror/energy_permits.csv.gz", "data/funnel.json"],
    "definition": f"generator, battery and solar_battery permits applied in the storm month and the next {WINDOW - 1} months, "
                  "Base installs left out, per 1,000 owner-occupied single-family homes",
    "storms": [{"name": s["name"], "months": sorted(windows[s["name"]])} for s in storms],
    "rows": rows,
}
(ROOT / "web/data/star_cards.json").write_text(json.dumps(out, indent=1))
print(len(rows), "zips;", sum(r["storm_permits"] for r in rows), "storm permits")
