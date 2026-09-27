# Permit lookup research: cities outside Austin (Issue #33)

Method: WebFetch on named city and portal URLs only (no live web search, no login, no code beyond this probe). Many city sites are JS-heavy and did not expose deep links to WebFetch's static fetch. Findings below are honest about what was confirmed vs. not found.

| City | Portal found | Type | Search by address (no login) | API/JSON seen | Licence |
|---|---|---|---|---|---|
| Round Rock | permits.roundrocktexas.gov | Custom portal, vendor "Timmons Group" (footer credit) | Unknown. Site was in maintenance mode at fetch time; a login prompt is shown on the front page | None seen | None seen |
| Pflugerville | Not located. Home page has an "Online Services" section but no direct permit link surfaced | Unknown | Unknown | Unknown | Unknown |
| Georgetown | Not fetchable. georgetown.org and www.georgetown.org both fail TLS validation (certificate mismatch to an Azure Web App hostname) from this tool | Unknown | Unknown | Unknown | Unknown |
| Hutto | huttotx.gov has a "Development & Construction" and "Building Inspections & Permitting" nav item, but the underlying portal URL did not resolve in the fetched page content | Unknown | Unknown | Unknown | Unknown |
| Cedar Park | cedarparktexas.gov has a "Forms & Applications" page (/653/Forms-Permits-Applications), but that specific URL 404'd or returned unrelated content (a fire department staff bio, likely a CMS ID collision) | Unknown | Unknown | Unknown | Unknown |
| Leander | leandertx.gov has a "Forms & Applications" section referenced; no permit portal URL surfaced in fetched content | Unknown | Unknown | Unknown | Unknown |
| Williamson County (data-wilco.opendata.arcgis.com) | ArcGIS Hub confirmed to exist at that host | Open data hub | Not confirmed. Page returned only a bare title, no dataset list, in this fetch | Not confirmed | Not confirmed |
| MyGov (mygov.us) | mygov.us now 301-redirects to empower.tylertech.com/mygov (Tyler Technologies rebrand) | Vendor SaaS | Not checked further (redirect not followed this pass) | Not checked | Not checked |
| Accela (aca-prod.accela.com/<city>) | Tried ROUNDROCK agency code, got HTTP 404 | Accela Citizen Access | Not confirmed for any of the 6 cities. Agency codes were guessed, not verified | Not applicable | Not applicable |

## What this pass could not do
WebFetch converts pages to a static markdown snapshot and cannot execute the JavaScript that most of these city CMS platforms (mostly CivicPlus/Granicus templates) use to render department sub-navigation and embedded portal widgets. Several guessed URLs (Accela agency codes, direct city permit subpages) 404'd because the real paths are not guessable and were not discoverable without either a live browser render or a search engine, both of which were out of scope for this pass.

## Recommendation
Round Rock is the best lead: it has one confirmed, dedicated permit-tracker subdomain (permits.roundrocktexas.gov) rather than a generic city-CMS page, meaning it is a single stable entry point to wire against once it is back from maintenance and once login/anonymous-search behavior is confirmed with a real browser session. Before Saturday, re-run this check with a headless browser (Playwright) against permits.roundrocktexas.gov to see the live login wall and whether an anonymous "public search" mode exists, since Timmons Group permit portals commonly offer one. If it requires login, fall back to checking Williamson County's ArcGIS Hub directly in a browser for a possible county-wide permits layer covering Round Rock, Hutto, and Cedar Park addresses without any city-specific integration.

## Base footprint outside Austin (Issue #54 track 4, 2026-09-26)

Goal: for each city in Base Power's markets, check whether an open permit feed exists, whether it names the contractor, whether it's keyless, and if so count Base Power permits by month in 2026. Aggregate queries only, no full dataset downloads. Script: `house/permits_other_cities.py`. Data: `data/base_footprint_cities.json`.

| City | Utility | Feed exists | URL | Names contractor | Base Power 2026 count |
|---|---|---|---|---|---|
| Austin | Austin Energy | Yes | data.austintexas.gov/resource/3syk-w9eu.json | Yes (`contractor_trade`) | ~300 (Aug-Sep 2026, prior work) |
| Houston | CenterPoint | Yes, but pre-aggregated | data.houstontx.gov/dataset/residential-building-permits | No | Cannot count, no contractor field |
| Dallas | Oncor | Yes, but stale | www.dallasopendata.com/resource/e7gq-4sah.json | Yes (`contractor`) | 0 (dataset tops out at 2019-12-31) |
| Fort Worth | Oncor | No | data.fortworthtexas.gov redirects to hub.arcgis.com/legacy | N/A | No open feed found |
| Arlington | Oncor | Yes | ArcGIS FeatureServer, OD_Property/MapServer/1 | No | 0 matches on NameofBusiness, but that field is not the contractor |
| Plano | Oncor | No | data-planogis.opendata.arcgis.com (catalog feed errored) | N/A | No open feed found |
| Frisco | Oncor | No | geodata-frisco.hub.arcgis.com (35 datasets, none are permits) | N/A | No open feed found |
| McKinney | Oncor | No | mckinneygis-mck.opendata.arcgis.com (56 datasets, only Health Food and Hunting permits) | N/A | No open feed found |
| San Antonio | CPS Energy | Yes | data.sanantonio.gov/dataset/building-permits (CKAN datastore_search_sql) | Weak (`PRIMARY CONTACT`, not documented as contractor) | 0 across PRIMARY CONTACT / PROJECT NAME / WORK TYPE |
| Round Rock | Oncor | No (unchanged from prior pass) | permits.roundrocktexas.gov | N/A | No open feed found |
| Georgetown | Oncor | No (unchanged) | TLS failure | N/A | No open feed found |
| Pflugerville | Oncor | No (unchanged) | none surfaced | N/A | No open feed found |
| Cedar Park | Oncor | No (unchanged) | 404 on Forms & Permits page | N/A | No open feed found |

### Notes
- Dallas and Arlington both have live, keyless, queryable feeds, but neither can answer the Base Power question: Dallas's contractor field exists but the data is 6+ years stale, and Arlington's schema has no contractor field at all.
- San Antonio's feed works and is current, but the closest field to a contractor name (`PRIMARY CONTACT`) is undocumented and returned 0 hits for Base Power, Base battery work, or "BATTERY" in the work-type/project-name fields. Treat as inconclusive, not a confirmed zero footprint.
- Houston's only open permit dataset is pre-aggregated by month/year with no contractor column, so CenterPoint-market activity is invisible from open data regardless of whether Base Power is filing there.
- Fort Worth, Plano, Frisco, and McKinney each have a GIS/open-data presence but no discoverable permits dataset within the 10-minute budget per city.
- Round Rock, Georgetown, Pflugerville, and Cedar Park were re-checked briefly and remain unchanged from the prior pass documented above: no usable open feed.
- Only Austin currently supports the full ask (contractor-named, keyless, monthly Base Power counts for 2026).

## Product surface (2026-09-27)

Install stage UI: `web/recovery.html` reads this research via `data/base_footprint_cities.json` and pairs it with Austin `data/market.json` milestones. See `docs/adr/0017-install-stage-honesty.md`. Data ceiling unchanged: only Austin names the contractor in a current keyless feed (#57).
