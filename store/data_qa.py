"""Build web/data/data_qa.json for web/data-qa.html ("Questions people ask").

Every number is computed at build time from the real files and data/fleet.db.
No hand-typed numbers. Run from anywhere: python3 store/data_qa.py
Cards are for Base users: a homeowner, a member with a battery, an older or
disabled member or a caregiver, a small business, a library or community host.
"""
import json, re, sqlite3, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fleet.db"
OUT = ROOT / "web" / "data" / "data_qa.json"

USERS = {
    "homeowner": "Homeowner",
    "member": "Member with a battery",
    "assisted": "Older or disabled, or a caregiver",
    "business": "Small business",
    "host": "Library or community host",
}
BACKUP = ("generator", "battery", "solar_battery")
DEAD = ("VOID", "Withdrawn", "Aborted", "Cancelled - Contractor Required")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def load(rel):
    return json.loads((ROOT / rel).read_text())


def n(x):
    return f"{x:,}"


def pct(x):
    return f"{round(100 * x)}%"


def hour12(h):
    """Clock hour 0..24 to '4 pm'."""
    h %= 24
    return "12 am" if h == 0 else "12 pm" if h == 12 else f"{h} am" if h < 12 else f"{h - 12} pm"


def he_span(hes):
    """Hour-ending list [19,20,21] -> '6 pm to 9 pm'."""
    return f"{hour12(min(hes) - 1)} to {hour12(max(hes))}"


def card(cid, q, users, say, number, source, computed, page, label=None, zip_=None):
    c = {"id": cid, "q": q, "users": users, "say": say, "number": number,
         "source": source, "computed": computed,
         "page": {"label": page[0], "href": page[1]}}
    if label:
        c["label"] = label
    if zip_:
        c["zip"] = zip_
    return c


# ---------- zip cards ----------

