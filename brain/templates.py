"""Templates first: intent patterns for the common questions.

A matched template fills a parameterised Socrata or local query. No model call.
A small code writer turns the result into 1 to 3 sentences. The critic in brain/ask.py
still checks every number. Unmatched questions go to the full agent path.

match(question, today) -> None or {id, source, why, params, query | code, say}
run_code(source, code) -> result   (in process, over data cached at first use)
"""
import csv
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

FILES = {  # source -> (file, how to read rows)
    "dam": ("ercot_dam_hourly_2025_2026.csv", "csv"),
    "load": ("ercot_load_hourly_2024_2026.csv", "csv"),
    "demographics": ("demographics.json", "rows"),
    "ptc": ("ptc_tdu.json", "zips"),
    "market": ("market.json", None),
    "zips": ("permits_by_zip.json", "rows"),
    "funnel": ("funnel.json", "rows"),
    "storms": ("storms.json", None),
    "deeds": ("deeds_by_zip.json", "rows"),
}
_cache = {}


def _num(v):
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def load(src):
    if src not in _cache:
        f, how = FILES[src]
        path = os.path.join(DATA, f)
        if how == "csv":
            with open(path) as fh:
                rows = [{k: _num(v) for k, v in r.items()} for r in csv.DictReader(fh)]
            _cache[src] = (rows, None)
        else:
            data = json.load(open(path))
            if how == "rows":
                rows = data["rows"]
            elif how == "zips":
                rows = [{"zip": z, **v} for z, v in data["zips"].items()]
            else:
                rows = None
            _cache[src] = (rows, data)
    return _cache[src]


def warm():
    for s in FILES:
        load(s)


def run_code(src, code):
    rows, data = load(src)
    env = {"rows": rows, "data": data, "Counter": Counter, "defaultdict": defaultdict,
           "statistics": statistics, "round": round}
    exec(code, env)
    res = env.get("result")
    return list(res)[:50] if isinstance(res, (list, tuple)) else res


# ---------- parameter parsing ----------

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
MON_RE = re.compile(r"\b(" + "|".join(m[:3] + (m[3:] and "(?:" + m[3:] + ")?") for m in MONTHS) + r")\.?\s*(?:of\s+)?(\d{4})?\b", re.I)
ZIP_RE = re.compile(r"\b(7\d{4})\b")
YEAR_RE = re.compile(r"\b(20[12]\d)\b")


def zips(q):
    return ZIP_RE.findall(q)


def years(q):
    ys = [int(y) for y in YEAR_RE.findall(q)]
    m = re.search(r"\b(20[12]\d)\s*(?:to|through|-|and)\s*(20[12]\d)\b", q)
    if m and "to" in m.group(0) or m and "through" in m.group(0):
        a, b = int(m.group(1)), int(m.group(2))
        return list(range(a, b + 1))
    return ys


def ym(y, m):
    return f"{y:04d}-{m:02d}"


def month_start(y, m):
    return f"{y:04d}-{m:02d}-01T00:00:00"


def next_month(y, m):
    return (y + (m == 12), 1 if m == 12 else m + 1)


def periods(q, today):
    """Time windows named in the question: list of (start, end, label). Empty means all time."""
    t = date.fromisoformat(today)
    ql = q.lower()
    out = []
    for mo, yr in MON_RE.findall(q):
        mi = [m[:3] for m in MONTHS].index(mo[:3].lower()) + 1
        if mo.lower() == "may" and not yr and not re.search(r"\bmay\s+20", ql):
            continue  # "may" as a verb
        y = int(yr) if yr else (t.year if mi <= t.month else t.year - 1)
        ny, nm = next_month(y, mi)
        out.append((month_start(y, mi), month_start(ny, nm), ym(y, mi)))
    if out:
        return out
    m = re.search(r"\blast (\d+) days\b", ql)
    if m:
        s = (t - timedelta(days=int(m.group(1)))).isoformat()
        return [(s + "T00:00:00", None, f"the last {m.group(1)} days")]
    if "last month" in ql:
        y, mi = (t.year, t.month - 1) if t.month > 1 else (t.year - 1, 12)
        return [(month_start(y, mi), month_start(t.year, t.month), ym(y, mi))]
    if "this month" in ql:
        ny, nm = next_month(t.year, t.month)
        return [(month_start(t.year, t.month), month_start(ny, nm), ym(t.year, t.month))]
    ys = years(q)
    if "this year" in ql and not ys:
        ys = [t.year]
    if "last year" in ql and not ys:
        ys = [t.year - 1]
    if len(ys) == 1:
        return [(f"{ys[0]}-01-01T00:00:00", f"{ys[0] + 1}-01-01T00:00:00", str(ys[0]))]
    if len(ys) == 2 and re.search(r"\b(vs|versus|compared?)\b", ql):
        return [(f"{y}-01-01T00:00:00", f"{y + 1}-01-01T00:00:00", str(y)) for y in ys]
    if len(ys) > 1:
        return [(f"{min(ys)}-01-01T00:00:00", f"{max(ys) + 1}-01-01T00:00:00", f"{min(ys)} to {max(ys)}")]
    return []


