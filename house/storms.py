"""Storm surges in backup-power permits (City of Austin permit feed).

Input:  data/mirror/energy_permits.csv.gz (applied_date by month)
        data/funnel.json (star = easy-fit homes per zip)
        data/demographics.json (owner-occupied single-family, for the rate)
Output: data/storms.json

Backup categories: generator, battery, solar_battery.
Baseline: mean monthly count in calendar 2020 (the year before Uri).
Surge multiple = month count / 2020 baseline.
Pre-storm multiple = month count / mean of the 3 months before the storm.
Duration = consecutive months, starting in the storm month or the month
after, with count at or above 1.5x the pre-storm 3-month mean.
Peak = highest month in the surge window, capped at 12 months from the storm.

Storm readiness (ESTIMATE):
  permit-ready homes = funnel star (easy-fit homes) in served zips
  (status energy_and_backup, mixed, backup_only).
  March 2023 excess = March 2023 count - pre-storm 3-month mean.
  rate = excess / owner-occupied single-family homes in the zips of the
  permit feed (City of Austin jurisdiction).
  surge per week = permit-ready homes x rate / (31 / 7).
Run: python3 house/storms.py
"""

import csv
import gzip
import json
import os
from collections import Counter
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATS = ("generator", "battery", "solar_battery")
STORMS = [("2021-02", "Winter storm Uri"), ("2023-02", "Austin ice storm")]
SERVED = ("energy_and_backup", "mixed", "backup_only")


def prev(m, n):
    y, mo = int(m[:4]), int(m[5:])
    out = []
    for _ in range(n):
        mo -= 1
        if mo == 0:
            y, mo = y - 1, 12
        out.append(f"{y:04d}-{mo:02d}")
    return out


def nxt(m, n):
    y, mo = int(m[:4]), int(m[5:]) + n
    y, mo = y + (mo - 1) // 12, (mo - 1) % 12 + 1
    return f"{y:04d}-{mo:02d}"


def months(a, b):
    out, y, mo = [], int(a[:4]), int(a[5:])
    while f"{y:04d}-{mo:02d}" <= b:
        out.append(f"{y:04d}-{mo:02d}")
        mo += 1
        if mo == 13:
            y, mo = y + 1, 1
    return out


def main():
    tot, by_cat, base_cnt, zips_feed = Counter(), Counter(), Counter(), set()
    with gzip.open(os.path.join(ROOT, "data/mirror/energy_permits.csv.gz"), "rt") as f:
        for r in csv.DictReader(f):
            zips_feed.add(r["zip"])
            if r["category"] not in CATS or not r["applied_date"]:
                continue
            m = r["applied_date"][:7]
            tot[m] += 1
            by_cat[(m, r["category"])] += 1
            if r["is_base"] == "1":
                base_cnt[m] += 1
    last = max(tot)
    series = [{"month": m, "count": tot[m], "base": base_cnt[m],
               **{c: by_cat[(m, c)] for c in CATS}} for m in months("2019-01", last)]
    baseline = sum(tot[m] for m in months("2020-01", "2020-12")) / 12
    for s in series:
        s["multiple"] = round(s["count"] / baseline, 1)

    storms = []
    for m, name in STORMS:
        pre = sum(tot[p] for p in prev(m, 3)) / 3
        # permits lag the storm: the run starts in the storm month or the next
        # month, and holds while the count is >= 1.5x the pre-storm mean
        run = []
        for cur in months(m, last):
            if tot[cur] >= 1.5 * pre:
                run.append(cur)
            elif run or cur > nxt(m, 1):
                break
        win = [x for x in (run or months(m, nxt(m, 2))) if x <= nxt(m, 11)]
        peak = max(win, key=lambda x: tot[x])
        # generator is the ice-storm signal; show the lead category
        lead = max(CATS, key=lambda c: sum(by_cat[(x, c)] for x in months(m, nxt(m, 2)) if x <= last))
        storms.append({
            "month": m, "name": name, "count": tot[m],
            "multiple": round(tot[m] / baseline, 1),
            "pre_storm_3mo_mean": round(pre, 1),
            "pre_storm_multiple": round(tot[m] / pre, 1),
            "peak_month": peak, "peak_count": tot[peak],
            "peak_multiple": round(tot[peak] / baseline, 1),
            "surge_months": len(run), "surge_window": [run[0], run[-1]] if run else None,
            "still_elevated": bool(run) and run[-1] == last,
            "lead_category": lead,
        })
    storm_months = set()
    for s in storms:
        storm_months |= set(months(s["month"], nxt(s["month"], 2)))
    over4 = [{"month": s["month"], "count": s["count"], "multiple": s["multiple"],
              "base": s["base"]} for s in series if s["multiple"] > 4]

    # readiness estimate
    funnel = json.load(open(os.path.join(ROOT, "data/funnel.json")))
    demo = {r["zip"]: r for r in json.load(open(os.path.join(ROOT, "data/demographics.json")))["rows"]}
    feed_sfd = sum(min(demo[z]["owner_occupied"] or 0, demo[z]["single_family_detached"] or 0)
                   for z in zips_feed if z in demo)
    ice = next(s for s in storms if s["month"] == "2023-02")
    excess = tot["2023-03"] - ice["pre_storm_3mo_mean"]
    rate = excess / feed_sfd
    ready = []
    for r in funnel["rows"]:
        if r["status"] not in SERVED:
            continue
        ready.append({"zip": r["zip"], "city": r["city"], "status": r["status"],
                      "permit_ready_homes": r["star"],
                      "surge_per_week_est": round(r["star"] * rate / (31 / 7), 2)})
    ready.sort(key=lambda x: -x["surge_per_week_est"])
    out = {
        "source": "data/mirror/energy_permits.csv.gz (City of Austin permits, applied_date)",
        "built": date.today().isoformat(),
        "categories": list(CATS),
        "baseline_2020_monthly": round(baseline, 1),
        "storms": storms,
        "months_over_4x": over4,
        "note_over_4x": ("After Uri the monthly count never went back to the 2020 level. "
                         "Most months from 2021-02 on are over 4x the 2020 baseline. "
                         "2026-08 is Base Backup Only installs (is_base=1), not a storm."),
        "readiness": {
            "label": "ESTIMATE",
            "method": ("permit-ready homes = funnel star (easy-fit) in served zips; "
                       "March 2023 excess permits over the pre-storm 3-month mean, "
                       "divided by owner-occupied single-family homes in the permit-feed zips, "
                       "gives a per-home monthly rate; per week = x 7/31"),
            "march_2023_count": tot["2023-03"],
            "march_2023_excess": round(excess, 1),
            "feed_owner_sfd_homes": feed_sfd,
            "rate_per_home_month": round(rate, 6),
            "total_permit_ready": sum(x["permit_ready_homes"] for x in ready),
            "total_surge_per_week_est": round(sum(x["surge_per_week_est"] for x in ready), 1),
            "zips": ready,
        },
        "series": series,
    }
    json.dump(out, open(os.path.join(ROOT, "data/storms.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("baseline_2020_monthly", "storms")}, indent=1))
    print(len(over4), "months over 4x;", {k: v for k, v in out["readiness"].items() if k != "zips"})
    for x in ready[:8]:
        print(x)


if __name__ == "__main__":
    main()
