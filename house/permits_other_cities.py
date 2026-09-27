"""Open permit feed probes for Texas cities outside Austin, for Issue #54
track 4 (Base Power footprint by contractor name in city permit data).

Stdlib only (urllib + json). Each function runs AGGREGATE queries only
(count / group by month) against a live feed. No bulk row downloads.

Only cities with a working, queryable, keyless feed are included here.
Cities with no open feed found (Fort Worth, Plano, Frisco, McKinney,
Round Rock, Georgetown, Pflugerville, Cedar Park) are documented in
house/PERMITS_OUTSIDE_AUSTIN.md, not scripted here, since there is
nothing to query.
"""

import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "base-fleet/house.permits_other_cities"}


def _get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Dallas — Socrata "Building Permits" (e7gq-4sah). Has a `contractor` field,
# but the dataset is stale (max issued_date seen: 2019-12-31), so it cannot
# answer a 2026 question. Kept here so a future re-check is one function call.
# ---------------------------------------------------------------------------

DALLAS_URL = "https://www.dallasopendata.com/resource/e7gq-4sah.json"


def dallas_base_power_count():
    """Total count of Dallas permits with contractor LIKE '%BASE POWER%'.
    `issued_date` is stored as text (MM/DD/YY), not a Socrata date, and the
    dataset tops out at 2019-12-31 (see dallas_max_issued_date), so a
    month-by-month 2026 breakdown is not possible from this feed."""
    params = {
        "$select": "count(*) as cnt",
        "$where": "contractor like '%BASE POWER%'",
    }
    url = f"{DALLAS_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
    return _get_json(url)


def dallas_max_issued_date():
    url = f"{DALLAS_URL}?{urllib.parse.urlencode({'$select': 'max(issued_date)'})}"
    return _get_json(url)


# ---------------------------------------------------------------------------
# Arlington — ArcGIS FeatureServer "Issued Permits" (OD_Property/MapServer/1).
# No contractor field in the schema (FOLDERNAME/NameofBusiness are the
# applicant/site fields, not the installing contractor), so Base Power
# cannot be identified from this feed. Query kept for a future schema check.
# ---------------------------------------------------------------------------

ARLINGTON_URL = (
    "https://gis2.arlingtontx.gov/agsext2/rest/services/OpenData/OD_Property/MapServer/1/query"
)


def arlington_name_hits(term="BASE POWER"):
    """Count Arlington issued-permit rows where NameofBusiness matches term.
    NameofBusiness is not documented as the contractor field, so a 0 here
    does not rule out Base Power activity in Arlington."""
    where = f"UPPER(NameofBusiness) LIKE '%{term.upper()}%'"
    params = {
        "where": where,
        "outFields": "OBJECTID",
        "returnCountOnly": "true",
        "f": "json",
    }
    url = f"{ARLINGTON_URL}?{urllib.parse.urlencode(params)}"
    return _get_json(url)


# ---------------------------------------------------------------------------
# San Antonio — CKAN datastore "PERMITS ISSUED" (Open Data SA). Uses CKAN's
# datastore_search_sql (native Postgres SQL, not Socrata SoQL). Field
# "PRIMARY CONTACT" is the closest analog to a contractor name but is not
# labeled as one; treat matches as a lead, not a confirmed contractor field.
# ---------------------------------------------------------------------------

SA_SQL_URL = "https://data.sanantonio.gov/api/3/action/datastore_search_sql"
SA_RESOURCE_ID = "c21106f9-3ef5-4f3a-8604-f992b4db7512"  # PERMITS ISSUED


def san_antonio_base_power_by_month(year=2026):
    sql = (
        f"SELECT to_char(\"DATE ISSUED\"::date,'YYYY-MM') as m, count(*) as cnt "
        f"FROM \"{SA_RESOURCE_ID}\" "
        f"WHERE upper(\"PRIMARY CONTACT\") LIKE '%BASE POWER%' "
        f"AND \"DATE ISSUED\" >= '{year}-01-01' AND \"DATE ISSUED\" < '{year + 1}-01-01' "
        f"GROUP BY m ORDER BY m"
    )
    url = f"{SA_SQL_URL}?{urllib.parse.urlencode({'sql': sql})}"
    return _get_json(url)["result"]["records"]


# ---------------------------------------------------------------------------
# Houston (CenterPoint) — City of Houston open data (CKAN) only publishes a
# pre-aggregated "Residential Building Permits by Month and Year" dataset.
# It has no per-permit contractor field, so Base Power cannot be counted
# from Houston's open feed at all.
# ---------------------------------------------------------------------------

HOUSTON_PACKAGE_SEARCH = "https://data.houstontx.gov/api/3/action/package_search?q=permit&rows=15"


def houston_permit_datasets():
    """List Houston's open-data permit datasets (aggregate metadata only)."""
    d = _get_json(HOUSTON_PACKAGE_SEARCH)
    return [(r["name"], r["title"]) for r in d["result"]["results"]]


if __name__ == "__main__":
    print("Dallas max issued_date:", dallas_max_issued_date())
    print("Dallas Base Power total count (all years, dataset is stale):", dallas_base_power_count())
    print("Arlington NameofBusiness hits for BASE POWER:", arlington_name_hits())
    print("San Antonio Base Power by month (2026):", san_antonio_base_power_by_month())
    print("Houston permit datasets:", houston_permit_datasets())