def threshold(q):
    m = re.search(r"(?:over|above|more than|exceed\w*|greater than|>)\s*\$?\s*(-?[\d,]+(?:\.\d+)?)", q, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def zone_dam(q):
    ql = q.lower()
    if "north" in ql:
        return "north", "LZ_NORTH"
    if "houston" in ql:
        return "houston", "LZ_HOUSTON"
    return "aen", "LZ_AEN"


def zone_load(q):
    ql = q.lower()
    if "scent" in ql or "south central" in ql or "austin" in ql:
        return "SCENT", "South Central (SCENT)"
    if "ncent" in ql or "north central" in ql:
        return "NCENT", "North Central (NCENT)"
    if "coast" in ql or "houston" in ql:
        return "COAST", "Coast"
    return "ERCOT", "ERCOT system"


def fmt(v):
    if isinstance(v, str):
        try:
            v = float(v) if "." in v else int(v)
        except ValueError:
            return v
    if isinstance(v, float):
        v = round(v, 2)
        if v == int(v) and abs(v) >= 1000:
            return f"{int(v):,}"
        return f"{v:,}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def pct(v):
    return f"{round(float(v) * 100, 1)}%"


def month_of(v):
    return str(v)[:7]


def listing(rows, key, val, unit="", n=8):
    parts = [f"{r[key]} ({fmt(r[val])}{unit})" for r in rows[:n]]
    return ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] if parts else ""


# ---------- permits (Socrata) ----------

def permits_match(q, today):
    ql = q.lower()
    if "permit" not in ql or re.search(r"\d{4}-\d{2}-\d{2}|\bafter\b|\bbefore\b|\bweek\b|per 1,?000|final rate|days from|median number of days|share of|"
                                       r"solar permits but|more solar|than battery|service upgrade|single family", ql):
        return None
    if re.search(r"\bcontractors?\b", ql):
        return None
    if re.search(r"\bbase\b", ql) and not re.search(r"\bbackup\b.*\bbase\b", ql):
        subj, where, noun = "base", "contractor_company_name='Base Power'", "Base Power permits"
    elif "solar" in ql:
        subj, where, noun = "solar", "upper(description) like '%SOLAR%'", "solar permits"
    elif re.search(r"backup|battery|auxiliary|generator", ql):
        subj, where, noun = "backup", "work_class='Auxiliary Power'", "Auxiliary Power (backup) permits"
    else:
        return None
    conds = [where]
    zs = zips(q)
    if zs:
        conds.append(f"original_zip='{zs[0]}'")
    if re.search(r"still active|are active|active permits", ql):
        conds.append("status_current='Active'")
    ps = periods(q, today)
    if re.search(r"each year|per year|by year|every year|annual", ql):
        group = "year"
    elif re.search(r"each month|by month|per month|monthly|which month", ql):
        group = "month"
    elif re.search(r"by status|final|status", ql) and "still active" not in ql:
        group = "status"
    elif re.search(r"which zip|top zip|by zip|per zip|most permits|where did|which zips|zip codes", ql) and not zs:
        group = "zip"
    else:
        group = None
    query = {}
    if len(ps) == 2 and group is None:
        sel = [f"sum(case(issue_date >= '{a}' AND issue_date < '{b}', 1, true, 0)) as p_{lab.replace('-', '_')}"
               for a, b, lab in ps]
        query["$select"] = ", ".join(sel)
        lo, hi = min(p[0] for p in ps), max(p[1] for p in ps)
        conds.append(f"issue_date >= '{lo}' AND issue_date < '{hi}'")
    else:
        if ps:
            a, b, _ = ps[0]
            conds.append(f"issue_date >= '{a}'" + (f" AND issue_date < '{b}'" if b else ""))
        if group == "zip":
            query.update({"$select": "original_zip, count(*) as permits", "$group": "original_zip",
                          "$order": "permits DESC", "$limit": 8})
        elif group == "month":
            query.update({"$select": "date_trunc_ym(issue_date) as month, count(*) as permits",
                          "$group": "month", "$order": "month", "$limit": 50})
        elif group == "year":
            query.update({"$select": "calendar_year_issued as year, count(*) as permits",
                          "$group": "year", "$order": "year", "$limit": 50})
        elif group == "status":
            query.update({"$select": "status_current as status, count(*) as permits",
                          "$group": "status", "$order": "permits DESC", "$limit": 10})
        else:
            query["$select"] = "count(*) as permits"
    query["$where"] = " AND ".join(conds)
    place = f"zip {zs[0]}" if zs else "Austin"
    when = " versus ".join(p[2] for p in ps) if len(ps) == 2 and group is None else (ps[0][2] if ps else "all years")
    params = {"subject": subj, "zip": zs[0] if zs else None, "group": group, "period": when}

    def say(res):
        if not res:
            return f"The permit data has no match for {noun} in {place}, {when}."
        if len(ps) == 2 and group is None:
            r = res[0]
            parts = [f"{fmt(r.get('p_' + lab.replace('-', '_'), 0))} in {lab}" for _, _, lab in ps]
            return f"{(noun[0].upper() + noun[1:])} issued in {place}: " + " versus ".join(parts) + "."
        if group == "zip":
            return f"{(noun[0].upper() + noun[1:])} by zip, {when}: the top zips are " + listing(res, "original_zip", "permits") + "."
        if group == "month":
            rows = [{"m": month_of(r["month"]), "n": r["permits"]} for r in res]
            top = max(rows, key=lambda r: int(r["n"]))
            return (f"{(noun[0].upper() + noun[1:])} per month in {place}, {when}: " + listing(rows, "m", "n", n=14)
                    + f". The busiest month is {top['m']} with {fmt(top['n'])}.")
        if group == "year":
            return f"{(noun[0].upper() + noun[1:])} per year in {place}: " + listing(res, "year", "permits", n=14) + "."
        if group == "status":
            return f"{(noun[0].upper() + noun[1:])} in {place}, {when}, by current status: " + listing(res, "status", "permits") + "."
        extra = " that are still active" if "status_current='Active'" in query["$where"] else ""
        return f"{fmt(res[0]['permits'])} {noun}{extra} were issued in {place}, {when}."
    why = f"{noun} {('by ' + group) if group else 'count'}, {when}, {place}"
    return {"id": f"permits.{subj}.{group or 'count'}", "source": "permits", "why": why, "params": params,
            "query": query, "say": say}


