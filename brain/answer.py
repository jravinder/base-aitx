"""Base Brain: answer one member question from the member record, then the app knowledge base.

Retrieval: token overlap between the question and each record section
(field names, node keys, day rows, event strings). No embeddings.
Generation: gemma4:e4b through local Ollama. If Ollama is down, a
rule-based answerer runs on the same retrieved sections.

Rule: never state Base policy. Policy questions (payments, cancelling, contracts,
credit payout dates, eligibility) get "GAP: ask Base support." with no model call.

Two sources, in order: the member's own record, then the app knowledge base
(store/kb.py kb_search) for questions the record cannot answer (how the battery
decides, the grid, storms, credits explained, privacy). A knowledge base answer
ends with "(Base Brain knowledge base: <slug>)". Set BRAIN_KB=0 for record only.
If neither has the answer, reply "GAP: not in your record. Ask Base support."

Every answer is logged to data/live/questions.jsonl (store/learn.py). LEARN_LOG=0 turns it off.

Usage: python3 -m brain.answer m001 "What did my node earn this week?"
       python3 -m brain.answer --backend jetson m001 "..."
Backends: laptop (default, localhost Ollama), jetson (LAN Ollama), gemini (Gemini CLI).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
MEMBERS = os.path.join(ROOT, "data", "members.json")
MEMBERS_FIXTURE = os.path.join(ROOT, "data", "members.fixture.json")
OLLAMA = "http://localhost:11434"
MODEL = "gemma4:e4b"
GAP = "GAP: not in your record. Ask Base support."
POLICY_RE = re.compile(
    r"\b(cancel\w*|terminat\w*|contracts?|payments?|pay me|paid out|payouts?|when .*\bpaid|refunds?|bill|billing|"
    r"billed|invoices?|fees?|warranty|eligib\w*|qualify|qualifies|move out|sell my (house|home)|next credit|"
    r"credit (date|day|payout)|deposit)\b", re.I)
KB_SYSTEM = (
    "You answer one question for one Base member from the KNOWLEDGE below. The knowledge explains how the "
    "Base Fleet app, the battery scheduler, the grid, storms and the data work. Answer in one or two short plain "
    "sentences, no markdown, using only the knowledge. Never state Base policy, fees, contracts, payout dates or "
    "eligibility as fact. If the knowledge does not answer the question, reply exactly: " + GAP
)
BACKENDS = {
    "laptop": ("ollama", "http://localhost:11434", "gemma4:e4b"),
    "jetson": ("ollama", os.environ.get("JETSON_OLLAMA", "http://jetson:11434"), "gemma4:e4b"),
    "gemini": ("gemini", None, "gemini-cli"),
}


def set_backend(name):
    """Point OLLAMA/MODEL at a backend. Returns the backend kind."""
    global OLLAMA, MODEL
    kind, host, model = BACKENDS[name]
    if host:
        OLLAMA = host
    MODEL = model
    return kind

SYSTEM = (
    "You answer one question for one Base member. Use only the RECORD below. "
    "The record is the member's own house, node, and weekly earnings. "
    "Answer in one or two short sentences with the numbers from the record. Plain text, no markdown. "
    "For earnings give battery, GPU, and the total. For a best or worst day compare battery_usd plus gpu_usd across days. "
    "Never state Base policy, fees, contracts, credit dates, or eligibility rules. "
    "If the record does not contain the answer, reply exactly: " + GAP
)

STOP = {"the", "a", "an", "my", "me", "i", "is", "was", "did", "do", "does", "what", "why",
        "when", "how", "on", "at", "in", "of", "to", "for", "and", "or", "it", "this", "that",
        "you", "your", "are", "am", "be", "can", "will", "there", "much", "many", "which", "pm", "am"}

SYN = {
    "earn": ["usd", "totals", "week"], "earned": ["usd", "totals", "week"], "earnings": ["usd", "totals"],
    "money": ["usd", "totals"], "paid": ["usd"], "discharge": ["discharged"], "discharged": ["discharge"],
    "charge": ["charged"], "reserve": ["reserve_min_pct"], "amps": ["panel_amps"], "amperage": ["panel_amps"],
    "panel": ["panel_amps", "panel_location"], "confirm": ["confirm_with_member"], "feeder": ["node"],
    "gpu": ["gpu_hours", "gpu_usd"], "hours": ["gpu_hours"], "battery": ["battery_usd", "battery_kwh"],
    "built": ["year_built"], "year": ["year_built"], "solar": ["solar"], "install": ["battery_install_date"],
    "installed": ["battery_install_date"], "monday": ["mon"], "tuesday": ["tue"], "wednesday": ["wed"],
    "thursday": ["thu"], "friday": ["fri"], "saturday": ["sat"], "sunday": ["sun"], "5": ["17:00", "18:00"], "17:00": ["18:00"],
    "week": ["totals"], "total": ["totals"], "node": ["node"], "zip": ["zip"], "fit": ["fit"],
    "house": ["house", "field", "zip", "year_built"], "home": ["house", "field"], "know": ["house", "field"],
    "best": ["day"], "worst": ["day"], "job": ["gpu", "day"], "jobs": ["gpu", "day"], "ran": ["gpu", "day"],
    "run": ["gpu", "day"], "sell": ["gpu_hours", "totals"], "sold": ["gpu_hours", "totals"],
    "floor": ["reserve_min_pct", "node"], "confirmation": ["confirm_with_member"], "need": ["confirm_with_member"],
    "fields": ["field", "confirm_with_member"], "field": ["field"],
}


def tokens(s):
    return {t for t in re.findall(r"[a-z0-9_:%]+", str(s).lower()) if t not in STOP}


def qtokens(q):
    t = tokens(q)
    out = set(t)
    for w in t:
        out.update(SYN.get(w, []))
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
    return out


def load_members():
    path = MEMBERS if os.path.exists(MEMBERS) else MEMBERS_FIXTURE
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "members" in data:
        data = data["members"]
    return {m["member_id"]: m for m in data}, path


def sections(m):
    """Flatten the record into (key, text) sections for overlap scoring."""
    out = []
    fit = m.get("fit")
    if isinstance(fit, dict):
        fit = f"{fit.get('bucket')} ({'; '.join(fit.get('reasons') or [])})"
    out.append(("house", f"house zip {m.get('zip')} year_built {m.get('year_built')} fit {fit}"))
    for k, v in (m.get("fields") or {}).items():
        out.append((f"field {k}", f"{k} value {v.get('value')} confidence {v.get('confidence')} source {v.get('source')}"))
    out.append(("confirm_with_member", "confirm_with_member " + ", ".join(m.get("confirm_with_member") or []) or "confirm_with_member none"))
    n = m.get("node") or {}
    out.append(("node", " ".join(f"{k} {v}" for k, v in n.items())))
    for d in m.get("week") or []:
        ev = "; ".join(d.get("events") or [])
        out.append((f"day {d.get('day')}", f"day {d.get('day')} date {d.get('date', '')} battery_usd {d.get('battery_usd')} gpu_usd {d.get('gpu_usd')} day_total_usd {round((d.get('battery_usd') or 0) + (d.get('gpu_usd') or 0), 2)} gpu_hours {d.get('gpu_hours')} reserve_min_pct {d.get('reserve_min_pct')} events: {ev or 'none'}"))
    t = m.get("totals") or {}
    out.append(("totals", "totals " + " ".join(f"{k} {v}" for k, v in t.items())))
    return out


def retrieve(m, question, k=8):
    qt = qtokens(question)
    scored = []
    for key, text in sections(m):
        st = tokens(key) | tokens(text)
        score = len(qt & st)
        if score:
            scored.append((score, key, text))
    scored.sort(key=lambda x: -x[0])
    return scored[:k]


def ollama_up():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=2) as r:
            return MODEL.split(":")[0] in r.read().decode()
    except Exception:
        return False


def build_prompt(question, ctx):
    return "RECORD:\n" + "\n".join(f"- [{k}] {t}" for _, k, t in ctx) + f"\n\nQUESTION: {question}\nANSWER:"


def ask_gemini(question, ctx):
    """Same SYSTEM and prompt, sent through the Gemini CLI (cloud)."""
    r = subprocess.run(["gemini", "-p", SYSTEM + "\n\n" + build_prompt(question, ctx)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0 and not r.stdout.strip():
        raise RuntimeError(r.stderr[:300])
    return r.stdout.strip().replace("\\", "").replace("**", "")


def ask_ollama(question, ctx):
    prompt = build_prompt(question, ctx)
    body = json.dumps({"model": MODEL, "think": False, "system": SYSTEM, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0, "num_predict": 200}}).encode()
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["response"].strip().replace("\\", "").replace("**", "")


def rule_answer(m, question, ctx):
    """Fallback when Ollama is down. Same retrieved sections, fixed templates."""
    q = question.lower()
    t = m.get("totals") or {}
    n = m.get("node") or {}
    if not ctx:
        return GAP
    if "reserve" in q:
        return f"Your reserve floor is {m['week'][0]['reserve_min_pct']}% and it was not breached this week (breaches: {t.get('reserve_breaches', 0)})."
    if "earn" in q or "make" in q or "total" in q:
        total = t.get("week_usd") or t.get("total_usd") or round((t.get("battery_usd") or 0) + (t.get("gpu_usd") or 0), 2)
        return f"This week your node earned ${total}: ${t.get('battery_usd')} from the battery and ${t.get('gpu_usd')} from {t.get('gpu_hours')} GPU hours."
    if "best" in q or "worst" in q:
        pick = max if "best" in q else min
        row = pick(m["week"], key=lambda x: x["battery_usd"] + x["gpu_usd"])
        return f"Day {row['day']} ({row.get('date', '')}): battery ${row['battery_usd']} plus GPU ${row['gpu_usd']}."
    if "house" in q or "home" in q:
        fit = m.get("fit"); fit = fit.get("bucket") if isinstance(fit, dict) else fit
        fs = ", ".join(f"{k} = {v['value']} ({int(v['confidence'] * 100)}% from {v['source']})" for k, v in m["fields"].items())
        return f"Zip {m['zip']}, built {m['year_built']}, fit {fit}. {fs}."
    if "feeder" in q or ("node" in q and "which" in q):
        return f"Node {n.get('nid')} on feeder {n.get('feeder')}, {n.get('battery_kwh')} kWh battery, GPU {n.get('gpu')}."
    if "confirm" in q:
        c = m.get("confirm_with_member") or []
        return ("Please confirm: " + ", ".join(c) + ".") if c else "Nothing is waiting for your confirmation."
    for key, text in ((k, x) for _, k, x in ctx):
        if key.startswith("day ") and any(w in q for w in ("discharge", "charge", "why", "happen")):
            d = key.split()[1]
            ev = [x for x in m["week"] if str(x["day"]) == d][0]["events"]
            return (f"{d}: " + " ".join(ev)) if ev else GAP
        if key.startswith("day ") and "gpu" in q:
            d = key.split()[1]
            row = [x for x in m["week"] if str(x["day"]) == d][0]
            return f"{d}: {row['gpu_hours']} GPU hours, ${row['gpu_usd']}."
        if key.startswith("field "):
            f = key.split()[1]
            v = m["fields"][f]
            return f"{f}: {v['value']} ({int(v['confidence'] * 100)}% confidence, source: {v['source']})."
    return GAP


def kb_hits(question, k=3):
    """store/kb.py kb_search, imported late. [(slug, text)]; [] when it is missing or fails."""
    if os.environ.get("BRAIN_KB", "1") == "0":
        return []
    try:
        from store import kb
        raw = kb.kb_search(question, k) or []
    except Exception as e:
        sys.stderr.write(f"knowledge base not available: {e}\n")
        return []
    out = []
    for h in raw:
        if isinstance(h, dict):
            if h.get("type") == "member_questions":  # other members' questions are not an answer
                continue
            slug = h.get("slug") or h.get("id") or h.get("node_id")
            text = h.get("body") or h.get("text") or h.get("content") or h.get("summary") or h.get("snippet") or ""
            if h.get("summary") and h["summary"] not in text:
                text = h["summary"] + "\n" + text
        elif isinstance(h, (list, tuple)) and h:
            slug, text = h[0], (h[2] if len(h) > 2 else "")
        else:
            continue
        if slug and str(text).strip():
            out.append((slug, str(text)))
    return out


def kb_rule(question, text):
    """No model: the two sentences of the page with the most words in common with the question."""
    qt = qtokens(question)
    body = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", re.sub(r"[#*`>|]+", " ", body)) if len(x.strip()) > 25]
    ranked = sorted(sents, key=lambda x: -len(qt & tokens(x)))
    best = [x for x in ranked[:2] if qt & tokens(x)]
    return " ".join(best)[:400] if best else GAP


def kb_answer(question, use_ollama):
    """Second source: the app knowledge base. Returns (answer, slug) or (GAP, None)."""
    hits = kb_hits(question)
    if not hits:
        return GAP, None
    slug, text = hits[0]
    a = GAP
    if use_ollama:
        try:
            prompt = "KNOWLEDGE:\n" + "\n\n".join(f"[{s}]\n{t[:2500]}" for s, t in hits[:2]) + f"\n\nQUESTION: {question}\nANSWER:"
            body = json.dumps({"model": MODEL, "think": False, "system": KB_SYSTEM, "prompt": prompt, "stream": False,
                               "options": {"temperature": 0, "num_predict": 200}}).encode()
            req = urllib.request.Request(OLLAMA + "/api/generate", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                a = json.loads(r.read())["response"].strip().replace("\\", "").replace("**", "")
        except Exception as e:
            sys.stderr.write(f"ollama failed on the knowledge base: {e}; using rules\n")
            a = kb_rule(question, text)
    else:
        a = kb_rule(question, text)
    if not a or "GAP" in a[:20]:
        return GAP, None
    return f"{a} (Base Brain knowledge base: {slug})", slug


def log(question, member_id, a, engine, path, t0):
    try:
        from store import learn
        learn.log_question(question, path, page="member", member_id=member_id,
                           template="rules" if engine == "rules" else None, answered=not a.startswith("GAP"),
                           seconds=time.time() - t0, answer=a)
    except Exception as e:
        sys.stderr.write(f"learn log failed: {e}\n")


def answer(member_id, question, use_ollama=None, backend=None):
    t0 = time.time()
    try:
        from store.learn import policy
        pol = policy(question)
    except Exception:  # store/learn.py missing: the short local list still routes policy questions
        pol = ("policy", "") if POLICY_RE.search(question) else None
    if pol:
        a = f"GAP: ask Base support. This is a Base policy question ({pol[0].replace('-', ' ')}). {pol[1]}".strip()
        log(question, member_id, a, "policy", "base_support", t0)
        return a, [], "policy"
    a, used, engine = answer_record(member_id, question, use_ollama, backend)
    path = "gap"
    if a.startswith("GAP"):
        up = use_ollama if use_ollama is not None else (engine not in ("rules",) and backend != "gemini")
        ka, slug = kb_answer(question, up and ollama_up())
        if slug:
            a, used, engine, path = ka, ["Base Brain knowledge base: " + slug], engine, "kb"
    else:
        path = "template" if engine == "rules" else "agent"
        used = ["Base Brain: your record"] + list(used)
    log(question, member_id, a, engine, path, t0)
    return a, used, engine


def answer_record(member_id, question, use_ollama=None, backend=None):
    members, _ = load_members()
    m = members[member_id]
    ctx = retrieve(m, question)
    if backend == "gemini":
        a = ask_gemini(question, ctx)
        if "GAP" in a[:20] or not a:
            a = GAP
        return a, [k for _, k, _ in ctx], "gemini-cli"
    if use_ollama is None:
        use_ollama = ollama_up()
    if use_ollama:
        try:
            a = ask_ollama(question, ctx)
            if "GAP" in a[:20] or not a:
                a = GAP
            return a, [k for _, k, _ in ctx], MODEL + ("" if OLLAMA.startswith("http://localhost") else "@" + OLLAMA)
        except Exception as e:
            sys.stderr.write(f"ollama failed: {e}; using rules\n")
    return rule_answer(m, question, ctx), [k for _, k, _ in ctx], "rules"


if __name__ == "__main__":
    args = sys.argv[1:]
    backend = None
    if args and args[0] in ("--backend", "--host"):
        backend = args[1]
        args = args[2:]
        set_backend(backend)
    mid, q = args[0], " ".join(args[1:])
    a, used, engine = answer(mid, q, backend=backend)
    print(f"[{engine}] sections: {used}\n{a}")
