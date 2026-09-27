"""Pull public-building candidate community nodes for base-fleet Issue #47 task 2.

Sources (all open, no login):
  - Austin Public Library Locations
    https://data.austintexas.gov/resource/tc36-hn4j.json
  - Austin Parks & Recreation - Recreation Centers
    https://datahub.austintexas.gov/resource/8dff-2vkt.json
  - Texas Education Agency AskTED school directory (all TX public/charter
    school campuses, incl. AISD) filtered to target zips
    https://data.texas.gov/resource/hzek-udky.json

Writes house/public_buildings.json: a flat list of
    {name, kind, address, city, state, zip, lat, lon, source}
filtered to TARGET_ZIPS, plus a summary of counts per zip and per kind.

stdlib only.
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

TARGET_ZIPS = {"78745", "78744", "78748", "78704", "78741"}

LIBRARY_URL = "https://data.austintexas.gov/resource/tc36-hn4j.json?$limit=200"
RECCENTER_URL = "https://datahub.austintexas.gov/resource/8dff-2vkt.json?$limit=200"
SCHOOL_BASE = "https://data.texas.gov/resource/hzek-udky.json"

OUT_PATH = Path(__file__).parent / "public_buildings.json"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "base-fleet/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def zip5(z):
    if not z:
        return None
    m = re.match(r"(\d{5})", z.strip())
    return m.group(1) if m else None


def load_libraries():
    rows = fetch_json(LIBRARY_URL)
    out = []
    for r in rows:
        addr = r.get("address", {})
        human = addr.get("human_address")
        zc = None
        addr_line = None
        city = "Austin"
        if human:
            try:
                h = json.loads(human)
                addr_line = h.get("address")
                zc = zip5(h.get("zip"))
                city = h.get("city") or city
            except json.JSONDecodeError:
                pass
        z = zc
        out.append(
            {
                "name": r.get("name"),
                "kind": "library",
                "address": addr_line,
                "city": city,
                "state": "TX",
                "zip": z,
                "lat": _to_float(addr.get("latitude")),
                "lon": _to_float(addr.get("longitude")),
                "source": "Austin Public Library Locations (tc36-hn4j)",
            }
        )
    return out


def load_rec_centers():
    rows = fetch_json(RECCENTER_URL)
    out = []
    for r in rows:
        loc = r.get("location_1", {})
        out.append(
            {
                "name": r.get("recreation_centers"),
                "kind": "recreation_center",
                "address": r.get("address"),
                "city": "Austin",
                "state": "TX",
                "zip": zip5(r.get("zip_code")),
                "lat": _to_float(loc.get("latitude")),
                "lon": _to_float(loc.get("longitude")),
                "source": "Austin Parks & Recreation - Recreation Centers (8dff-2vkt)",
            }
        )
    return out


def load_schools():
    where = " or ".join(f"school_zip like '{z}%'" for z in TARGET_ZIPS)
    url = SCHOOL_BASE + "?" + urllib.parse.urlencode({"$where": where, "$limit": 2000})
    rows = fetch_json(url)
    out = []
    seen = set()
    for r in rows:
        if r.get("school_status") != "Active":
            continue
        num = r.get("school_number")
        if num in seen:
            continue
        seen.add(num)
        out.append(
            {
                "name": r.get("school_name"),
                "kind": "school",
                "address": r.get("school_street_address"),
                "city": r.get("school_city"),
                "state": r.get("school_state") or "TX",
                "zip": zip5(r.get("school_zip")),
                "lat": None,
                "lon": None,
                "district": r.get("district_name"),
                "source": "TEA AskTED school directory (hzek-udky)",
            }
        )
    return out


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    all_rows = load_libraries() + load_rec_centers() + load_schools()
    filtered = [r for r in all_rows if r.get("zip") in TARGET_ZIPS]

    by_zip = {}
    by_kind = {}
    for r in filtered:
        by_zip.setdefault(r["zip"], {}).setdefault(r["kind"], 0)
        by_zip[r["zip"]][r["kind"]] += 1
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1

    out = {
        "target_zips": sorted(TARGET_ZIPS),
        "count_total": len(filtered),
        "count_by_zip": by_zip,
        "count_by_kind": by_kind,
        "sites": filtered,
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(filtered)} sites to {OUT_PATH}")
    print(json.dumps({"by_zip": by_zip, "by_kind": by_kind}, indent=2))


if __name__ == "__main__":
    main()
