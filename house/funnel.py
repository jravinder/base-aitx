"""Per-zip funnel from households to easy-fit Base homes.

These are ESTIMATES built from public aggregates (Census ACS, city permit
counts, the TDU zip table). They are not surveys and not parcel counts.
No public record says where a panel is or what size it is.

Stages, for each zip in house/territory.py ZIP_TABLE:

  1. households                 ACS households in the zip
  2. owner_sfd                  min(owner_occupied, single_family_detached)
  3. in_territory               owner_sfd x offer weight x zip confidence
                                weight x TDU confidence weight
                                (offer: energy_and_backup 1.0,
                                 backup_only 0.5, mixed 0.6,
                                 not_served 0;
                                 confidence: HIGH 1.0 / MEDIUM 0.7 / LOW 0.4)
  4. likely_200a                in_territory x 200A share
                                share = (new_sfr + service_upgrade) / permits
                                when the permit feed covers the zip with
                                at least MIN_PERMITS rows (small counts are
                                Austin-feed spillover, not coverage);
                                else a build-year proxy:
                                0.8 if median_year_built >= 2000,
                                0.5 if >= 1980, else 0.3
  5. easy_fit                   likely_200a x (easy / cohort size)
                                from house/cohort.json (22 of 40 today)
  star = easy_fit

Inputs:  data/demographics.json, data/permits_by_zip.json
         (falls back to data/funnel.fixture.json when they are absent)
Output:  data/funnel.json

Run:  python3 house/funnel.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from house.territory import ZIP_TABLE, zip_status  # noqa: E402

DEMO_PATH = os.path.join(ROOT, "data", "demographics.json")
PERMIT_PATH = os.path.join(ROOT, "data", "permits_by_zip.json")
FIXTURE_PATH = os.path.join(ROOT, "data", "funnel.fixture.json")
COHORT_PATH = os.path.join(HERE, "cohort.json")
OUT_PATH = os.path.join(ROOT, "data", "funnel.json")

CONF_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.4}

# backup_only = 0.5 is a judgment, not a measured rate. The offer is
# confirmed (Austin Energy 2026-05-19, Base launch 2026-07-15), but:
#   - the program is capped at 40 MW and Base says "Capacity is limited";
#   - the home pays $695 + $19/mo for backup only, with no energy-rate
#     savings to offset it, so fewer homes will say yes than on
#     Energy + Backup.
# mixed = 0.6 is also a judgment: part of the zip is a competitive TDU
# (Energy + Backup), the rest is a muni, co-op, or Austin Energy. No
# public source gives the split inside the zip.
OFFER_WEIGHT = {"energy_and_backup": 1.0, "backup_only": 0.5, "mixed": 0.6, "not_served": 0.0}
OFFER_WHY = {
    "energy_and_backup": "Base can be the energy provider (Energy + Backup)",
    "backup_only": ("battery only, utility stays the provider; offer weight 0.5 "
                    "because the 40 MW program is capacity-limited and backup-only "
                    "has no rate savings to offset $695 + $19/mo"),
    "mixed": ("part of the zip is a competitive TDU (Energy + Backup), the rest is "
              "another utility; offer weight 0.6 is a judgment, no public source "
              "gives the split inside the zip"),
    "not_served": "no Base offer found",
}
MIN_PERMITS = 100


def _rows(path, key):
    with open(path) as f:
        return {str(r["zip"]): r for r in json.load(f)[key]}


def load_inputs():
    """Return (demographics, permits, source_label).

    Each input falls back to data/funnel.fixture.json on its own when the
    real file is absent.
    """
    fx = None
    if not (os.path.exists(DEMO_PATH) and os.path.exists(PERMIT_PATH)):
        with open(FIXTURE_PATH) as f:
            fx = json.load(f)
    src = []
    if os.path.exists(DEMO_PATH):
        demo = _rows(DEMO_PATH, "rows")
        src.append("demographics=real")
    else:
        demo = {str(r["zip"]): r for r in fx["demographics"]}
        src.append("demographics=fixture")
    if os.path.exists(PERMIT_PATH):
        perm = _rows(PERMIT_PATH, "rows")
        src.append("permits=real")
    else:
        perm = {str(r["zip"]): r for r in fx["permits"]}
        src.append("permits=fixture")
    return demo, perm, ", ".join(src)


def easy_share():
    with open(COHORT_PATH) as f:
        cohort = json.load(f)
    easy = sum(1 for h in cohort if h.get("fit", {}).get("bucket") == "easy")
    return easy, len(cohort)


def assisted(z, d, status):
    """Assisted-onboarding priority: share of people 65+ or with a
    disability (ACS B01001 + B18101 under-65 disabled, so no double count)
    x the offer weight for the zip status. Score is on a 0-100 scale."""
    pop, old, dis = d.get("population"), d.get("pop_65plus"), d.get("pop_disabled_under65")
    if not pop or old is None or dis is None:
        return None, "ACS age or disability data missing for this zip"
    share = (old + dis) / pop
    w = OFFER_WEIGHT[status]
    score = round(share * w * 100, 1)
    why = (f"{old:,} people 65+ and {dis:,} under 65 with a disability of {pop:,} "
           f"(ACS B01001, B18101) = {share:.0%}; x {status} weight {w:.1f} -> {score}")
    return score, why


def funnel_for_zip(z, demo, perm, easy, total):
    tdu, city, county, conf, note, mixed_with = ZIP_TABLE[z]
    status, tdu_conf, tdu_src = zip_status(z)
    eligible = status in ("energy_and_backup", "mixed")
    if mixed_with:
        tdu = f"{tdu} + {mixed_with}"
    d = demo.get(z)
    if d is None:
        return None

    households = int(d["households"])
    owner_sfd = min(int(d["owner_occupied"]), int(d["single_family_detached"]))

    w = OFFER_WEIGHT[status] * CONF_WEIGHT[conf] * CONF_WEIGHT[tdu_conf]
    in_territory = owner_sfd * w

    p = perm.get(z)
    if p and p.get("covered") and (p.get("permits") or 0) >= MIN_PERMITS:
        share = (p["new_sfr"] + p["service_upgrade"]) / p["permits"]
        share_why = (
            f"permit feed covers this zip: {p['new_sfr']} new SFR + "
            f"{p['service_upgrade']} service upgrades of {p['permits']} permits "
            f"= {share:.0%} likely 200A"
        )
    else:
        yb = int(d["median_year_built"])
        share = 0.8 if yb >= 2000 else 0.5 if yb >= 1980 else 0.3
        share_why = (
            f"permit feed has under {MIN_PERMITS} rows for this zip; build-year proxy: median year built "
            f"{yb} -> {share:.0%} likely 200A"
        )
    likely_200a = in_territory * share

    easy_fit = likely_200a * easy / total

    stages = [
        {
            "key": "households",
            "label": "Households",
            "count": households,
            "why": f"ACS households in {z} ({city}, {county} County)",
        },
        {
            "key": "owner_sfd",
            "label": "Owner-occupied single-family",
            "count": owner_sfd,
            "why": (
                f"min of owner-occupied ({d['owner_occupied']}) and "
                f"single-family detached ({d['single_family_detached']})"
            ),
        },
        {
            "key": "in_territory",
            "label": "In Base territory",
            "count": round(in_territory),
            "why": (
                f"{tdu} is {status}: {OFFER_WHY[status]} "
                f"[{OFFER_WEIGHT[status]:.1f}]; zip confidence {conf} "
                f"[{CONF_WEIGHT[conf]:.1f}] ({note}); TDU confidence {tdu_conf} "
                f"[{CONF_WEIGHT[tdu_conf]:.1f}] ({tdu_src}) -> weight {w:.2f}"
            ),
        },
        {
            "key": "likely_200a",
            "label": "Likely 200A service",
            "count": round(likely_200a),
            "why": share_why,
        },
        {
            "key": "easy_fit",
            "label": "Easy fit",
            "count": round(easy_fit),
            "why": f"{easy} of {total} cohort homes were easy fit -> x {easy/total:.2f}",
        },
    ]
    ap, ap_why = assisted(z, d, status)
    return {
        "zip": z,
        "city": city,
        "county": county,
        "tdu": tdu,
        "status": status,
        "eligible": eligible,
        "confidence": conf,
        "star": round(easy_fit),
        "assisted_priority": ap,
        "assisted_why": ap_why,
        "stages": stages,
    }


def main():
    demo, perm, source = load_inputs()
    easy, total = easy_share()
    rows = []
    for z in sorted(ZIP_TABLE):
        r = funnel_for_zip(z, demo, perm, easy, total)
        if r:
            rows.append(r)
    rows.sort(key=lambda r: -r["star"])
    out = {
        "note": (
            "Estimates from public aggregates (ACS, permit counts, TDU table). "
            "Not surveys, not parcel counts. No public record says where the panel is."
        ),
        "inputs": source,
        "easy_share": {"easy": easy, "total": total},
        "territory_zips": sorted(
            z for z in ZIP_TABLE if zip_status(z)[0] == "energy_and_backup"
        ),
        "mixed_zips": sorted(z for z in ZIP_TABLE if zip_status(z)[0] == "mixed"),
        "backup_only_zips": sorted(
            z for z in ZIP_TABLE if zip_status(z)[0] == "backup_only"
        ),
        "rows": rows,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {OUT_PATH} ({len(rows)} zips, inputs={source})")
    for r in rows[:10]:
        print(f"  {r['zip']} {r['city']:<28} {r['status']:<18} star={r['star']}")


if __name__ == "__main__":
    main()
