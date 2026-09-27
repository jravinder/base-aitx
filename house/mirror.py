"""Energy permit mirror: every City of Austin energy permit since 2015.

Producer for docs/MIRROR_SCHEMA.md. Stdlib only.

Source: Socrata dataset 3syk-w9eu (keyless), paged row pull with $select,
$limit 50000, $offset, $order=permit_number.

Scope rule (pulled server side, tightened here):
  work_class 'Auxiliary Power', or an Electrical Permit whose description
  names battery, energy storage, Powerwall, solar, photovoltaic, PV,
  generator, service upgrade, meter or panel upgrade, 200 amp, EV charger or
  electric vehicle. Only Electrical Permits count for the keyword match, so
  one job does not count again as its building, plumbing or mechanical permit.

Writes:
  data/mirror/energy_permits.csv.gz   full rows (no owner names, no addresses)
  web/data/explorer_points.json       slim points for the browser
  web/data/explorer_zip.json          counts by zip and by month

Run from the repo root:
  python3 -m house.mirror                 full pull
  python3 -m house.mirror --incremental   only rows issued on or after the
                                          newest issue_date on file
  python3 -m house.mirror --llm           also send other_electrical rows to
                                          gemma4:e4b on local Ollama
"""

import argparse
import csv
import gzip
import io
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

SODA = "https://data.austintexas.gov/resource/3syk-w9eu.json"
SINCE = "2015-01-01"
PAGE = 50000
CSV_PATH = "data/mirror/energy_permits.csv.gz"
POINTS_PATH = "web/data/explorer_points.json"
ZIP_PATH = "web/data/explorer_zip.json"
DEMO_PATH = "data/demographics.json"
OLLAMA = "http://localhost:11434/api/chat"
MODEL = "gemma4:e4b"

CATEGORIES = ["battery", "solar", "solar_battery", "generator",
              "panel_upgrade", "ev_charger", "other_electrical"]
FIELDS = ["permit_number", "issue_date", "applied_date", "zip", "lat", "lon",
          "category", "contractor", "is_base", "work_class", "status", "description"]
SELECT = ("permit_number, issue_date, applieddate, original_zip, latitude, longitude, "
          "work_class, status_current, description, contractor_company_name")

# Server-side match. Broad on purpose (PV also hits PVC, storage also hits
# storage rooms); keep() below applies the exact rule.
_D = "upper(description)"
_LIKES = ["%BATTER%", "%STORAGE%", "%POWERWALL%", "%SOLAR%", "%PHOTOVOLTAIC%",
          "%PV%", "%GENERATOR%", "%SERVICE UPGRADE%", "%METER UPGRADE%",
          "%PANEL UPGRADE%", "%200 AMP%", "%200AMP%", "%EV CHARG%",
          "%ELECTRIC VEHICLE%"]
WHERE = ("work_class='Auxiliary Power' OR (permit_type_desc='Electrical Permit' AND ("
         + " OR ".join(f"{_D} like '{p}'" for p in _LIKES) + "))")

# Scope regexes (applied to keyword-matched Electrical Permits).
BATTERY = re.compile(r"batter|power ?walls?|energy storage|storage system|battery storage|"
                     r"\bess\b|\bbess\b|home battery|iq battery|franklin", re.I)
SOLAR = re.compile(r"solar|soalr|solor|photovoltaic|\bpv\b|\bp\.v\.|roof[- ]mounted array|"
                   r"\bmodules?\b.*\binverter|micro-?inverter", re.I)
GENERATOR = re.compile(r"generator|\bgenerac\b|\bkohler\b", re.I)
EV = re.compile(r"\bev\b.{0,20}charg|ev[- ]?charg|electric vehicle|\bevse\b|"
                r"car charg|tesla (wall|charg)|wall connector|level 2 charg", re.I)
UPGRADE = re.compile(r"service upgrade|upgrad\w* (a |the |to |existing |main |electrical |"
                     r"overhead |underground |\d+[- ]?a(mps?)?\b[- ]?)*(service|panel|meter|msp|main)|"
                     r"(panel|meter|service|msp) (upgrade|change ?out|replacement|swap)|"
                     r"(replace|change|swap)\w* (the |existing |out )*(main )?"
                     r"(panel|meter base|meter can|msp|breaker box|load center)|"
                     r"\b(100|125|150) ?a(mp)?s?\b.{0,30}\b(200|225|320|400) ?a(mp)?|"
                     r"to (200|225|320|400) ?a(mp)?s?\b|200 ?amp\w* (service|panel|upgrade|meter)",
                     re.I)
NOT_UPGRADING = re.compile(r"not upgrading the (size of the )?service", re.I)
AMP200 = re.compile(r"200 ?amp", re.I)
SUFFIX = re.compile(r"[,.]?\s+\b(l\.?l\.?c|inc|incorporated|corp|corporation|co|company|"
                    r"ltd|lp|llp|pllc|l\.?p)\b\.?$", re.I)


