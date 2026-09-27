"""ACS demographics per zip (ZCTA) for the Base territory zips.

Source: Census Reporter API, keyless mirror of Census ACS 5-year tables.
  https://api.censusreporter.org/1.0/data/show/latest?table_ids=...&geo_ids=86000US<zip>
The Census Data API (api.census.gov) now refuses requests without a key
(checked 2026-09-26). Census Reporter serves the same ACS estimates.

Tables:
  B11001  households (B11001001)
  B25003  owner-occupied units (B25003002)
  B25024  single-family detached units (B25024002)
  B25035  median year structure built (B25035001)
  B19013  median household income (B19013001)
  B25077  median home value (B25077001)
  B01001  population (B01001001); 65 and over = sum of B01001020-025
          (male) and B01001044-049 (female)
  B18101  civilian noninstitutionalized population (B18101001); with a
          disability = sum of the "With a disability" cells; also the
          under-65 part of that sum, so 65+ or disabled does not count
          a person twice
  B11007  households with one or more people 65 and over (B11007002)

Output: data/demographics.json
Run: python3 house/demographics.py
"""

import json
import os
import sys
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from house.territory import ZIP_TABLE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "demographics.json")
URL = "https://api.censusreporter.org/1.0/data/show/latest?table_ids={t}&geo_ids={g}"
TABLES = "B11001,B25003,B25024,B25035,B19013,B25077,B01001,B18101,B11007"
FIELDS = {
    "households": ("B11001", "B11001001"),
    "owner_occupied": ("B25003", "B25003002"),
    "single_family_detached": ("B25024", "B25024002"),
    "median_year_built": ("B25035", "B25035001"),
    "median_income": ("B19013", "B19013001"),
    "median_home_value": ("B25077", "B25077001"),
    "population": ("B01001", "B01001001"),
    "disability_universe": ("B18101", "B18101001"),
    "households_with_65plus": ("B11007", "B11007002"),
}
DIS_UNDER65 = ["004", "007", "010", "013", "023", "026", "029", "032"]
DIS_65PLUS = ["016", "019", "035", "038"]
# key -> (table, [column ids]) summed
SUMS = {
    "pop_65plus": ("B01001", [f"B01001{i:03d}" for i in list(range(20, 26)) + list(range(44, 50))]),
    "pop_disabled": ("B18101", ["B18101" + c for c in DIS_UNDER65 + DIS_65PLUS]),
    "pop_disabled_under65": ("B18101", ["B18101" + c for c in DIS_UNDER65]),
}


def zips():
    z = set(ZIP_TABLE)
    p = os.path.join(ROOT, "data", "austin_zips.json")
    if os.path.exists(p):
        z |= {r["zip"] for r in json.load(open(p))["rows"]}
    return sorted(z)


def fetch(batch):
    geos = ",".join("86000US" + z for z in batch)
    req = urllib.request.Request(URL.format(t=TABLES, g=geos), headers={"User-Agent": "base-fleet"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    all_zips = zips()
    rows, release = [], None
    for i in range(0, len(all_zips), 20):
        d = fetch(all_zips[i:i + 20])
        release = release or d.get("release", {}).get("name")
        for z in all_zips[i:i + 20]:
            g = d["data"].get("86000US" + z)
            if not g:
                continue
            row = {"zip": z}
            for k, (t, c) in FIELDS.items():
                v = g.get(t, {}).get("estimate", {}).get(c)
                row[k] = int(v) if v is not None and v >= 0 else None
            for k, (t, cols) in SUMS.items():
                e = g.get(t, {}).get("estimate", {})
                vals = [e.get(c) for c in cols]
                row[k] = int(sum(vals)) if all(v is not None and v >= 0 for v in vals) else None
            rows.append(row)
    json.dump({"source": "Census Reporter API (ACS 5-year), https://api.censusreporter.org",
               "vintage": release, "fetched_at": date.today().isoformat(), "rows": rows},
              open(OUT, "w"), indent=1)
    print(f"{len(rows)} zips, {release} -> {OUT}")


if __name__ == "__main__":
    main()
