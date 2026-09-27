# Year built / sqft / stories / gas service for Travis County addresses — source check

Date: 2026-09-26. Research only, web search budget exhausted, WebFetch used on explicit URLs only. Several pages returned only nav shells or 404/DNS errors (noted below) — those need a manual follow-up click, not a re-fetch.

## Findings table

| Source | URL | Fields (confirmed or likely) | Access method | Bulk vs per-address | Login? | Format | Effort (hrs) | Licence |
|---|---|---|---|---|---|---|---|---|
| TCAD Certified Appraisal Export | https://traviscad.org/publicinformation | Full appraisal roll incl. improvement details (construction, likely year built, sqft) | Bulk file download, "2026 Certified Appraisal Export (July)" and "Supplemental Appraisal Roll Export" | Bulk (whole county) | No login mentioned | ZIP (layout file explains schema); also a JSON "Certified Special Export" | 3-5 (download, unzip, read layout doc, parse to lookup table by address/TCAD ID) | Not stated on page; treat as public record, confirm no redistribution restriction before publishing |
| TCAD Improvement Details Report | https://traviscad.org/publicinformation | Construction details per improvement (likely includes year built, sqft) | CSV report download | Bulk | No | CSV | 1-2 (easiest to parse of the TCAD set) | Same as above |
| TCAD GIS data page | https://traviscad.org/gis-data | Unknown — page returned 404 on fetch | Unknown | Unknown | Unknown | Unknown | N/A until re-checked manually | N/A |
| TNRIS / data.tnris.org | https://tnris.org, https://data.tnris.org | Statewide parcels, unconfirmed whether year built is included | Unknown — DNS lookup for data.tnris.org failed (domain may have moved/been retired) | Unknown | Unknown | Unknown | N/A until re-checked manually (try tnris.org directly or Texas Natural Resources Information System successor site) | Unknown |
| Austin open data — parcels | https://data.austintexas.gov/browse?q=parcel | Not extracted — page returned only nav/catalog shell, not dataset listing | Socrata portal, should have per-dataset API (SODA) once a specific dataset is found | Both (Socrata supports per-record API queries) | No | JSON/CSV via API | 2-3 once specific dataset identified (need a follow-up visit to click into actual results) | Public domain typically (Socrata city portals) |
| Austin open data — building footprints | https://data.austintexas.gov/browse?q=building%20footprint | Not extracted — same nav-shell issue | Same as above | Same | No | Same | Same, unresolved | Same |
| Texas Comptroller property tax | https://comptroller.texas.gov/taxes/property-tax/ | No bulk format info surfaced; page points to "Data Submission Requirements" subpage and says county appraisal districts are the actual data holders | N/A — comptroller does not host per-property bulk data directly, TCAD does | N/A | N/A | N/A | N/A — not a useful direct source, TCAD supersedes it | N/A |
| Overture Maps buildings | https://docs.overturemaps.org/guides/buildings/ | Building footprints with height and num_floors-style attributes referenced by the schema (exact field names not returned by this fetch — need the schema reference page); no year_built field in Overture buildings theme (it is not a property in OSM-derived building schema) | Cloud bulk download only: s3://overturemaps-us-west-2/release/.../theme=buildings/, Parquet format, queryable via DuckDB/Athena | Bulk (global dataset, filter by bounding box for Austin) | No login (public S3, pay-per-request egress only if applicable) | GeoParquet | 4-6 (need DuckDB spatial query per address, no year_built so only useful for stories/height) | ODbL (share-alike — check before redistributing derived output) |
| Texas Gas Service / Austin Energy open data | not fetched — no working URL supplied, and web search is exhausted so a URL could not be found this session | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown | Unknown |

## What actually panned out vs what needs a manual re-check

Confirmed useful:
- **TCAD bulk appraisal export and Improvement Details Report** are real, public, downloadable now, no login. This is the only source in this list confirmed today to plausibly carry year_built and sqft together, at the county level, in one file.

Dead ends / inconclusive this session (do not re-fetch blindly, needs a human click-through):
- traviscad.org/gis-data: 404. Try traviscad.org main nav for "GIS" or "Maps" link instead of the guessed URL.
- data.tnris.org: DNS failure, domain likely moved. Try tnris.org home page navigation for a "data" or "TxGIO" link (TNRIS was renamed Texas Geographic Information Office in recent years).
- data.austintexas.gov browse pages: returned only the Socrata site chrome, not actual dataset search results (browse pages are JS-rendered client-side, WebFetch cannot execute the search). Needs a headless browser (Playwright) or a direct Socrata SODA API query, e.g. hitting the Austin data portal's dataset API endpoint directly once a dataset ID is known, not the /browse search UI.
- comptroller.texas.gov: confirmed not a direct per-property data source; it defers to county CADs (i.e., TCAD). No further action needed here.
- Texas Gas Service / Austin Energy: no explicit URL was given and search is exhausted, so this was not checked. Unresolved.

## Recommendation for Saturday hackathon build

**Primary path: TCAD Certified Appraisal Export (bulk ZIP) + Improvement Details Report (CSV).**
- Fastest way to get year_built and square footage per address in Travis County.
- No login, no API key, just download and parse.
- Match by TCAD property ID or by parsing the situs address field in the export.
- Estimated wiring time: 3-5 hours for the appraisal export, or as little as 1-2 hours if the Improvement Details CSV alone has both fields (needs opening the file to confirm columns; the layout/schema doc on the same TCAD page explains column names).

**Fallback: Overture Maps buildings (Parquet, S3, public, no login).**
- Use only if TCAD's per-address matching proves too slow to wire up in the time box, or as a supplement for building height/number of stories, which TCAD's raw export may not cleanly expose.
- Overture does NOT carry year_built, so it cannot replace TCAD for that field — it is a stories/footprint fallback only, not a year_built fallback.

**Not recommended as primary:**
- Austin open data portal parcel/building-footprint datasets — plausible but unverified this session because the browse UI is JS-rendered and WebFetch could not see actual dataset results. Would need Playwright or a known dataset ID/SODA endpoint to confirm before relying on it Saturday.
- TNRIS/data.tnris.org — URL structure appears stale; needs a fresh URL before it is actionable.
- Texas Comptroller — not a direct source, skip.
- Gas service — unresolved, no source identified this session.

## Answer in one line for the build call

**Use the TCAD bulk appraisal export as the single source for year_built + sqft** (free, no login, per-parcel, ready today). Treat Overture Parquet buildings as backup for stories/footprint only, not for year built. Austin's open data portal and TNRIS need a follow-up look (Playwright or a corrected URL) before Saturday if more fields are wanted; do not block the build on them.
