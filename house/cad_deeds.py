"""Deed dates per parcel, summarized per zip, for Travis and Williamson.

Lead signal: a recent deed means a new owner who is still deciding on
backup power. A long hold means an older, settled household.

Sources (both free, no login):
  TCAD  2026 Certified Appraisal Export (fixed width, 557 MB zip).
        We do NOT download the zip. We read it over HTTP Range requests
        and decompress only PROP.TXT and IMP_DET.TXT in memory.
  WCAD  Socrata portal data.wcad.org. We request only the columns we keep.

Privacy rule: we keep ONLY property id, situs zip, year built, deed date,
deed type, homestead flag. Owner names, mailing addresses, agent and
mortgage fields are sliced away at read time (TCAD) or never requested
(WCAD). Nothing else is written to disk.

Outputs:
  data/deeds_by_zip.json
  data/mirror/deeds_min.csv.gz

Usage:
  python3 -m house.cad_deeds            # both counties
  python3 -m house.cad_deeds --only wcad
"""

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "data" / "deeds_by_zip.json"
OUT_CSV = ROOT / "data" / "mirror" / "deeds_min.csv.gz"

TCAD_ZIP = ("https://traviscad.org/wp-content/largefiles/"
            "2026%20Certified%20Appraisal%20Export%20Supp%200_07182026.zip")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 Chrome/128 Safari/537.36")

WCAD = "https://data.wcad.org/resource/{}.csv"
WCAD_PROPERTY = "ai3c-c9pf"   # Property - Certified
WCAD_SALE = "2k72-e257"       # Sale - Certified (deed history)
WCAD_EXEMPT = "nbn7-h4pp"     # Exemptions
WCAD_IMPSEG = "xs93-mfpk"     # Imp Seg Real Property - Certified

TODAY = dt.date(2026, 9, 26)
FIELDS = ["county", "prop_id", "situs_zip", "year_built",
          "deed_date", "deed_type", "homestead"]

# TCAD PROP.TXT fixed-width slices (1-based start, end inclusive), from
# Legacy8.0.33-AppraisalExportLayout. Only these slices are ever read.
P_ID = (1, 12)
P_TYPE = (13, 17)
P_ZIP = (1140, 1149)
P_DEED_DT = (2034, 2058)
P_HS = (2609, 2609)
P_IMPRV_STATE = (2732, 2741)
D_ID = (1, 12)
D_YR = (86, 89)


