"""Learning loop from member questions. Stdlib only.

1. log_question(...)   one JSON line per answered question -> data/live/questions.jsonl
                       (called by brain/ask.py, brain/answer.py and POST /learn/log from web/member.html)
2. python3 store/learn.py
                       loads the log into data/fleet.db table questions, groups recent questions,
                       ranks the groups, proposes one fix per group, writes web/data/learning.json
                       and docs/LEARNING.md, and writes a member_questions node to the knowledge base.
3. approve(pid, who) / reject(pid, who)
                       called by POST /learn/approve and /learn/reject on the ask server (localhost only).
                       Only an approved cached answer goes into brain/insights.json.

Privacy: no names, addresses, emails, phone numbers or IP addresses are stored. log_question
scrubs them from the question and the answer before it writes the line.
"""
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
LOG = os.path.join(ROOT, "data", "live", "questions.jsonl")
DECISIONS = os.path.join(ROOT, "data", "live", "learn_decisions.jsonl")
DB = os.path.join(ROOT, "data", "fleet.db")
OUT_JSON = os.path.join(ROOT, "web", "data", "learning.json")
OUT_MD = os.path.join(ROOT, "docs", "LEARNING.md")
INSIGHTS = os.path.join(ROOT, "brain", "insights.json")
PATHS = ("cache", "template", "kb", "agent", "gap", "base_support")
SLOW_S = 10.0
WINDOW_DAYS = 30

# Base policy: the data cannot answer these. Route to Base support with the reason; never answer them as fact.
# Same ten topics and reasons as the "Ask Base support" items in store/faq.py.
POLICY = [
    ("credit-payout", r"\b((next|my) credits?|credits? (date|day|payout|paid|pay out)|when .* credits?|payouts?|paid out)\b",
     "The credits on this site are assumed. Base has not offered them, so no payout date exists."),
    ("pay-billing", r"\b(pay|pays|paying|payments?|bill|billing|billed|invoices?|refunds?|deposit|warranty|how much does base cost)\b",
     "Billing is in Base's Help Center (17 Texas energy articles), which a public crawl cannot read."),
    ("cancel", r"\b(cancel\w*|terminat\w*|fees?)\b", "No public Base page states cancel terms."),
    ("contract", r"\b(contracts?|agreement length|how long .* (sign|commit))\b",
     "Contract length is a gap in the public pages (faq/FAQ.md #14)."),
    ("final-eligibility", r"\b(qualify|qualifies|qualified|eligib\w*|approved for|will i get base)\b",
     "Base engineers decide. Public records give a starting point only (faq/FAQ.md #1 to #4)."),
    ("own-battery", r"\b(own the battery|owns? the (battery|system)|buy the battery|keep the battery)\b",
     "The page lists this as a video title only, with no answer text (faq/FAQ.md #22)."),
    ("second-battery", r"\b(second battery|another battery|add (a |another |more )?batter(y|ies)|more batteries|two batteries)\b",
     "Video title only on Base's page (faq/FAQ.md #24)."),
    ("solar", r"\b((work|works|compatible) with (my )?solar|my solar|solar panels)\b",
     "Video title only; Help Center articles on solar are not public text (faq/FAQ.md #19)."),
    ("hoa", r"\b(hoa|homeowners? association)\b", "Only a member review on Base's page says so. That is not a policy (faq/FAQ.md #6)."),
    ("renter", r"\b(rent|renter|renting|landlord|tenant|lease)\b", "Not stated on any public Base page (faq/FAQ.md #7)."),
]
POLICY_RX = [(k, re.compile(rx, re.I), why) for k, rx, why in POLICY]


def policy(q):
    """(topic, reason) when the question is Base policy, else None."""
    for k, rx, why in POLICY_RX:
        if rx.search(q or ""):
            return k, why
    return None


def is_policy(q):
    return policy(q) is not None


# ---------- 1. log ----------

_SCRUB = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "[email]"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "[ip]"),
    (re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b"), "[phone]"),
    (re.compile(r"\b\d{2,6}\s+(?:[A-Za-z]+\s+){1,3}(?:st|street|ave|avenue|rd|road|dr|drive|ln|lane|blvd|"
                r"boulevard|ct|court|way|cir|circle|trl|trail|pkwy|parkway|cv|cove|pl|place)\b\.?", re.I), "[address]"),
    (re.compile(r"\b(my name is|i am called|this is)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?", re.I), r"\1 [name]"),
]