def zip_cards(db, z, fz, terr, dem, base_rank, deeds, storm_zip, austin_base_median):
    out = []
    zc = z["zip"]
    place = f"{zc} ({z['city']})"
    t = terr.get(zc)
    # 1. Territory
    if t:
        st, tdu, plans, mixed = t["status"], t["tdu"], t["ptc_plans"], t["mixed_with"]
        if st == "energy_and_backup":
            say = f"Yes, the public record points that way. {tdu} delivers power in {place}, and Base can be your electricity provider there, with or without a battery."
        elif st == "backup_only":
            say = f"Yes, for a backup battery. {tdu} delivers power in {place} and stays your electricity provider. Base installs a battery only (Backup Only plan)."
        elif st == "mixed":
            say = f"Part of {place}, yes. {tdu} serves part of the zip, where Base can be your provider. {mixed} serves the rest, where no Base offer was found. Your bill shows which one you have."
        else:
            say = f"Not today, from the public record. {tdu} serves {place}, and no Base offer was found for it."
        out.append(card(f"{zc}:territory", "Can Base serve my home here?", ["homeowner", "business", "assisted"], say,
            f"{tdu}; {n(plans or 0)} retail plans on Power to Choose (0 means a city utility or co-op)",
            "Power to Choose plan list for the zip, and Base's public pricing page. Base confirms service at your address.",
            f"SELECT tdu, status, ptc_plans, mixed_with FROM territory WHERE zip='{zc}' (data/fleet.db, from data/ptc_tdu.json)",
            ("Next areas", "star.html"), "Public record, not a Base confirmation", zc))
    # 2. Neighbours with backup
    rows = dict(db.execute(
        f"SELECT category, COUNT(*) FROM permits WHERE zip=? AND status NOT IN ({','.join('?'*len(DEAD))}) GROUP BY category",
        (zc, *DEAD)).fetchall())
    if rows:
        backup = sum(rows.get(k, 0) for k in BACKUP)
        own = dem.get(zc, {}).get("owner_occupied")
        per = f" That is about {round(1000 * backup / own)} for every 1,000 owner homes." if own else ""
        say = (f"The City of Austin permit record shows {n(backup)} backup permits in {place} since 2015: "
               f"{n(rows.get('generator', 0))} generators, {n(rows.get('battery', 0))} batteries, "
               f"{n(rows.get('solar_battery', 0))} solar plus battery.{per}")
        num = f"{n(backup)} backup permits; also {n(rows.get('solar', 0))} solar only"
    else:
        say = f"The City of Austin permit feed has no rows for {place}. Your city or county keeps its own permits, and we do not read them yet."
        num = "No data in the Austin feed"
    out.append(card(f"{zc}:neighbours", "How many neighbours have backup already?", ["homeowner"], say, num,
        "City of Austin issued construction permits (open data), classified by type. Contractor names other than Base are hidden.",
        f"SELECT category, COUNT(*) FROM permits WHERE zip='{zc}' AND status not void or withdrawn GROUP BY category",
        ("Permit explorer", "explorer.html"), None, zc))
    # 3. Base near me
    b = db.execute("""SELECT COUNT(*), SUM(status='Final'), SUM(status='Active'), MAX(issue_date)
        FROM permits WHERE is_base=1 AND work_class='Auxiliary Power' AND issue_date>='2026' AND zip=?""", (zc,)).fetchone()
    if b[0]:
        rank, of = base_rank[zc]
        say = (f"Base has {n(b[0])} backup battery permits in {place} this year, rank {rank} of {of} zips. "
               f"{b[1] or 0} are final and {b[2] or 0} are still open. The newest was issued {b[3]}.")
        num = f"{n(b[0])} Base permits in 2026, rank {rank} of {of}"
    elif rows:
        say = f"The Austin permit record shows no Base backup permits in {place} in 2026. You could be one of the first on your street."
        num = "0 Base permits in 2026"
    else:
        say = f"We cannot tell. The Austin permit feed does not cover {place}, so Base work there is not visible to us."
        num = "No data in the Austin feed"
    out.append(card(f"{zc}:base", "How busy is Base near me?", ["homeowner", "member"], say, num,
        "City of Austin permits with contractor Base Power and work class Auxiliary Power, issued in 2026.",
        f"SELECT COUNT(*) FROM permits WHERE is_base=1 AND work_class='Auxiliary Power' AND issue_date>='2026' AND zip='{zc}'",
        ("Market", "market.html"), None, zc))
    # 4. Permit time
    days = [r[0] for r in db.execute("""SELECT julianday(issue_date)-julianday(applied_date) FROM permits
        WHERE is_base=1 AND work_class='Auxiliary Power' AND zip=? AND applied_date IS NOT NULL AND issue_date IS NOT NULL""", (zc,))]
    if len(days) >= 3:
        med = statistics.median(days)
        say = f"About {round(med)} days from application to permit, the median for {len(days)} Base permits in {place}. After the permit comes the install and the final inspection."
        num, sql = f"{round(med)} days median ({len(days)} Base permits)", "Base permits in the zip"
    else:
        days = [r[0] for r in db.execute("""SELECT julianday(issue_date)-julianday(applied_date) FROM permits
            WHERE zip=? AND category IN ('generator','battery','solar_battery') AND issue_date>='2025'
            AND applied_date IS NOT NULL""", (zc,))]
        if len(days) >= 3:
            med = statistics.median(days)
            say = f"About {round(med)} days, the median for {len(days)} backup permits in {place} since 2025 (all installers). Base's own Austin median is {round(austin_base_median)} days."
            num, sql = f"{round(med)} days median ({len(days)} backup permits)", "backup permits in the zip since 2025"
        else:
            say = f"The Austin feed has too few permits in {place} to say. Across Austin, Base's median is {round(austin_base_median)} days from application to permit. Your city may differ."
            num, sql = f"{round(austin_base_median)} days, Austin-wide Base median", "all Base permits, Austin"
    out.append(card(f"{zc}:time", "How long does a permit take?", ["homeowner", "business"], say, num,
        "Applied date and issued date on each City of Austin permit.",
        f"median(julianday(issue_date) - julianday(applied_date)) over {sql} (data/fleet.db permits)",
        ("Market", "market.html"), None, zc))
    # 5. 200 A readiness
    stg = {s["key"]: s for s in fz["stages"]}
    osfd, a200, easy = stg["owner_sfd"]["count"], stg["likely_200a"]["count"], stg["easy_fit"]["count"]
    why = stg["likely_200a"]["why"]
    m = re.search(r"(\d+)% likely 200A", why)
    share = f"{m.group(1)}%" if m else (pct(a200 / osfd) if osfd else "unknown")
    if a200:
        say = (f"Likely, for many. About {share} of owner homes in {place} probably have 200 A service, "
               f"about {n(a200)} of {n(osfd)}. Our estimate of easy-fit homes is {n(easy)}. The public record does not show your panel; an engineer confirms it.")
    else:
        say = (f"The estimate for {place} is zero, because no Base offer was found there, not because of the panels. "
               f"Build-year rule: {why.split('proxy: ')[-1] if 'proxy' in why else why}.")
    out.append(card(f"{zc}:ready", "Are homes here likely ready (200 A)?", ["homeowner"], say,
        f"{n(a200)} likely 200 A of {n(osfd)} owner homes; {n(easy)} easy fit",
        "Census (ACS) home counts and build year, plus permit history. An estimate, not a count of real panels.",
        f"data/funnel.json rows[zip={zc}].stages likely_200a, easy_fit (built by house/funnel.py)",
        ("Next areas", "star.html"), "Estimate", zc))
    # 6. Storms
    def cnt(a, b):
        return db.execute(f"""SELECT COUNT(*) FROM permits WHERE zip=? AND category IN ('generator','battery','solar_battery')
            AND substr(applied_date,1,7) BETWEEN ? AND ?""", (zc, a, b)).fetchone()[0]
    if rows:
        base20 = cnt("2020-01", "2020-12") / 12
        uri, ice = cnt("2021-02", "2021-04"), cnt("2023-02", "2023-04")
        last12 = cnt("2025-10", "2026-09")
        ratio = f" That is {(uri / 3) / base20:.1f} times the 2020 monthly rate." if base20 else ""
        say = (f"In {place}, backup permits jumped after big storms: {uri} in the 3 months after Winter Storm Uri (Feb to Apr 2021) "
               f"and {ice} after the 2023 ice storm, against {base20:.1f} a month in 2020.{ratio} Last 12 months: {last12}.")
        num = f"Uri {uri}, ice storm {ice}, 2020 average {base20:.1f} a month"
        rz = storm_zip.get(zc)
        if rz:
            num += f"; a 2023-size storm adds about {rz['surge_per_week_est']} a week here (estimate)"
    else:
        say = f"We cannot tell for {place}. Storm history comes from the City of Austin permit feed, which does not cover this zip."
        num = "Austin only"
    out.append(card(f"{zc}:storms", "How often do storms push people to backup here?", ["homeowner", "assisted"], say, num,
        "City of Austin permits for generators and batteries, by the month people applied. Austin only.",
        f"COUNT(*) FROM permits WHERE zip='{zc}' AND category IN backup AND applied month in 2020, 2021-02..04, 2023-02..04; data/storms.json readiness",
        ("Market", "market.html"), None, zc))
    # 7. Deeds
    d = deeds.get(zc)
    if d and d["parcels_with_deed_date"]:
        say = (f"The median home in {place} last changed hands {d['median_years_since_deed']} years ago. "
               f"{pct(d['share_held_20y_plus'])} have not changed hands in 20 years, and {pct(d['share_sold_last_2y'])} changed hands in the last 2.")
        num = f"{d['median_years_since_deed']} years median; {pct(d['share_sold_last_2y'])} in 2 years; {n(d['parcels'])} homes"
    else:
        say = f"No appraisal district data for {place}. We read Travis and Williamson counties only."
        num = "No data"
    out.append(card(f"{zc}:deeds", "How long do people here stay in their homes?", ["homeowner"], say, num,
        "Travis and Williamson appraisal district exports (2026). Owner names and addresses are dropped when the file is read. A transfer is any deed, not only a sale.",
        f"data/deeds_by_zip.json rows[zip={zc}] (built by house/cad_deeds.py)",
        ("Next areas", "star.html"), None, zc))
    return out