def _cut(line, span):
    return line[span[0] - 1:span[1]].strip()


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP Range requests (nothing on disk)."""

    CHUNK = 16 * 1024 * 1024

    def __init__(self, url):
        self.url = url
        self.pos = 0
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req) as r:
            self.size = int(r.headers["Content-Length"])
        self.buf_start, self.buf = 0, b""
        self.fetched = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def _fill(self, start, n):
        end = min(self.size, start + max(n, self.CHUNK)) - 1
        for attempt in range(5):
            try:
                req = urllib.request.Request(
                    self.url, headers={"User-Agent": UA,
                                       "Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    self.buf = r.read()
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(2 * (attempt + 1))
        self.buf_start = start
        self.fetched += len(self.buf)

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        off = self.pos - self.buf_start
        if not (0 <= off and off + n <= len(self.buf)):
            self._fill(self.pos, n)
            off = 0
        out = self.buf[off:off + n]
        self.pos += len(out)
        return out

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def _parse_date(s):
    """Parse MM-DD-YYYY (TCAD) or ISO (WCAD) to a date; None if bad."""
    s = (s or "").strip().split("T")[0].split(" ")[0]
    d = None
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            break
        except ValueError:
            pass
    if d is None or d.year < 1850 or d > TODAY:
        return None
    return d


def _member(zf, short):
    for name in zf.namelist():
        if name.upper().endswith(short):
            return name
    raise KeyError(short)


def tcad_rows():
    """Yield kept-field dicts for TCAD single-family parcels (state code A*)."""
    raw = HttpRangeFile(TCAD_ZIP)
    zf = zipfile.ZipFile(io.BufferedReader(raw, buffer_size=HttpRangeFile.CHUNK))
    print("tcad members:", zf.namelist(), file=sys.stderr)

    year = {}
    with zf.open(_member(zf, "IMP_DET.TXT")) as f:
        for line in io.TextIOWrapper(f, encoding="latin-1"):
            yr = _cut(line, D_YR)
            if yr.isdigit() and 1800 <= int(yr) <= TODAY.year:
                pid = _cut(line, D_ID).lstrip("0")
                y = int(yr)
                if pid not in year or y < year[pid]:
                    year[pid] = y
    print(f"tcad imp_det: {len(year)} props with year built, "
          f"{raw.fetched / 1e6:.0f} MB fetched", file=sys.stderr)

    seen = set()
    with zf.open(_member(zf, "PROP.TXT")) as f:
        for line in io.TextIOWrapper(f, encoding="latin-1"):
            # Slice kept fields only; the rest of the line is dropped here.
            pid = _cut(line, P_ID).lstrip("0")
            if pid in seen or _cut(line, P_TYPE) != "R":
                continue
            if not _cut(line, P_IMPRV_STATE).upper().startswith("A"):
                continue
            seen.add(pid)
            d = _parse_date(_cut(line, P_DEED_DT))
            yield {"county": "travis", "prop_id": pid,
                   "situs_zip": _cut(line, P_ZIP)[:5],
                   "year_built": year.get(pid),
                   "deed_date": d.isoformat() if d else None,
                   "deed_type": None,  # not in the legacy PROP.TXT layout
                   "homestead": _cut(line, P_HS) == "T"}
    print(f"tcad: {len(seen)} A* parcels, {raw.fetched / 1e6:.0f} MB "
          "fetched in total", file=sys.stderr)


def _soql(dataset, params, page=50000):
    """Page a Socrata CSV query. Yields dict rows with the selected columns."""
    offset = 0
    while True:
        q = dict(params, **{"$limit": page, "$offset": offset})
        url = WCAD.format(dataset) + "?" + urllib.parse.urlencode(q)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=180) as r:
                    text = r.read().decode("utf-8")
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
        rows = list(csv.DictReader(io.StringIO(text)))
        yield from rows
        if len(rows) < page:
            return
        offset += page


def wcad_rows():
    """Yield kept-field dicts for WCAD residential (type RES) parcels."""
    props = {r["propertyid"]: (r["zip"] or "")[:5] for r in _soql(
        WCAD_PROPERTY, {"$select": "propertyid,zip",
                        "$where": "propertytypecode='RES'",
                        "$order": "propertyid"})}
    print(f"wcad: {len(props)} RES parcels", file=sys.stderr)

    deed = {}
    for r in _soql(WCAD_SALE, {"$select": "propertyid,deeddate,instrumenttypecode",
                               "$where": "deeddate IS NOT NULL",
                               "$order": ":id"}):
        pid = r["propertyid"]
        if pid not in props:
            continue
        d = _parse_date(r["deeddate"])
        if d and (pid not in deed or d > deed[pid][0]):
            deed[pid] = (d, r["instrumenttypecode"] or None)
    print(f"wcad: {len(deed)} parcels with a deed date", file=sys.stderr)

    hs = {r["propertyid"] for r in _soql(
        WCAD_EXEMPT, {"$select": "propertyid",
                      "$where": "exemptiontypedescription='Homestead' "
                                "AND exemptionstatuscode='A' "
                                "AND adhoctaxyear='2026'",
                      "$order": ":id"})}

    year = {}
    for r in _soql(WCAD_IMPSEG, {"$select": "propertyid,min(factyear) AS yb",
                                 "$where": "fsegtype='MA' AND factyear>1800",
                                 "$group": "propertyid",
                                 "$order": "propertyid"}):
        try:
            year[r["propertyid"]] = int(float(r["yb"]))
        except (TypeError, ValueError):
            pass

    for pid, z in props.items():
        d, t = deed.get(pid, (None, None))
        yield {"county": "williamson", "prop_id": pid, "situs_zip": z,
               "year_built": year.get(pid),
               "deed_date": d.isoformat() if d else None,
               "deed_type": t, "homestead": pid in hs}


def summarize(rows):
    by_zip = {}
    for r in rows:
        z = r["situs_zip"]
        if not (len(z) == 5 and z.isdigit()):
            continue
        by_zip.setdefault(z, []).append(r)
    two_ago = TODAY.replace(year=TODAY.year - 2)
    twenty_ago = TODAY.replace(year=TODAY.year - 20)
    out = []
    for z, rs in sorted(by_zip.items()):
        dated = [dt.date.fromisoformat(r["deed_date"]) for r in rs if r["deed_date"]]
        yrs = [(TODAY - d).days / 365.25 for d in dated]
        n = len(dated)
        out.append({
            "zip": z,
            "counties": sorted({r["county"] for r in rs}),
            "parcels": len(rs),
            "parcels_with_deed_date": n,
            "median_years_since_deed": round(statistics.median(yrs), 1) if n else None,
            "share_sold_last_2y": round(sum(d >= two_ago for d in dated) / n, 3) if n else None,
            "share_held_20y_plus": round(sum(d <= twenty_ago for d in dated) / n, 3) if n else None,
            "share_homestead": round(sum(r["homestead"] for r in rs) / len(rs), 3),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["tcad", "wcad"])
    a = ap.parse_args()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with gzip.open(OUT_CSV, "wt", newline="") as g:
        w = csv.DictWriter(g, fieldnames=FIELDS)
        w.writeheader()
        sources = [("wcad", wcad_rows), ("tcad", tcad_rows)]
        for name, fn in sources:
            if a.only and a.only != name:
                continue
            for r in fn():
                w.writerow(r)
                rows.append(r)

    zips = summarize(rows)
    OUT_JSON.write_text(json.dumps({
        "as_of": TODAY.isoformat(),
        "universe": "Travis: real property, improvement state code A* "
                    "(single-family). Williamson: property type RES.",
        "sources": {"travis": TCAD_ZIP,
                    "williamson": "https://data.wcad.org (ai3c-c9pf, 2k72-e257, "
                                  "nbn7-h4pp, xs93-mfpk)"},
        "definitions": {
            "median_years_since_deed": "median of (as_of - last deed date), "
                                       "parcels with a deed date only",
            "share_sold_last_2y": "last deed on or after as_of minus 2 years; "
                                  "any transfer, not only arm's-length sales",
            "share_held_20y_plus": "last deed on or before as_of minus 20 years",
            "share_homestead": "share of all parcels with an active homestead exemption",
        },
        "rows": zips,
    }, indent=1) + "\n")
    print(f"wrote {OUT_JSON} ({len(zips)} zips), {OUT_CSV} "
          f"({OUT_CSV.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


if __name__ == "__main__":
    main()