# ---------- market.json ----------

def market_match(q, today):
    ql = q.lower()
    if re.search(r"contractors?", ql) and re.search(r"backup|auxiliary|battery|permit", ql):
        code = "result = data['contractors_2026'][:8]"

        def say(res):
            base = next((r for r in res if r["contractor"] == "Base Power"), None)
            rank = res.index(base) + 1 if base else None
            s = "Auxiliary Power permits by contractor in 2026: " + listing(res, "contractor", "permits_2026", n=5) + "."
            if base:
                s += f" Base Power is contractor number {rank} with {fmt(base['permits_2026'])}."
            return s
        return {"id": "market.contractors", "source": "market", "why": "contractor ranking 2026 from market.json",
                "params": {}, "code": code, "say": say}
    if re.search(r"final (versus|vs|or|and) (still )?active|final rate|share of base.*final|are final", ql) and not re.search(r"above|below|over|zips", ql):
        code = "result = {'total': data['base_totals']['total'], **data['base_totals']['by_status'], 'final_rate': data['base_totals']['final_rate']}"
        return {"id": "market.status", "source": "market", "why": "Base permit status split from market.json",
                "params": {}, "code": code,
                "say": lambda r: (f"Of {fmt(r['total'])} Base Power permits, {fmt(r['final'])} are final and "
                                  f"{fmt(r['active'])} are still active, a final rate of {pct(r['final_rate'])}.")}
    if re.search(r"days from appl|application to issue|days to issue|how long.*issue", ql):
        code = "result = {'median_days_applied_to_issued': data['base_totals']['median_days_applied_to_issued'], 'total': data['base_totals']['total']}"
        return {"id": "market.days", "source": "market", "why": "median days from application to issue, market.json",
                "params": {}, "code": code,
                "say": lambda r: (f"The median time from application to issue for Base Power permits is "
                                  f"{fmt(r['median_days_applied_to_issued'])} days, over {fmt(r['total'])} permits.")}
    if re.search(r"per 1,?000", ql) and "base" in ql:
        code = ("top = sorted(data['base_by_zip'], key=lambda r: -r['per_1000_owner_occupied'])[:6]\n"
                "result = [{'zip': r['zip'], 'per_1000': r['per_1000_owner_occupied'], 'count': r['count']} for r in top]")
        return {"id": "market.per1000", "source": "market", "why": "Base permits per 1,000 owner-occupied homes by zip",
                "params": {}, "code": code,
                "say": lambda r: ("Base Power permits per 1,000 owner-occupied homes, top zips: "
                                  + listing(r, "zip", "per_1000") + ".")}
    return None