# ---------- general cards ----------

def general_cards(db):
    out = []
    today = load("web/data/grid_today.json")
    bat = today["battery"]
    out.append(card("battery-today", "What will my battery do today?", ["member"],
        f"On {today['date']} the plan is to charge from {he_span(bat['charge_he'])}, when power is cheapest, and send power back from "
        f"{he_span(bat['discharge_he'])}, when it is dearest. {pct(bat['reserve'])} of the {bat['kwh']} kWh always stays in for your backup.",
        f"Net ${bat['net']:.2f} for the day on one battery ({bat['zone']})",
        "Today's ERCOT day-ahead prices for the Austin zone, one charge and one discharge a day. Our plan, not Base's real dispatch.",
        "web/data/grid_today.json battery (built by grid/today.py from the ERCOT system-wide-prices feed)",
        ("Grid", "grid.html"), "Our model, not Base's dispatch"))
    yr = load("web/data/grid_year.json")
    y25 = yr["years"]["2025"]["aen"]
    out.append(card("battery-year", "What did one battery earn last year?", ["homeowner", "member"],
        f"About ${y25['total']:.0f} for all of 2025, or ${y25['per_day']:.2f} a day, on real Austin prices. This is a floor: day-ahead prices and one cycle a day only. It is the value to the grid, not a payment to you.",
        f"${y25['total']:.2f} in 2025; best 10 days gave ${y25['top10_price_days']:.2f}",
        "ERCOT day-ahead price archive (report 13060), Austin zone, 39.2 kWh battery, 30% kept for backup.",
        "web/data/grid_year.json years.2025.aen (built by grid/year.py)",
        ("Grid", "grid.html"), "Our estimate, not a Base offer"))
    # grid stress hours
    load_by = db.execute("SELECT he, AVG(ercot) FROM load_hourly GROUP BY he ORDER BY 2 DESC").fetchall()
    price_by = db.execute("SELECT he, AVG(price) FROM dam_prices WHERE point='LZ_AEN' GROUP BY he ORDER BY 2 DESC").fetchall()
    top_price = sorted(h for h, _ in price_by[:4])
    peak_load = load_by[0]
    dlo, dhi = db.execute("SELECT MIN(date), MAX(date) FROM load_hourly").fetchone()
    out.append(card("grid-stress", "When is the grid most stressed?", ["member", "business", "assisted"],
        f"Late afternoon and evening. Texas uses the most power from {he_span([peak_load[0]])}, and Austin prices are highest from {he_span(top_price)}. Solar fades then while air conditioning is still on.",
        f"Peak load hour ends {hour12(peak_load[0])} ({n(round(peak_load[1]))} MW average); top price hours {he_span(top_price)}",
        f"ERCOT hourly load {dlo} to {dhi} and day-ahead prices for the Austin zone.",
        "SELECT he, AVG(ercot) FROM load_hourly GROUP BY he; SELECT he, AVG(price) FROM dam_prices WHERE point='LZ_AEN' GROUP BY he",
        ("Grid", "grid.html")))
    sig = load("web/data/signals.json")
    rules = {r["name"]: r for r in sig["rules"]}
    alerts = rules["storm_alert"]["now"]["value"]
    prc = rules["low_reserves"]["now"]["value"]
    out.append(card("storm-now", "Is a storm coming?", ["homeowner", "member", "assisted", "business", "host"],
        (f"No weather alert is active for Travis or Williamson county right now." if not alerts else
         f"Yes: {alerts} National Weather Service alert(s) are active for Travis or Williamson county.")
        + f" The grid has {n(round(prc))} MW of reserve; ERCOT asks people to save power under 3,000 MW.",
        f"{alerts} active alerts; {sig['fired_now']} of {len(sig['rules'])} alarms firing",
        "National Weather Service active alerts and ERCOT reserves, checked every hour. Active alerts only, no forecast.",
        "web/data/signals.json (built by store/signals.py from nws_alerts and prc in data/fleet.db)",
        ("Grid", "grid.html"), f"As of {sig['built_at'][:16].replace('T', ' ')} UTC"))
    js = (ROOT / "web" / "onboarding.js").read_text()
    order = re.search(r"const ORDER = \[([^\]]+)\]", js).group(1)
    nfields = len(re.findall(r'"(\w+)"', order))
    ms = (ROOT / "web" / "milestones.js").read_text()
    reward = dict((k, int(v)) for k, v in re.findall(r"(\w+): (\d+)", re.search(r"const REWARD = \{([^}]+)\}", ms).group(1)))
    pay = {"field": reward["field"], "photo": reward["photo"], "finish": reward["complete"], "join": reward["neighbour"]}
    mem = load("data/members.json")["members"]
    known = [sum(1 for f in m["fields"].values() if f.get("value") is not None and (f.get("confidence") or 0) >= 0.85) for m in mem]
    out.append(card("what-to-do", "What do I need to do?", ["homeowner", "assisted"],
        f"Check {nfields} short answers about your home, then add one photo of your panel if you can. City permits fill in most of it first; you only confirm or correct.",
        f"{nfields} questions and 1 photo",
        "The My Home steps. Each answer starts from the city permit record for the home.",
        "web/onboarding.js ORDER (the questions) and the photo task",
        ("My Home", "onboarding.html#home")))
    amps = [m["fields"].get("main_breaker_amps") or {} for m in mem]
    by_permit = sum(1 for a in amps if re.match(r"\d{4}-", str(a.get("source", ""))))
    by_year = sum(1 for a in amps if str(a.get("source", "")).startswith("built "))
    out.append(card("breaker", "Do I need to read my breaker?", ["homeowner", "assisted"],
        f"No. The guide does not ask you to. For {by_permit + by_year} of {len(mem)} sample homes the records give a starting point: "
        f"{by_permit} from a panel permit, {by_year} from the year the home was built. An engineer confirms the size. A photo only makes it faster.",
        f"{by_permit + by_year} of {len(mem)} sample homes have a record to start from",
        "City permits for each sample home (panel and service work) and the build year. The voice guide says: we will not ask you to read the breaker.",
        "data/members.json fields.main_breaker_amps.source (permit number or 'built <year>')",
        ("Voice guide", "voice.html")))
    most = nfields * pay["field"] + pay["photo"] + pay["finish"]
    out.append(card("credit", "What credit do I get?", ["homeowner", "member"],
        f"In this design, energy credit, not cash: {pay['field']} kWh for each answer you confirm, {pay['photo']} kWh for the panel photo, {pay['finish']} kWh when you finish, and {pay['join']} kWh when a neighbour you told joins. Base has not offered this.",
        f"Up to {most} kWh for your own home, plus {pay['join']} kWh a neighbour",
        "The reward rules in the My Home page. Amounts are assumed.",
        "web/onboarding.js PAY",
        ("My Home credits", "onboarding.html#credits"), "Assumed, not a Base offer"))
    deeds = load("data/deeds_by_zip.json")
    parcels = sum(r["parcels"] for r in deeds["rows"])
    others = db.execute("SELECT COUNT(DISTINCT contractor) FROM permits WHERE is_base=0 AND contractor IS NOT NULL").fetchone()[0]
    out.append(card("private", "Is my information private?", ["homeowner", "member", "assisted", "business", "host"],
        f"Yes. We read {n(parcels)} appraisal records and drop every owner name and address when the file is read. Other installers show as numbers, not names. Your answers on My Home stay in your browser; nothing is sent.",
        f"{n(parcels)} parcels, 0 names kept; {n(others)} installers made anonymous",
        "Appraisal district exports and City of Austin permits, cleaned at read time.",
        "SUM(parcels) in data/deeds_by_zip.json; SELECT COUNT(DISTINCT contractor) FROM permits WHERE is_base=0",
        ("Data flow", "dataflow.html")))
    rec = load("web/data/recovery.json")
    steps = [s for c in rec["cases"] for b in c["blockers"] for s in b["steps"]]
    not_member = sum(1 for s in steps if s["who"] != "member")
    out.append(card("no-photo", "What if I can't do the photo?", ["assisted"],
        "Skip it. The voice guide reads each step out loud and has a Skip the photo button. Hand this to a caregiver shows every step on one page as text. Some fix steps are done by Base or an electrician, not by you.",
        f"{not_member} of {len(steps)} fix steps in our cases are done by Base or an electrician, not you",
        "The voice guide and caregiver view, and the fix steps in Path to yes.",
        "web/recovery.json cases[].blockers[].steps[].who; web/voice.html caregiver switch",
        ("Voice guide", "voice.html")))
    from collections import Counter
    reasons = Counter(b["reason"].split(".")[0] for c in rec["cases"] for b in c["blockers"])
    top, top_n = reasons.most_common(1)[0]
    homes = [c for c in rec["cases"] if c["kind"] == "house"]
    out.append(card("path-to-yes", "What would make my home a yes?", ["homeowner"],
        f"Usually one or two steps. The most common reason in our sample is: {top.lower()}. The fix is a photo of the label and the panel, then an engineer check. Each step says who does it and if it needs a permit.",
        f"{top_n} of {len(homes)} sample homes share that reason",
        "Sample homes in 78745 and the fit rules. Costs are not estimated.",
        "web/data/recovery.json cases[].blockers[].reason (built by house/recovery.py)",
        ("Path to yes", "recovery.html"), "Sample homes, not your home"))
    res = {}
    for be in ("laptop", "jetson"):
        rows = [json.loads(l) for l in (ROOT / "brain" / f"pred_{be}.jsonl").read_text().splitlines() if l.strip()]
        ok = sum(1 for r in rows if r["verdict"] in ("correct", "gap_correct"))
        res[be] = (ok, len(rows), statistics.median(r["secs"] for r in rows))
    lp, jt = res["laptop"], res["jetson"]
    out.append(card("business-ai", "Can my AI run nearby?", ["business"],
        f"In our test, yes for short answers. A small model on a laptop got {lp[0]} of {lp[1]} right in {lp[2]:.1f} s (median); on a small edge box on the same network, {jt[0]} of {jt[1]} in {jt[2]:.1f} s. We have not tested a Windows PC yet.",
        f"Laptop {lp[0]}/{lp[1]}, edge box {jt[0]}/{jt[1]}",
        "Our own test: 10 questions, 2 runs each, same model on each machine. No internet-off test yet.",
        "brain/pred_laptop.jsonl, brain/pred_jetson.jsonl (verdict, secs)",
        ("My Battery", "member.html"), "Our test, not a Base offer"))
    lib = load("data/library_node.json")
    ln, hn = lib["library_node"], lib["house_node"]
    out.append(card("host-hub", "What would a hub earn for a library?", ["host"],
        f"About ${ln['total_weekly']:.2f} a week in our design: ${ln['battery_net_weekly']:.2f} from {ln['num_batteries']} batteries and ${ln['gpu_net_weekly']:.2f} from AI computers. A single home would earn ${hn['total_weekly']:.2f}.",
        f"${ln['total_weekly']:.2f} a week at {pct(ln['utilization_assumption'])} computer use",
        "Real Austin power prices and assumed computer rates and use. This hub is our design; Base has not planned it.",
        "data/library_node.json library_node.total_weekly (built from grid/LIBRARY_NODE.md model)",
        ("Hub placement", "placement.html"), "Our design, not a Base offer"))
    return out


