"""Property appraisal lookup by address.

For Williamson County, this shells out to house/wcad.js (Playwright,
headless) which scrapes https://search.wcad.org/. For Travis County, no
scraper is wired up yet; see house/YEAR_BUILT_SOURCES.md for the source
survey and the TODO stub below.

Do NOT store or print owner names. The WCAD OWNER NAME column is stripped
in wcad.js before any data reaches this module.

Usage:
    python3 -m house.appraisal "2444 SOME ST, ROUND ROCK, TX"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

WCAD_SCRIPT = Path(__file__).parent / "wcad.js"


def lookup_wcad(address):
    """Run the WCAD Playwright script for `address`, return parsed dict."""
    result = subprocess.run(
        ["node", str(WCAD_SCRIPT), address],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if not result.stdout.strip():
        return {"error": "wcad.js produced no output", "stderr": result.stderr}
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {"error": "could not parse wcad.js output", "raw": result.stdout}


def lookup_tcad(address):
    """TODO: Travis County appraisal lookup.

    house/YEAR_BUILT_SOURCES.md recommends the TCAD Certified Appraisal
    Export (bulk ZIP, no login) as the primary source. Before downloading
    it, state its file size in the report. Do not download it as part of
    this function; join by address or TCAD account ID once the export is
    on disk.

    Expected output shape (same fields as lookup_wcad):
        {
            "cad": "TCAD",
            "cad_id": None,       # TCAD account ID
            "year_built": None,
            "sqft_living": None,
            "storeys": None,
            "garage_detached_sqft": None,
            "porch_patio_sqft": None,
            "foundation": None,
            "hvac": None,
            "lot_acres": None,
            "lot_sqft": None,
            "source_url": None,
        }
    """
    return {"error": "TCAD lookup not implemented, see house/YEAR_BUILT_SOURCES.md"}


def lookup(address, county="WCAD"):
    if county.upper() == "WCAD":
        return lookup_wcad(address)
    if county.upper() == "TCAD":
        return lookup_tcad(address)
    return {"error": f"unknown county appraisal district: {county}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", help='e.g. "2444 SOME ST, ROUND ROCK, TX"')
    parser.add_argument("--county", default="WCAD", choices=["WCAD", "TCAD"])
    args = parser.parse_args()

    result = lookup(args.address, county=args.county)
    print(json.dumps(result, indent=2))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
