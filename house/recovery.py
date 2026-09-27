"""Denial recovery packet (issue #38).

When a house is not a fit today, list what blocks it and the path to yes.
Blocking reasons come only from the existing rules:

  - fit()               in house/permits.py  (bucket "needs_love" reasons,
                        already stored in house/cohort.json)
  - estimate_clearance() in house/clearance.py (the three DEMO_CASES)

For each reason: the fix in plain words, who does it (member, electrician,
Base), whether a City of Austin permit is needed and which type, and what
the permit record will show after. Austin permit types are the
permit_type_desc and work_class values in the city feed (Socrata 3syk-w9eu)
that house/permits.py and house/mirror.py already read.

Costs: no repo source prices these fixes, so every step says
"cost not estimated".

Run from the repo root:
  python3 -m house.recovery        writes web/data/recovery.json
"""

import json
import re
from datetime import date
from pathlib import Path

from house import clearance as C

ROOT = Path(__file__).resolve().parent.parent
COHORT = ROOT / "house" / "cohort.json"
OUT = ROOT / "web" / "data" / "recovery.json"

NO_COST = "cost not estimated"

# Austin permit types, as the city feed names them.
EP_UPGRADE = "Electrical Permit, work class Upgrade (number ends in EP)"
EP_AUX = "Electrical Permit, work class Auxiliary Power (number ends in EP)"
EP_OTHER = "Electrical Permit (number ends in EP); work class not confirmed in repo sources"

# BATTERY_RE in permits.py also matches "storage" and "ess". A match whose
# text names none of these words may be a storage shed, not a battery.
REAL_ENERGY_RE = re.compile(
    r"\bsolar\b|\bpv\b|\bphotovoltaic\b|\bbattery\b|\bpowerwall\b|energy storage|\bess\b|\binverter\b",
    re.IGNORECASE,
)


def step(action, who, unblocks, permit_needed, permit_type, record_after, base_can=None):
    return {
        "action": action,
        "who": who,
        "unblocks": unblocks,
        "permit": {"needed": permit_needed, "type": permit_type},
        "record_after": record_after,
        "base_can": base_can,
        "cost": NO_COST,
    }


NO_PERMIT_RECORD = "Nothing new. This step does not go on the city permit record."


# ---------------------------------------------------------------------------
# Fit rule reasons (house/permits.py fit())
# ---------------------------------------------------------------------------

def solar_battery_steps(evidence):
    steps = []
    doubtful = [e for e in evidence if not REAL_ENERGY_RE.search(e["text"] or "")]
    if doubtful:
        p = ", ".join(e["permit"] for e in doubtful)
        steps.append(step(
            f"Check permit {p}. The rule matched the word \"storage\" or similar, and the text does not name solar or a battery. It may be a shed.",
            "Base",
            "If there is no solar or battery at the house, the fit rule runs again without this reason.",
            False, None, NO_PERMIT_RECORD,
            base_can="Read the permit text and ask the member one yes or no question.",
        ))
    steps.append(step(
        "Send a photo of the existing solar inverter or battery label, and a photo of the main panel with the door open.",
        "member",
        "Lets Base engineers see the make and how it ties into the panel.",
        False, None, NO_PERMIT_RECORD,
    ))
    steps.append(step(
        "Engineers review how a Base battery can connect next to the existing system, and for how many batteries (0, 1, or 2).",
        "Base",
        "Turns \"interconnect complexity\" into a yes or no with a plan.",
        False, None, NO_PERMIT_RECORD,
        base_can="Base lists solar and generator integrations in its help center, and its engineers confirm each home (faq/corpus).",
    ))
    steps.append(step(
        "Install the Base battery with the interconnect to the existing system.",
        "Base",
        "The house is backed up.",
        True, EP_AUX,
        "A new Auxiliary Power electrical permit for the address. Base permits in Austin read \"BASE: Installing a backup battery system\" (316 of 324 Base permits in data/mirror use this work class).",
        base_can="Base pulls the permit and does the install.",
    ))
    return steps


def panel_steps(reason):
    return [
        step(
            "Send one photo of the main breaker, close enough to read the amp number.",
            "member",
            "If it reads 200 A, the house needs no upgrade and Base can clear it from the photo.",
            False, None, NO_PERMIT_RECORD,
        ),
        step(
            "If the main breaker is under 200 A, upgrade the electric service to 200 A.",
            "electrician",
            "Removes \"" + reason + "\". The fit rule treats a service upgrade since 2010 as the easy case.",
            True, EP_UPGRADE,
            "A service upgrade event with a date after 2015. The fit rule then reads \"easy\".",
        ),
        step(
            "Run the fit check again with the new permit or the photo.",
            "Base",
            "Moves the house from \"needs love\" to \"easy\".",
            False, None, "Nothing new. Base reads the record; it does not add to it.",
            base_can="Base's own amp limit is not public (help-center gap in faq/corpus), so Base confirms it at review.",
        ),
    ]


