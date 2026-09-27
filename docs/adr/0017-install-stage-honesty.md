# ADR 0017: Install stage uses Austin permits + #57 honesty

**Date:** 2026-09-27  
**Status:** Accepted  
**Issue:** #57

## Decision

Make the **Install** stage of the demo vertical real without inventing Oncor/CenterPoint contractor-named permits.

1. **Austin evidence:** surface Base Auxiliary Power permit milestones from `data/market.json` (issued → active/open → final, median applied→issued days, top zips by final) on `web/recovery.html` (Install stage) and a strip on `web/market.html`.
2. **Outside Austin:** load `data/base_footprint_cities.json` and say plainly that only Austin has a keyless, current, contractor-named feed. Star/Oncor zips keep territory + star estimates; install counts stay blank.
3. **Clearance path-to-yes** stays on the same page as pre-install checks; it is not presented as completed installs.
4. **Do not close #57** while the open-data ceiling remains. Advance with a PR comment: product hole for the demo is addressed; citywide contractor feeds outside Austin still need open records or Base data.

## Consequences

Judges can walk Lead → Photo → Permit → Install → Grid and see a concrete install stage. Claiming Base installs in Round Rock / Cedar Park / Houston from open data remains forbidden.
