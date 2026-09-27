"""Stages 1 to 4: the funnel. Each stage takes a list of members and returns the survivors plus a panel dict.

Every panel dict has: number, unit, ceiling, ceiling_note, assumptions. Stubs are marked STUB in assumptions.
"""

import random

# Dials. Defaults are assumptions until Base gives a real number Saturday.
DIALS = {
    "leads_per_week": 200,
    "photo_drop_rate": 0.35,          # assumption from the funnel walk and conversations at kickoff
    "photo_drop_rate_guided": 0.15,   # assumption: guided collection with on-the-spot check
    "crews": 4,
    "installs_per_crew_day": 3,
}

import json, os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from house import territory  # noqa: E402

ZIPS = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "austin_zips.json")))["rows"]
EQUIPMENT = ["none", "solar", "generator", "battery"]


def territory_for(zip_code):
    """Zip to (TDU, Base offer status) from house/territory.py, the one territory rule in the repo.
    Status: energy_and_backup, backup_only (Austin Energy), mixed, not_served, or unmapped when the zip is not
    in territory.py ZIP_TABLE. Unmapped counts as not served: no source says Base sells there."""
    r = territory.lookup(zip_code)
    if "error" in r:
        return "not in territory.py", "unmapped"
    return r["tdu"], r["status"]


def make_members(n, rng):
    weights = [z["permits"] for z in ZIPS]
    picks = rng.choices(ZIPS, weights=weights, k=n)
    out = []
    for i, z in enumerate(picks):
        # new-construction share drives "no address yet"; electrical share nudges existing equipment
        new_build = rng.random() < z["new_share"] / 100.0 * 0.15
        eq_p = min(0.6, 0.25 + z["electrical_share"] / 10.0)
        out.append({
            "id": i,
            "zip": z["zip"],
            "territory": territory_for(z["zip"])[0],
            "status": territory_for(z["zip"])[1],
            "owns": rng.random() < 0.7,
            "new_build": new_build,
            "equipment": rng.choice(EQUIPMENT[1:]) if rng.random() < eq_p else "none",
            "x": rng.uniform(0, 30),
            "y": rng.uniform(0, 30),
        })
    return out


def stage1_territory(members):
    served_status = ("energy_and_backup", "backup_only", "mixed")
    served = [m for m in members if m["status"] in served_status and m["owns"] and not m["new_build"]]
    by_t, by_s = {}, {}
    for m in members:
        by_t[m["territory"]] = by_t.get(m["territory"], 0) + 1
        by_s[m["status"]] = by_s.get(m["status"], 0) + 1
    in_territory = sum(by_s.get(k, 0) for k in served_status)
    no_address = sum(m["new_build"] for m in members)
    return served, {
        "name": "Territory and lead",
        "number": round(len(served) / max(len(members), 1), 3),
        "unit": "share of leads resolved to a served territory, owner, with an address",
        "by_territory": by_t,
        "by_status": by_s,
        "territory_only_share": round(in_territory / max(len(members), 1), 3),
        "no_address_yet": no_address,
        "ceiling": "Base's own eligibility rules; unknown to us",
        "assumptions": [
            "leads drawn by zip in proportion to permit volume (49 Austin zips, Undervolt extract)",
            "territory: house/territory.py lookup(); served = energy_and_backup, backup_only (Austin Energy, Backup Only plan), or mixed (competitive TDU in part of the zip)",
            "zips missing from territory.py ZIP_TABLE count as unmapped, not served; territory_only_share ignores tenure and new builds",
            "new-build share drives 'no address yet' (Base's head of software: homes still being built have no address)",
        ],
    }


def stage2_photo(members, rng, drop_rate):
    states = {"complete": [], "dropped": []}
    for m in members:
        (states["dropped"] if rng.random() < drop_rate else states["complete"]).append(m)
    return states["complete"], {
        "name": "Photo step",
        "number": drop_rate,
        "unit": "share of leads that never complete the panel photos",
        "ceiling": "Base's real drop rate; ask Saturday",
        "assumptions": ["drop rate is a dial, default from the funnel walk", "state machine asked/reminded/partial not modelled yet"],
    }


def stage3_permits(members):
    perms = {(m["territory"], m["status"], m["owns"], m["equipment"]) for m in members}
    return members, {
        "name": "Permit permutations",
        "number": len(perms),
        "unit": "distinct territory x tenure x equipment paths observed",
        "ceiling": "Base's head of software: 'in the hundreds, will probably get into thousands' with fire and electrical codes",
        "assumptions": ["STUB: 3 axes only; fire code and electrical code axes not added"],
    }


def stage4_routing(members, crews, per_crew_day):
    # greedy: nearest-next from the depot per crew day
    todo = list(members)
    greedy_miles = 0.0
    while todo:
        cx, cy = 0.0, 0.0
        for _ in range(per_crew_day):
            if not todo:
                break
            nxt = min(todo, key=lambda m: (m["x"] - cx) ** 2 + (m["y"] - cy) ** 2)
            greedy_miles += ((nxt["x"] - cx) ** 2 + (nxt["y"] - cy) ** 2) ** 0.5
            cx, cy = nxt["x"], nxt["y"]
            todo.remove(nxt)
    naive_miles = 0.0
    cx, cy = 0.0, 0.0
    for i, m in enumerate(members):
        if i % per_crew_day == 0:
            cx, cy = 0.0, 0.0
        naive_miles += ((m["x"] - cx) ** 2 + (m["y"] - cy) ** 2) ** 0.5
        cx, cy = m["x"], m["y"]
    n = max(len(members), 1)
    return members, {
        "name": "Install routing",
        "number": round(greedy_miles / n, 2),
        "unit": "miles per install, greedy nearest-next",
        "naive": round(naive_miles / n, 2),
        "ceiling": "a real VRP solver; greedy is the floor",
        "assumptions": ["toy 30x30 mile plane, one depot", "drive time = miles"],
    }