def house_blockers(h):
    blockers = []
    for reason in h["fit"]["reasons"]:
        if reason == "existing solar or battery adds interconnect complexity":
            ev = [
                {"permit": e["permit"], "date": (e["date"] or "")[:10], "kind": e["kind"], "text": e["text"]}
                for e in h["events"] if e["kind"] in ("solar", "battery")
            ]
            blockers.append({
                "reason": "Existing solar or battery on the permit record. It adds interconnect work.",
                "rule": "house/permits.py fit(): has_solar or has_battery -> needs_love",
                "evidence": ev,
                "steps": solar_battery_steps(ev),
            })
        elif reason in ("no electrical permit activity since 2015", "likely 100 A, no record"):
            ev = [
                {"permit": e["permit"], "date": (e["date"] or "")[:10], "kind": e["kind"], "text": e["text"]}
                for e in h["events"] if e["kind"] in ("service_upgrade", "sub_panel")
            ]
            blockers.append({
                "reason": "No service upgrade on file since 2015. The panel may be an older, smaller one.",
                "rule": f"house/permits.py fit(): \"{reason}\" -> needs_love",
                "evidence": ev,
                "steps": panel_steps(reason),
            })
        else:
            blockers.append({"reason": reason, "rule": "house/permits.py fit()", "evidence": [],
                             "steps": [], "note": "No recovery steps written for this reason yet."})
    return blockers


# ---------------------------------------------------------------------------
# Clearance rule reasons (house/clearance.py)
# ---------------------------------------------------------------------------

def site_check_step(unblocks):
    return step(
        "Send a site tech to measure the side yard, the wall near the electric meter, and the distance to the gas meter, A/C unit, and fence.",
        "Base",
        unblocks,
        False, None, NO_PERMIT_RECORD,
        base_can="Base finds \"a clean, code-compliant spot for your system close to your electric meter\" (faq/corpus/how-it-works.md).",
    )


def photo_step(photo):
    return step(
        photo.replace("Please take", "Take"), "member",
        "Replaces the lot-shape estimate with what is really on the wall.",
        False, None, NO_PERMIT_RECORD,
    )


def move_meter_step():
    return step(
        "If no wall near the meter has room, move the electric meter and main panel to a wall that has 9 ft clear.",
        "electrician",
        "Gives the battery a wall that passes the 9 ft and 3 ft rules.",
        True, EP_OTHER,
        "A new electrical permit for the address for the meter and panel move.",
    )


def clearance_blockers(kw, res):
    lot, foot = kw["lot_sqft"], kw["footprint_sqft"]
    cov = foot / lot
    wall, side = res["wall_estimate_ft"], res["side_setback_ft_estimate"]
    photo = res["photo_to_ask"]
    out = []
    if cov > C.HIGH_COVERAGE_RATIO:
        out.append({
            "reason": f"The house covers {cov:.0%} of the lot, over the {C.HIGH_COVERAGE_RATIO:.0%} limit. The side yard is likely built out to the property line.",
            "rule": "house/clearance.py: footprint / lot > HIGH_COVERAGE_RATIO -> unlikely",
            "evidence": [],
            "steps": [
                photo_step(photo),
                site_check_step(f"Confirms whether there is {C.FENCE_SETBACK_FT:.0f} ft to the fence and {C.WALL_FT_PER_BATTERY:.0f} ft of wall. The estimate cannot."),
                move_meter_step(),
            ],
        })
    if lot < C.SMALL_LOT_SQFT and kw.get("garage_detached"):
        out.append({
            "reason": f"Lot under {C.SMALL_LOT_SQFT:,} sq ft with a detached garage. The rule cannot decide without a site check.",
            "rule": "house/clearance.py: lot < SMALL_LOT_SQFT and garage_detached -> unclear",
            "evidence": [],
            "steps": [photo_step(photo), site_check_step("Gives a measured answer in place of \"unclear\".")],
        })
    if side < C.FENCE_SETBACK_FT:
        out.append({
            "reason": f"Side setback estimate {side} ft is under the {C.FENCE_SETBACK_FT:.0f} ft fence setback.",
            "rule": "house/clearance.py: side_setback < FENCE_SETBACK_FT -> unlikely",
            "evidence": [],
            "steps": [site_check_step("Measures the real distance to the fence."), move_meter_step()],
        })
    if wall < C.WALL_FT_PER_BATTERY:
        out.append({
            "reason": f"Usable wall estimate {wall} ft is under the {C.WALL_FT_PER_BATTERY:.0f} ft one battery needs.",
            "rule": "house/clearance.py: wall_estimate < WALL_FT_PER_BATTERY",
            "evidence": [],
            "steps": [
                site_check_step("The estimate subtracts the garage from the short side. A tape measure can find more wall."),
                move_meter_step(),
            ],
        })
    if kw.get("has_gas") is None:
        out.append({
            "reason": f"Gas service unknown, so the rule assumes a gas meter and keeps {C.GAS_METER_SETBACK_FT:.0f} ft clear of it.",
            "rule": "house/clearance.py: has_gas None -> assume gas meter present",
            "evidence": [],
            "steps": [step(
                "Tell Base if the house has gas service, or send a photo of the gas meter.",
                "member",
                f"If there is no gas, the {C.GAS_METER_SETBACK_FT:.0f} ft gas meter setback no longer applies.",
                False, None, NO_PERMIT_RECORD,
            )],
        })
    return out


