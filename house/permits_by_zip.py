"""Per-zip permit counts for the greater-Austin territory (issue #50, task b).

Reuses the Socrata query helper and permit classifier from house/permits.py.
Does not write a second query helper or a second classifier.

Data source: Austin open data Socrata dataset 3syk-w9eu (same as permits.py)
https://data.austintexas.gov/resource/3syk-w9eu.json

This dataset is City of Austin issued permits. It covers Austin and parts of
Austin's extraterritorial jurisdiction (ETJ), not every zip in
house/territory.py's ZIP_TABLE. Round Rock, Georgetown, Hutto proper, and a
few other zips issue their own permits through a different city system and
do not show up here at all. See house/PERMITS_OUTSIDE_AUSTIN.md for what was
checked for those cities and what a follow-up pull would need.

A note on panel location. No public record says where the electrical panel
sits on a given house. Permit descriptions do not carry a location field for
the panel itself. The two proxies this codebase has are the house's build
year (newer homes are more likely to have a 200 A panel and an accessible
exterior location by code) and the geometry rule in house/clearance.py
(setback math that estimates whether a battery stack fits next to the
panel). Both are estimates, not a lookup. Say that plainly to anyone reading
this file: we are guessing from proxies, not reading a record.
"""

import json
import time

from house.permits import _get, SLEEP_SECONDS
from house.territory import ZIP_TABLE

OUTPUT_PATH = "data/permits_by_zip.json"
SINCE_YEAR = 2016
WINDOW_LABEL = "2016-2026"

# Same classification vocabulary as permits.py's _classify(), expressed as
# SoQL WHERE fragments so the counts come back as one aggregate query per
# metric instead of row-by-row pulls.
RESIDENTIAL = "permit_class_mapped='Residential'"
SINCE = f"calendar_year_issued >= '{SINCE_YEAR}'"

WHERE_SERVICE_UPGRADE = (
    f"{RESIDENTIAL} AND {SINCE} AND permit_type_desc='Electrical Permit' "
    f"AND work_class='Upgrade'"
)
WHERE_SOLAR = (
    f"{RESIDENTIAL} AND {SINCE} AND "
    f"(upper(description) like '%SOLAR%' OR upper(description) like '%PHOTOVOLTAIC%' "
    f"OR upper(description) like '%PV %' OR upper(description) like '% PV%')"
)
WHERE_BATTERY = (
    f"{RESIDENTIAL} AND {SINCE} AND "
    f"(upper(description) like '%BATTERY%' OR upper(description) like '%POWERWALL%' "
    f"OR upper(description) like '%ESS%' OR upper(description) like '%STORAGE%')"
)
WHERE_NEW_SFR = (
    f"{RESIDENTIAL} AND {SINCE} AND permit_type_desc='Building Permit' "
    f"AND (work_class='New' OR upper(description) like '%HOMEBUILDER LOOP%')"
)
WHERE_TOTAL = f"{RESIDENTIAL} AND {SINCE}"


def _grouped_counts(where_clause):
    """One SoQL $group query over all zips. Returns {zip: count}."""
    rows = _get({
        "$select": "original_zip, count(*) as cnt",
        "$where": where_clause,
        "$group": "original_zip",
        "$limit": 1000,
    })
    out = {}
    for r in rows:
        z = r.get("original_zip")
        if z:
            out[z] = int(r["cnt"])
    return out


def build():
    """Pull five aggregate queries (one per metric, all zips at once) and
    assemble per-zip rows for every zip in house/territory.py's ZIP_TABLE."""
    print("Querying Austin permits dataset, 5 aggregate queries...")
    totals = _grouped_counts(WHERE_TOTAL)
    time.sleep(SLEEP_SECONDS)
    upgrades = _grouped_counts(WHERE_SERVICE_UPGRADE)
    time.sleep(SLEEP_SECONDS)
    solar = _grouped_counts(WHERE_SOLAR)
    time.sleep(SLEEP_SECONDS)
    battery = _grouped_counts(WHERE_BATTERY)
    time.sleep(SLEEP_SECONDS)
    new_sfr = _grouped_counts(WHERE_NEW_SFR)

    rows = []
    for zip_code in sorted(ZIP_TABLE):
        covered = zip_code in totals
        if not covered:
            rows.append({
                "zip": zip_code,
                "covered": False,
                "permits": None,
                "service_upgrade": None,
                "solar": None,
                "battery": None,
                "new_sfr": None,
            })
            continue
        rows.append({
            "zip": zip_code,
            "covered": True,
            "permits": totals.get(zip_code, 0),
            "service_upgrade": upgrades.get(zip_code, 0),
            "solar": solar.get(zip_code, 0),
            "battery": battery.get(zip_code, 0),
            "new_sfr": new_sfr.get(zip_code, 0),
        })

    out = {
        "source": "https://data.austintexas.gov/resource/3syk-w9eu.json",
        "window": WINDOW_LABEL,
        "rows": rows,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    n_covered = sum(1 for r in rows if r["covered"])
    print(f"Wrote {len(rows)} zips to {OUTPUT_PATH} ({n_covered} covered by the dataset)")
    return out


if __name__ == "__main__":
    build()