# ---------- ERCOT day-ahead prices ----------

def dam_match(q, today):
    ql = q.lower()
    if not re.search(r"price|\$/mwh|lz_", ql) or re.search(r"than lz|higher than|spread|difference|hour ending|he ?\d", ql):
        return None
    col, zname = zone_dam(q)
    ps = periods(q, today)
    if len(ps) > 1 or (ps and ps[0][1] is None):
        return None
    pref = ps[0][2] if ps else ""
    if re.search(r"summer|winter|june to|to august", ql):
        return None
    cond = f"str(r['date']).startswith('{pref}')" if pref else "True"
    when = pref or "2025 to 2026"
    p = {"zone": zname, "period": when}
    thr = threshold(q)
    if re.search(r"below zero|negative|under zero|less than zero|below \$?0\b", ql):
        thr, below = 0.0, True
    else:
        below = False
    if thr is not None and re.search(r"how many hours|hours", ql):
        op = "<" if below else ">"
        code = (f"hits = [r for r in rows if {cond} and r['{col}'] {op} {thr:g}]\n"
                f"result = {{'hours': len(hits), 'days': len(set(r['date'] for r in hits)), "
                f"'{'min' if below else 'max'}_price': {'min' if below else 'max'}(r['{col}'] for r in hits) if hits else None}}")
        p["threshold"] = thr

        def say(r):
            side = "below $0" if below else f"over ${fmt(thr)}"
            if not r["hours"]:
                return f"No hours in {when} had a {zname} day-ahead price {side} per MWh."
            ext = "lowest" if below else "highest"
            return (f"{fmt(r['hours'])} hours in {when} had a {zname} day-ahead price {side} per MWh, "
                    f"across {fmt(r['days'])} day{'s' if r['days'] != 1 else ''}. The {ext} of those hours was ${fmt(r[('min' if below else 'max') + '_price'])} per MWh.")
        return {"id": "dam.hours_threshold", "source": "dam", "why": f"count hours {'below' if below else 'over'} a price, {zname}, {when}",
                "params": p, "code": code, "say": say}
    if re.search(r"(top|highest|most expensive|biggest).{0,20}(price )?days|price days", ql):
        code = (f"d = defaultdict(list)\nfor r in rows:\n    if {cond}: d[r['date']].append(r['{col}'])\n"
                f"top = sorted(d.items(), key=lambda kv: -max(kv[1]))[:5]\n"
                f"result = [{{'date': k, 'max_price': max(v), 'avg_price': round(sum(v) / len(v), 2)}} for k, v in top]")

        def say(r):
            return (f"The top {zname} day-ahead price days in {when}, by highest hourly price in $/MWh: "
                    + ", ".join(f"{x['date']} (${fmt(x['max_price'])}, daily average ${fmt(x['avg_price'])})" for x in r) + ".")
        return {"id": "dam.top_days", "source": "dam", "why": f"top price days by daily max, {zname}, {when}",
                "params": p, "code": code, "say": say}
    if re.search(r"highest|maximum|max|peak|most expensive", ql):
        code = (f"top = sorted([r for r in rows if {cond}], key=lambda r: -r['{col}'])[:3]\n"
                f"result = [{{'date': r['date'], 'hour_ending': r['he'], 'price': r['{col}']}} for r in top]")

        def say(r):
            a = r[0]
            rest = "; ".join(f"{x['date']} hour ending {x['hour_ending']} at ${fmt(x['price'])}" for x in r[1:])
            return (f"The highest {zname} day-ahead price in {when} was ${fmt(a['price'])} per MWh on {a['date']}, "
                    f"hour ending {a['hour_ending']}. The next highest: {rest}.")
        return {"id": "dam.max", "source": "dam", "why": f"highest hourly price, {zname}, {when}",
                "params": p, "code": code, "say": say}
    if re.search(r"average|mean", ql) and re.search(r"month", ql):
        code = (f"d = defaultdict(list)\nfor r in rows:\n    if {cond}: d[str(r['date'])[:7]].append(r['{col}'])\n"
                f"result = [{{'month': k, 'avg_price': round(sum(v) / len(v), 2)}} for k, v in sorted(d.items())]")

        def say(r):
            hi = max(r, key=lambda x: x["avg_price"])
            return (f"Average {zname} day-ahead price by month in {when}, $/MWh: "
                    + ", ".join(f"{x['month']} ${fmt(x['avg_price'])}" for x in r)
                    + f". The highest month is {hi['month']}.")
        return {"id": "dam.avg_month", "source": "dam", "why": f"average price by month, {zname}, {when}",
                "params": p, "code": code, "say": say}
    return None