def path(blockers):
    """One ordered checklist for the case: steps shared by two blockers
    appear once. Order: member first, then Base review, then permitted work."""
    seen = {}
    for bi, b in enumerate(blockers):
        for st in b["steps"]:
            key = st["action"]
            if key not in seen:
                seen[key] = dict(st, fixes=[bi], unblocks_all=[st["unblocks"]])
            else:
                seen[key]["fixes"].append(bi)
                if st["unblocks"] not in seen[key]["unblocks_all"]:
                    seen[key]["unblocks_all"].append(st["unblocks"])
    def rank(st):
        if st["permit"]["needed"]:
            return 3 if st["who"] == "Base" else 2
        return 0 if st["who"] == "member" else 1
    out = sorted(seen.values(), key=rank)
    for st in out:
        st["unblocks"] = " ".join(st.pop("unblocks_all"))
    return out


DEMO_NAMES = {
    0: ("demo-a", "Demo a: small lot, 2-storey, detached garage"),
    1: ("demo-b", "Demo b: large lot, 1-storey, attached garage"),
    2: ("demo-c", "Demo c: small lot, zero-lot-line"),
}


def build():
    cases = []
    for i, case in enumerate(C.DEMO_CASES):
        kw = case["kwargs"]
        res = C.estimate_clearance(**kw)
        cid, label = DEMO_NAMES[i]
        blockers = clearance_blockers(kw, res) if res["clearance_ok"] != "likely" else []
        cases.append({
            "id": cid,
            "kind": "clearance_demo",
            "label": label,
            "source": "house/clearance.py DEMO_CASES",
            "verdict": f"clearance {res['clearance_ok']} ({res['confidence']} confidence)",
            "status": "not_today" if blockers else "fits",
            "facts": {
                "lot_sqft": kw["lot_sqft"], "footprint_sqft": kw["footprint_sqft"],
                "wall_estimate_ft": res["wall_estimate_ft"],
                "side_setback_ft_estimate": res["side_setback_ft_estimate"],
                "year_built": kw.get("year_built"),
            },
            "blockers": blockers,
            "path": path(blockers),
        })

    for h in json.loads(COHORT.read_text()):
        if h["fit"]["bucket"] != "needs_love":
            continue
        addr = re.sub(r"\s+", " ", h["address"]).strip()
        addr = re.sub(r" A 00000$", " A", addr)
        yb = h["year_built"]
        yb = yb["lower_bound"] if isinstance(yb, dict) else yb
        cases.append({
            "id": re.sub(r"[^a-z0-9]+", "-", addr.lower()).strip("-"),
            "kind": "house",
            "label": f"{addr.title()}, {h['zip']}",
            "source": "house/cohort.json fit bucket needs_love",
            "verdict": "fit: needs love",
            "status": "not_today",
            "facts": {"year_built": yb, "permits_on_file": len(h["events"])},
            "blockers": house_blockers(h),
        })
        cases[-1]["path"] = path(cases[-1]["blockers"])

    return {
        "generated": date.today().isoformat(),
        "issue": 38,
        "sources": [
            "house/cohort.json (fit from house/permits.py fit())",
            "house/clearance.py DEMO_CASES and estimate_clearance()",
            "data/mirror/energy_permits.csv.gz (Base permit work class)",
            "faq/corpus/how-it-works.md, faq/corpus/help-center.md",
        ],
        "cost_note": "No repo source prices these fixes, so each step says \"cost not estimated\". The only price on file is the Base install fee ($695, faq/corpus/home.md), which is not a fix cost.",
        "cases": cases,
    }


def main():
    data = build()
    OUT.write_text(json.dumps(data, indent=1))
    n = sum(1 for c in data["cases"] if c["status"] == "not_today")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(data['cases'])} cases, {n} not today.")


if __name__ == "__main__":
    main()
