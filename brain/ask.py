"""Cited Q&A over Base Fleet open data.

Four roles, one question:
  planner  picks one source from CATALOG.
  analyst  writes a SoQL query (Socrata) or a small Python filter (local file) and runs it.
  critic   checks that every number in the draft is in the result or the question.
           A failed check forces one revision.
  reporter writes 2 to 4 plain sentences. Each number from the result gets a [n] tag.

Loop guard: at most 3 analyst steps. A repeated identical plan (source + query) stops the loop.
Model: gemma4:e4b on local Ollama, think false, temperature 0.

Usage:
  python3 -m brain.ask "How many Base permits in August 2026?"
  python3 -m brain.ask --insights          # run brain/questions80.py, write brain/insights.json
  python3 -m brain.ask --serve 8742        # POST /ask {"q": "..."}; POST /ask?stream=1 streams NDJSON steps
                                           # POST /photo/read {"image": base64, "mime", "shot"} checks one checklist photo with Gemini

Order: cache (an exact match in brain/insights.json), then Base policy (route to Base support),
then templates (brain/templates.py: a fixed query, no model call), then the knowledge base
(store/kb.py kb_search, for questions about our data or methods), then the four-role agent.
The server logs every question to data/live/questions.jsonl (store/learn.py) and serves
POST /learn/approve, /learn/reject and /learn/log to localhost only.
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from brain import templates
except ImportError:  # run as a script from brain/
    import templates

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
OLLAMA = os.environ.get("OLLAMA", "http://localhost:11434")
MODEL = os.environ.get("ASK_MODEL", "gemma4:e4b")
SOCRATA = "https://data.austintexas.gov/resource/3syk-w9eu.json"
TODAY = os.environ.get("ASK_TODAY", date.today().isoformat())
MAX_STEPS = 3
MAX_ROWS = 50

CATALOG = {
    "permits": {
        "label": "City of Austin issued construction permits (Socrata 3syk-w9eu, live)",
        "kind": "socrata",
        "schema": (
            "One row per permit. Text fields: permit_number, permit_type_desc, permit_class, work_class, description, "
            "status_current (Active, Final, Expired, ...), original_zip (5 digit text), contractor_company_name, "
            "calendar_year_issued (text like '2026'). Timestamps: issue_date, applieddate (floating, compare as "
            "'2026-08-01T00:00:00'). Base Power permits: contractor_company_name='Base Power'. Backup battery or "
            "backup power permits citywide: work_class='Auxiliary Power'. Solar permits: upper(description) like '%SOLAR%'. "
            "Monthly buckets: date_trunc_ym(issue_date). Count with count(*)."),
        "use_for": "permit counts, Base Power installs by zip or month, backup and solar permits, contractors, status",
    },
    "dam": {
        "label": "ERCOT day-ahead settlement point prices, hourly, 2025 to 2026 (data/ercot_dam_hourly_2025_2026.csv)",
        "kind": "csv", "file": "ercot_dam_hourly_2025_2026.csv",
        "schema": "Columns: date (text 'YYYY-MM-DD'), he (int hour ending 1..24), aen (float $/MWh at LZ_AEN, Austin Energy load zone), "
                  "north (float $/MWh LZ_NORTH), houston (float $/MWh LZ_HOUSTON).",
        "use_for": "day-ahead power prices, price spikes, hours over a price, LZ_AEN, LZ_NORTH, LZ_HOUSTON",
    },
    "load": {
        "label": "ERCOT hourly load by weather zone, 2024 to 2026 (data/ercot_load_hourly_2024_2026.csv)",
        "kind": "csv", "file": "ercot_load_hourly_2024_2026.csv",
        "schema": "Columns: datetime (text 'MM/DD/YYYY HH:00'), year (int), month (int), hour_ending (int 1..24), "
                  "SCENT (float MW, South Central zone incl. Austin), NCENT (float MW), COAST (float MW), ERCOT (float MW, system total).",
        "use_for": "grid demand, peak load, when load peaks, hour of day, month, weather zone load",
    },
    "demographics": {
        "label": "Census ACS 2024 5-year by zip, Austin area (data/demographics.json)",
        "kind": "json", "file": "demographics.json", "rows_key": "rows",
        "schema": "rows: list of {zip (text), households, owner_occupied, single_family_detached, median_year_built, "
                  "median_income, median_home_value} (all int).",
        "use_for": "households, homeowners, income, home value, house age by zip",
    },
    "ptc": {
        "label": "Power to Choose retail plans by zip, fetched 2026-09-26 (data/ptc_tdu.json)",
        "kind": "json", "file": "ptc_tdu.json",
        "schema": "rows: list of {zip (text), plans (int, 0 means no retail choice: municipal or co-op utility), "
                  "tdus (dict of wires utility name to plan count)}.",
        "use_for": "retail electricity choice, deregulated zips, which utility (TDU) serves a zip, Oncor, Austin Energy",
    },
    "market": {
        "label": "Austin backup power permit market summary (data/market.json, built from Socrata 3syk-w9eu)",
        "kind": "json", "file": "market.json",
        "schema": "data: dict with monthly (list of {month 'YYYY-MM', base, others}: Auxiliary Power permits), "
                  "contractors_2026 (list of {contractor, permits_2026, type}), base_totals {total, by_status, final_rate, "
                  "median_days_applied_to_issued}, base_by_zip (list of {zip, count, final, active, final_rate, "
                  "owner_occupied, per_1000_owner_occupied}), annual (list of {year, total}: Auxiliary Power permits per year).",
        "use_for": "market share, Base vs other contractors, competitor installers, final rate, days to issue, annual trend",
    },
    "zips": {
        "label": "Permits by zip 2016 to 2026 (data/permits_by_zip.json, built from Socrata 3syk-w9eu)",
        "kind": "json", "file": "permits_by_zip.json", "rows_key": "rows",
        "schema": "rows: list of {zip, covered (bool, false means outside City of Austin permit data), permits, "
                  "service_upgrade, solar, battery, new_sfr} (counts, null when not covered).",
        "use_for": "solar vs battery by zip, service upgrades, new single family homes by zip",
    },
    "funnel": {
        "label": "Lead funnel estimates by zip, from ACS, permits and TDU table (data/funnel.json)",
        "kind": "json", "file": "funnel.json", "rows_key": "rows",
        "schema": "rows: list of {zip, city, county, tdu, status, eligible (bool), confidence ('HIGH'...), star (int, "
                  "estimated easy-fit homes), assisted_priority (float), assisted_why (text), stages (list of {key, count})}. "
                  "data['easy_share'] = {easy, total} for the house cohort.",
        "use_for": "easy-fit homes by zip or county, assisted onboarding priority, territory status, confidence",
    },
    "storms": {
        "label": "Backup permit surges after storms, from City of Austin permits (data/storms.json)",
        "kind": "json", "file": "storms.json",
        "schema": "data: dict with storms (list of {month, name, count, multiple, peak_month, peak_count, surge_months}), "
                  "months_over_4x (list of {month, count, multiple}), baseline_2020_monthly (float), "
                  "series (list of {month, count, base, generator, battery, solar_battery, multiple}).",
        "use_for": "storms, Uri, ice storm, surge months, backup permit series by category",
    },
    "deeds": {
        "label": "Deed turnover by zip, Travis and Williamson appraisal districts (data/deeds_by_zip.json)",
        "kind": "json", "file": "deeds_by_zip.json", "rows_key": "rows",
        "schema": "rows: list of {zip, parcels, median_years_since_deed, share_sold_last_2y, share_held_20y_plus, "
                  "share_homestead} (shares are 0 to 1).",
        "use_for": "deed turnover, homes sold recently, homes held long, homestead share",
    },
}


# ---------- model ----------

def chat(system, user, as_json=False, timeout=180):
    body = {"model": MODEL, "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if as_json:
        body["format"] = "json"
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = json.load(r)["message"]["content"].strip()
    if not as_json:
        return text
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


# ---------- planner ----------

def plan(question):
    menu = "\n".join(f"- {k}: {v['use_for']}" for k, v in CATALOG.items())
    out = chat("You route a data question to exactly one source. Reply JSON {\"source\": <key>, \"why\": <short>}. "
               "Rules: competitors or contractor ranking, Base market share, final rate, days from application to issue, "
               "or permits per 1,000 owner-occupied homes -> market. Solar versus battery by zip -> zips. "
               "A specific month, date window, or live permit count -> permits.",
               f"Today is {TODAY}.\nSources:\n{menu}\n\nQuestion: {question}", as_json=True)
    src = str(out.get("source", "")).strip().lower()
    return (src if src in CATALOG else "permits"), str(out.get("why", ""))[:200]


# ---------- analyst ----------

SOQL_KEYS = ("$select", "$where", "$group", "$having", "$order", "$limit")


def soql_url(q):
    params = {k: str(q[k]) for k in SOQL_KEYS if q.get(k) not in (None, "")}
    params.setdefault("$limit", str(MAX_ROWS))
    return SOCRATA + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def run_socrata(q):
    url = soql_url(q)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            rows = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Socrata {e.code}: {e.read()[:300].decode(errors='replace')}")
    return rows[:MAX_ROWS], url


# The filter runs in a child process: a bad or looping filter cannot hang the server.
RUNNER = r"""
import csv, json, sys, statistics
from collections import Counter, defaultdict
spec = json.loads(sys.stdin.read())
def num(v):
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v
if spec["kind"] == "csv":
    with open(spec["path"]) as f:
        rows = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(f)]
    data = None