# ---------- ERCOT load ----------

def load_match(q, today):
    ql = q.lower()
    if not re.search(r"\bload\b|demand", ql) or re.search(r"average (ercot |system )?load in|which (weather )?zone", ql):
        return None
    col, zname = zone_load(q)
    ys = years(q)
    ycond = f"r['year'] in {tuple(ys) if len(ys) > 1 else '(' + str(ys[0]) + ',)'}" if ys else "True"
    when = ", ".join(map(str, ys)) if ys else "2024 to 2026"
    p = {"zone": zname, "years": ys}
    if re.search(r"hour of the day|what hour|which hour|peak hours?|hour does", ql):
        code = (f"d = defaultdict(list)\nfor r in rows:\n    if {ycond}: d[r['hour_ending']].append(r['{col}'])\n"
                f"avg = sorted(((h, sum(v) / len(v)) for h, v in d.items()), key=lambda x: -x[1])\n"
                f"result = [{{'hour_ending': h, 'avg_mw': round(v)}} for h, v in avg[:3]]")

        def say(r):
            return (f"{zname} load in {when} peaks on average at hour ending {r[0]['hour_ending']}, "
                    f"at {fmt(r[0]['avg_mw'])} MW. The next highest hours are hour ending {r[1]['hour_ending']} "
                    f"({fmt(r[1]['avg_mw'])} MW) and hour ending {r[2]['hour_ending']} ({fmt(r[2]['avg_mw'])} MW).")
        return {"id": "load.peak_hour", "source": "load", "why": f"average load by hour, {zname}, {when}",
                "params": p, "code": code, "say": say}
    if re.search(r"which month|what month|month of", ql):
        code = (f"d = {{}}\nfor r in rows:\n    if {ycond} and r['{col}'] > d.get(r['month'], (0,))[0]: d[r['month']] = (r['{col}'], r['datetime'])\n"
                f"top = sorted(d.items(), key=lambda kv: -kv[1][0])[:3]\n"
                f"result = [{{'month': m, 'peak_mw': round(v[0]), 'at': v[1]}} for m, v in top]")

        def say(r):
            a = r[0]
            return (f"In {when}, the month with the highest peak {zname} load is {MONTHS[a['month'] - 1].title()}, "
                    f"with {fmt(a['peak_mw'])} MW at {a['at']}. Next: {MONTHS[r[1]['month'] - 1].title()} ({fmt(r[1]['peak_mw'])} MW) "
                    f"and {MONTHS[r[2]['month'] - 1].title()} ({fmt(r[2]['peak_mw'])} MW).")
        return {"id": "load.peak_month", "source": "load", "why": f"peak load per month, {zname}, {when}",
                "params": p, "code": code, "say": say}
    if re.search(r"highest|peak|max", ql):
        code = (f"d = {{}}\nfor r in rows:\n    if {ycond} and r['{col}'] > d.get(r['year'], (0,))[0]: d[r['year']] = (r['{col}'], r['datetime'])\n"
                f"result = [{{'year': y, 'peak_mw': round(v[0]), 'at': v[1]}} for y, v in sorted(d.items())]")

        def say(r):
            return f"Peak hourly {zname} load: " + "; ".join(
                f"{x['year']}: {fmt(x['peak_mw'])} MW at {x['at']}" for x in r) + "."
        return {"id": "load.peak_year", "source": "load", "why": f"peak load per year, {zname}, {when}",
                "params": p, "code": code, "say": say}
    return None


# ---------- storms ----------

