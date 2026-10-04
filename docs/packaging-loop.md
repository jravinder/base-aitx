# Packaging loop

Reader: a Base Power data engineering hiring manager with a link and 2 minutes.
Package: `web/start.html`, `web/grid.html?track=home&persona=operations` (ERCOT), `web/judgments.html?track=home&persona=operations` (Permits), README first screen, repo layout.
Scores are taken at the start of each loop, before its fix: (a) 10-second test, (b) one click to the ERCOT pipeline, (c) README first screen, (d) credibility, (e) repo hygiene.

## Loop 1
- Scores: a 3 · b 2 · c 2 · d 4 · e 2 = **13**
- Why: landing headline "Two things built on Base in one weekend" never names the pipeline; the ERCOT pipeline is only a footer link. README opened as a hackathon entry with track bullets; the warehouse section sat ~160 lines down. Repo tracks 6 stray screenshots under `private/tmp/...scratchpad/` and `warehouse/dbt/.user.yml`.
- Fix: README first screen rewritten: one-paragraph pipeline pitch with the measured result, a 3-row "See it (2 min)" table of live links, a Measured / Upper bound / Simulation line, run + rebuild + tests commands. Nothing below changed.
- Verify: pytest 40 passed; public-entry, persona-navigation, home-admin-focused PASS.
- Screenshots: before `docs/screenshots/packaging/loop-1-before-{start,grid,permits}-{1440,390}.png`; after `docs/screenshots/packaging/loop-1-after-readme.png`.

## Loop 2
- Scores: a 3 · b 2 · c 4 · d 4 · e 2 = **15**
- Why: README now pitches the pipeline, but a visitor who opens the landing page still sees no pipeline until the footer.
- Fix: a "The data underneath: an ERCOT pipeline" band below the two cards on `web/start.html`: three tagged numbers (1.67M ERCOT rows, Measured; 22% in 88 hours, Upper bound; 34 of 34 injected faults, Simulation) and a "See the pipeline" button (`#pipeline-link`) to `grid.html?track=home&persona=operations`. It sits outside `<main>` and uses no `h2`, so the entry test's two-card contract (7 links in main, two h2s, tab order) holds. On a 1440×900 screen it shows without scrolling.
- Verify: 0 console errors at 1440/390, no horizontal scroll; public-entry, persona-navigation, home-admin-focused PASS.
- Screenshots: `docs/screenshots/packaging/loop-2-after-start-{1440,390}.png` (full page).

## Loop 3
- Scores: a 4 · b 4 · c 4 · d 4 · e 2 = **18**
- Why: (e) is the lowest, but its fix (removing the stray `private/tmp/.../scratchpad/entry/*.png` files and `warehouse/dbt/.user.yml` from the tree) was denied to this agent as a local deletion; it is left for the maintainer (`git rm -r --cached private warehouse/dbt/.user.yml`, then add both to `.gitignore`). Next-highest: the README's ERCOT link goes to the live Vercel site, which still serves the pre-pipeline `grid.html` (checked: `build_ercot_warehouse` absent from the live HTML), so a GitHub reader who clicks lands on an older page.
- Fix: the README first screen now shows a settled 1440 screenshot of the ERCOT page (`docs/screenshots/ercot/grid-first-screen-1440.png`), linked to the live page, so the proof is visible on GitHub without a click.
- Verify: README rendered with GitHub markdown CSS; image loads.
- Screenshots: before `docs/screenshots/packaging/loop-3-before-grid-1440-settled.png`; after `docs/screenshots/packaging/loop-3-after-readme.png`.

## Loop 4
- Scores: a 4 · b 4 · c 5 · d 4 · e 2 = **19**
- Why: 18 top-level folders with no map; a reader cannot tell which one is the pipeline. (Tracked junk still open, blocked for this agent.)
- Fix: an 8-row "Repo map" table right after the README first screen, `warehouse/` first.
- Verify: pytest 40 passed; README render below.
- Screenshot: `docs/screenshots/packaging/loop-4-after-readme.png`.

## Loop 5 (assessment only, then stop)
- Scores: a 4 · b 4 · c 5 · d 4 · e 3 = **20** (13 → 15 → 18 → 19 → 20)
- Every remaining point is outside what this loop may do, so I stopped here rather than spend two loops proving that:
  - **(e) 3 → 5:** untrack `private/tmp/.../scratchpad/entry/*.png` (6 stray screenshots) and `warehouse/dbt/.user.yml`, then ignore both. Needs `git rm --cached`; the delete was denied to this agent.
  - **(d) 4 → 5:** deploy this branch. The live `grid.html` still serves the pre-pipeline page, so every live link in the README and on the landing page undersells the work until a deploy.
  - **(a) 4 → 5:** the landing H1 ("Two things built on Base in one weekend.") and its two-card layout are pinned by `tests/public-entry.cjs` (H1 text, 7 links in `<main>`, exactly two `h2`, tab order). A data-engineering headline means changing that test contract, which is the owner's call.
- Ceiling: a 5/5 package for this reader also wants things no copy loop can make: a 60-second screen recording of `python3 -m warehouse.build` running, CI badges from a real CI run of pytest + dbt build, and a clean history (the 2.6 MB full-page PNGs in `docs/screenshots/ercot/` and the stray files stay in git history even after untracking).
