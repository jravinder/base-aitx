"""Base Brain FAQs: one member FAQ and one internal FAQ for the Base team. Stdlib only.

Base Brain is a prototype, not a Base product. It is the member Q&A plus the app knowledge base.

Writes web/data/faq.json for web/brain.html. Each item has a short answer, one number where it helps,
the source file or page, a link to the page that shows it, and the computation when the answer is
computed at build. Member answers that depend on the zip carry a per-zip answer for every zip in
web/data/data_qa.json.

If data/fleet.db has the table kb_nodes (store/kb.py), each FAQ is also a node (type faq_member or
faq_internal) with edges to the dataset and page it cites. store/kb.py replaces all kb rows when it
runs, so run this file after store/kb.py. Without kb_nodes it skips that step with no message.

  python3 store/faq.py
"""

import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
OUT = os.path.join(ROOT, "web", "data", "faq.json")
PREFIX = "hackathons/2026-09-base-fleet-data/"
BASE_HOME = "https://basepowercompany.com/"
BASE_HOW = "https://basepowercompany.com/how-it-works"
BASE_PRICING = "https://basepowercompany.com/pricing"
BASE_HELP = "https://help.basepowercompany.com/"

MEMBER_CATS = ["Getting started", "My home and the photo", "My battery and the grid", "Storms and backup",
               "Credits (assumed, not a Base offer)", "Privacy", "Help", "Ask Base support"]
TEAM_CATS = ["Ops", "Installers", "Support", "Growth", "Grid and fleet", "Data"]