def storm_match(q, today):
    ql = q.lower()
    if re.search(r"4 ?(times|x)|four times", ql):
        code = ("m = data['months_over_4x']\ntop = max(m, key=lambda r: r['count'])\n"
                "result = {'months_over_4x': len(m), 'first': m[0]['month'], 'last': m[-1]['month'], "
                "'top_month': top['month'], 'top_count': top['count'], 'top_multiple': top['multiple'], "
                "'baseline_2020_monthly': data['baseline_2020_monthly']}")
        return {"id": "storms.over4x", "source": "storms", "why": "months over 4 times the 2020 backup permit rate",
                "params": {}, "code": code,
                "say": lambda r: (f"{fmt(r['months_over_4x'])} months had more than 4 times the 2020 monthly rate of "
                                  f"{fmt(r['baseline_2020_monthly'])} backup permits, from {r['first']} to {r['last']}. "
                                  f"The biggest was {r['top_month']} with {fmt(r['top_count'])} permits, "
                                  f"{fmt(r['top_multiple'])} times the baseline.")}
    if not re.search(r"storm|uri\b|surge", ql):
        return None
    code = ("result = [{'name': s['name'], 'month': s['month'], 'count': s['count'], 'multiple': s['multiple'], "
            "'peak_month': s['peak_month'], 'peak_count': s['peak_count'], 'surge_months': s['surge_months'], "
            "'lead_category': s['lead_category'], 'baseline_year': 2020} for s in data['storms']]")
    pick = "uri" if "uri" in ql else "ice" if "ice" in ql else None

    def say(r):
        rows = [s for s in r if not pick or pick in s["name"].lower()] or r
        return " ".join(
            f"{s['name']} ({s['month']}): {fmt(s['count'])} backup permits in the storm month, {fmt(s['multiple'])} "
            f"times the 2020 rate, peaking at {fmt(s['peak_count'])} in {s['peak_month']}; the surge lasted "
            f"{fmt(s['surge_months'])} months, led by {s['lead_category'].replace('_', ' ')} permits." for s in rows)
    return {"id": "storms.list", "source": "storms", "why": "storm months and permit surges from storms.json",
            "params": {"storm": pick}, "code": code, "say": say}


# ---------- funnel: easy fit, assisted priority ----------

def funnel_match(q, today):
    ql = q.lower()
    zs = zips(q)
    if re.search(r"easy[- ]?fit|star homes|permit-ready", ql):
        if re.search(r"share|cohort|how many of", ql) and not re.search(r"homes are in|homes in zip", ql):
            code = "result = data['easy_share']"
            return {"id": "funnel.easy_share", "source": "funnel", "why": "easy-fit share in the house cohort",
                    "params": {}, "code": code,
                    "say": lambda r: f"{fmt(r['easy'])} of {fmt(r['total'])} houses in the cohort are easy fits."}
        if re.search(r"county|williamson|travis|confidence", ql):
            return None
        if zs:
            code = (f"r = next((x for x in rows if x['zip'] == '{zs[0]}'), None)\n"
                    "result = r and {'zip': r['zip'], 'city': r['city'], 'easy_fit': r['star'], 'tdu': r['tdu'], "
                    "'households': r['stages'][0]['count'], 'status': r['status']}")
            return {"id": "funnel.easy_zip", "source": "funnel", "why": f"easy-fit homes in zip {zs[0]}",
                    "params": {"zip": zs[0]}, "code": code,
                    "say": lambda r: (f"Zip {r['zip']} ({r['city']}, {r['tdu']}) has an estimated {fmt(r['easy_fit'])} "
                                      f"easy-fit homes out of {fmt(r['households'])} households."
                                      if r else f"Zip {zs[0]} is not in the funnel data.")}
        code = ("top = sorted(rows, key=lambda r: -(r['star'] or 0))[:8]\n"
                "result = [{'zip': r['zip'], 'city': r['city'], 'easy_fit': r['star']} for r in top]")
        return {"id": "funnel.easy_top", "source": "funnel", "why": "zips ranked by estimated easy-fit homes",
                "params": {}, "code": code,
                "say": lambda r: "Zips with the most estimated easy-fit homes: " + ", ".join(
                    f"{x['zip']} {x['city']} ({fmt(x['easy_fit'])})" for x in r) + "."}
    if re.search(r"assisted", ql):
        if zs:
            code = (f"r = next((x for x in rows if x['zip'] == '{zs[0]}'), None)\n"
                    "result = r and {'zip': r['zip'], 'city': r['city'], 'assisted_priority': r['assisted_priority'], "
                    "'why': r['assisted_why']}")
            return {"id": "funnel.assisted_zip", "source": "funnel", "why": f"assisted priority for zip {zs[0]}",
                    "params": {"zip": zs[0]}, "code": code,
                    "say": lambda r: (f"Zip {r['zip']} ({r['city']}) has an assisted onboarding priority of "
                                      f"{fmt(r['assisted_priority'])}. Basis: {r['why']}."
                                      if r else f"Zip {zs[0]} is not in the funnel data.")}
        code = ("top = sorted(rows, key=lambda r: -(r['assisted_priority'] or 0))[:6]\n"
                "result = [{'zip': r['zip'], 'city': r['city'], 'assisted_priority': r['assisted_priority']} for r in top]")
        return {"id": "funnel.assisted_top", "source": "funnel", "why": "zips ranked by assisted onboarding priority",
                "params": {}, "code": code,
                "say": lambda r: ("Zips ranked by assisted onboarding priority (share of older residents and residents "
                                  "with a disability, weighted by service status): " + ", ".join(
                                      f"{x['zip']} {x['city']} ({fmt(x['assisted_priority'])})" for x in r) + ".")}
    return None


