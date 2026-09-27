"""Real distribution substations for the top 10 star zips -> data/feeders.json.

No Texas utility in Base territory publishes open feeder or hosting-capacity data (checked
2026-09-26, see grid/FEEDERS.md). The best open, keyless source is OpenStreetMap substations
through the Overpass API (ODbL). So each zip gets its real substations (name, operator, voltage),
feeder_ids = [] and hosting_capacity_kw = null. The sim uses the substations and keeps its STUB
export cap where no hosting capacity is given.

Query is one bounding-box call per zip (from data/zcta.geojson), not a layer download.

python3 -m house.feeders -> data/feeders.json
"""

import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(__file__), "..")
OVERPASS = "https://overpass-api.de/api/interpreter"
TOP_N = 10


def top_zips(n=TOP_N):
    rows = json.load(open(os.path.join(ROOT, "data", "funnel.json")))["rows"]
    return [r for r in sorted(rows, key=lambda r: -r["star"])[:n]]


def polygons():
    g = json.load(open(os.path.join(ROOT, "data", "zcta.geojson")))
    out = {}
    for f in g["features"]:
        geom = f["geometry"]
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        out[f["properties"]["zip"]] = rings
    return out


def inside(lon, lat, rings):
    hit = False
    for ring in rings:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][:2]
            xj, yj = ring[j][:2]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def overpass(bbox, tries=3):
    s, w, n, e = bbox
    q = f'[out:json][timeout:25];nwr["power"="substation"]({s},{w},{n},{e});out center tags;'
    url = OVERPASS + "?" + urllib.parse.urlencode({"data": q})
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "base-fleet-research/0.1"})
            return json.load(urllib.request.urlopen(req, timeout=60))["elements"]
        except Exception as ex:   # Overpass returns 504 under load; back off and retry
            err = ex
            time.sleep(5 * (k + 1))
    raise RuntimeError(f"overpass failed for {bbox}: {err}")


def build():
    polys = polygons()
    out = {}
    for r in top_zips():
        z = r["zip"]
        rings = polys[z]
        xs = [p[0] for ring in rings for p in ring]
        ys = [p[1] for ring in rings for p in ring]
        bbox = (min(ys), min(xs), max(ys), max(xs))
        subs = []
        for e in overpass(bbox):
            c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
            t = e.get("tags", {})
            if c["lat"] is None or t.get("substation") in ("transmission", "generation", "minor_distribution"):
                continue
            if not inside(c["lon"], c["lat"], rings):
                continue
            subs.append({"osm": f"{e['type']}/{e['id']}", "name": t.get("name"), "operator": t.get("operator"),
                         "voltage": t.get("voltage"), "type": t.get("substation"),
                         "lat": round(c["lat"], 5), "lon": round(c["lon"], 5)})
        subs.sort(key=lambda s: s["osm"])
        out[z] = {"city": r["city"], "tdu_in_funnel": r["tdu"], "star": r["star"],
                  "bbox": [round(v, 4) for v in bbox], "substations": subs,
                  "feeder_ids": [], "hosting_capacity_kw": None}
        time.sleep(2)
    return {
        "source": "OpenStreetMap via Overpass API (power=substation, inside the ZCTA polygon); fetched "
                  + time.strftime("%Y-%m-%d"),
        "license": "ODbL 1.0, (c) OpenStreetMap contributors. Attribution required; share-alike on the derived database.",
        "note": "No open feeder ids or hosting capacity from Oncor, CenterPoint, Austin Energy or PEC. "
                "feeder_ids = [] and hosting_capacity_kw = null everywhere. See grid/FEEDERS.md.",
        "zips": out,
    }


if __name__ == "__main__":
    d = build()
    json.dump(d, open(os.path.join(ROOT, "data", "feeders.json"), "w"), indent=1)
    for z, v in d["zips"].items():
        ops = sorted({s["operator"] or "?" for s in v["substations"]})
        print(z, v["city"], v["tdu_in_funnel"], len(v["substations"]), ops)