else:
    data = json.load(open(spec["path"]))
    if spec.get("rows_key"): rows = data[spec["rows_key"]]
    elif "zips" in data: rows = [{"zip": z, **v} for z, v in data["zips"].items()]
    else: rows = None
import builtins
SAFE = {n: getattr(builtins, n) for n in
        ("len sum min max sorted round abs set dict list tuple zip enumerate range int float str bool any all map "
         "filter isinstance reversed").split()}
env = {"__builtins__": SAFE, "rows": rows, "data": data, "Counter": Counter, "defaultdict": defaultdict,
       "statistics": statistics}
exec(spec["code"], env)
res = env.get("result")
if isinstance(res, (list, tuple)): res = list(res)[:50]
print(json.dumps(res, default=str))
"""


def run_local(src, code):
    s = CATALOG[src]
    spec = {"kind": s["kind"], "path": os.path.join(DATA, s["file"]), "rows_key": s.get("rows_key"), "code": code}
    p = subprocess.run([sys.executable, "-c", RUNNER], input=json.dumps(spec), capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "filter failed")
    return json.loads(p.stdout)


SOQL_EXAMPLE = (
    'Example. Question: how many Base Power permits per zip in March 2026?\n'
    '{"$select": "original_zip, count(*) as permits", "$where": "contractor_company_name=\'Base Power\' AND '
    'issue_date >= \'2026-03-01T00:00:00\' AND issue_date < \'2026-04-01T00:00:00\'", "$group": "original_zip", '
    '"$order": "permits DESC", "$limit": 10}\n'
    'Example. Question: backup permits in May 2019 vs May 2020?\n'
    '{"$select": "sum(case(issue_date >= \'2019-05-01T00:00:00\' AND issue_date < \'2019-06-01T00:00:00\', 1, true, 0)) as may_2019, '
    'sum(case(issue_date >= \'2020-05-01T00:00:00\' AND issue_date < \'2020-06-01T00:00:00\', 1, true, 0)) as may_2020", '
    '"$where": "work_class=\'Auxiliary Power\'"}\n'
    'Every value is one SoQL string, never a JSON object.')
PY_EXAMPLE = (
    "Example for a CSV source (rows are dicts with numbers already parsed):\n"
    "{\"code\": \"hits = [r for r in rows if str(r['date']).startswith('2025-07') and r['north'] > 100]\\n"
    "result = {'hours_over_100_july_2025': len(hits), 'max_price': max(r['north'] for r in hits) if hits else None}\"}\n"
    "Example for a JSON source with a data dict:\n"
    "{\"code\": \"top = sorted(data['annual'], key=lambda r: -r['total'])[:3]\\nresult = top\"}\n"
    "Never type the answer in by hand: the code must read rows or data.")

ANALYST_SOQL = (
    "You write one SoQL query for the Socrata dataset below to answer the question. Reply JSON with keys "
    "\"$select\", \"$where\", \"$group\", \"$having\", \"$order\", \"$limit\" (omit unused keys). Use aggregates "
    "(count(*), sum, max) so the result is small. Use alias names without spaces. Quote text with single quotes. "
    "For two periods to compare, select one count per period with sum(case(<cond>, 1, true, 0)) as name.")
ANALYST_PY = (
    "You write a short Python filter over the local data below. The variable `rows` (list of dicts) and `data` "
    "(parsed file) exist. Counter, defaultdict and statistics exist. No imports, no pandas, no files, no print. "
    "Assign the answer to `result` as a small dict or a list of at most 20 dicts, with clear key names. "
    "Compute every number the answer needs (totals, differences, shares) inside `result`. "
    "Reply JSON {\"code\": \"<python>\"}.")


def analyse(question, src, feedback):
    s = CATALOG[src]
    user = f"Today is {TODAY}.\nSource: {s['label']}\n{s['schema']}\n\nQuestion: {question}"
    if feedback:
        user += "\n\nYour last attempt failed. Fix it.\n" + feedback
    if s["kind"] == "socrata":
        q = chat(ANALYST_SOQL + "\n\n" + SOQL_EXAMPLE, user, as_json=True)
        q = {k: q[k] for k in SOQL_KEYS if q.get(k) not in (None, "")}
        bad = [k for k, v in q.items() if isinstance(v, (dict, list))]
        if bad or "$select" not in q:
            raise ValueError(f"keys {bad or ['$select']} must be SoQL strings: {json.dumps(q)[:300]}")
        return q
    code = str(chat(ANALYST_PY + "\n\n" + PY_EXAMPLE, user, as_json=True).get("code", ""))
    if not re.search(r"\b(rows|data)\b", code):
        raise ValueError(f"the code does not read rows or data, so it types the answer in by hand: {code[:200]}")
    return {"code": code}


def execute(src, query):
    if CATALOG[src]["kind"] == "socrata":
        return run_socrata(query)
    return run_local(src, query["code"]), None


# ---------- critic ----------

NUM = re.compile(r"(?<![\w.])-?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?")
ZIP = re.compile(r"^7\d{4}$")
DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?(?:T[\d:.]+)?\b|\b\d{1,2}/\d{1,2}/\d{4}(?: \d{2}:\d{2})?\b|\b\d{1,2}:\d{2}\b")


def to_num(tok):
    t = tok.replace("$", "").replace(",", "").rstrip("%")
    try:
        return float(t)
    except ValueError:
        return None


def pool(obj, out):
    """All numbers in a result, including numbers inside strings."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            pool(k, out)
            pool(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            pool(v, out)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        out.append(float(obj))
    else:
        for tok in re.findall(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", str(obj)):
            v = to_num(tok)
            if v is not None:
                out.append(v)
    return out


def matches(tok, value, nums):
    dec = len(tok.replace("%", "").split(".")[1]) if "." in tok else 0
    tol = 0.5 * 10 ** -dec + 1e-9
    for n in nums:
        cands = [n, n * 100] if tok.endswith("%") else [n]
        if any(abs(value - c) <= tol for c in cands):
            return True
        if abs(n) >= 1000 and dec == 0 and abs(value) >= 1000 and abs(value - n) / abs(n) < 0.005 and tok.endswith(("k", "K")):
            return True
    return False


def critic(draft, result, question, query=None):
    """Return the draft numbers that are in neither the result, the query, nor the question."""
    blob = json.dumps(result, default=str) + json.dumps(query or {})
    nums = pool(result, []) + pool(question, []) + pool(query or {}, [])
    bad = []
    if result not in (None, [], {}) and re.search(r"\bno (match|data|results?)\b", draft, re.I):
        bad.append("'no match' while RESULT has rows")
    text = draft
    for d in DATE.findall(draft):
        if d in blob or d in question:
            text = text.replace(d, " ")
    for tok in NUM.findall(text):
        v = to_num(tok)
        if v is None or matches(tok, v, nums):
            continue
        bad.append(tok)
    return bad


# ---------- reporter ----------

REPORTER = (
    "You answer a Base Power growth or operations lead in 2 to 4 short plain sentences. Use only numbers that appear "
    "in RESULT, copied exactly as they appear there (you may add thousands commas or round). Do not compute new "
    "numbers: no sums, differences, percentages or averages that RESULT does not show. Name the place, period and "
    "unit. Round long decimals to at most 1 decimal place. If RESULT has 8 rows or fewer, mention every row; "
    "if it has more, give the top 5 in RESULT order. Only if RESULT is empty, say the data has no match. "
    "Write sentences: no markdown, no lists, no tables.")


def draft_answer(question, src, query, result, fix=None):
    user = (f"Question: {question}\nSource: {CATALOG[src]['label']}\nQuery: {json.dumps(query)}\n"
            f"RESULT: {json.dumps(result, default=str)[:6000]}")
    if fix:
        user += (f"\n\nA checker found numbers in your last answer that are not in RESULT: {', '.join(fix)}. "
                 "Rewrite the answer without them. Every number must be copied from RESULT.")
    return chat(REPORTER, user).strip()


def cite(answer, result, question, tag="[1]"):
    """Put the source tag after every number that came from the result."""
    nums = pool(result, [])

    def sub(m):
        tok = m.group(0)
        v = to_num(tok)
        if v is None or ZIP.match(tok) or not matches(tok, v, nums):
            return tok
        if re.search(r"(?<![\d.])" + re.escape(tok.lstrip("$")) + r"(?![\d])", question):
            return tok
        return f"{tok} {tag}"
    out, last = [], 0
    for d in DATE.finditer(answer):
        out.append(NUM.sub(sub, answer[last:d.start()]))
        out.append(d.group(0) + (f" {tag}" if d.group(0) in json.dumps(result, default=str) else ""))
        last = d.end()
    out.append(NUM.sub(sub, answer[last:]))
    return "".join(out)


# ---------- pipeline ----------

class Trace:
    """Records each step (role, model or code, ms) and streams it to the caller as it happens."""

    def __init__(self, emit=None):
        self.steps, self.emit, self.t0 = [], emit or (lambda ev: None), time.time()

    def begin(self, role, by, title):
        self.emit({"ev": "begin", "role": role, "by": by, "title": title, "at_ms": self.ms()})
        return time.time()

    def done(self, t, role, by, title, **detail):
        step = {"role": role, "by": by, "title": title, "ms": round((time.time() - t) * 1000), **detail}
        self.steps.append(step)
        self.emit({"ev": "step", **step})
        return step

    def ms(self):
        return round((time.time() - self.t0) * 1000)


def short(obj, n=4000):
    return obj if len(json.dumps(obj, default=str)) < n else "(truncated)"


def finish(question, path, src, query, url, result, draft, bad, revised, tr, attempts=None, stop="ok", tmpl=None):
    t = tr.begin("reporter", "code", "Adding source tags")
    answer = cite(draft, result, question) if result not in (None, [], {}) else draft
    tr.done(t, "reporter", "code", "Answer with source tags", answer=answer)
    s = CATALOG[src]
    source = {"n": 1, "label": s["label"]}
    if url:
        source["url"] = url
    elif "file" in s:
        source["file"] = "data/" + s["file"]
    secs = round(time.time() - tr.t0, 2)
    return {"question": question, "path": path, "template": tmpl, "answer": answer, "source": src,
            "sources": [source], "query_url": url, "query": query, "result": short(result),
            "critic": {"pass": not bad and result not in (None, [], {}), "revised": revised, "unsupported": bad},
            "model_calls": sum(1 for x in tr.steps if x["by"] == "model"), "stop": stop,
            "attempts": attempts or [], "steps": tr.steps, "seconds": secs}


def ask_template(question, hit, tr, t_match):
    src = hit["source"]
    tr.done(t_match, "planner", "code", f"Template {hit['id']}: {hit['why']}", source=src,
            source_label=CATALOG[src]["label"], params=hit["params"])
    if "query" in hit:
        query = hit["query"]
        t = tr.begin("analyst", "code", "Running SoQL on Socrata 3syk-w9eu")
        result, url = run_socrata(query)
        for r in result if isinstance(result, list) else []:
            for k, v in r.items():
                if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-01T00:00:00(\.000)?$", v):
                    r[k] = v[:7]
        tr.done(t, "analyst", "code", f"SoQL on Socrata: {len(result)} row{'s' if len(result) != 1 else ''}",
                query=query, url=url, rows=len(result))
    else:
        query, url = {"code": hit["code"]}, None
        t = tr.begin("analyst", "code", f"Running local filter on data/{CATALOG[src]['file']}")
        result = templates.run_code(src, hit["code"])
        rows = len(result) if isinstance(result, list) else (0 if result is None else 1)
        tr.done(t, "analyst", "code", f"Local filter on data/{CATALOG[src]['file']}: {rows} row{'s' if rows != 1 else ''}",
                query=query, rows=rows)
    t = tr.begin("reporter", "code", "Writing the sentence from the result")
    draft = hit["say"](result)
    tr.done(t, "reporter", "code", "Draft from the template writer (no model)", draft=draft)
    t = tr.begin("critic", "code", "Checking every number against the result")
    bad = critic(draft, result, question, query)
    nums = len(NUM.findall(draft))
    tr.done(t, "critic", "code", f"{'Pass' if not bad else 'Fail'}: {nums} numbers checked" + (f", unsupported {', '.join(bad)}" if bad else ""),
            checked=nums, unsupported=bad, verdict="pass" if not bad else "fail")
    return finish(question, "template", src, query, url, result, draft, bad, False, tr, tmpl=hit["id"])


def learn():
    """store/learn.py, imported late so a missing or broken module never stops an answer."""
    try:
        from store import learn as L
        return L
    except Exception as e:
        sys.stderr.write(f"store.learn not available: {e}\n")
        return None


_cache = {"mtime": None, "items": {}}


def cache_hit(question):
    """Exact match (normalised text) against brain/insights.json answers that passed the critic."""
    L = learn()
    path = os.path.join(ROOT, "brain", "insights.json")
    try:
        mt = os.path.getmtime(path)
        if mt != _cache["mtime"]:
            with open(path) as f:
                items = json.load(f).get("insights", [])
            _cache["items"] = {L.norm(i["question"]): i for i in items if i.get("critic", {}).get("pass")}
            _cache["mtime"] = mt
        return _cache["items"].get(L.norm(question)) if L else None
    except Exception:
        return None


METHOD_RE = re.compile(
    r"^(how (do|does|did|is|are|was|were) (you|we|the|this|base fleet|your)\b|how .*\b(calculated|computed|counted|estimated|measured|"
    r"built|made|scored|decide|decides|picked|works?)\b|what (is|are|does) .*\b(source|method|definition|meaning|mirror|funnel|signal|"
    r"judgment|easy.fit|star area|assisted|feeder|node|reserve|gap)|where (does|do|did) .* come from|why (do|does|is|are|did)\b|"
    r"explain\b|what does .* mean|which (data|source))", re.I)


def is_method(q):
    """A question about our data or methods: a method phrase, and no number or 'how many' in it."""
    return bool(METHOD_RE.search(q)) and not re.search(r"\d|^\s*how (many|much)\b", q, re.I)


def kb_hits(question, k=3):
    """store/kb.py kb_search, imported late. Returns [(slug, title, text, score)]; [] when missing."""
    try:
        from store import kb
    except Exception as e:
        sys.stderr.write(f"knowledge base not available: {e}\n")
        return []
    try:
        raw = kb.kb_search(question, k) or []
    except Exception as e:
        sys.stderr.write(f"kb_search failed: {e}\n")
        return []
    out = []
    for h in raw:
        if isinstance(h, dict):
            if h.get("type") == "member_questions" or (h.get("score") is not None and h["score"] < 4):
                continue
            slug = h.get("slug") or h.get("id") or h.get("node_id")
            text = h.get("body") or h.get("text") or h.get("content") or h.get("summary") or h.get("snippet") or ""
            summ = h.get("summary") or ""
            if summ and summ.rstrip().endswith(".") and not summ.endswith("..."):
                text = summ + "\n" + text  # the one-line summary leads the answer
            boost = 1.3 if h.get("type") in ("dataset", "learned_answer") else 1.0
            out.append((slug, h.get("title") or slug, str(text), (h.get("score") or 0) * boost))
        elif isinstance(h, (list, tuple)) and h:
            out.append((h[0], h[1] if len(h) > 1 else h[0], str(h[2]) if len(h) > 2 else "", h[3] if len(h) > 3 else None))
    out = [x for x in out if x[0] and x[2].strip()]
    return sorted(out, key=lambda x: -(x[3] or 0))


def kb_snippet(question, text, n=2, limit=420):
    """The n sentences of a knowledge base node with the most words in common with the question, in page order."""
    qt = set(re.findall(r"[a-z0-9]+", question.lower())) - {"the", "a", "an", "is", "of", "how", "what", "do", "does", "you", "we"}
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
    body = re.sub(r"[#*`>]+", "", body)
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", body) if len(x.strip()) > 25]
    if not sents:
        return body.strip()[:limit]
    ranked = sorted(range(1, len(sents)), key=lambda i: -len(qt & set(re.findall(r"[a-z0-9]+", sents[i].lower()))))
    keep = [0] + sorted(ranked[:n - 1])  # the first sentence (summary or lead) plus the best match
    return " ".join(sents[i] for i in keep)[:limit]


def ask_kb(question, tr):
    t = tr.begin("planner", "code", "Searching the knowledge base (store/kb.py)")
    hits = kb_hits(question)
    if not hits:
        tr.done(t, "planner", "code", "Knowledge base: no page, or not available")
        return None
    slug, title, text, score = hits[0]
    tr.done(t, "planner", "code", f"Knowledge base: {slug}", source="kb", slug=slug, score=score)
    t = tr.begin("reporter", "code", "Quoting the knowledge base page")
    answer = kb_snippet(question, text) + " [1]"
    tr.done(t, "reporter", "code", "Answer quoted from the page (no model)", answer=answer)
    return {"question": question, "path": "kb", "template": None, "answer": answer, "source": "kb",
            "sources": [{"n": 1, "label": f"Base Brain knowledge base: {slug}", "file": "data/fleet.db kb_nodes"}],
            "query_url": None, "query": {"kb_search": question}, "result": {"slug": slug, "title": title},
            "critic": {"pass": True, "revised": False, "unsupported": [], "note": "quoted from the knowledge base"},
            "model_calls": 0, "stop": "ok", "attempts": [], "steps": tr.steps, "seconds": round(time.time() - tr.t0, 2)}


_FAQ = None
_STOP = set("a an and are as at be can do does for from how i if in is it my of on or the to what when where which who why will with you your me we our this that".split())


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1}


def faq_hit(question, floor=0.6):
    """Best member FAQ (web/data/faq.json) whose question shares most of the asker's words, or None."""
    global _FAQ
    if _FAQ is None:
        try:
            with open(os.path.join(ROOT, "web", "data", "faq.json")) as f:
                _FAQ = [it for it in json.load(f).get("items", []) if it.get("audience") == "member" and it.get("a")]
        except (OSError, ValueError):
            _FAQ = []
    asked = _words(question)
    if len(asked) < 2:
        return None
    best, score = None, 0.0
    for it in _FAQ:
        have = _words(it["q"])
        if not have:
            continue
        s = len(asked & have) / max(len(asked), len(have))
        if s > score:
            best, score = it, s
    return best if score >= floor else None


def ask_faq(question, it, tr, t):
    tr.done(t, "planner", "code", f"Written answer: {it['id']}")
    return {"question": question, "path": "faq", "template": it["id"], "answer": it["a"], "source": "faq",
            "sources": [{"n": 1, "label": it.get("source") or "Base Fleet FAQ", "url": it.get("source_url")}],
            "query_url": None, "query": None, "result": {"faq": it["id"], "q": it["q"]},
            "critic": {"pass": True, "revised": False, "unsupported": []}, "model_calls": 0, "stop": "faq",
            "attempts": [], "steps": tr.steps, "seconds": round(time.time() - tr.t0, 2)}


def ask(question, emit=None, use_cache=True):
    tr = Trace(emit)
    t = tr.begin("planner", "code", "Looking for a recorded answer")
    hit = cache_hit(question) if use_cache else None
    if hit:
        tr.done(t, "planner", "code", f"Recorded answer from {hit.get('recorded') or 'brain/insights.json'}")
        r = dict(hit, path="cache", cached_path=hit.get("path"), steps=tr.steps,
                 seconds=round(time.time() - tr.t0, 2), model_calls=0)
        return r
    L = learn()
    pol = L.policy(question) if L else None
    if pol:
        tr.done(t, "planner", "code", f"Base policy question ({pol[0]}): route to Base support")
        return {"question": question, "path": "base_support", "template": pol[0],
                "answer": f"Ask Base support. This is a Base policy question ({pol[0].replace('-', ' ')}). {pol[1]}",
                "source": None, "sources": [], "query_url": None, "query": None, "result": None,
                "critic": {"pass": True, "revised": False, "unsupported": []}, "model_calls": 0, "stop": "policy",
                "attempts": [], "steps": tr.steps, "seconds": round(time.time() - tr.t0, 2)}
    hit = faq_hit(question)
    if hit:
        return ask_faq(question, hit, tr, t)
    tr.done(t, "planner", "code", "No recorded answer")
    if is_method(question):  # about our data or methods, not a live number: the knowledge base first
        r = ask_kb(question, tr)
        if r:
            return r
    t = tr.begin("planner", "code", "Matching the question to a template")
    hit = templates.match(question, TODAY)
    if hit:
        try:
            return ask_template(question, hit, tr, t)
        except Exception as e:  # a template query failed: fall back to the agent
            tr.done(time.time(), "planner", "code", f"Template {hit['id']} failed ({str(e)[:120]}); using the full agent")
    else:
        tr.done(t, "planner", "code", "No template matched; using the full agent")
    return ask_agent(question, tr)


def answered(r):
    if r["path"] in ("base_support", "gap"):
        return False
    if r["path"] == "agent":
        a = str(r.get("answer", ""))
        return r.get("result") not in (None, [], {}) and not a.startswith("No answer") and "has no match" not in a
    return bool(r.get("critic", {}).get("pass"))


def log_result(r, page=None, seconds=None):
    L = learn()
    if L:
        L.log_question(r["question"], r["path"], page=page, template=r.get("template"), answered=answered(r),
                       critic_pass=r.get("critic", {}).get("pass"), seconds=seconds if seconds is not None else r.get("seconds"),
                       answer=r.get("answer"))


def ask_agent(question, tr):
    t = tr.begin("planner", "model", "Choosing one source")
    src, why = plan(question)
    tr.done(t, "planner", "model", f"Chose {src}: {why or CATALOG[src]['use_for']}", source=src,
            source_label=CATALOG[src]["label"])
    seen, feedback, result, url, query = set(), None, None, None, None
    attempts, stop = [], "ok"
    kind = "SoQL" if CATALOG[src]["kind"] == "socrata" else "Python filter"
    for n in range(1, MAX_STEPS + 1):
        t = tr.begin("analyst", "model", f"Writing a {kind} (attempt {n})")
        try:
            query = analyse(question, src, feedback)
        except Exception as e:  # bad JSON or a query that fails validation
            feedback, stop = f"Your reply was rejected: {e}", "rejected"
            tr.done(t, "analyst", "model", f"Attempt {n} rejected: {str(e)[:160]}", verdict="rejected")
            continue
        tr.done(t, "analyst", "model", f"Wrote a {kind} (attempt {n})", query=query)
        sig = (src, json.dumps(query, sort_keys=True))
        if sig in seen:
            stop = "repeated-plan"
            tr.done(time.time(), "analyst", "code", "Stopped: the same query twice")
            break
        seen.add(sig)
        t = tr.begin("analyst", "code", "Running the SoQL on Socrata" if kind == "SoQL" else f"Running the filter on data/{CATALOG[src]['file']}")
        try:
            result, url = execute(src, query)
            rows = len(result) if isinstance(result, list) else (0 if result in (None, {}) else 1)
            attempts.append({"step": n, "query": query, "url": url, "rows": rows})
            tr.done(t, "analyst", "code", f"{kind} returned {rows} row{'s' if rows != 1 else ''}", query=query, url=url, rows=rows)
            if result in (None, [], {}):
                feedback, stop = f"Query: {json.dumps(query)}\nIt returned no rows. Loosen the filter.", "empty"
                continue
            stop = "ok"
            break
        except Exception as e:
            attempts.append({"step": n, "query": query, "error": str(e)[:300]})
            tr.done(t, "analyst", "code", f"Query error: {str(e)[:160]}", query=query, verdict="error")
            feedback, stop = f"Query: {json.dumps(query)}\nError: {str(e)[:400]}", "error"
            result = None
    if result is None:
        draft = "No answer: the analyst could not get a result from the data."
        return finish(question, "agent", src, query, None, None, draft, [], False, tr, attempts, stop)
    t = tr.begin("reporter", "model", "Writing the answer from the result")
    draft = draft_answer(question, src, query, result)
    tr.done(t, "reporter", "model", "Draft answer", draft=draft)
    t = tr.begin("critic", "code", "Checking every number against the result")
    bad = critic(draft, result, question, query)
    nums = len(NUM.findall(draft))
    tr.done(t, "critic", "code", f"{'Pass' if not bad else 'Revise'}: {nums} numbers checked" + (f", unsupported {', '.join(bad)}" if bad else ""),
            checked=nums, unsupported=bad, verdict="pass" if not bad else "revise")
    revised = False
    if bad:
        t = tr.begin("reporter", "model", "Rewriting without the unsupported numbers")
        draft = draft_answer(question, src, query, result, fix=bad)
        tr.done(t, "reporter", "model", "Revised answer", draft=draft)
        revised = True
        t = tr.begin("critic", "code", "Checking the revision")
        bad = critic(draft, result, question, query)
        tr.done(t, "critic", "code", f"{'Pass' if not bad else 'Fail'} after revision" + (f", unsupported {', '.join(bad)}" if bad else ""),
                unsupported=bad, verdict="pass" if not bad else "fail")
    return finish(question, "agent", src, query, url, result, draft, bad, revised, tr, attempts, stop)


# ---------- batch ----------

def run_insights(path=os.path.join(ROOT, "brain", "insights.json")):
    from brain.questions80 import QUESTIONS
    out = []
    for i, (q, page, persona) in enumerate(QUESTIONS, 1):
        print(f"[{i}/{len(QUESTIONS)}] {q}", flush=True)
        try:
            r = ask(q, use_cache=False)
        except Exception as e:
            r = {"question": q, "path": "agent", "answer": f"No answer: {e}", "sources": [], "query_url": None,
                 "seconds": 0, "critic": {"pass": False, "revised": False, "unsupported": []}, "steps": [], "stop": "crash"}
        r.update({"page": page, "persona": persona, "recorded": TODAY})
        print(f"   {r['path']} {r.get('template') or r.get('source')} {r['seconds']}s pass={r['critic']['pass']} :: {r['answer'][:140]}", flush=True)
        out.append(r)

    def med(xs):
        return round(statistics.median(xs), 2) if xs else None
    tpl = [r["seconds"] for r in out if r["path"] == "template"]
    agt = [r["seconds"] for r in out if r["path"] == "agent" and r["seconds"]]
    doc = {"generated": TODAY, "model": MODEL, "questions": len(out),
           "critic_pass": sum(r["critic"]["pass"] for r in out),
           "template_count": len(tpl), "median_seconds": med([r["seconds"] for r in out if r["seconds"]]),
           "median_template_seconds": med(tpl), "median_agent_seconds": med(agt), "insights": out}
    with open(path, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    print(f"critic pass {doc['critic_pass']}/{len(out)}, templates {len(tpl)}, median template {doc['median_template_seconds']} s, "
          f"agent {doc['median_agent_seconds']} s -> {path}")


# ---------- photo reading (Gemini, key from the environment only) ----------

PHOTO_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
PHOTO_MAX = 4 * 1024 * 1024
PHOTO_TYPES = ("panel_open", "panel_closed", "meter_exterior", "other")


PHOTO_SHOTS = os.path.join(os.path.dirname(__file__), "..", "web", "data", "photo-shots.json")


def photo_prompt(shot=None):
    """Shot-aware prompt from web/data/photo-shots.json, shared with the page and api/read-photo.js."""
    with open(PHOTO_SHOTS) as f:
        cfg = json.load(f)
    shot = shot if shot in cfg["shots"] else cfg["default"]
    s = cfg["shots"][shot]
    return shot, cfg["prompt"].replace("{label}", s["label"]).replace("{asks}", s["asks"])


def read_photo(image_b64, mime="image/jpeg", shot=None):
    """Returns (status, body). Never includes the key in the body or the log."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return 503, {"error": "reading unavailable"}
    image_b64 = re.sub(r"^data:[^,]*,", "", str(image_b64 or ""))
    if not image_b64 or not re.fullmatch(r"[A-Za-z0-9+/=\s]+", image_b64):
        return 400, {"error": "image must be base64"}
    if len(image_b64) * 3 // 4 > PHOTO_MAX:
        return 413, {"error": "image too large"}
    mime = mime if mime in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
    shot, prompt = photo_prompt(shot)
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{PHOTO_MODEL}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime, "data": image_b64}}]}],
                         "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    t0 = time.time()
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=45).read())
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        out = json.loads(text)
        if not isinstance(out, dict):
            raise ValueError
    except Exception:
        return 502, {"error": "reading failed"}
    amps = out.get("main_breaker_amps")
    amps = amps if isinstance(amps, int) and not isinstance(amps, bool) and 30 <= amps <= 600 else None
    brand = out.get("brand")
    conf = out.get("confidence")
    return 200, {
        "photo_type": out.get("photo_type") if out.get("photo_type") in PHOTO_TYPES else "other",
        "manufacturer": brand.strip()[:40] if isinstance(brand, str) and brand.strip() else None,
        "main_breaker_amps": amps,
        "usable": out.get("pass") is True,
        "retake_reason": out.get("retake_reason")[:300] if isinstance(out.get("retake_reason"), str) else None,
        "confidence": max(0.0, min(1.0, float(conf))) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else None,
        "shot": shot,
        "model": PHOTO_MODEL,
        "seconds": round(time.time() - t0, 1),
    }


# ---------- server ----------

class Handler(BaseHTTPRequestHandler):
    def cors(self):
        origin = self.headers.get("Origin", "")
        if re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def reply(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/health"):
            return self.reply(200, {"ok": True, "model": MODEL, "stream": True, "learn": True})
        self.reply(404, {"error": "use POST /ask"})

    def local(self):
        """Learning endpoints: localhost callers and localhost pages only."""
        origin = self.headers.get("Origin", "")
        return self.client_address[0] in ("127.0.0.1", "::1") and (
            not origin or re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", origin))

    def page(self, body):
        p = body.get("page") if isinstance(body, dict) else None
        if not p:  # the page path only; never the host or the query string
            p = urllib.parse.urlparse(self.headers.get("Referer", "")).path.split("/")[-1] or None
        return p

    def do_learn(self, body):
        L = learn()
        if not self.local():
            return self.reply(403, {"error": "localhost only"})
        if not L:
            return self.reply(503, {"error": "store/learn.py not available"})
        if self.path.startswith("/learn/log"):
            q = str(body.get("question", "")).strip()[:400]
            if not q:
                return self.reply(400, {"error": "empty question"})
            path = body.get("path") if body.get("path") in L.PATHS else "agent"
            rec = L.log_question(q, path, page=self.page(body) or "member.html", member_id=body.get("member_id"),
                                 template=body.get("template"), answered=body.get("answered"),
                                 critic_pass=body.get("critic_pass"), seconds=body.get("seconds"), answer=body.get("answer"))
            return self.reply(200, {"ok": bool(rec)})
        pid = str(body.get("id", ""))[:40]
        try:
            if self.path.startswith("/learn/approve"):
                return self.reply(200, L.approve(pid, body.get("who")))
            if self.path.startswith("/learn/reject"):
                return self.reply(200, L.reject(pid, body.get("who")))
        except Exception as e:
            return self.reply(500, {"ok": False, "error": str(e)[:300]})
        return self.reply(404, {"error": "use /learn/approve, /learn/reject or /learn/log"})

    def do_POST(self):
        if self.path.startswith("/photo/read"):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n > PHOTO_MAX * 1.4:
                    return self.reply(413, {"error": "image too large"})
                body = json.loads(self.rfile.read(n) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self.reply(400, {"error": "body must be JSON {\"image\": \"<base64>\"}"})
            return self.reply(*read_photo(body.get("image"), body.get("mime"), body.get("shot")))
        if not (self.path.startswith("/ask") or self.path.startswith("/learn/")):
            return self.reply(404, {"error": "use POST /ask"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
            q = str(body.get("q", "")).strip()[:400]
        except ValueError:
            return self.reply(400, {"error": "body must be JSON {\"q\": \"...\"}"})
        if self.path.startswith("/learn/"):
            return self.do_learn(body)
        if not q:
            return self.reply(400, {"error": "empty question"})
        page = self.page(body)
        if "stream=1" not in self.path:
            try:
                r = ask(q)
            except Exception as e:
                return self.reply(502, {"error": str(e)[:300]})
            log_result(r, page)
            return self.reply(200, r)
        # Stream one JSON object per line: begin and step events as each role runs, then done.
        self.send_response(200)
        self.cors()
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(ev):
            self.wfile.write((json.dumps(ev, default=str) + "\n").encode())
            self.wfile.flush()
        try:
            r = ask(q, emit)
            log_result(r, page)
            emit({"ev": "done", "result": r})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            emit({"ev": "error", "error": str(e)[:300]})

    def log_message(self, fmt, *args):
        sys.stderr.write("ask: " + fmt % args + "\n")


def main(argv):
    if argv[:1] == ["--serve"]:
        port = int(argv[1]) if len(argv) > 1 else 8742
        templates.warm()
        print(f"ask server on http://localhost:{port}/ask (model {MODEL}, stream with /ask?stream=1)", flush=True)
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    elif argv[:1] == ["--insights"]:
        run_insights()
    elif argv:
        r = ask(" ".join(argv), emit=lambda ev: ev["ev"] == "step" and print(
            f"  {ev['role']:8} {ev['by']:5} {ev['ms']:6} ms  {ev['title']}", file=sys.stderr))
        print(r["answer"])
        for s in r["sources"]:
            print(f"[{s['n']}] {s['label']}  {s.get('url') or s.get('file')}")
        print(f"path={r['path']} critic pass={r['critic']['pass']} model_calls={r['model_calls']} {r['seconds']}s")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