# ---------- Power to Choose ----------

def ptc_match(q, today):
    ql = q.lower()
    zs = zips(q)
    if re.search(r"zero retail|no retail|no choice|zero plans|0 plans", ql):
        code = "z = sorted(r['zip'] for r in rows if r['plans'] == 0)\nresult = {'zips_without_choice': len(z), 'zips': z}"
        return {"id": "ptc.no_choice", "source": "ptc", "why": "zips with 0 retail plans on Power to Choose",
                "params": {}, "code": code,
                "say": lambda r: (f"{r['zips_without_choice']} zips have no retail electricity plans on Power to Choose (a municipal or "
                                  f"co-op utility serves them): " + ", ".join(r['zips']) + ".")}
    if "oncor" in ql and not zs:
        code = "z = sorted(r['zip'] for r in rows if any('ONCOR' in t for t in r['tdus']))\nresult = {'oncor_zips': len(z), 'zips': z}"
        return {"id": "ptc.oncor", "source": "ptc", "why": "zips whose wires utility is Oncor",
                "params": {}, "code": code,
                "say": lambda r: f"{r['oncor_zips']} zips in the data are served by Oncor: " + ", ".join(r['zips']) + "."}
    if zs and re.search(r"who sells|sells power|utility|tdu|retail|plans|power to choose|serves", ql):
        code = (f"r = next((x for x in rows if x['zip'] == '{zs[0]}'), None)\n"
                "result = r and {'zip': r['zip'], 'plans': r['plans'], 'tdus': r['tdus']}")

        def say(r):
            if not r:
                return f"Zip {zs[0]} is not in the Power to Choose table."
            if not r["plans"]:
                return (f"Zip {r['zip']} has 0 retail plans on Power to Choose, so no retail provider sells there: "
                        f"a municipal utility or co-op serves it.")
            t = ", ".join(k.title() for k in r["tdus"])
            return (f"Zip {r['zip']} has retail choice: {fmt(r['plans'])} plans on Power to Choose from competing "
                    f"retail providers, delivered over the wires of {t}.")
        return {"id": "ptc.zip", "source": "ptc", "why": f"retail plans and wires utility for zip {zs[0]}",
                "params": {"zip": zs[0]}, "code": code, "say": say}
    return None


# ---------- deeds ----------

def deed_match(q, today):
    ql = q.lower()
    if not re.search(r"deed|turnover|sold in the last|held 20|years since", ql):
        return None
    zs = zips(q)
    if zs:
        code = (f"r = next((x for x in rows if x['zip'] == '{zs[0]}'), None)\n"
                "result = r and {k: r[k] for k in ('zip', 'parcels', 'median_years_since_deed', 'share_sold_last_2y', "
                "'share_held_20y_plus', 'share_homestead')}")
        return {"id": "deeds.zip", "source": "deeds", "why": f"deed turnover for zip {zs[0]}",
                "params": {"zip": zs[0]}, "code": code,
                "say": lambda r: (f"In zip {r['zip']}, over {fmt(r['parcels'])} single-family parcels, "
                                  f"{pct(r['share_sold_last_2y'])} changed hands in the last 2 years, "
                                  f"{pct(r['share_held_20y_plus'])} were held 20 years or more, and the median time "
                                  f"since the last deed is {fmt(r['median_years_since_deed'])} years."
                                  if r else f"Zip {zs[0]} is not in the deed data.")}
    key = "share_held_20y_plus" if re.search(r"held 20|20 years|longest", ql) else "share_sold_last_2y"
    label = "held 20 years or more" if key == "share_held_20y_plus" else "changed hands in the last 2 years"
    code = (f"big = [r for r in rows if r['parcels'] >= 1000]\n"
            f"top = sorted(big, key=lambda r: -r['{key}'])[:6]\n"
            f"result = [{{'zip': r['zip'], '{key}': r['{key}'], 'parcels': r['parcels']}} for r in top]")
    return {"id": f"deeds.top.{key}", "source": "deeds", "why": f"zips ranked by share {label}, 1,000+ parcels",
            "params": {"rank_by": key}, "code": code,
            "say": lambda r: (f"Zips with 1,000 or more single-family parcels, ranked by share {label}: " + ", ".join(
                f"{x['zip']} ({pct(x[key])} of {fmt(x['parcels'])})" for x in r) + ".")}