def scrub(s):
    s = str(s or "")
    for rx, rep in _SCRUB:
        s = rx.sub(rep, s)
    return s


def log_question(question, path, page=None, member_id=None, template=None, answered=None,
                 critic_pass=None, seconds=None, answer=None):
    """Append one line to data/live/questions.jsonl. Never raises."""
    try:
        if os.environ.get("LEARN_LOG", "1") == "0":
            return None
        path = path if path in PATHS else "agent"
        mid = str(member_id)[:12] if member_id and re.match(r"^[A-Za-z0-9_-]{1,12}$", str(member_id)) else None
        rec = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "page": (re.sub(r"[^\w./-]", "", str(page))[:60] or None) if page else None,
               "question": scrub(question)[:400], "member_id": mid, "path": path,
               "template": str(template)[:80] if template else None,
               "answered": bool(answered) if answered is not None else path not in ("gap", "base_support"),
               "critic_pass": None if critic_pass is None else bool(critic_pass),
               "seconds": round(float(seconds), 2) if seconds is not None else None,
               "answer": scrub(answer)[:200] if answer else None}
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec
    except Exception as e:  # logging must never break an answer
        sys.stderr.write(f"learn log failed: {e}\n")
        return None


def read_log():
    out = []
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return out


def load_db(rows):
    """Upsert the log into data/fleet.db table questions. Natural key: ts plus question."""
    con = sqlite3.connect(DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS questions (ts TEXT, page TEXT, question TEXT, member_id TEXT,
      path TEXT, template TEXT, answered INTEGER, critic_pass INTEGER, seconds REAL, answer TEXT,
      PRIMARY KEY (ts, question))""")
    con.executemany("INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (r.get("ts"), r.get("page"), r.get("question"), r.get("member_id"), r.get("path"), r.get("template"),
         None if r.get("answered") is None else int(bool(r["answered"])),
         None if r.get("critic_pass") is None else int(bool(r["critic_pass"])), r.get("seconds"), r.get("answer"))
        for r in rows])
    con.commit()
    n = con.execute("SELECT count(*) FROM questions").fetchone()[0]
    con.close()
    return n


# ---------- knowledge base writes (tables kb_nodes, kb_edges in data/fleet.db) ----------

KB_PREFIX = "hackathons/2026-09-base-fleet-data/"  # same slug prefix as store/kb.py
# ask.py CATALOG source -> Base Brain dataset slug (store/kb.py); other sources match on repo_path data/<file>.
KB_DATASET = {"permits": "energy-permit-mirror", "market": "base-rollout", "zips": "energy-permit-mirror"}


def kb_dataset(source):
    if not source:
        return None
    if source in KB_DATASET:
        return KB_PREFIX + KB_DATASET[source]
    try:
        from brain.ask import CATALOG
        f = CATALOG.get(source, {}).get("file")
        con = sqlite3.connect(DB, timeout=30)
        row = con.execute("SELECT slug FROM kb_nodes WHERE type='dataset' AND repo_path=?", ("data/" + f,)).fetchone() if f else None
        con.close()
        return row[0] if row else None
    except Exception:
        return None


def kb_page(page):
    name = re.sub(r"\.html$", "", str(page or "").split("/")[-1])
    return KB_PREFIX + "page-" + name if re.match(r"^[\w-]+$", name) else None


def kb_put(slug, ntype, title, summary, body, repo_path, edges=()):
    """Write one node and its edges into Base Brain (kb_nodes, kb_edges in data/fleet.db).
    edges: [(dst_slug, type)]. Only edges to nodes that exist. Returns 'ok ...' or why it skipped. Never raises."""
    try:
        con = sqlite3.connect(DB, timeout=30)
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "kb_nodes" not in tabs or "kb_edges" not in tabs:
            con.close()
            return "skipped: no kb tables (run python3 store/kb.py)"
        slug = KB_PREFIX + slug
        con.execute("INSERT OR REPLACE INTO kb_nodes (slug, type, title, summary, body, repo_path, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)", (slug, ntype, title[:200], summary[:400], body, repo_path,
                                               datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")))
        con.execute("DELETE FROM kb_edges WHERE src=? AND source='store/learn.py'", (slug,))
        known = {r[0] for r in con.execute("SELECT slug FROM kb_nodes")}
        n = 0
        for dst, typ in edges:
            if dst and dst in known:
                con.execute("INSERT OR IGNORE INTO kb_edges (src, dst, type, source) VALUES (?,?,?,?)",
                            (slug, dst, typ, "store/learn.py"))
                n += 1
        con.commit()
        con.close()
        return f"ok, {slug}, {n} edges"
    except Exception as e:
        sys.stderr.write(f"kb write failed: {e}\n")
        return f"skipped: {str(e)[:120]}"


def kb_learned(pid, rec, pages, who, when):
    edges = [(kb_dataset(rec.get("source")), "cites")] + [(kb_page(p), "asked_on") for p in pages or []]
    body = (f"Question: {rec['question']}\nAnswer: {rec['answer']}\nTemplate: {rec.get('template')}\n"
            f"Source: {rec.get('query_url') or rec.get('source')}\nApproved by {who} at {when}.")
    return kb_put("learned-" + pid, "learned_answer", rec["question"], rec["answer"][:400], body,
                  "brain/insights.json", edges)


def kb_restore():
    """store/kb.py rebuilds its tables from zero; write every approved learned answer back."""
    n = 0
    try:
        with open(INSIGHTS) as f:
            for rec in json.load(f).get("insights", []):
                a = rec.get("approved")
                if a and kb_learned(a["proposal"], rec, [rec.get("page")], a["who"], a["when"]).startswith("ok"):
                    n += 1
    except Exception as e:
        sys.stderr.write(f"kb restore failed: {e}\n")
    return n


# ---------- 2. group, rank, propose ----------

STOP = set("a an the of in on at to for by and or is are was were be been what which who how many much does do did it "
           "its this that there their with from as than per any all each give me show list my i we our you your can "
           "will would should could please tell about get have has there right now last next into".split())
SYN = {"batteries": "battery", "zips": "zip", "zipcode": "zip", "highest": "top", "most": "top", "peak": "top",
       "biggest": "top", "utility": "tdu", "auxiliary": "backup", "installs": "permit", "installations": "permit"}


def norm_tokens(q):
    ts = re.findall(r"[a-z0-9]+", str(q).lower())
    out = []
    for t in ts:
        if t in STOP:
            continue
        t = SYN.get(t, t)
        if not t[0].isdigit() and len(t) > 4:
            t = t[:-3] + "y" if t.endswith("ies") else t[:-3] if t.endswith("ing") else t[:-2] if t.endswith("ed") \
                else t[:-1] if t.endswith("s") and not t.endswith("ss") else t
        out.append(t)
    return out


def norm(q):
    return " ".join(norm_tokens(q))


def group(rows, jac=0.6):
    """Greedy grouping: same normalised text, or token overlap (Jaccard) >= jac with the group's first question."""
    groups = []
    for r in rows:
        ts = set(norm_tokens(r["question"]))
        pol = policy(r["question"])
        key = "policy:" + pol[0] if pol else norm(r["question"])  # policy questions group by topic
        best = None
        for g in groups:
            if g["key"] == key:
                best = g
                break
            u = ts | g["tokens"]
            if not pol and not g["key"].startswith("policy:") and u and len(ts & g["tokens"]) / len(u) >= jac:
                best = g
                break
        if not best:
            best = {"key": key, "tokens": ts, "rows": []}
            groups.append(best)
        best["rows"].append(r)
    return groups


def pick_source(q):
    """Rule-based source choice for a draft template: token overlap with the ask catalog."""
    try:
        from brain.ask import CATALOG
    except Exception:
        return None, 0
    qt = set(norm_tokens(q)) - {"base", "austin", "power"}  # too common to pick a source
    best, score = None, 0
    for k, s in CATALOG.items():
        use = set(norm_tokens(s["use_for"] + " " + k))
        n = 2 * len(qt & use) + len(qt & set(norm_tokens(s["label"])))
        if n > score:
            best, score = k, n
    return best, score


def params_of(q):
    p = {}
    z = re.findall(r"\b7[5-9]\d{3}\b", q)
    if z:
        p["zip"] = z
    y = re.findall(r"\b20[12]\d\b", q)
    if y:
        p["year"] = y
    m = re.findall(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", q, re.I)
    if m:
        p["month"] = [x.lower()[:3] for x in m]
    d = re.findall(r"\$\s?(\d+)", q)
    if d:
        p["price_over"] = d
    if re.search(r"\bbase\b", q, re.I):
        p["contractor"] = "Base Power"
    return p


def draft_query(src, p, q):
    if src == "permits":
        where = []
        if p.get("contractor"):
            where.append("contractor_company_name='Base Power'")
        if re.search(r"solar", q, re.I):
            where.append("upper(description) like '%SOLAR%'")
        elif re.search(r"backup|battery|batteries|generator", q, re.I):
            where.append("work_class='Auxiliary Power'")
        if p.get("zip"):
            where.append("original_zip in (" + ",".join(f"'{z}'" for z in p["zip"]) + ")")
        if p.get("year"):
            where.append(f"calendar_year_issued='{p['year'][0]}'")
        q_ = {"$where": " AND ".join(where) or "1=1"}
        if re.search(r"\bzips?\b", q, re.I) and not p.get("zip"):
            q_.update({"$select": "original_zip, count(*) as permits", "$group": "original_zip",
                       "$order": "permits DESC", "$limit": 10})
        else:
            q_["$select"] = "count(*) as permits"
        return {"kind": "soql", "query": q_}
    if not src:
        return None
    cond = []
    if p.get("zip"):
        cond.append(f"r['zip'] in {p['zip']}")
    if p.get("price_over") and src == "dam":
        cond.append(f"float(r['aen']) > {p['price_over'][0]}")
    if p.get("year") and src in ("dam",):
        cond.append(f"r['date'].startswith('{p['year'][0]}')")
    if src == "dam" and re.search(r"last week|this week", q, re.I):
        cond.append("r['date'] >= TODAY_MINUS_7")
    rows = f"[r for r in rows if {' and '.join(cond) or 'True'}]"
    if re.search(r"\b(highest|most|top|max|peak|biggest)\b", q, re.I):
        key = {"dam": "aen", "load": "SCENT"}.get(src, "count")
        rows = f"sorted({rows}, key=lambda r: -float(r['{key}']))[:5]"
    return {"kind": "local filter", "query": rows}


def insight_questions():
    try:
        with open(INSIGHTS) as f:
            return {norm(i["question"]) for i in json.load(f).get("insights", [])}
    except Exception:
        return set()


def template_record(q):
    """A cached answer may only come from code: run the template for this question now."""
    try:
        from brain import ask as A
        from brain import templates
        if not templates.match(q, A.TODAY):
            return None
        r = A.ask(q, use_cache=False)
        if r.get("path") == "template" and r["critic"]["pass"]:
            r.pop("steps", None)
            return r
    except Exception as e:
        sys.stderr.write(f"template run failed for {q[:60]}: {e}\n")
    return None


def decisions():
    out = {}
    try:
        with open(DECISIONS) as f:
            for line in f:
                try:
                    d = json.loads(line)
                    out[d["id"]] = d
                except (ValueError, KeyError):
                    pass
    except FileNotFoundError:
        pass
    return out


def pid_of(kind, key):
    import hashlib
    return kind[:2] + "-" + hashlib.sha1(key.encode()).hexdigest()[:8]


def propose(groups, cached, run_templates=True):
    props = []
    for g in groups:
        rows = g["rows"]
        rep = Counter(r["question"] for r in rows).most_common(1)[0][0]
        n = len(rows)
        unanswered = sum(1 for r in rows if not r.get("answered") or r.get("path") in ("gap", "base_support"))
        slow = sum(1 for r in rows if r.get("path") == "agent" and (r.get("seconds") or 0) > SLOW_S)
        fails = sum(1 for r in rows if r.get("critic_pass") is False)
        paths = Counter(r.get("path") for r in rows)
        stats = {"asked": n, "unanswered": unanswered, "slow_agent": slow, "critic_fail": fails, "paths": dict(paths),
                 "pages": sorted({r.get("page") for r in rows if r.get("page")}),
                 "examples": sorted({r["question"] for r in rows})[:4], "last": max(r["ts"] for r in rows)}
        prio = unanswered * 3 + fails * 2 + slow * 1.5
        if is_policy(rep):
            props.append({"id": pid_of("base_support", g["key"]), "kind": "base_support", "question": rep,
                          "priority": round(n * 3, 1), "stats": stats,
                          "proposal": "Base policy question: route to Base support",
                          "why": "Credits, cancelling, payments, contracts and eligibility are Base policy. The data cannot answer them."})
            continue
        ok_paths = {"template", "cache", "kb"}
        if g["key"] not in cached and paths.get("template") and fails == 0 and run_templates:
            rec = template_record(rep)
            if rec:
                props.append({"id": pid_of("cached_answer", g["key"]), "kind": "cached_answer", "question": rep,
                              "priority": round(n * 1.0, 1), "stats": stats,
                              "proposal": f"Cache the answer from template {rec.get('template')}",
                              "why": "A template answered it and the critic passed. Caching skips the server call.",
                              "answer": rec["answer"], "template": rec.get("template"), "source": rec.get("source"),
                              "record": rec})
                continue
        if prio == 0 and set(paths) <= ok_paths:
            continue
        if prio == 0 and all(str(r.get("page") or "").startswith("member") for r in rows):
            continue  # Base Brain answered from the member record, fast: nothing to fix
        src, score = pick_source(rep)
        p = params_of(rep)
        tok = [t for t in norm_tokens(rep) if not t.isdigit()][:3]
        props.append({"id": pid_of("new_template", g["key"]), "kind": "new_template", "question": rep,
                      "priority": round(prio or n * 0.5, 1), "stats": stats,
                      "proposal": f"New template {(src or 'none')}.{'_'.join(tok)}",
                      "why": ("Unanswered" if unanswered else "Slow agent answer" if slow else "Critic fail" if fails else "Agent path")
                             + f" {n} time{'s' if n != 1 else ''}." + ("" if src else " No current data source covers it."),
                      "intent": "_".join(tok), "parameters": p,
                      "data_source": src if score else None, "draft": draft_query(src if score else None, p, rep)})
    props.sort(key=lambda x: (-x["priority"], -x["stats"]["asked"]))
    return props


def week_stats(rows, since):
    wk = [r for r in rows if r["ts"] >= since]
    by = Counter(r.get("path") for r in wk)
    ans = Counter(r.get("path") for r in wk if r.get("answered"))
    return wk, {p: {"asked": by.get(p, 0), "answered": ans.get(p, 0)} for p in PATHS if by.get(p)}


def build(run_templates=True):
    rows = read_log()
    n_db = load_db(rows) if rows else 0
    now = datetime.now(timezone.utc)
    since7 = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since14 = (now - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since_w = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent = [r for r in rows if r.get("ts", "") >= since_w]
    wk, by_path = week_stats(rows, since7)
    prev = [r for r in rows if since14 <= r["ts"] < since7]
    groups = group(recent)
    props = propose(groups, insight_questions(), run_templates)
    dec = decisions()
    for p in props:
        if p["id"] in dec:
            p["status"] = dec[p["id"]]["action"]
            p["decided"] = {"who": dec[p["id"]]["who"], "when": dec[p["id"]]["when"]}
        else:
            p["status"] = "proposed"
    unans = [g for g in groups if any(not r.get("answered") for r in g["rows"])]
    top_unanswered = sorted(({"question": Counter(r["question"] for r in g["rows"]).most_common(1)[0][0],
                              "asked": len(g["rows"]), "paths": dict(Counter(r.get("path") for r in g["rows"]))}
                             for g in unans), key=lambda x: -x["asked"])[:10]
    base_only = [{"question": p["question"], "asked": p["stats"]["asked"]} for p in props if p["kind"] == "base_support"]
    un7 = sum(1 for r in wk if not r.get("answered"))
    un_prev = sum(1 for r in prev if not r.get("answered"))
    secs = sorted(r["seconds"] for r in wk if r.get("seconds") is not None)
    doc = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "log": "data/live/questions.jsonl", "db_rows": n_db,
           "total_logged": len(rows), "week": {"asked": len(wk), "answered": sum(1 for r in wk if r.get("answered")),
                                                "median_seconds": secs[len(secs) // 2] if secs else None,
                                                "by_path": by_path, "pages": dict(Counter(r.get("page") or "unknown" for r in wk))},
           "signal": {"name": "unanswered_spike", "unanswered_7d": un7, "unanswered_prev_7d": un_prev,
                      "ratio": round(un7 / un_prev, 2) if un_prev else None},
           "top_unanswered": top_unanswered, "base_support": base_only,
           "proposals": [{k: v for k, v in p.items() if k != "record"} for p in props[:40]],
           "kb": {}}
    # A proposed cached answer keeps its full record next to the page data, for approve().
    doc["_records"] = {p["id"]: p["record"] for p in props if p.get("record")}
    pages = sorted({r.get("page") for r in wk if r.get("page")})
    datasets = sorted({kb_dataset(p.get("data_source") or p.get("source")) for p in props} - {None})
    doc["kb"]["member_questions"] = kb_put(
        "member-questions", "member_questions", f"Member questions, week to {now:%Y-%m-%d}",
        f"{doc['week']['asked']} questions this week, {doc['week']['answered']} answered.", weekly_summary(doc),
        "web/data/learning.json", [(kb_page(p), "asked_on") for p in pages] + [(d, "asks_about") for d in datasets])
    doc["kb"]["learned_restored"] = kb_restore()
    doc["kb"]["learned_answers"] = sum(1 for d in dec.values() if d["action"] == "approved")
    with open(OUT_JSON, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    with open(OUT_MD, "w") as f:
        f.write(markdown(doc))
    return doc


def weekly_summary(d):
    w = d["week"]
    lines = [f"{w['asked']} questions this week, {w['answered']} answered."]
    lines += [f"{p}: {v['answered']} of {v['asked']} answered." for p, v in w["by_path"].items()]
    if d["top_unanswered"]:
        lines.append("Top unanswered: " + "; ".join(f"{x['question']} ({x['asked']})" for x in d["top_unanswered"][:5]) + ".")
    if d["base_support"]:
        lines.append("Only Base support can answer: " + "; ".join(x["question"] for x in d["base_support"][:8]) + ".")
    return "\n".join(lines)


def markdown(d):
    w = d["week"]
    out = ["# Base Brain: learning from member questions", "",
           f"Generated {d['generated']} by `store/learn.py`. Do not edit by hand.", "",
           "## How the loop works", "",
           "1. Log. The ask server (`/ask` and `/ask?stream=1`), Base Brain (`brain/answer.py`) and typed questions on "
           "`web/member.html` (through `POST /learn/log` when a local server runs) append one line per question to "
           "`data/live/questions.jsonl`: time, page, question, member id, path, template id, answered, critic pass, seconds, "
           "and the first 200 characters of the answer. The logger removes emails, phone numbers, street addresses, "
           "IP addresses and \"my name is\" names. The server does not log the caller IP address.",
           "2. Learn. `collect/daily.sh` runs `python3 store/learn.py` each night. It loads the log into table `questions` in "
           "`data/fleet.db`, groups the last 30 days of questions by normalised text and token overlap, and ranks the groups: "
           "unanswered or gap first, then critic fails, then slow agent answers (more than 10 s).",
           "3. Propose. Each group gets one proposal: a new template (intent, parameters, data source, draft SoQL or local "
           "filter), a new cached answer (only when a template produces it now and the critic passes; never from an agent "
           "answer), or \"Base policy question: route to Base support\" (credits, cancelling, payments, contracts, eligibility).",
           "4. Approve. A person approves or rejects each proposal on the admin page. The buttons call `POST /learn/approve` "
           "and `POST /learn/reject` on the ask server, which accepts localhost only and records who and when in "
           "`data/live/learn_decisions.jsonl`. An approved cached answer goes into `brain/insights.json` and into the app "
           "knowledge base as a `learned_answer` node. Nothing goes live without approval.",
           "5. Knowledge base. The ask planner has a `kb` source: questions about our data or methods (not a live number) "
           "get an answer from `store/kb.py` `kb_search`, cited as \"Base Brain knowledge base: <slug>\". Base Brain answers a member from "
           "the member record first, then from the knowledge base. Each run of this script writes the weekly summary as a "
           "`member_questions` node. No personal data goes into the knowledge base, and Base policy is never written as fact.",
           "6. Signal. `learning.json` field `signal` has `unanswered_7d` and `unanswered_prev_7d` for an `unanswered_spike` rule.",
           "", "## This week", "",
           f"{w['asked']} questions, {w['answered']} answered, median {w['median_seconds']} s. "
           f"All time logged: {d['total_logged']}.", "",
           "| Path | Asked | Answered |", "|---|---:|---:|"]
    out += [f"| {p} | {v['asked']} | {v['answered']} |" for p, v in w["by_path"].items()]
    out += ["", f"Signal unanswered_spike: {d['signal']['unanswered_7d']} unanswered this week, "
            f"{d['signal']['unanswered_prev_7d']} the week before.", "", "## Top unanswered", ""]
    out += [f"- {x['question']} (asked {x['asked']})" for x in d["top_unanswered"]] or ["- none"]
    out += ["", "## What members ask that only Base can answer", ""]
    out += [f"- {x['question']} (asked {x['asked']})" for x in d["base_support"]] or ["- none"]
    out += ["", "## Proposals", "", "| # | Kind | Question | Proposal | Asked | Status |", "|---:|---|---|---|---:|---|"]
    for i, p in enumerate(d["proposals"][:25], 1):
        out.append(f"| {i} | {p['kind']} | {p['question'].replace('|', '/')} | {p['proposal'].replace('|', '/')} | "
                   f"{p['stats']['asked']} | {p['status']} |")
    out += ["", "Draft queries for new templates are in `web/data/learning.json` (`proposals[].draft`).", ""]
    return "\n".join(out)


# ---------- 3. approve / reject ----------

def decide(pid, action, who):
    who = re.sub(r"[^\w .@-]", "", str(who or "admin"))[:40] or "admin"
    with open(OUT_JSON) as f:
        doc = json.load(f)
    prop = next((p for p in doc.get("proposals", []) if p["id"] == pid), None)
    if not prop:
        return {"ok": False, "error": f"no proposal {pid}"}
    if prop.get("status") in ("approved", "rejected"):
        return {"ok": False, "error": f"already {prop['status']}"}
    when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {"ok": True, "id": pid, "action": action, "who": who, "when": when}
    if action == "approved" and prop["kind"] == "cached_answer":
        rec = (doc.get("_records") or {}).get(pid)
        if not rec or rec.get("path") != "template" or not rec.get("critic", {}).get("pass"):
            return {"ok": False, "error": "no template record with a critic pass; cannot cache"}
        with open(INSIGHTS) as f:
            ins = json.load(f)
        if norm(rec["question"]) not in {norm(i["question"]) for i in ins["insights"]}:
            rec = dict(rec, page=(prop["stats"].get("pages") or ["learned"])[0], persona="member",
                       recorded=when, approved={"who": who, "when": when, "proposal": pid})
            ins["insights"].append(rec)
            ins["questions"] = len(ins["insights"])
            ins["critic_pass"] = sum(1 for i in ins["insights"] if i["critic"]["pass"])
            ins["template_count"] = sum(1 for i in ins["insights"] if i["path"] == "template")
            tmp = INSIGHTS + ".tmp"
            with open(tmp, "w") as f:
                json.dump(ins, f, indent=1, default=str)
            os.replace(tmp, INSIGHTS)
            result["insights"] = "added"
        result["kb"] = kb_learned(pid, rec, prop["stats"].get("pages"), who, when)
    with open(DECISIONS, "a") as f:
        f.write(json.dumps({"id": pid, "action": action, "who": who, "when": when, "kind": prop["kind"],
                            "question": prop["question"]}) + "\n")
    prop["status"], prop["decided"] = action, {"who": who, "when": when}
    tmp = OUT_JSON + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1, default=str)
    os.replace(tmp, OUT_JSON)
    return result


def approve(pid, who):
    return decide(pid, "approved", who)


def reject(pid, who):
    return decide(pid, "rejected", who)


if __name__ == "__main__":
    t0 = time.time()
    d = build(run_templates="--no-templates" not in sys.argv)
    print(f"learning.json: {d['total_logged']} logged, week {d['week']['asked']} asked / {d['week']['answered']} answered, "
          f"{len(d['proposals'])} proposals, kb {d['kb']['member_questions']}, {round(time.time() - t0, 1)} s")