def main():
    db = sqlite3.connect(DB)
    funnel = load("data/funnel.json")
    terr = {r[0]: dict(zip(["zip", "city", "county", "tdu", "mixed_with", "status", "zip_confidence", "tdu_confidence", "ptc_plans", "note"], r))
            for r in db.execute("SELECT zip, city, county, tdu, mixed_with, status, zip_confidence, tdu_confidence, ptc_plans, note FROM territory")}
    dem = {r[0]: {"owner_occupied": r[1]} for r in db.execute("SELECT zip, owner_occupied FROM demographics")}
    ranks = db.execute("""SELECT zip, COUNT(*) c FROM permits WHERE is_base=1 AND work_class='Auxiliary Power'
        AND issue_date>='2026' GROUP BY zip ORDER BY c DESC""").fetchall()
    base_rank = {z: (i + 1, len(ranks)) for i, (z, _) in enumerate(ranks)}
    austin_base_median = statistics.median(r[0] for r in db.execute("""SELECT julianday(issue_date)-julianday(applied_date)
        FROM permits WHERE is_base=1 AND work_class='Auxiliary Power' AND applied_date IS NOT NULL"""))
    deeds = {r["zip"]: r for r in load("data/deeds_by_zip.json")["rows"]}
    storm_zip = {r["zip"]: r for r in load("data/storms.json")["readiness"]["zips"]}
    zips, by_zip = [], {}
    for fz in sorted(funnel["rows"], key=lambda r: r["zip"]):
        zips.append({"zip": fz["zip"], "city": fz["city"], "status": fz["status"]})
        by_zip[fz["zip"]] = zip_cards(db, fz, fz, terr, dem, base_rank, deeds, storm_zip, austin_base_median)
    general = general_cards(db)
    doc = {
        "rebuilt_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "store/data_qa.py",
        "users": USERS,
        "default_zip": "78745",
        "zips": zips,
        "zip_cards": by_zip,
        "cards": general,
    }
    OUT.write_text(json.dumps(doc, indent=1))
    total = len(general) + sum(len(v) for v in by_zip.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {len(zips)} zips x 7 zip cards + {len(general)} general = {total} cards")


if __name__ == "__main__":
    main()
