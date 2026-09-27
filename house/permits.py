"""Austin building permit puller and heuristic classifier for the residential
electrical-upgrade cohort. Stdlib only (urllib + json).

Data source: Austin open data Socrata dataset 3syk-w9eu
https://data.austintexas.gov/resource/3syk-w9eu.json
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

from house.mirror import BATTERY as MIRROR_BATTERY_RE

BASE_URL = "https://data.austintexas.gov/resource/3syk-w9eu.json"
COHORT_PATH = "house/cohort.json"
SLEEP_SECONDS = 0.35


def _get(params):
    """GET the Socrata endpoint with SoQL params, return parsed JSON list."""
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = f"{BASE_URL}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "base-fleet/house.permits"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Step 1: densest_area
# ---------------------------------------------------------------------------

def densest_area(top_n=5, since_year=2018, verbose=True):
    """Find the residential zip with the most Electrical Permit / Upgrade or
    Auxiliary Power rows since `since_year`, and check permits-per-address
    density. Returns the chosen zip and prints a top-N table.
    """
    where_upgrade = (
        f"permit_type_desc='Electrical Permit' "
        f"AND (work_class='Upgrade' OR work_class='Auxiliary Power') "
        f"AND permit_class_mapped='Residential' "
        f"AND calendar_year_issued >= '{since_year}'"
    )
    rows = _get({
        "$select": "original_zip, count(*) as cnt",
        "$where": where_upgrade,
        "$group": "original_zip",
        "$order": "cnt DESC",
        "$limit": 20,
    })
    # filter valid-looking zips
    candidates = [r for r in rows if r.get("original_zip") and re.match(r"^\d{5}$", r["original_zip"])][:top_n]

    table = []
    for r in candidates:
        zip_code = r["original_zip"]
        upgrade_aux_count = int(r["cnt"])
        # permits-per-distinct-location for this zip (all residential permits, not just electrical)
        loc_rows = _get({
            "$select": "permit_location, count(*) as cnt",
            "$where": f"original_zip='{zip_code}' AND permit_class_mapped='Residential' AND permit_location IS NOT NULL",
            "$group": "permit_location",
            "$order": "cnt DESC",
            "$limit": 1,
        })
        max_per_location = int(loc_rows[0]["cnt"]) if loc_rows else 0
        top_address = loc_rows[0]["permit_location"] if loc_rows else None
        table.append({
            "zip": zip_code,
            "upgrade_aux_count": upgrade_aux_count,
            "max_permits_per_address": max_per_location,
            "top_address": top_address,
        })
        time.sleep(SLEEP_SECONDS)

    if verbose:
        print(f"{'zip':<8}{'upgrade/aux count':<20}{'max permits/address':<22}top address")
        for row in table:
            print(f"{row['zip']:<8}{row['upgrade_aux_count']:<20}{row['max_permits_per_address']:<22}{row['top_address']}")

    chosen = table[0]["zip"] if table else None
    return chosen, table


# ---------------------------------------------------------------------------
# Step 1b: pick 40 addresses in the chosen zip
# ---------------------------------------------------------------------------

def pick_addresses(zip_code, target=40, min_permits=4, verbose=True):
    """Pick `target` addresses in zip_code with >= min_permits permits each,
    mixing addresses that have an Upgrade/Aux Power electrical row (preferred)
    with plain addresses. Target mix: ~15 upgrade, ~10 aux power, ~15 other.
    """
    all_addrs = _get({
        "$select": "permit_location, count(*) as cnt",
        "$where": f"original_zip='{zip_code}' AND permit_class_mapped='Residential' AND permit_location IS NOT NULL",
        "$group": "permit_location",
        "$having": f"count(*) >= {min_permits}",
        "$order": "cnt DESC",
        "$limit": 1000,
    })
    eligible = {r["permit_location"]: int(r["cnt"]) for r in all_addrs if r.get("permit_location")}
    time.sleep(SLEEP_SECONDS)

    upgrade_rows = _get({
        "$select": "permit_location",
        "$where": (
            f"original_zip='{zip_code}' AND permit_type_desc='Electrical Permit' "
            f"AND work_class='Upgrade'"
        ),
        "$group": "permit_location",
        "$limit": 5000,
    })
    upgrade_set = {r["permit_location"] for r in upgrade_rows if r.get("permit_location") in eligible}
    time.sleep(SLEEP_SECONDS)

    aux_rows = _get({
        "$select": "permit_location",
        "$where": (
            f"original_zip='{zip_code}' AND permit_type_desc='Electrical Permit' "
            f"AND work_class='Auxiliary Power'"
        ),
        "$group": "permit_location",
        "$limit": 5000,
    })
    aux_set = {r["permit_location"] for r in aux_rows if r.get("permit_location") in eligible} - upgrade_set
    time.sleep(SLEEP_SECONDS)

    neither = [a for a in eligible if a not in upgrade_set and a not in aux_set]

    upgrade_list = sorted(upgrade_set, key=lambda a: -eligible[a])
    aux_list = sorted(aux_set, key=lambda a: -eligible[a])
    neither_list = sorted(neither, key=lambda a: -eligible[a])

    n_upgrade = min(15, len(upgrade_list))
    n_aux = min(10, len(aux_list))
    n_other = target - n_upgrade - n_aux
    n_other = min(n_other, len(neither_list))

    chosen = upgrade_list[:n_upgrade] + aux_list[:n_aux] + neither_list[:n_other]

    # top off to target from whatever pool has leftovers
    remaining_target = target - len(chosen)
    if remaining_target > 0:
        leftover_pool = (
            upgrade_list[n_upgrade:] + aux_list[n_aux:] + neither_list[n_other:]
        )
        chosen += leftover_pool[:remaining_target]

    if verbose:
        print(f"Picked {len(chosen)} addresses: {n_upgrade} upgrade, {n_aux} aux power, "
              f"{len(chosen) - n_upgrade - n_aux} other/other.")

    return chosen[:target]


# ---------------------------------------------------------------------------
# Step 2: house() - pull + classify permits for one address
# ---------------------------------------------------------------------------

AMP_RE = re.compile(r"(\d{2,3})\s*[- ]?\s*(?:amp|a)\b", re.IGNORECASE)
UPGRADE_TEXT_RE = re.compile(r"\b(amp|service|panel)\b.*\bupgrade\b|\bupgrade\b.*\b(amp|service|panel)\b", re.IGNORECASE)
SOLAR_RE = re.compile(r"\bsolar\b|\bpv\b|\bphotovoltaic\b", re.IGNORECASE)
# Battery: the stricter mirror rule (#81). "Storage" alone is a shed, not a battery.
BATTERY_RE = MIRROR_BATTERY_RE
GENERATOR_RE = re.compile(r"\bgenerator\b|\bgenerac\b", re.IGNORECASE)
SUBPANEL_RE = re.compile(r"\bsub[- ]?panel\b", re.IGNORECASE)
BUILT_LOOP_RE = re.compile(r"homebuilder\s*loop", re.IGNORECASE)
POOL_RE = re.compile(r"\bpool\b|\bspa\b", re.IGNORECASE)
REMODEL_RE = re.compile(r"\bremodel\b", re.IGNORECASE)
ADDITION_RE = re.compile(r"\baddition\b", re.IGNORECASE)
DEMO_RE = re.compile(r"\b(demo|demolition|demolish\w*)\b([^.;\n]{0,60})", re.IGNORECASE)
PARTIAL_DEMO_RE = re.compile(r"partial|interior|wall demo|cap[- ]?off", re.IGNORECASE)
# The main house. Checked against the words after "demo" or at the start of a new-build text.
PRIMARY_RE = re.compile(
    r"single[- ]?family|\bsfr\b|\bsf res\b|\bres\b|residence|residential|primary dwelling|"
    r"\bduplex\b|\bdup\b|condo\w*|\bunit\b", re.IGNORECASE)
# Accessory structures. A "New" building permit for one of these is not the house.
ACCESSORY_RE = re.compile(
    r"pool|\bspa\b|accessory|\badu\b|secondary|garage|carport|shed|storage|studio|greenhouse|"
    r"home office|amenity|rear dwelling|guest|deck|patio|fence|pergola|cabana", re.IGNORECASE)
PANEL_REPLACE_RE = re.compile(
    r"(replac\w*|change ?out|swap\w*)\s+(?:[\w/-]+\s+){0,5}?(main\s+)?(breaker\s+)?"
    r"(panel|load ?center|breaker box|msp|meter base)\b", re.IGNORECASE)
HVAC_REPLACE_RE = re.compile(
    r"(change ?out|replac\w*)\b[^.]{0,40}\b(hvac|a/?c\b|air condition\w*|heat and air|heat pump|"
    r"condenser|central (heat|air))|(hvac|a/?c|condenser)\b[^.]{0,20}\b(change ?out|replacement)",
    re.IGNORECASE)


def _is_primary_new(ptype, wclass, desc):
    """A Building Permit, work class New, for the main house (not a pool,
    studio, garage, ADU or other accessory structure)."""
    if ptype != "Building Permit" or wclass.strip().lower() != "new":
        return False
    prim = PRIMARY_RE.search(desc)
    if not prim:
        return False
    acc = ACCESSORY_RE.search(desc)
    return acc is None or prim.start() < acc.start()


def _demo_kind(wclass, desc):
    """'demolition' for a full demolition of the main house, 'demolition_accessory'
    for a full demolition of a garage, shed or other accessory, None otherwise
    (partial or interior demo is part of a remodel)."""
    m = DEMO_RE.search(desc)
    is_demo_class = wclass.strip().lower() in ("demo", "demolition")
    if not m and not is_demo_class:
        return None
    if PARTIAL_DEMO_RE.search(desc):
        return None
    window = m.group(2) if m else desc
    if PRIMARY_RE.search(window) or (is_demo_class and PRIMARY_RE.search(desc) and not m):
        return "demolition"
    return "demolition_accessory"


TO_AMP_RE = re.compile(r"\bto\s+(?:a\s+)?(?:new\s+)?(\d{2,3})\s*[- ]?\s*(?:amp|a)\b", re.IGNORECASE)


def _extract_amps(text):
    """Extract the target/new amperage from an upgrade description. Prefers
    a 'to NNNamp' phrase (the new size in a 'from X to Y' upgrade); falls
    back to the largest amp value mentioned."""
    text = text or ""
    to_match = TO_AMP_RE.search(text)
    if to_match:
        return int(to_match.group(1))
    matches = [int(m.group(1)) for m in AMP_RE.finditer(text)]
    return max(matches) if matches else None


def _classify(row):
    ptype = (row.get("permit_type_desc") or "")
    wclass = (row.get("work_class") or "")
    desc = (row.get("description") or "")
    text = f"{ptype} {wclass} {desc}"

    kind = "other"
    amps = None

    demo = _demo_kind(wclass, desc)
    if _is_primary_new(ptype, wclass, desc):
        kind = "built"
    elif BUILT_LOOP_RE.search(text):
        kind = "temp_power"
    elif demo:
        kind = demo
    elif ptype == "Electrical Permit" and wclass.strip().lower() == "upgrade":
        kind = "service_upgrade"
        amps = _extract_amps(desc)
    elif UPGRADE_TEXT_RE.search(desc):
        kind = "service_upgrade"
        amps = _extract_amps(desc)
    elif SUBPANEL_RE.search(text):
        kind = "sub_panel"
    elif ptype == "Electrical Permit" and PANEL_REPLACE_RE.search(desc):
        # Main panel replaced. Recorded as panel or service work, same as an upgrade.
        kind = "service_upgrade"
        amps = _extract_amps(desc)
    elif SOLAR_RE.search(text):
        kind = "solar"
    elif BATTERY_RE.search(desc):
        kind = "battery"
    elif GENERATOR_RE.search(text):
        kind = "generator"
    elif ptype == "Mechanical Permit" and ("change out" in wclass.lower() or HVAC_REPLACE_RE.search(desc)):
        kind = "ac_changeout"
    elif REMODEL_RE.search(text):
        kind = "remodel"
    elif ADDITION_RE.search(text):
        kind = "addition"
    elif POOL_RE.search(text):
        kind = "pool"

    return kind, amps


def house(address):
    """Pull all permits for an address, classify into events, derive
    year_built. Returns the house dict (without fit/guessable - added by
    caller)."""
    rows = _get({
        "$where": f"permit_location='{address}'",
        "$order": "issue_date ASC",
        "$limit": 1000,
    })

    events = []
    for r in rows:
        date = r.get("issue_date")
        kind, amps = _classify(r)
        ev = {
            "date": date,
            "kind": kind,
            "permit": r.get("permit_number"),
            "text": (r.get("description") or "").strip()[:300],
        }
        if amps:
            ev["amps"] = amps
        events.append(ev)

    zip_code = None
    for r in rows:
        if r.get("original_zip"):
            zip_code = r["original_zip"]
            break

    # Teardown: permits before the last full demolition of the house, or
    # before the new build, belong to the old structure. Keep them on the
    # timeline, flag them, and leave them out of the derived fields.
    # The city sometimes issues the demolition permit after the new-build
    # permit, so a build up to two years before the demo counts as the rebuild.
    dated = [e for e in events if e.get("date")]
    demos = [e["date"] for e in dated if e["kind"] == "demolition"]
    last_demo = max(demos) if demos else None
    if last_demo:
        window = f"{int(last_demo[:4]) - 2}{last_demo[4:]}"
        builds_after = [e for e in dated if e["kind"] == "built" and e["date"] >= window]
    else:
        builds_after = [e for e in dated if e["kind"] == "built"]
    starts = ([last_demo] if last_demo else []) + ([builds_after[0]["date"]] if builds_after else [])
    cutoff = min(starts) if starts else None
    if cutoff:
        for e in dated:
            if e["date"] < cutoff:
                e["old_structure"] = True

    # year_built comes only from a new-build permit for the main house
    # (appraisal data is not wired for Travis County yet).
    if builds_after:
        year_built = int(builds_after[0]["date"][:4])
    else:
        years = [int(e["date"][:4]) for e in events if e.get("date")]
        if years:
            year_built = {
                "lower_bound": min(years),
                "source": "earliest permit",
                "confidence": 0.3,
            }
        else:
            year_built = None

    return {
        "address": address,
        "zip": zip_code,
        "year_built": year_built,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Step 3: fit()
# ---------------------------------------------------------------------------

def _year_of(date_str):
    try:
        return int(date_str[:4])
    except (TypeError, ValueError):
        return None


def _current(h):
    """Events on the standing structure (drops old_structure events)."""
    return [e for e in h["events"] if not e.get("old_structure")]


def fit(h):
    reasons = []
    bucket = None

    events = _current(h)
    year_built = h["year_built"]
    # A dict is the earliest permit on file: the house existed by then. It is
    # not a build year, so only the pre-1980 rule may use it.
    yb_known = year_built if isinstance(year_built, int) else None
    yb_by = year_built["lower_bound"] if isinstance(year_built, dict) else year_built

    service_upgrades = [e for e in events if e["kind"] == "service_upgrade"]
    big_recent_upgrade = [
        e for e in service_upgrades
        if e.get("amps") and e["amps"] >= 200 and (_year_of(e["date"]) or 0) >= 2010
    ]
    has_solar = any(e["kind"] == "solar" for e in events)
    has_battery = any(e["kind"] == "battery" for e in events)
    has_generator = any(e["kind"] == "generator" for e in events)
    no_electrical_ever = not any(
        e["kind"] in ("service_upgrade", "sub_panel") for e in events
    )
    last_event = events[-1] if events else None
    recent_electrical = [
        e for e in events
        if e["kind"] == "service_upgrade" and (_year_of(e["date"]) or 0) >= 2015
    ]

    if big_recent_upgrade:
        bucket = "easy"
        reasons.append(
            f"service upgrade to {big_recent_upgrade[0]['amps']}A in "
            f"{_year_of(big_recent_upgrade[0]['date'])} (permit {big_recent_upgrade[0]['permit']})"
        )

    # Austin descriptions rarely carry amps. Date of build or upgrade is the signal we have.
    upgrade_2010 = [e for e in service_upgrades if (_year_of(e["date"]) or 0) >= 2010]
    if bucket is None and upgrade_2010 and not (has_solar or has_battery):
        bucket = "easy"
        last_up = upgrade_2010[-1]
        amps_txt = f"{last_up['amps']} A" if last_up.get("amps") else "amps to confirm"
        reasons.append(f"panel or service work in {_year_of(last_up['date'])} (permit {last_up['permit']}), {amps_txt}")
    if bucket is None and yb_known is not None and yb_known >= 2000 and not (has_solar or has_battery):
        bucket = "easy"
        reasons.append(f"built {yb_known}, 200 A by code for that era, one photo to confirm")

    if bucket is None and (has_solar or has_battery):
        bucket = "needs_love"
        reasons.append("existing solar or battery adds interconnect complexity")

    if bucket is None and no_electrical_ever and yb_by is not None and yb_by < 1980:
        bucket = "needs_love"
        reasons.append("likely 100 A, no record")

    if bucket is None and last_event and last_event["kind"] == "demolition":
        bucket = "not_now"
        reasons.append("demolition is the most recent event")

    if bucket is None:
        if recent_electrical:
            bucket = "easy"
            reasons.append(
                f"electrical permit since 2015 (permit {recent_electrical[-1]['permit']})"
            )
        else:
            bucket = "needs_love"
            reasons.append("no electrical permit activity since 2015")

    return {"bucket": bucket, "reasons": reasons}


def guessable_fields(h):
    events = _current(h)
    service_upgrades = [e for e in events if e["kind"] == "service_upgrade"]
    guesses = []

    if service_upgrades:
        last = service_upgrades[-1]
        if last.get("amps"):
            guesses.append({
                "field": "main_breaker_amps",
                "value": last["amps"],
                "source": last["permit"],
                "confidence": 0.85,
            })
        else:
            guesses.append({
                "field": "main_breaker_amps",
                "value": None,
                "source": last["permit"],
                "confidence": 0.4,
            })
    else:
        yb = h["year_built"] if isinstance(h["year_built"], int) else None
        if yb and yb >= 2000:
            guesses.append({"field": "main_breaker_amps", "value": 200,
                            "source": f"built {yb}, 200 A by code for that era", "confidence": 0.7})
        else:
            guesses.append({"field": "main_breaker_amps", "value": 100,
                            "source": "no electrical permit on file", "confidence": 0.3})

    solar_events = [e for e in events if e["kind"] == "solar"]
    guesses.append({
        "field": "has_solar",
        "value": bool(solar_events),
        "source": solar_events[-1]["permit"] if solar_events else "no permit on file",
        "confidence": 0.9 if solar_events else 0.6,
    })

    battery_events = [e for e in events if e["kind"] == "battery"]
    guesses.append({
        "field": "has_battery",
        "value": bool(battery_events),
        "source": battery_events[-1]["permit"] if battery_events else "no permit on file",
        "confidence": 0.9 if battery_events else 0.5,
    })

    gen_events = [e for e in events if e["kind"] == "generator"]
    guesses.append({
        "field": "has_generator",
        "value": bool(gen_events),
        "source": gen_events[-1]["permit"] if gen_events else "no permit on file",
        "confidence": 0.9 if gen_events else 0.5,
    })

    ac_events = [e for e in events if e["kind"] == "ac_changeout"]
    if ac_events:
        ac_year = _year_of(ac_events[-1]["date"])
        guesses.append({
            "field": "ac_age_years",
            "value": 2026 - ac_year if ac_year else None,
            "source": ac_events[-1]["permit"],
            "confidence": 0.8,
        })
    else:
        guesses.append({
            "field": "ac_age_years",
            "value": None,
            "source": "no mechanical change-out permit on file",
            "confidence": 0.2,
        })

    return guesses


def build_house_record(address):
    h = house(address)
    h["fit"] = fit(h)
    h["guessable"] = guessable_fields(h)
    h["confirm_with_member"] = [
        g["field"] for g in h["guessable"] if g["confidence"] < 0.7
    ]
    return h


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_cohort(rebuild=False):
    if rebuild:
        with open(COHORT_PATH) as f:
            addresses = [h["address"] for h in json.load(f)]
        print(f"Rebuilding the {len(addresses)} addresses already in {COHORT_PATH}")
    else:
        print("Finding densest residential electrical-upgrade zip...")
        zip_code, table = densest_area()
        print(f"\nChosen zip: {zip_code}\n")

        print("Selecting 40 addresses...")
        addresses = pick_addresses(zip_code, target=40)

    houses = []
    for i, addr in enumerate(addresses):
        try:
            h = build_house_record(addr)
        except Exception as exc:  # pragma: no cover - network flake
            print(f"  [{i+1}/{len(addresses)}] {addr}: ERROR {exc}", file=sys.stderr)
            continue
        houses.append(h)
        print(f"  [{i+1}/{len(addresses)}] {addr}: {len(h['events'])} permits, fit={h['fit']['bucket']}")
        time.sleep(SLEEP_SECONDS)

    with open(COHORT_PATH, "w") as f:
        json.dump(houses, f, indent=2)

    bucket_counts = defaultdict(int)
    amps_hits = 0
    yb_known = 0
    for h in houses:
        bucket_counts[h["fit"]["bucket"]] += 1
        if any(e.get("amps") for e in h["events"]):
            amps_hits += 1
        if not isinstance(h["year_built"], dict) and h["year_built"] is not None:
            yb_known += 1

    print(f"\nWrote {len(houses)} houses to {COHORT_PATH}")
    print(f"Bucket counts: {dict(bucket_counts)}")
    print(f"Amps extracted: {amps_hits}/{len(houses)}")
    print(f"year_built known (not lower bound): {yb_known}/{len(houses)}")


def main():
    parser = argparse.ArgumentParser(description="Austin permit puller and classifier")
    parser.add_argument("address", nargs="?", help="Single address to look up")
    parser.add_argument("--cohort", action="store_true", help="Build the full 40-house cohort")
    parser.add_argument("--rebuild", action="store_true",
                        help="Reclassify the addresses already in house/cohort.json (same 40 houses)")
    args = parser.parse_args()

    if args.cohort or args.rebuild:
        run_cohort(rebuild=args.rebuild)
    elif args.address:
        h = build_house_record(args.address)
        print(json.dumps(h, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