# ---------- Census ----------

DEMO_FIELDS = [("median year built", "median_year_built", ""), ("median household income", "median_income", "$"),
               ("median income", "median_income", "$"), ("median home value", "median_home_value", "$"),
               ("owner-occupied", "owner_occupied", ""), ("households", "households", "")]


def demo_match(q, today):
    ql = q.lower()
    zs = zips(q)
    if re.search(r"permit|price|load|deed|easy", ql):
        return None
    if zs:
        for words, field, unit in DEMO_FIELDS:
            if words in ql or words.replace("median ", "") in ql:
                code = (f"r = next((x for x in rows if x['zip'] == '{zs[0]}'), None)\n"
                        f"result = r and {{'zip': r['zip'], '{field}': r['{field}'], 'households': r['households']}}")
                return {"id": f"census.zip.{field}", "source": "demographics", "why": f"{words} for zip {zs[0]}",
                        "params": {"zip": zs[0], "field": field}, "code": code,
                        "say": lambda r, f=field, w=words, u=unit: (
                            f"Zip {r['zip']} has a {w} of {u}{r[f] if f == 'median_year_built' else fmt(r[f])}, across {fmt(r['households'])} households (Census ACS)."
                            if f != "households" else f"Zip {r['zip']} has {fmt(r['households'])} households (Census ACS)."
                        ) if r else f"Zip {zs[0]} is not in the Census table."}
        return None
    if re.search(r"most owner.occupied", ql):
        code = ("top = sorted(rows, key=lambda r: -r['owner_occupied'])[:6]\n"
                "result = [{'zip': r['zip'], 'owner_occupied': r['owner_occupied']} for r in top]")
        return {"id": "census.top_owner", "source": "demographics", "why": "zips ranked by owner-occupied homes",
                "params": {}, "code": code,
                "say": lambda r: "Zips with the most owner-occupied homes (Census ACS): " + listing(r, "zip", "owner_occupied") + "."}
    if re.search(r"oldest (housing|homes|houses)", ql):
        code = ("top = sorted([r for r in rows if r['median_year_built']], key=lambda r: r['median_year_built'])[:6]\n"
                "result = [{'zip': r['zip'], 'median_year_built': r['median_year_built']} for r in top]")
        return {"id": "census.oldest", "source": "demographics", "why": "zips ranked by oldest median year built",
                "params": {}, "code": code,
                "say": lambda r: ("Zips with the oldest housing, by median year built: "
                                  + ", ".join(f"{x['zip']} ({x['median_year_built']})" for x in r) + ".")}
    thr = threshold(q)
    if thr and "home value" in ql:
        code = (f"hits = sorted([r for r in rows if (r['median_home_value'] or 0) > {thr:g}], key=lambda r: -r['median_home_value'])\n"
                "result = {'zips_over': len(hits), 'threshold': " + f"{thr:g}" + ", 'rows': [{'zip': r['zip'], 'median_home_value': r['median_home_value'], 'households': r['households']} for r in hits[:10]]}")
        return {"id": "census.value_over", "source": "demographics", "why": f"zips with median home value over {fmt(thr)}",
                "params": {"threshold": thr}, "code": code,
                "say": lambda r: (f"{r['zips_over']} zips have a median home value over ${fmt(thr)}. The top ones: " + ", ".join(
                    f"{x['zip']} (${fmt(x['median_home_value'])}, {fmt(x['households'])} households)" for x in r['rows']) + ".")}
    return None


MATCHERS = [market_match, storm_match, funnel_match, ptc_match, deed_match, dam_match, load_match,
            permits_match, demo_match]


def match(question, today):
    for m in MATCHERS:
        hit = m(question, today)
        if hit:
            return hit
    return None


if __name__ == "__main__":
    import sys
    from datetime import date as _d
    h = match(" ".join(sys.argv[1:]), _d.today().isoformat())
    if not h:
        print("no template")
    else:
        print(h["id"], "|", h["why"])
        print(json.dumps(h.get("query") or h.get("code"), indent=1))
        if "code" in h:
            r = run_code(h["source"], h["code"])
            print(json.dumps(r, default=str)[:400])
            print(h["say"](r))
