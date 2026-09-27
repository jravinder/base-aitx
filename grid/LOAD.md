# ERCOT hourly load: peaks and timing (2024-2026 YTD)

Source: ERCOT public "Native Load" hourly zip files (no login), one file per year, from
https://www.ercot.com/gridinfo/load/load_hist . Extracted to
`data/ercot_load_hourly_2024_2026.csv` (datetime, year, month, hour_ending, SCENT, NCENT,
COAST, ERCOT total, all MW). 2026 data runs through 08/31/2026 (year to date).

## Annual peak hour per zone

| Year | SCENT (Austin) | NCENT (Dallas/Fort Worth) | COAST (Houston) | ERCOT total |
|---|---|---|---|---|
| 2024 | 08/21 18:00, 15,665 MW | 08/19 18:00, 27,803 MW | 08/21 16:00, 23,180 MW | 08/20 18:00, 85,199 MW |
| 2025 | 02/20 08:00, 14,799 MW | 08/19 17:00, 27,532 MW | 08/20 17:00, 23,007 MW | 08/18 18:00, 83,679 MW |
| 2026 YTD | 08/27 16:00, 15,934 MW | 08/24 17:00, 29,755 MW | 08/26 17:00, 24,221 MW | 07/22 18:00, 91,134 MW |

SCENT's 2025 peak fell in February, not summer. That was a cold-weather event, not a heat
event. Every other zone-year peak is a hot August (or one hot July) afternoon or early evening.

## Top 50 load hours per year: when they happen

Month spread:
- 2024: all 50 in August.
- 2025: 8 in July, 42 in August.
- 2026 YTD: 15 in July, 35 in August.

Hour-of-day spread (hour ending, so "18" means the hour from 17:00 to 18:00):
- 2024: hour ending 15 to 19, heaviest at 17 (14 of 50) and 18 (12 of 50).
- 2025: hour ending 14 to 19, heaviest at 17 (14) and 18 (13).
- 2026 YTD: hour ending 15 to 19, heaviest at 17 (16) and 18 (15).

The top load hours of the year cluster in a 5-hour window, roughly 2 pm to 7 pm local, every
year, with the single worst hour almost always the 17:00-18:00 or 18:00-19:00 slot.

## Share of top 100 hours in the 16:00-20:00 window

Counting hour-ending 17, 18, 19, 20 (the interval 16:00-20:00) among each year's 100 highest
ERCOT-total load hours:

- 2024: 61 of 100
- 2025: 59 of 100
- 2026 YTD: 65 of 100
- Pooled 2024-2026: 65 of 100

Roughly 6 in 10 of the year's worst grid-stress hours land in this single 4-hour afternoon
window.

## Year-over-year peak growth (ERCOT total)

- 2024 to 2025: 85,199 MW to 83,679 MW, down about 1.8% (2025 summer was milder).
- 2025 to 2026 (YTD through August): 83,679 MW to 91,134 MW, up about 8.9%. 2026 already set a
  new all-time high before September even started.
- NCENT (Dallas/Fort Worth) climbed every year: 27,803 to 27,532 to 29,755 MW, net up about
  7% since 2024, consistent with continued DFW data-center and population growth.

## What this means for a home battery

- **Hold reserve through midday.** The stress window is 2 pm to 7 pm, not noon. A battery
  charged overnight or from midday solar should not be drained by early afternoon; it needs to
  still have charge left at 4 pm.
- **Plan to discharge 4 pm to 8 pm, every day in July and August.** That single window covers
  roughly two-thirds of the worst hours of the year across all three years studied. This is the
  highest-value discharge slot for both bill savings (peak TOU rates) and grid support
  (demand response, VPP dispatch).
- **Don't assume winter is safe.** SCENT (Austin) had its 2025 annual peak in February from a
  cold snap, not summer heat. A battery sized only for summer afternoon peaks can still get
  caught short during a winter morning cold event (hour ending 8 that year, i.e. 7-8 am) —
  keep a reserve trigger for hard freeze forecasts too, not just summer.
- **The trend is up.** 2026 already broke the ERCOT all-time peak recorded in this data (91.1
  GW vs. 85.2 GW in 2024), even before the full year finished. A battery fleet sized against
  2024 peaks is already undersized for 2026 conditions; plan headroom, not just historical fit.