def load(rel, default=None):
    try:
        with open(os.path.join(ROOT, rel)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def n(x):
    return f"{x:,}"


def pct(x):
    return f"{round(x * 100)}%"


def item(audience, cat, id_, q, a, number, source, page, data=(), computed=None, url=None, **kw):
    """One FAQ entry. data = repo files the answer reads (used for kb edges). computed = how the build got it."""
    return dict(id=id_, audience=audience, category=cat, q=q, a=a, number=number, source=source,
                source_url=url, page=dict(label=page[0], href=page[1]), data=list(data),
                computed=computed, **kw)


def support(id_, q, reason):
    return item("member", "Ask Base support", id_, q, "Ask Base support.", None,
                "Not in Base's public pages (faq/FAQ.md gap list). Members: support@basepowercompany.com. "
                "New customers: 512-518-1009 (faq/corpus/home.md).",
                ("Questions people ask", "data-qa.html"), data=["faq/FAQ.md", "faq/corpus/home.md"],
                url=BASE_HELP, route="base_support", reason=reason)


# ---------------- member FAQ ----------------

def member_items(dq):
    cards = {c["id"]: c for c in dq.get("cards", [])}
    zc = dq.get("zip_cards", {})
    dz = dq.get("default_zip", "78745")
    out = []

    def from_card(cat, cid, q=None):
        c = cards.get(cid)
        if not c:
            return
        out.append(item("member", cat, cid, q or c["q"], c["say"], c.get("number"), c.get("source"),
                        (c["page"]["label"], c["page"]["href"]), data=["web/data/data_qa.json"],
                        computed=c.get("computed"), label=c.get("label")))

    def from_zip(cat, key):
        rows = {z: next((c for c in cs if c["id"].endswith(":" + key)), None) for z, cs in zc.items()}
        base = rows.get(dz)
        if not base:
            return
        out.append(item("member", cat, "zip-" + key, base["q"], base["say"], base.get("number"), base.get("source"),
                        (base["page"]["label"], base["page"]["href"]), data=["web/data/data_qa.json"],
                        computed=re.sub(r"'\d{5}'", "'<zip>'", base.get("computed") or "") or None,
                        zip_aware=True, default_zip=dz,
                        by_zip={z: dict(a=c["say"], number=c.get("number")) for z, c in rows.items() if c}))

    G, H, B, S, C, P, HL = MEMBER_CATS[:7]
    # Getting started
    out.append(item("member", G, "what-is-base", "What is Base?",
                    "Base is a power company in Texas and Illinois. It puts a large backup battery at your home. "
                    "In some areas it is also your electricity provider. Base says 30,000+ homes use it.",
                    "30,000+ homes (Base's own number)", "Base home page, quoted (faq/corpus/home.md)",
                    ("Story overview", "story.html"), data=["faq/corpus/home.md"], url=BASE_HOME))
    out.append(item("member", G, "signup-steps", "How does sign-up work?",
                    "Three steps on Base's page. 1: check your zip or talk to an energy advisor. 2: Base engineers "
                    "review your setup and say if the home fits, and for 0, 1 or 2 batteries. 3: install in two visits.",
                    "3 steps", "Base How it works page, paraphrased (faq/corpus/how-it-works.md)",
                    ("My Home", "onboarding.html#home"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    from_zip(G, "territory")
    out.append(item("member", G, "plans", "What plans are there?",
                    "Three on Base's page. Energy: a fixed rate, where you can choose your provider. Backup + Energy: "
                    "the battery plus energy. Backup Only: the battery with your current utility, in some areas only.",
                    "3 plans", "Base home page and pricing page (faq/corpus/home.md, pricing.md)",
                    ("Next areas", "star.html"), data=["faq/corpus/home.md", "faq/corpus/pricing.md"], url=BASE_PRICING))
    out.append(item("member", G, "cost", "What does it cost?",
                    "It depends on your address. Base's sample plan for Oncor areas is a $695 one-time install, "
                    "a $19 monthly membership and an all-in rate of 13.9 cents per kWh. Enter your zip on Base's site for your price.",
                    "$695 install, $19 a month (Oncor sample)", "Base home page sample plan (faq/corpus/home.md)",
                    ("Next areas", "star.html"), data=["faq/corpus/home.md"], url=BASE_PRICING))
    out.append(item("member", G, "switch-provider", "Do I have to switch my electricity provider?",
                    "Not always. It depends on who delivers your power. In co-op and city utility areas (Austin Energy "
                    "is one), your utility stays and Base adds only the battery.",
                    None, "Base How it works page (faq/corpus/how-it-works.md)",
                    ("Next areas", "star.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    from_card(G, "what-to-do")
    out.append(item("member", G, "install-visits", "How long does the install take?",
                    "Two visits. The first puts in the electrical equipment. Base comes back within three weeks to put "
                    "the battery outside near your meter. No one needs to be home, and your power stays on.",
                    "2 visits, within 3 weeks", "Base How it works page (faq/corpus/how-it-works.md)",
                    ("Path to yes", "recovery.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    from_zip(G, "time")
    from_zip(G, "base")
    from_zip(G, "neighbours")
    # My home and the photo
    from_card(H, "breaker")
    from_card(H, "no-photo")
    from_zip(H, "ready")
    out.append(item("member", H, "where-battery", "Where does the battery go?",
                    "Outside, near your electric meter. Base says it finds a clean, code-compliant spot close to the "
                    "meter, and adds a soft start for a large air conditioner if needed.",
                    None, "Base How it works page, quoted (faq/corpus/how-it-works.md)",
                    ("Clearance", "wall.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    out.append(item("member", H, "wall-space", "Why might my wall not fit?",
                    "Our rule of thumb, from installer reports: a battery needs about 9 ft of clear outside wall, and "
                    "3 ft from the gas meter, the A/C unit and the fence. This is our estimate, not Base's rule. "
                    "A Base engineer makes the real check.",
                    "9 ft of wall, 3 ft clear", "house/clearance.py (our rule-only estimate)",
                    ("Clearance", "wall.html"), data=["house/clearance.py"]))
    from_card(H, "path-to-yes")
    # My battery and the grid
    out.append(item("member", B, "battery-size", "How big is the battery?",
                    "39.2 kWh in each Base Core. Base says that is one of the largest home batteries.",
                    "39.2 kWh", "Base home page (faq/corpus/home.md)",
                    ("My Battery", "member.html"), data=["faq/corpus/home.md"], url=BASE_HOME))
    from_card(B, "battery-today")
    out.append(item("member", B, "not-full", "Why is my battery not full?",
                    "That is expected. The battery charges when power is cheap and may send some back when the grid is "
                    "stressed. Base always keeps backup in reserve, and the charge rarely drops to that minimum.",
                    "30% kept for backup in our plan", "Base How it works page (faq/corpus/how-it-works.md); "
                    "30% is our plan in grid/earned.py", ("My Battery", "member.html"),
                    data=["faq/corpus/how-it-works.md", "web/data/grid_today.json"], url=BASE_HOW))
    from_card(B, "battery-year")
    from_card(B, "grid-stress")
    out.append(item("member", B, "how-rates-low", "How does Base keep rates low?",
                    "Base says: we earn from the grid, not you. The battery helps balance the grid at peak demand.",
                    None, "Base home page, quoted (faq/corpus/home.md)", ("Grid", "grid.html"),
                    data=["faq/corpus/home.md"], url=BASE_HOME))
    out.append(item("member", B, "safe", "Is the battery safe?",
                    "Base says the battery is certified to UL 1973, UL 1741, UL 9540 and UL 9540A. It is tested from "
                    "-22 to 122 F, for flash floods, and under 3 ft of water.",
                    "4 UL standards", "Base home and How it works pages (faq/corpus/home.md, how-it-works.md)",
                    ("My Battery", "member.html"), data=["faq/corpus/home.md", "faq/corpus/how-it-works.md"], url=BASE_HOW))
    # Storms and backup
    out.append(item("member", S, "outage", "What happens when the power goes out?",
                    "The battery takes over by itself, usually in under half a second. Base says most members do not notice.",
                    "Under 1 second", "Base How it works and home pages (faq/corpus/how-it-works.md, home.md)",
                    ("Grid", "grid.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    out.append(item("member", S, "how-long", "How long does backup last?",
                    "Up to 36 hours on one battery, and about 36 to 72 hours with 1 or 2. It depends on how much power you use.",
                    "Up to 36 hours, 1 battery", "Base home and How it works pages",
                    ("My Battery", "member.html"), data=["faq/corpus/home.md", "faq/corpus/how-it-works.md"], url=BASE_HOW))
    out.append(item("member", S, "longer-outage", "What if the outage lasts longer than the battery?",
                    "Base's page says you can recharge the battery with a generator through the built-in port, or with "
                    "connected solar. Neither is required.",
                    None, "Base home page (faq/corpus/home.md)", ("Grid", "grid.html"),
                    data=["faq/corpus/home.md"], url=BASE_HOME))
    out.append(item("member", S, "no-turn-on", "Why did my battery not turn on?",
                    "The home must use under 20 kW for the battery to start. If large devices push use higher, turn "
                    "some off, then turn the battery on in the Base App.",
                    "Under 20 kW", "Base How it works page (faq/corpus/how-it-works.md)",
                    ("My Battery", "member.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    from_card(S, "storm-now")
    from_zip(S, "storms")
    # Credits
    from_card(C, "credit")
    # Privacy
    from_card(P, "private")
    out.append(item("member", P, "answers-stay", "Where do my My Home answers go?",
                    "They stay in your browser. The page sends nothing. The city permit record only gives a starting "
                    "point; you confirm or correct it.",
                    "0 answers sent", "web/onboarding.js (answers kept in the browser)",
                    ("My Home", "onboarding.html#home"), data=["web/onboarding.js"]))
    # Help
    out.append(item("member", HL, "voice-guide", "Can someone read the steps to me?",
                    "Yes. The voice guide reads each step out loud, one at a time. You can skip the photo.",
                    None, "The voice guide page (web/voice.html)", ("Voice guide", "voice.html"), data=["web/voice.html"]))
    out.append(item("member", HL, "caregiver", "Can a caregiver do this for me?",
                    "Yes. Hand this to a caregiver shows every step on one page as text, so a family member or helper "
                    "can do it with you or for you.",
                    None, "The voice guide caregiver view (web/voice.html)", ("Voice guide", "voice.html"),
                    data=["web/voice.html"]))
    out.append(item("member", HL, "contact", "How do I talk to Base?",
                    "New customers: 512-518-1009. Members: support@basepowercompany.com. This app is a prototype and "
                    "is not Base.",
                    None, "Base home page (faq/corpus/home.md)", ("Story overview", "story.html"),
                    data=["faq/corpus/home.md"], url=BASE_HOME))
    out.append(item("member", HL, "move", "What happens if I move?",
                    "Base says the battery agreement runs with the home. If the new owner signs up, it transfers. If not, "
                    "Base removes the system.",
                    None, "Base How it works page, quoted (faq/corpus/how-it-works.md)",
                    ("Questions people ask", "data-qa.html"), data=["faq/corpus/how-it-works.md"], url=BASE_HOW))
    # Policy: Ask Base support
    out += [
        support("pay-billing", "How and when do I pay?",
                "Billing is in Base's Help Center (17 Texas energy articles), which a public crawl cannot read."),
        support("cancel", "Can I cancel, and is there a fee?",
                "No public Base page states cancel terms."),
        support("contract", "How long is the contract?",
                "Contract length is a gap in the public pages (faq/FAQ.md #14)."),
        support("credit-payout", "When is a credit paid out?",
                "The credits on this site are assumed. Base has not offered them, so no payout date exists."),
        support("final-eligibility", "Will my home qualify for sure?",
                "Base engineers decide. Public records give a starting point only (faq/FAQ.md #1 to #4)."),
        support("own-battery", "Do I own the battery?",
                "The page lists this as a video title only, with no answer text (faq/FAQ.md #22)."),
        support("second-battery", "Can I add a second battery later?",
                "Video title only on Base's page (faq/FAQ.md #24)."),
        support("solar", "Does it work with my solar panels?",
                "Video title only; Help Center articles on solar are not public text (faq/FAQ.md #19)."),
        support("hoa", "Does Base handle my HOA?",
                "Only a member review on Base's page says so. That is not a policy (faq/FAQ.md #6)."),
        support("renter", "Can I get Base if I rent?",
                "Not stated on any public Base page (faq/FAQ.md #7)."),
    ]
    return out


# ---------------- internal FAQ ----------------

def db_rows(sql, args=()):
    try:
        con = sqlite3.connect(DB)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []


def team_items():
    O, I, SU, GR, GF, DA = TEAM_CATS
    out = []
    add = lambda *a, **k: out.append(item("internal", *a, **k))
    market = load("data/market.json", {})
    bt = market.get("base_totals", {})
    bz = market.get("base_by_zip", [])

    # Ops
    st = dict((s, (c, b or 0)) for s, c, b in db_rows("SELECT status, COUNT(*), SUM(is_base) FROM permits GROUP BY status"))
    tot = sum(c for c, _ in st.values()) or 1
    g = lambda k: st.get(k, (0, 0))
    add(O, "permit-status", "What does each permit status mean?",
        "Active: issued, work not yet passed final inspection. Final: passed final inspection, the job is done. "
        "Expired: no inspection in time, the permit lapsed. Withdrawn, VOID, Cancelled, Aborted: stopped, no work. "
        "Pending: applied, not yet issued.",
        f"{n(g('Final')[0])} Final, {n(g('Active')[0])} Active of {n(tot)} energy permits; Base: {g('Active')[1]} Active, {g('Final')[1]} Final",
        "City of Austin permit field status_current, in the permits table", ("Permit explorer", "explorer.html"),
        data=["data/mirror/energy_permits.csv.gz"], computed="SELECT status, COUNT(*), SUM(is_base) FROM permits GROUP BY status")
    add(O, "base-2026", "How many Base permits this year, and how many are still open?",
        f"{bt.get('total', 0)} Base permits in Austin in 2026. {bt.get('by_status', {}).get('active', 0)} are open "
        f"(Active) and {bt.get('by_status', {}).get('final', 0)} are final.",
        f"{pct(bt.get('final_rate', 0))} final", f"data/market.json base_totals (rule: {market.get('base_rule', '')})",
        ("Market", "market.html"), data=["data/market.json"], computed="data/market.json base_totals (house/market.py)")
    top_open = sorted(bz, key=lambda r: -r.get("active", 0))[:5]
    add(O, "open-to-chase", "Which zips have the most open Base permits to chase?",
        "Most open permits: " + ", ".join(f"{r['zip']} ({r['active']})" for r in top_open) +
        ". Open means issued but no final inspection yet.",
        f"{sum(r['active'] for r in top_open)} open in the top 5 zips", "data/market.json base_by_zip",
        ("Market", "market.html"), data=["data/market.json"], computed="sort base_by_zip by active, top 5")
    add(O, "median-days", "How long from application to permit?",
        f"The median Base permit takes {bt.get('median_days_applied_to_issued', 0):g} days from applied to issued in Austin.",
        f"{bt.get('median_days_applied_to_issued', 0):g} days (median)", "data/market.json base_totals",
        ("Market", "market.html"), data=["data/market.json"], computed="median(issued - applied) over Base 2026 permits")
    slow = sorted([r for r in bz if r.get("count", 0) >= 5], key=lambda r: -(r.get("median_days_applied_to_issued") or 0))[:3]
    if slow:
        add(O, "slow-zips", "Which zips are slowest to permit?",
            "Slowest medians (zips with 5 or more Base permits): " +
            ", ".join(f"{r['zip']} ({r['median_days_applied_to_issued']:g} days)" for r in slow) + ".",
            f"{slow[0]['median_days_applied_to_issued']:g} days in {slow[0]['zip']}", "data/market.json base_by_zip",
            ("Market", "market.html"), data=["data/market.json"], computed="base_by_zip, count >= 5, sort by median days")
    aux = db_rows("SELECT SUM(is_base), COUNT(*) FROM permits WHERE work_class='Auxiliary Power' AND issue_date>='2026-07-15'")
    if aux and aux[0][1]:
        add(O, "aux-share", "What share of Auxiliary Power permits is Base since Backup Only launched?",
            f"{aux[0][0]} of {aux[0][1]} Auxiliary Power permits issued since 2026-07-15 are Base's.",
            pct(aux[0][0] / aux[0][1]), "permits table (City of Austin feed)", ("Market", "market.html"),
            data=["data/mirror/energy_permits.csv.gz"],
            computed="SELECT SUM(is_base), COUNT(*) FROM permits WHERE work_class='Auxiliary Power' AND issue_date>='2026-07-15'")
    add(O, "base-rule", "What counts as a Base permit?",
        f"Contractor 'Base Power', work class Auxiliary Power, issued 2026 or later. Other contractors show as numbers, not names.",
        None, "data/market.json base_rule; docs/MIRROR_SCHEMA.md", ("Permit explorer", "explorer.html"),
        data=["data/market.json", "docs/MIRROR_SCHEMA.md"])

    # Installers
    sys.path.insert(0, ROOT)
    try:
        from house import clearance as cl
        wall, gas, ac, fence = cl.WALL_FT_PER_BATTERY, cl.GAS_METER_SETBACK_FT, cl.CONDENSER_SETBACK_FT, cl.FENCE_SETBACK_FT
        small, cov = cl.SMALL_LOT_SQFT, cl.HIGH_COVERAGE_RATIO
    except Exception:
        wall, gas, ac, fence, small, cov = 9.0, 3.0, 3.0, 3.0, 4500, 0.4
    add(I, "clearance-rule", "What is the clearance rule?",
        f"About {wall:g} ft of clear outside wall per battery, next to the electric meter and main panel, with "
        f"{gas:g} ft from the gas meter, {ac:g} ft from the A/C condenser and {fence:g} ft from the fence. "
        "A rule-only estimate for triage, not a site plan.",
        f"{wall:g} ft wall, {gas:g} ft setbacks", "house/clearance.py constants", ("Clearance", "wall.html"),
        data=["house/clearance.py"], computed="house/clearance.py WALL_FT_PER_BATTERY and *_SETBACK_FT")
    add(I, "why-wall-fails", "Why does a wall fail the check?",
        f"Four reasons in the rule: the usable wall is under {wall:g} ft; the lot is under {n(small)} sq ft with a "
        f"detached garage (unclear, send a tech); the house covers over {pct(cov)} of the lot, so the side yard is "
        f"thin; or gas is unknown, so the rule keeps {gas:g} ft clear for a meter that may exist.",
        "4 fail reasons", "house/clearance.py estimate_clearance(); web/data/recovery.json", ("Clearance", "wall.html"),
        data=["house/clearance.py", "web/data/recovery.json"])
    rec = load("web/data/recovery.json", {})
    cases = rec.get("cases", [])
    steps = [s for c in cases for b in c.get("blockers", []) for s in b.get("steps", [])]
    after = Counter(s.get("permit", {}).get("type") or "none" for s in steps)
    add(I, "record-after-fix", "What will the permit record show after a fix?",
        "Most fix steps add nothing to the city record. A battery install adds an Electrical Permit, work class "
        "Auxiliary Power. A panel upgrade adds an Electrical Permit, work class Upgrade, and the fit rule then reads "
        "easy. A meter and panel move adds an Electrical Permit.",
        f"{after.get('none', 0)} of {len(steps)} fix steps add no permit",
        "web/data/recovery.json cases[].blockers[].steps[].record_after", ("Path to yes", "recovery.html"),
        data=["web/data/recovery.json"], computed="count steps where permit.type is null")
    reasons = Counter(b["reason"].split(".")[0] for c in cases for b in c.get("blockers", []))
    if reasons:
        r0, k0 = reasons.most_common(1)[0]
        add(I, "top-blocker", "What blocks homes most often?",
            f"{r0}. The fix is a photo of the label and the panel, then an engineer check.",
            f"{k0} of {len(cases)} cases in Path to yes", "web/data/recovery.json (built by house/recovery.py)",
            ("Path to yes", "recovery.html"), data=["web/data/recovery.json"], computed="Counter of blocker reasons")
    who = Counter(s.get("who") for s in steps)
    add(I, "who-fixes", "Who does the fix steps?",
        f"Base does {who.get('Base', 0)}, an electrician {who.get('electrician', 0)}, the member {who.get('member', 0)}. "
        "Each step says if it needs a permit.",
        f"{who.get('Base', 0) + who.get('electrician', 0)} of {len(steps)} steps not by the member",
        "web/data/recovery.json steps[].who", ("Path to yes", "recovery.html"), data=["web/data/recovery.json"],
        computed="Counter of steps[].who")
    add(I, "fix-cost", "What does a fix cost?",
        "Not estimated. No repo source prices these fixes. The only price on file is the $695 Base install fee, "
        "which is not a fix cost.",
        None, "web/data/recovery.json cost_note", ("Path to yes", "recovery.html"), data=["web/data/recovery.json"])
    add(I, "draw-limit", "Why does a battery not start in an outage?",
        "The home must draw under 20 kW. A soft start is added for large HVAC if needed. The member can turn the "
        "battery on in the Base App after cutting use.",
        "Under 20 kW", "Base How it works page (faq/corpus/how-it-works.md)", ("My Battery", "member.html"),
        data=["faq/corpus/how-it-works.md"], url=BASE_HOW)

    # Support
    live_q = os.path.join(ROOT, "data", "live", "questions.jsonl")
    asked = []
    if os.path.exists(live_q):
        with open(live_q) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("path") == "base_support" or r.get("route") == "base_support":
                    asked.append(r.get("question") or r.get("q") or "")
    if asked:
        top = Counter(q.strip().lower() for q in asked if q).most_common(5)
        add(SU, "only-base", "What do members ask that only Base can answer?",
            "Most asked policy questions: " + "; ".join(q for q, _ in top) + ".",
            f"{len(asked)} questions routed to Base support", "data/live/questions.jsonl",
            ("Questions people ask", "data-qa.html"), data=["data/live/questions.jsonl"], computed="path == base_support")
    else:
        gaps = []
        try:
            with open(os.path.join(ROOT, "faq", "FAQ.md")) as f:
                gaps = [m.group(1).strip() for m in re.finditer(r"^\|\s*\d+\s*\|\s*([^|]+)\|\s*GAP\s*\|", f.read(), re.M)]
        except OSError:
            pass
        add(SU, "only-base", "What do members ask that only Base can answer?",
            "From the gap list: " + "; ".join(gaps) + ". The live question log is not on disk yet.",
            f"{len(gaps)} test questions marked GAP", "faq/FAQ.md gap list (data/live/questions.jsonl not present)",
            ("Questions people ask", "data-qa.html"), data=["faq/FAQ.md"], computed="rows marked GAP in faq/FAQ.md")
    try:
        with open(os.path.join(ROOT, "faq", "FAQ.md")) as f:
            rows = re.findall(r"^\|\s*\d+\s*\|[^|]+\|\s*(\w+)", f.read(), re.M)
    except OSError:
        rows = []
    ok = sum(1 for r in rows if r == "Answered")
    add(SU, "public-coverage", "How much can the public pages answer?",
        f"{ok} of {len(rows)} test member questions, plus the move question that retrieval missed. They cover what "
        "Base is and what it costs, but not who can get it.",
        f"{ok} of {len(rows)}", "faq/FAQ.md table rows", ("Questions people ask", "data-qa.html"), data=["faq/FAQ.md"],
        computed="rows marked Answered in the faq/FAQ.md table")
    add(SU, "help-center", "Why not use the Help Center?",
        "Its article text needs JavaScript or a login. A plain fetch sees only the index: 62 battery articles, "
        "17 Texas energy articles.",
        "62 + 17 articles, 0 readable", "faq/corpus/help-center.md", ("Gaps", "gaps.html"),
        data=["faq/corpus/help-center.md"], url=BASE_HELP)
    add(SU, "policy-route", "What does Base Brain say to a policy question?",
        "It does not guess. Questions on credits, cancelling, payments, contracts or eligibility get: Ask Base support.",
        "10 member questions routed", "brain/ask.py BASE_SUPPORT; this FAQ", ("Ask the data", "ask.html"),
        data=["brain/ask.py"])
    add(SU, "contacts", "Where do we send people?",
        "New customers: 512-518-1009. Existing members: support@basepowercompany.com.",
        None, "Base home page (faq/corpus/home.md)", ("Story overview", "story.html"),
        data=["faq/corpus/home.md"], url=BASE_HOME)
    add(SU, "move-miss", "Why did the model say gap for the move question?",
        "Retrieval missed the chunk. The page does answer it: the agreement runs with the home, or Base removes the system.",
        "1 retrieval miss of 25", "faq/FAQ.md note on #17", ("Questions people ask", "data-qa.html"), data=["faq/FAQ.md"])

    # Growth
    look = market.get("lookalikes", {}).get("zips", [])
    if look:
        add(GR, "knock-next", "Where should we knock next?",
            "Zips like Base's best ones (home value, owner homes) with few Base permits: " +
            ", ".join(f"{r['zip']} ({r['base_permits']} permits)" for r in look[:5]) + ".",
            f"{len(look)} lookalike zips", "data/market.json lookalikes (rule: " +
            ", ".join(f"{k} {v:,}" if isinstance(v, int) else f"{k} {v}" for k, v in market["lookalikes"]["rule"].items()) + ")",
            ("Next areas", "star.html"), data=["data/market.json"], computed="market.json lookalikes")
    fun = load("data/funnel.json", {})
    frows = fun.get("rows", [])
    easy = sorted(frows, key=lambda r: -(r.get("star") or 0))[:5]
    if easy:
        add(GR, "easy-fit", "Which zips have the most easy-fit homes?",
            "Estimated easy-fit homes: " + ", ".join(f"{r['zip']} {r.get('city', '')} ({n(r['star'])})" for r in easy) +
            ". Estimates from public totals, not a count of homes.",
            f"{n(easy[0]['star'])} in {easy[0]['zip']}", "data/funnel.json rows[].star (house/funnel.py)",
            ("Next areas", "star.html"), data=["data/funnel.json"], computed="sort funnel rows by star (easy_fit stage)")
    ass = sorted(frows, key=lambda r: -(r.get("assisted_priority") or 0))[:5]
    if ass:
        add(GR, "assisted", "Which zips need assisted onboarding first?",
            "Highest share of people 65+ or with a disability, weighted by offer: " +
            ", ".join(f"{r['zip']} ({r['assisted_priority']:g})" for r in ass) + ". Send the voice guide and caregiver view there.",
            f"score {ass[0]['assisted_priority']:g} in {ass[0]['zip']}", "data/funnel.json assisted_priority (ACS B01001, B18101)",
            ("Voice guide", "voice.html"), data=["data/funnel.json", "data/demographics.json"],
            computed="assisted_priority = share x offer weight x 100")
    deeds = load("data/deeds_by_zip.json", {})
    ours = {z["zip"] for z in load("web/data/data_qa.json", {}).get("zips", [])}
    dr = sorted([r for r in deeds.get("rows", []) if r["zip"] in ours and r.get("parcels", 0) >= 1000],
                key=lambda r: -(r.get("share_sold_last_2y") or 0))[:5]
    if dr:
        add(GR, "recent-buyers", "Where are the recent buyers?",
            "Highest share of homes with a deed in the last 2 years: " +
            ", ".join(f"{r['zip']} ({pct(r['share_sold_last_2y'])})" for r in dr) +
            ". A deed is any transfer, not only a sale. No owner names are kept.",
            f"{pct(dr[0]['share_sold_last_2y'])} in {dr[0]['zip']}", "data/deeds_by_zip.json (Travis and Williamson CAD)",
            ("My Street", "house.html"), data=["data/deeds_by_zip.json"],
            computed="zips in the 59-zip set with 1,000+ parcels, sort by share_sold_last_2y")
    sc = load("web/data/star_cards.json", {})
    storm = sorted(sc.get("rows", []), key=lambda r: -(r.get("per_1000_homes") or 0))[:3]
    if storm:
        add(GR, "storm-zips", "Where did storms push people to backup most?",
            "Backup permits per 1,000 owner homes after Uri and the 2023 ice storm: " +
            ", ".join(f"{r['zip']} ({r['per_1000_homes']:g})" for r in storm) + ". Base installs left out.",
            f"{storm[0]['per_1000_homes']:g} per 1,000 in {storm[0]['zip']}", "web/data/star_cards.json",
            ("Next areas", "star.html"), data=["web/data/star_cards.json", "data/storms.json"],
            computed="sort star_cards rows by per_1000_homes")
    add(GR, "territory-count", "Where can Base be the energy provider?",
        f"{len(fun.get('territory_zips', []))} of our zips are Energy + Backup, {len(fun.get('mixed_zips', []))} are mixed, "
        f"and {len(fun.get('backup_only_zips', []))} are Backup Only (Austin Energy and co-ops).",
        f"{len(fun.get('territory_zips', []))} Energy + Backup zips", "data/funnel.json (from data/ptc_tdu.json)",
        ("Next areas", "star.html"), data=["data/funnel.json", "data/ptc_tdu.json"], computed="len of each zip list")
    con = market.get("contractors_2026", [])
    if len(con) > 1:
        add(GR, "vs-others", "How does Base compare to other installers in Austin?",
            f"Base has {con[0]['permits_2026']} permits in 2026. The next installer has {con[1]['permits_2026']}. "
            "Other installers show as numbers, not names.",
            f"{con[0]['permits_2026']} vs {con[1]['permits_2026']}", "data/market.json contractors_2026",
            ("Market", "market.html"), data=["data/market.json"], computed="market.json contractors_2026")

    # Grid and fleet
    sig = load("web/data/signals.json", {})
    plain = {"base_week": "Base week: are Base permits up or down against the last 4 weeks?",
             "zip_surge": "Zip surge: is one zip getting many backup permits all at once?",
             "price_spike": "Price spike: is Austin power very expensive right now?",
             "low_reserves": "Low reserves: is the grid close to asking people to save power?",
             "storm_alert": "Storm alert: is there a weather alert for Travis or Williamson county?"}
    for r in sig.get("rules", []):
        now = r.get("now", {})
        val = now.get("value")
        unit = now.get("unit") or ("permits in 7 days" if r["name"] == "base_week" else "")
        add(GF, "signal-" + r["name"], f"What does the {r['name'].replace('_', ' ')} signal mean?",
            f"{plain.get(r['name'], '')} Rule: {r['rule']} It fires at {r['threshold']}.",
            f"Now {val:,g} {unit}".strip() + (f" (baseline {now['baseline']:g})" if "baseline" in now else "") +
            f"; firing: {'yes' if r.get('fired_now') else 'no'}" if isinstance(val, (int, float)) else r["threshold"],
            f"store/signals.py RULES; {r['source']}", ("Admin", "admin.html"),
            data=["web/data/signals.json", "store/signals.py"], computed="store/signals.py (web/data/signals.json)")
    gt = load("web/data/grid_today.json", {})
    bat = gt.get("battery")
    if bat:
        hr = lambda he: f"{(he - 1) % 12 or 12} {'am' if he - 1 < 12 else 'pm'}"
        add(GF, "battery-now", "What does the battery do today?",
            f"Plan for {gt.get('date')}: charge from {hr(bat['charge_he'][0])} to {hr(bat['charge_he'][-1] + 1)}, "
            f"discharge from {hr(bat['discharge_he'][0])} to {hr(bat['discharge_he'][-1] + 1)}. "
            f"{pct(bat['reserve'])} of {bat['kwh']:g} kWh stays for backup. Our plan, not Base's dispatch.",
            f"Net ${bat['net']:.2f} today on one battery ({bat['zone']})", "web/data/grid_today.json battery (grid/today.py)",
            ("Grid", "grid.html"), data=["web/data/grid_today.json"], computed=bat.get("rule"))
    gy = load("web/data/data_qa.json", {})
    card = next((c for c in gy.get("cards", []) if c["id"] == "battery-year"), None)
    if card:
        add(GF, "battery-year", "What did one battery earn for the grid last year?",
            card["say"], card.get("number"), card.get("source"), ("Grid", "grid.html"),
            data=["web/data/grid_year.json"], computed=card.get("computed"))
    card = next((c for c in gy.get("cards", []) if c["id"] == "grid-stress"), None)
    if card:
        add(GF, "peak-hours", "When is the grid under most stress?", card["say"], card.get("number"), card.get("source"),
            ("Grid", "grid.html"), data=["data/ercot_load_hourly_2024_2026.csv"], computed=card.get("computed"))

    # Data
    add(DA, "where-number", "Where does a number come from?",
        "Seven steps: public sources, collectors, raw and mirror files, one database (data/fleet.db), derived "
        "tables, small page files, then pages. Each page reads only page files.",
        "8 public sources, no login", "docs/DATAFLOW.md", ("Data flow", "dataflow.html"), data=["docs/DATAFLOW.md"])
    add(DA, "category-accuracy", "How accurate are the permit categories?",
        "143 of 150 sample permits had the right category. Weighted by the mirror mix, about 97%. An AI labelled "
        "the sample, not a domain expert.",
        "143 of 150 (95.3%)", "docs/MIRROR_SCHEMA.md category accuracy check", ("Permit explorer", "explorer.html"),
        data=["docs/MIRROR_SCHEMA.md"])
    gp = load("web/data/gaps.json", {})
    if gp:
        opens = [i for i in gp.get("issues", []) if i.get("state") == "open" and i["title"].startswith("Gap:")]
        add(DA, "open-gaps", "What are the open gaps?",
            "; ".join(f"#{i['number']} {i['title'].replace('Gap: ', '')}" for i in opens) + ".",
            f"{len(opens)} open, {gp.get('fixed', 0)} of {gp.get('found', 0)} fixed", "web/data/gaps.json (GitHub issues)",
            ("Gaps", "gaps.html"), data=["web/data/gaps.json"], computed="issues where state is open")
    mx = db_rows("SELECT MAX(issue_date), COUNT(*) FROM permits")
    if mx:
        add(DA, "freshness", "How fresh is the permit data?",
            f"The newest permit on file was issued {mx[0][0]}. The daily job pulls new rows each morning at 06:15.",
            f"{n(mx[0][1])} energy permits on file", "permits table; collect/daily.sh", ("Data flow", "dataflow.html"),
            data=["data/mirror/energy_permits.csv.gz", "collect/daily.sh"], computed="SELECT MAX(issue_date), COUNT(*) FROM permits")
    add(DA, "names-kept", "Do we keep any owner names?",
        "No. Owner names and addresses are dropped when the appraisal file is read. Other installers show as numbers.",
        "0 names kept", "house/cad_deeds.py; docs/DEEDS.md", ("Data flow", "dataflow.html"),
        data=["data/deeds_by_zip.json", "docs/DEEDS.md"])
    add(DA, "fleet-db", "What is in data/fleet.db?",
        "One SQLite file with permits, ERCOT prices, load, reserves, demographics, territory, signals, judgments and "
        "the Base Brain knowledge base.",
        None, "docs/DATAFLOW.md database table", ("Data flow", "dataflow.html"), data=["docs/DATAFLOW.md"])
    return out


# ---------------- kb ----------------

def kb_upsert(items):
    try:
        con = sqlite3.connect(DB)
        if not con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='kb_nodes'").fetchone():
            con.close()
            return 0
        sys.path.insert(0, os.path.join(ROOT, "store"))
        try:
            from kb import DATASETS
        except Exception:
            DATASETS = {}
        file_ds = {}
        for name, spec in DATASETS.items():
            for f in spec[2]:
                file_ds[f.rstrip("/")] = PREFIX + name
        nodes = {r[0] for r in con.execute("SELECT slug FROM kb_nodes")}
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        with con:
            con.execute("DELETE FROM kb_edges WHERE src LIKE ?", (PREFIX + "faq-%",))
            con.execute("DELETE FROM kb_nodes WHERE type IN ('faq_member', 'faq_internal')")
            for it in items:
                typ = "faq_member" if it["audience"] == "member" else "faq_internal"
                slug = f"{PREFIX}faq-{it['audience']}-{it['id']}"
                body = f"{it['a']}\nNumber: {it.get('number') or '-'}\nSource: {it['source']}\nPage: {it['page']['href']}"
                con.execute("INSERT OR REPLACE INTO kb_nodes VALUES (?,?,?,?,?,?,?)",
                            (slug, typ, it["q"], it["a"][:300], body, "web/data/faq.json", now))
                page = PREFIX + "page-" + it["page"]["href"].split("#")[0].replace(".html", "")
                if page in nodes:
                    con.execute("INSERT OR IGNORE INTO kb_edges VALUES (?,?,?,?)", (slug, page, "shown_on", "store/faq.py"))
                for f in it.get("data", []):
                    ds = file_ds.get(f)
                    if ds and ds in nodes:
                        con.execute("INSERT OR IGNORE INTO kb_edges VALUES (?,?,?,?)", (slug, ds, "cites", f))
        con.close()
        return len(items)
    except sqlite3.Error:
        return 0


def main():
    dq = load("web/data/data_qa.json", {})
    items = member_items(dq) + team_items()
    cats = {"member": MEMBER_CATS, "internal": TEAM_CATS}
    doc = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "builder": "store/faq.py",
        "label": "Base Brain is a prototype, not a Base product.",
        "default_zip": dq.get("default_zip", "78745"),
        "zips": dq.get("zips", []),
        "categories": cats,
        "counts": {a: {c: sum(1 for i in items if i["audience"] == a and i["category"] == c) for c in cs}
                   for a, cs in cats.items()},
        "items": items,
    }
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1)
    k = kb_upsert(items)
    m = sum(1 for i in items if i["audience"] == "member")
    print(f"faq: {m} member, {len(items) - m} internal, "
          f"{sum(1 for i in items if i.get('route') == 'base_support')} to Base support, kb nodes {k} -> {OUT}")


if __name__ == "__main__":
    main()