def soda_url(params):
    return SODA + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def get(params, tries=4):
    url = soda_url(params)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "base-fleet/house.mirror"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network retry only
            if i == tries - 1:
                raise
            print(f"retry {i + 1}: {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))


def where_since(day):
    return f"issue_date >= '{day}' AND ({WHERE})"


def count(day):
    return int(get({"$select": "count(*) as n", "$where": where_since(day)})[0]["n"])


def pull(day):
    rows, offset = [], 0
    while True:
        page = get({"$select": SELECT, "$where": where_since(day), "$order": "permit_number",
                    "$limit": PAGE, "$offset": offset})
        rows += page
        print(f"  page offset={offset} rows={len(page)}", file=sys.stderr)
        if len(page) < PAGE:
            return rows
        offset += PAGE
        time.sleep(0.5)


def keep(r):
    """Exact scope rule on a server-side match."""
    if r.get("work_class") == "Auxiliary Power":
        return True
    if r.get("work_class") == "Wall":  # signs ("Interstate Batteries", "Extra Space Storage")
        return False
    d = r.get("description") or ""
    if BATTERY.search(d) or SOLAR.search(d) or GENERATOR.search(d) or EV.search(d):
        return True
    if UPGRADE.search(d) or AMP200.search(d):
        return True
    # Storage alone (sheds, storage buildings, storage signs) is out of scope.
    return False


def categorize(desc, work_class):
    d = desc or ""
    bat = bool(BATTERY.search(d))
    sol = bool(SOLAR.search(d))
    upg = bool(UPGRADE.search(d)) and not NOT_UPGRADING.search(d)
    if work_class == "Upgrade" and upg:
        return "panel_upgrade"
    if bat and sol:
        return "solar_battery"
    if bat:
        return "battery"
    if sol:
        return "solar"
    if GENERATOR.search(d):
        return "generator"
    if EV.search(d):
        return "ev_charger"
    if upg:
        return "panel_upgrade"
    return "other_electrical"


def norm_contractor(name):
    n = " ".join((name or "").replace(" ", " ").split())
    if not n:
        return ""
    prev = None
    while prev != n:
        prev, n = n, SUFFIX.sub("", n).strip(" ,.")
    n = n.title() if n.isupper() or n.islower() else n
    if n.lower() == "base power":
        return "Base Power"
    # Store no contractor names except Base: a stable anonymous id per company.
    return "c" + hashlib.sha1(n.lower().encode()).hexdigest()[:8]


def llm_category(desc):
    prompt = ("Classify this City of Austin electrical permit description into exactly one of: "
              + ", ".join(CATEGORIES) + ". battery = home battery or energy storage; "
              "solar_battery = both solar and battery; panel_upgrade = service, meter or panel "
              "upgrade; other_electrical = none of these. Answer with the label only.\n\n"
              f"Description: {desc[:600]}")
    body = json.dumps({"model": MODEL, "think": False, "stream": False,
                       "options": {"temperature": 0},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())["message"]["content"].strip().lower()
    for c in sorted(CATEGORIES, key=len, reverse=True):
        if c in out:
            return c
    return "other_electrical"


def to_row(r):
    lat, lon = r.get("latitude"), r.get("longitude")
    try:
        lat, lon = float(lat), float(lon)
        if not (29 < lat < 31.5 and -99 < lon < -96.5):
            lat = lon = None
    except (TypeError, ValueError):
        lat = lon = None
    issue = (r.get("issue_date") or "")[:10]
    contractor = norm_contractor(r.get("contractor_company_name"))
    wc = r.get("work_class") or ""
    return {
        "permit_number": r.get("permit_number", ""),
        "issue_date": issue,
        "applied_date": (r.get("applieddate") or "")[:10],
        "zip": str(r.get("original_zip") or "")[:5],
        "lat": "" if lat is None else round(lat, 6),
        "lon": "" if lon is None else round(lon, 6),
        "category": categorize(r.get("description"), wc),
        "contractor": contractor,
        # Same rule as house/market.py: Base-named rows before 2026 are a
        # different company.
        "is_base": int(contractor == "Base Power" and issue >= "2026-01-01"),
        "work_class": wc,
        "status": r.get("status_current") or "",
        "description": "",  # not stored; category is derived at pull time
    }


def read_csv():
    if not os.path.exists(CSV_PATH):
        return []
    with gzip.open(CSV_PATH, "rt", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(rows):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
    with gzip.GzipFile(CSV_PATH, "wb", mtime=0) as f:
        f.write(buf.getvalue().encode("utf-8"))


def write_browser(rows, fetched_at):
    counts = Counter(r["contractor"] for r in rows if r["contractor"] and r["contractor"] != "Base Power")
    ranked = [n for n, _ in counts.most_common()]
    rank = {n: i + 1 for i, n in enumerate(ranked)}

    def display(name):
        return "Base Power" if name == "Base Power" else f"Installer {rank[name]}"

    top = [display(n) for n, _ in Counter(r["contractor"] for r in rows if r["contractor"]).most_common(15)]
    top_raw = [n for n, _ in Counter(r["contractor"] for r in rows if r["contractor"]).most_common(15)]
    cidx = {n: i for i, n in enumerate(top_raw)}
    months = sorted({r["issue_date"][:7] for r in rows if r["issue_date"]})
    midx = {m: i for i, m in enumerate(months)}
    cat = {c: i for i, c in enumerate(CATEGORIES)}
    points = []
    for r in rows:
        if r["lat"] == "" or not r["issue_date"]:
            continue
        points.append([round(float(r["lat"]), 4), round(float(r["lon"]), 4), cat[r["category"]],
                       midx[r["issue_date"][:7]], int(r["is_base"]), cidx.get(r["contractor"], -1)])
    with_loc = len(points)
    replay = soda_url({"$select": "count(*)", "$where": where_since(SINCE)})
    data = {
        "_meta": {
            "source": "City of Austin Issued Construction Permits, Socrata 3syk-w9eu",
            "soda_url": replay,
            "fetched_at": fetched_at,
            "rows": len(rows),
            "rows_with_location": with_loc,
            "scope": "issued since 2015-01-01; work_class Auxiliary Power, or an Electrical Permit "
                     "whose description names an energy term (see house/mirror.py)",
            "point": "[lat, lon, category_index, month_index, is_base, contractor_index]; "
                     "contractor_index -1 = blank or not in the top 15",
            "contractor_rule": "Base Power by name; every other contractor is 'Installer N', "
                               "ranked by permit count in this mirror",
            "base_rule": "contractor 'Base Power' and issued 2026 or later",
        },
        "categories": CATEGORIES,
        "contractors": top,
        "months": months,
        "points": points,
    }
    with open(POINTS_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    households = {}
    if os.path.exists(DEMO_PATH):
        households = {d["zip"]: d.get("households") for d in json.load(open(DEMO_PATH))["rows"]}
    blank = lambda: {**{c: 0 for c in CATEGORIES}, "base": 0}
    by_zip, by_month = defaultdict(blank), defaultdict(blank)
    for r in rows:
        for key, bucket in ((r["zip"] or "unknown", by_zip), (r["issue_date"][:7], by_month)):
            bucket[key][r["category"]] += 1
            bucket[key]["base"] += int(r["is_base"])
    for z, v in by_zip.items():
        v["households"] = households.get(z)
    zdata = {"_meta": {"source": data["_meta"]["source"], "soda_url": replay,
                       "fetched_at": fetched_at, "rows": len(rows),
                       "households": "ACS 2024 5-year, data/demographics.json"},
             "by_zip": dict(sorted(by_zip.items())), "by_month": dict(sorted(by_month.items()))}
    with open(ZIP_PATH, "w") as f:
        json.dump(zdata, f, separators=(",", ":"))
    return with_loc


def merge_case(rows, old=()):
    """One spelling per contractor when names differ only by case."""
    spell = Counter(r["contractor"] for r in list(old) + rows if r["contractor"])
    best = {}
    for name, n in spell.most_common():
        best.setdefault(name.lower(), name)
    for r in rows:
        if r["contractor"]:
            r["contractor"] = best[r["contractor"].lower()]


def build(raw, use_llm, old=()):
    rows = [to_row(r) for r in raw if keep(r)]
    merge_case(rows, old)
    if use_llm:
        todo = [r for r in rows if r["category"] == "other_electrical" and r["description"]]
        print(f"LLM pass on {len(todo)} other_electrical rows", file=sys.stderr)
        cache = {}
        for i, r in enumerate(todo):
            d = r["description"]
            if d not in cache:
                cache[d] = llm_category(d)
            r["category"] = cache[d]
            if i % 500 == 0:
                print(f"  llm {i}/{len(todo)}", file=sys.stderr)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incremental", action="store_true")
    ap.add_argument("--llm", action="store_true", help="gemma4:e4b pass on other_electrical rows")
    ap.add_argument("--count-only", action="store_true")
    a = ap.parse_args()

    old = read_csv() if a.incremental else []
    day = max((r["issue_date"] for r in old if r["issue_date"]), default=SINCE)
    n = count(day)
    print(f"server rows issued since {day}: {n}")
    print(f"replay: {soda_url({'$select': 'count(*)', '$where': where_since(day)})}")
    if a.count_only:
        return
    new = build(pull(day), a.llm, old)
    merged = {r["permit_number"]: r for r in old}
    merged.update({r["permit_number"]: r for r in new})
    rows = sorted(merged.values(), key=lambda r: r["permit_number"])
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_csv(rows)
    with_loc = write_browser(rows, fetched_at)
    cats = Counter(r["category"] for r in rows)
    print(f"rows kept: {len(rows)} (new or updated: {len(new)})")
    print(f"with location: {with_loc} ({with_loc / max(len(rows), 1):.1%})")
    print(f"base rows: {sum(int(r['is_base']) for r in rows)}")
    for c in CATEGORIES:
        print(f"  {c}: {cats.get(c, 0)}")


if __name__ == "__main__":
    main()
