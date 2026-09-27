"""Base Brain, the app knowledge base: how the docs, datasets, pages, gaps, personas, zips, signals and jobs connect. Stdlib only.

Writes two tables in data/fleet.db and one browser file:
  kb_nodes(slug, type, title, summary, body, repo_path, updated_at)
  kb_edges(src, dst, type, source)
  web/data/kb_graph.json   nodes (type, title, slug, summary, path) and edges (type) for web/knowledge.html

Every link comes from the repo, not from a hand list:
  page reads dataset / dataset feeds page   fetch paths and data file names in web/*.html and their local js
  doc describes / cites_number              repo file paths named in the doc (a line with a number is a citation)
  gap affects / fixed_by                    paths and page names in web/data/gaps.json issue text; git log for the fix
  persona tours page                        web/data/tours.json
  zip appears_in page                       the zip string in the page or in a data file the page reads
  job refreshes dataset / serves page       collect/install_mac.sh, the job scripts, the port in the page
  signal watches dataset                    RULES in store/signals.py
A run replaces the rows of its own node types in one transaction (store/faq.py and store/learn.py add
other types; run them after this file), so a run twice gives the same rows.

  python3 store/kb.py                       build tables and export
  python3 store/kb.py --search "question"   print kb_search results (what the ask server gets)
"""

import argparse
import glob
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
OUT = os.path.join(ROOT, "web", "data", "kb_graph.json")
# Same prefix as the gbrain dataset, learned-answer and member-question pages, so a slug means one thing everywhere.
PREFIX = "hackathons/2026-09-base-fleet-data/"
OWN_TYPES = ("hub", "dataset", "doc", "page", "gap", "persona", "zip", "signal", "job")
SPINE_DATASETS = ["energy-permit-mirror", "base-rollout", "easy-fit-funnel", "deeds", "ercot-prices-year"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_nodes (slug TEXT PRIMARY KEY, type TEXT, title TEXT, summary TEXT, body TEXT,
  repo_path TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS kb_edges (src TEXT, dst TEXT, type TEXT, source TEXT, PRIMARY KEY (src, dst, type));
CREATE INDEX IF NOT EXISTS kb_edges_dst ON kb_edges(dst);
"""

# Datasets: the 15 data pages under PREFIX (the index page is the hub). files = repo paths that hold or make the
# data; a page that reads one of them reads the dataset. producers = what a job script must call to refresh it.
DATASETS = {
    "energy-permit-mirror": ("Energy permit mirror",
        "City of Austin energy permits since 2015, 34,334 rows, contractors anonymized except Base.",
        ["data/mirror/energy_permits.csv.gz", "web/data/explorer_points.json", "web/data/explorer_zip.json",
         "data/permits_by_zip.json", "house/mirror.py", "house/permits_by_zip.py"],
        ["house.mirror", "house.permits_by_zip", "store/build.py"], "docs/MIRROR_SCHEMA.md"),
    "base-rollout": ("Base rollout (permit-visible)",
        "Base backup permits in Austin: 316 in 2026, 264 still open, 69% of the Auxiliary Power class since July.",
        ["data/market.json", "house/market.py"], ["house.market"], "docs/SUBMISSION.md"),
    "storms": ("Storm surges and readiness",
        "Backup permit surges after Uri and the 2023 ice storm, and a per-zip storm readiness estimate.",
        ["data/storms.json", "house/storms.py"], [], "docs/STORM_RUSH.md"),
    "territory-power-to-choose": ("Territory and Power to Choose",
        "Zip to utility (TDU) and Base offer status for 59 zips, checked on the Power to Choose API.",
        ["data/ptc_tdu.json", "house/territory.py"], [], None),
    "easy-fit-funnel": ("Easy-fit funnel and star areas",
        "Estimated easy-fit homes per zip through a 5-stage funnel from public aggregates.",
        ["data/funnel.json", "data/funnel.fixture.json", "web/data/star_cards.json", "house/funnel.py",
         "house/cohort.json"], [], "docs/STAR_AREAS.md"),
    "demographics-assisted-priority": ("Demographics and assisted priority",
        "ACS 5-year demographics per zip and the assisted-onboarding priority score.",
        ["data/demographics.json", "house/demographics.py"], ["house/demographics.py"], "docs/STORM_RUSH.md"),
    "deeds": ("Deeds",
        "Deed dates per zip from Travis and Williamson CAD, 588,135 parcels, no owner names.",
        ["data/deeds_by_zip.json", "data/mirror/deeds_min.csv.gz", "house/cad_deeds.py"], [], "docs/DEEDS.md"),
    "ercot-prices-year": ("ERCOT prices, one year",
        "One battery against 627 days of real ERCOT day-ahead prices.",
        ["data/ercot_dam_hourly_2025_2026.csv", "web/data/grid_year.json", "grid/year.py", "grid/ercot_archive.py"],
        [], "grid/YEAR.md"),
    "ercot-load": ("ERCOT load",
        "ERCOT hourly load 2024 to 2026 by weather zone; peaks fall 4 to 8 pm in July and August.",
        ["data/ercot_load_hourly_2024_2026.csv", "web/data/grid_load.json"], [], "grid/LOAD.md"),
    "ercot-live-feeds": ("ERCOT live feeds",
        "Live ERCOT dashboard feeds with no login: prices, supply and demand, fuel mix, reserves.",
        ["data/live/ercot", "data/ercot/", "web/data/grid_today.json", "grid/today.py", "grid/ercot_system.js",
         "collect/ercot_feeds.sh"], ["dashboards", "grid/today.py"], "grid/ERCOT_LIVE.md"),
    "sim-fleet-numbers": ("Sim and fleet numbers",
        "Every sim and grid headline number, rerunnable, with the before and after of the territory fix.",
        ["grid/NUMBERS.md", "out/report.json", "out/density.json", "web/data/report.json", "web/data/density.json",
         "web/data/fleet_kill_log.json", "sim/fleet.py", "grid/earned.py"], [], "grid/NUMBERS.md"),
    "judgments": ("Judgments",
        "Confidence routing for every guessed field: auto, model review, or human.",
        ["web/data/judgments.json", "store/judgments.py"], ["store/build.py"], "docs/MIRROR_SCHEMA.md"),
    "signals": ("Signals",
        "Five live alert rules over fleet.db: Base week, zip surge, price spike, low reserves, storm alert.",
        ["web/data/signals.json", "store/signals.py"], ["store/signals.py"], None),
    "local-ai-tests": ("Local AI tests",
        "Member brain answers on a laptop, an edge box and a cloud model, scored on fixed questions.",
        ["brain/LOCAL_VS_CLOUD.md", "brain/score.py", "brain/answer.py", "brain/pred.jsonl", "brain/pred_laptop.jsonl", "brain/pred_jetson.jsonl",
         "brain/pred_gemini.jsonl", "brain/questions.json", "brain/questions.fixture.json"], [],
        "brain/LOCAL_VS_CLOUD.md"),
    "gaps": ("Gaps (claim audit)",
        "Claim audit ledger: every headline claim tested against public data, tracked as Gap issues.",
        ["docs/GAPS.md", "web/data/gaps.json"], ["admin/build.py"], "docs/GAPS.md"),
}

DOCS = (["docs/SUBMISSION.md", "docs/VIDEO.md", "docs/GAPS.md", "docs/DATAFLOW.md", "docs/MIRROR_SCHEMA.md",
         "docs/STORM_RUSH.md", "docs/DEEDS.md", "docs/STAR_AREAS.md", "docs/PERSONAS.md", "docs/DEMO_RUNBOOK.md",
         "docs/BACKEND_CHECK.md", "docs/LEARNING.md", "docs/SUBMISSION_FORM.md", "docs/UX_REDESIGN.md",
         "docs/KNOWLEDGE_BASE.md"]
        + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "docs", "adr", "*.md")))
        + ["grid/YEAR.md", "grid/LOAD.md", "grid/NUMBERS.md", "grid/RATES.md", "grid/FEEDERS.md",
           "grid/LIBRARY_NODE.md", "grid/ERCOT_DATA.md", "grid/ERCOT_LIVE.md", "brain/LOCAL_VS_CLOUD.md",
           "collect/README.md"])

STOP = set("""a an and are as at be been but by can could did do does for from had has have how i if in into is it
its of on or our should so than that the their them then there these they this to up was we were what when where which
who why will with would you your me my about any all also more most much no not one out over per some such very""".split())

DATA_RE = re.compile(r"""(?:\.\./)?((?:web/)?(?:data|brain|house|panel|out)/[\w./-]+\.(?:json|jsonl|geojson|csv|gz))""")
PATH_RE = re.compile(r"\b((?:docs|grid|house|brain|store|sim|web|data|collect|out|panel|admin)/[\w./-]*[\w/])")
NUM_RE = re.compile(r"(?<![\w.#])(?:\$?\d[\d,]*(?:\.\d+)?%?)(?![\w])")
SECRET_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|\b(?:sk|pk|ghp|xox[bp])[-_][A-Za-z0-9_-]{10,}"
                       r"|[\w.%+-]+@[\w-]+\.[\w.]+")
ADDR_RE = re.compile(r"\b\d{2,6}(?: [A-Z][a-z]+){1,3} (?:Dr|Drive|St|Street|Ave|Avenue|Ln|Lane|Rd|Road|Blvd|Cir|Ct|Cv|Pl|Pkwy|Trl|Way|Loop)\b\.?"
                     r"|\b\d{3,6} [A-Z][a-z]+(?= ?[:(,])")
PERSON_RE = re.compile(r"\bRavi(?:nder)?(?:\s+[A-Z][a-z]+)?\b")
META_RE = re.compile(r"^(?:Date|Status|Written|Branch|Issue|Issues|Page|Script|Producer|Built|Numbers from|Run )\b", re.I)


MOD_RE = re.compile(r"\b(house|brain|store|sim|grid|admin)\.([a-z_]+)\b")
ADR_RE = re.compile(r"\bADR[- ]?0*(\d{1,4})\b")


def paths_in(text):
    """Repo paths named in text, including module names (house.mirror -> house/mirror.py)."""
    out = set(PATH_RE.findall(text))
    out.update(f"{a}/{b}.py" for a, b in MOD_RE.findall(text) if b not in ("py", "md", "json"))
    return out


def doc_refs(text, docs):
    """Doc slugs named in text: a doc path, an ADR number, or a bare upper-case doc name (VIDEO, SUBMISSION)."""
    out = set()
    for p in PATH_RE.findall(text):
        if p in docs:
            out.add(docs[p])
    for n in ADR_RE.findall(text):
        for rel, slug in docs.items():
            if re.search(rf"docs/adr/0*{int(n):04d}-", rel):
                out.add(slug)
    for stem in set(re.findall(r"\b([A-Z][A-Z_]{3,})(?:\.md)?\b", text)):
        for rel, slug in docs.items():
            if os.path.splitext(os.path.basename(rel))[0] == stem:
                out.add(slug)
    return out


def rd(rel):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def clean(text):
    """Drop network addresses and key-shaped strings before anything goes in the store."""
    text = SECRET_RE.sub("[removed]", text)
    text = ADDR_RE.sub("[address removed]", text)
    return PERSON_RE.sub("the builder", text)


def s(kind, name):
    return PREFIX + name if kind == "dataset" else f"{PREFIX}{kind}-{name}"


def md_plain(line):
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    line = re.sub(r"(?<![\w])_+|_+(?![\w])", "", line)
    return re.sub(r"[*`>#]+", "", line).strip()


def doc_summary(text, lines=8):
    """First prose lines of a markdown doc (no headings, tables, code or frontmatter)."""
    out, fence = [], False
    body = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    for raw in body.splitlines():
        if raw.strip().startswith("```"):
            fence = not fence
            continue
        t = raw.strip()
        if fence or not t or t.startswith(("#", "|", "---", "<", "![")):
            if out and not t:
                out.append("")
            continue
        t = md_plain(re.sub(r"^[-*]\s+|^\d+\.\s+", "", t))
        if META_RE.match(t) and len(t) < 160:
            continue
        out.append(t)
        if sum(1 for x in out if x) >= lines:
            break
    return "\n".join(out).strip()


def first_title(text, fallback):
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return md_plain(m.group(1)) if m else fallback


def one_line(text, n=180):
    """First real sentence: at least 50 characters, not a date or status line."""
    t = " ".join(text.split())
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", t) if x.strip()]
    pick = next((x for x in sents if len(x) >= 50 and not META_RE.match(x)), sents[0] if sents else t)
    pick = re.sub(r"^Context:\s*", "", pick)
    return pick if len(pick) <= n else pick[:n - 1].rsplit(" ", 1)[0] + "..."


def gbrain_body(slug):
    """Read the dataset page from gbrain when the CLI is there (read only). Empty string when it is not."""
    exe = os.path.expanduser("~/.bun/bin/gbrain")
    if not os.path.exists(exe):
        return ""
    try:
        r = subprocess.run([exe, "get", slug], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return ""
    return re.sub(r"\A---\n.*?\n---\n", "", r.stdout, flags=re.S).strip() if r.returncode == 0 else ""


class KB:
    def __init__(self):
        self.nodes, self.edges = {}, {}

    def node(self, slug, typ, title, summary, body, path):
        self.nodes[slug] = dict(slug=slug, type=typ, title=title, summary=clean(one_line(summary or title)),
                                body=clean(body), repo_path=path)

    def edge(self, src, dst, typ, source):
        if src != dst:
            self.edges.setdefault((src, dst, typ), source)


# ---------- build ----------

def file_map():
    """repo path (or path prefix) -> dataset slug."""
    m = {}
    for name, (_, _, files, _, _) in DATASETS.items():
        for f in files:
            m[f] = s("dataset", name)
    return m


def match_path(p, fmap):
    p = p.lstrip("./")
    if p in fmap:
        return fmap[p]
    if p.startswith("data/ercot-dam-"):
        return s("dataset", "ercot-live-feeds")
    for f, slug in fmap.items():
        if f.endswith("/") and p.startswith(f):
            return slug
        if "." not in os.path.basename(f) and p.startswith(f + "/"):
            return slug
    return None


def add_datasets(kb, prev):
    for name, (title, summary, files, _, doc) in DATASETS.items():
        slug = s("dataset", name)
        body = gbrain_body(slug) or prev.get(slug) or ""
        if not body:
            body = f"{summary}\n\nFiles: " + ", ".join(files) + (f"\nDocumented in {doc}." if doc else "")
        kb.node(slug, "dataset", title, summary, body, files[0])
        if doc:
            kb.edge(s("doc", doc_key(doc)), slug, "describes", "dataset definition in store/kb.py")


def doc_key(rel):
    return re.sub(r"[^a-z0-9]+", "-", os.path.splitext(rel)[0].lower()).strip("-")


def page_files(html_rel):
    """Data files a page reads: string literals in the page and in the local js files it loads."""
    text = rd(html_rel)
    for js in re.findall(r"""<script[^>]+src=["']([\w./-]+\.js)["']""", text):
        if js != "shell.js" and not js.startswith("http"):
            text += rd(os.path.normpath(os.path.join("web", js)))
    found = set()
    for m in DATA_RE.finditer(text):
        p = m.group(1)
        rel = p if p.startswith(("web/", "data/", "brain/", "house/", "panel/", "out/")) else p
        start = m.start()
        # "data/x.json" without ../ inside web/ means web/data/x.json
        if p.startswith("data/") and text[max(0, start - 3):start] != "../":
            rel = "web/" + p
        found.add(rel)
    return text, sorted(found)


def add_pages(kb, fmap, tours):
    pages = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "web", "*.html"))):
        rel = os.path.relpath(path, ROOT)
        name = os.path.splitext(os.path.basename(rel))[0]
        text, files = page_files(rel)
        raw = rd(rel)
        title = re.sub(r"\s+", " ", (re.search(r"<title>([^<]*)", raw) or [None, name])[1]).strip()
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", raw, re.S)
        question = re.sub(r"<[^>]+>|\s+", " ", h1.group(1)).strip() if h1 else title
        in_tours = [t["label"] for t in tours if any(st["page"].split("#")[0] == os.path.basename(rel) for st in t["stops"])]
        body = (f"Page {rel}. Question it answers: {question}\nData files it reads: "
                + (", ".join(files) or "none (static or live API)")
                + "\nPersona tours it is in: " + (", ".join(in_tours) or "none"))
        slug = s("page", name)
        kb.node(slug, "page", title, question, body, rel)
        pages[os.path.basename(rel)] = (slug, text, files)
        for f in files:
            ds = match_path(f, fmap)
            if ds:
                kb.edge(slug, ds, "reads", f)
                kb.edge(ds, slug, "feeds", f)
    return pages


def add_docs(kb, fmap, pages):
    for rel in DOCS:
        text = rd(rel)
        if not text:
            continue
        slug = s("doc", doc_key(rel))
        heads = [md_plain(h) for h in re.findall(r"^#{2,3}\s+(.+)$", text, re.M)][:30]
        summary = doc_summary(text)
        body = f"Doc {rel}.\n{summary}\n\nSections: " + "; ".join(heads) + "\n\n" + text[:20000]
        kb.node(slug, "doc", first_title(text, os.path.basename(rel)), summary, body, rel)
        for line in text.splitlines():
            has_num = bool(NUM_RE.search(PATH_RE.sub("", line)))
            for p in paths_in(line):
                ds = match_path(p, fmap)
                if ds:
                    kb.edge(slug, ds, "cites_number" if has_num else "describes", p)
            for pg in set(re.findall(r"\b([\w-]+\.html)\b", line)):
                if pg in pages:
                    kb.edge(slug, pages[pg][0], "describes", pg)
    docs = {n["repo_path"]: n["slug"] for n in kb.nodes.values() if n["type"] == "doc"}
    for rel, slug in docs.items():
        for other in doc_refs(rd(rel), docs):
            kb.edge(slug, other, "references", "doc path, ADR number or doc name in the text")


def git_fix(num):
    try:
        r = subprocess.run(["git", "-C", ROOT, "log", "--all", "-E", f"--grep=#{num}([^0-9]|$)", "--format=%h %s", "-n", "1"],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def add_gaps(kb, fmap, pages):
    g = json.loads(rd("web/data/gaps.json") or "{}")
    docs = {n["repo_path"]: n["slug"] for n in kb.nodes.values() if n["type"] == "doc"}
    for i in g.get("issues", []):
        if not i["title"].startswith("Gap:"):
            continue
        slug = s("gap", str(i["number"]))
        text = i["title"] + "\n" + (i.get("body") or "")
        fix = git_fix(i["number"]) if i["state"] == "closed" else ""
        body = (f"GitHub issue #{i['number']}, {i['state']}" + (f", closed {i['closed']}" if i.get("closed") else "")
                + f".\n{text}" + (f"\nFixed by commit: {fix}" if fix else ""))
        kb.node(slug, "gap", f"#{i['number']} {i['title'][5:].strip()}", i["title"][5:].strip(), body, "docs/GAPS.md")
        for p in paths_in(text):
            ds = match_path(p, fmap)
            if ds:
                kb.edge(slug, ds, "affects", p)
        for d in doc_refs(text, docs):
            kb.edge(slug, d, "affects", "doc named in the issue")
        named = set(re.findall(r"\b([\w-]+\.html)\b", text))
        named |= {w + ".html" for w in re.findall(r"\b([a-z]+) (?:page|map|view)\b", text)}
        named |= {"story.html"} if re.search(r"\bstory\b", text) else set()
        for pg in named:
            if pg in pages:
                kb.edge(slug, pages[pg][0], "affects", pg)
        if fix:
            kb.edge(slug, "commit:" + fix.split()[0], "fixed_by", fix)


def add_personas(kb, tours, pages):
    for t in tours:
        slug = s("persona", t["id"])
        stops = "\n".join(f"- {st['page']}: {st['headline']} ({st['number']['value']} {st['number']['text']}, "
                          f"source {st['number']['source']})" for st in t["stops"])
        kb.node(slug, "persona", t["label"], t["story"], f"{t['story']}\nTour stops:\n{stops}", "web/data/tours.json")
        for st in t["stops"]:
            pg = st["page"].split("#")[0]
            if pg in pages:
                kb.edge(slug, pages[pg][0], "tours", st["page"])


def add_zips(kb, pages):
    funnel = json.loads(rd("data/funnel.json") or "{}").get("rows", [])
    deeds = {r["zip"]: r for r in json.loads(rd("data/deeds_by_zip.json") or "{}").get("rows", [])}
    base = {}
    try:
        con = sqlite3.connect(DB)
        base = dict(con.execute("SELECT zip, count(*) FROM permits WHERE is_base=1 AND issue_date >= '2026' GROUP BY zip"))
        con.close()
    except sqlite3.Error:
        pass
    offer = {"energy_and_backup": "Base can sell energy and backup", "backup_only": "Base sells backup only",
             "mixed": "Base offer is mixed across the zip", "not_served": "Base does not serve it"}
    blobs = {}
    for name, (slug, text, files) in pages.items():
        blob = text
        for f in files:
            full = os.path.join(ROOT, f)
            if os.path.isfile(full) and os.path.getsize(full) < 3_000_000 and not f.endswith((".gz", "kb_graph.json")):
                blob += rd(f)
        blobs[slug] = blob
    for r in funnel:
        z = r["zip"]
        d = deeds.get(z)
        facts = [f"Zip {z}, {r.get('city')}, {r.get('county')} County.",
                 f"Who sells power: utility (TDU) {r.get('tdu')}; {offer.get(r.get('status'), r.get('status'))} "
                 f"(confidence {r.get('confidence')}).",
                 f"Easy-fit homes (estimate): {r.get('star', 0):,} (data/funnel.json).",
                 f"Base permits issued in 2026 in this zip: {base.get(z, 0)} (fleet.db permits, Austin feed only).",
                 (f"Deed turnover: {d['share_sold_last_2y']:.0%} of {d['parcels']:,} parcels changed hands in the last "
                  f"2 years; median {d['median_years_since_deed']} years since the last deed (data/deeds_by_zip.json)."
                  if d else "Deed turnover: no county deed data for this zip."),
                 f"Assisted-onboarding priority: {r.get('assisted_priority')} ({r.get('assisted_why', '')})."]
        slug = s("zip", z)
        kb.node(slug, "zip", f"{z} {r.get('city')}", f"{r.get('city')}: {r.get('tdu')}, {r.get('star', 0):,} easy-fit homes, "
                f"{base.get(z, 0)} Base permits in 2026", "\n".join(facts), "data/funnel.json")
        for pslug, blob in blobs.items():
            if re.search(rf"(?<!\d){z}(?!\d)", blob):
                kb.edge(slug, pslug, "appears_in", "zip string in page or its data")


def add_signals(kb):
    sys.path.insert(0, os.path.join(ROOT, "store"))
    try:
        import signals as sig
        rules = sig.RULES
    except Exception:
        return
    watch = [("permits", "energy-permit-mirror"), ("Base permits", "base-rollout"), ("backup permits", "storms"),
             ("snapshot", "ercot-live-feeds"), ("Weather Service", "storms"), ("NWS", "ercot-live-feeds")]
    for r in rules:
        slug = s("signal", r["name"])
        text = f"{r['rule']} Source: {r['source']}"
        kb.node(slug, "signal", r["name"].replace("_", " "), r["rule"],
                f"Rule {r['name']}: {r['rule']}\nThreshold: {r['threshold']}\nSource: {r['source']}\nDefined in store/signals.py.",
                "store/signals.py")
        for key, ds in watch:
            if key in text:
                kb.edge(slug, s("dataset", ds), "watches", key)
        kb.edge(slug, s("dataset", "signals"), "writes", "web/data/signals.json")


def add_jobs(kb, pages):
    inst = rd("collect/install_mac.sh")
    sched = {m.group(1): m.group(2) for m in re.finditer(r"^#\s+(\S+\.sh)\s+(.+)$", inst, re.M)}
    for name, script in re.findall(r"^mk (\w+) (\S+\.sh)", inst, re.M):
        text = rd(f"collect/{script}")
        slug = s("job", name)
        kb.node(slug, "job", f"com.basefleet.{name}", f"launchd job {script}, {sched.get(script, 'scheduled')}",
                f"launchd job com.basefleet.{name} runs collect/{script}, {sched.get(script, '')}.\n"
                + "\n".join(l for l in text.splitlines() if l.strip() and not l.startswith("#"))[:3000],
                f"collect/{script}")
        for ds, (_, _, _, producers, _) in DATASETS.items():
            if any(p in text for p in producers):
                kb.edge(slug, s("dataset", ds), "refreshes", next(p for p in producers if p in text))
    for name, port, args in re.findall(r"^svc (\w+) (\d+) (.+)$", inst, re.M):
        slug = s("job", name)
        kb.node(slug, "job", f"com.basefleet.{name}", f"launchd service on port {port}: python3 {args}",
                f"launchd service com.basefleet.{name}, kept alive, python3 {args}, port {port}.", "collect/install_mac.sh")
        for pg, (pslug, text, _) in pages.items():
            if port in text:
                kb.edge(slug, pslug, "serves", f"port {port}")


def build():
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    prev = dict(con.execute("SELECT slug, body FROM kb_nodes WHERE type='dataset'"))
    kb = KB()
    tours = json.loads(rd("web/data/tours.json") or "{}").get("tours", [])
    fmap = file_map()
    add_datasets(kb, prev)
    pages = add_pages(kb, fmap, tours)
    add_docs(kb, fmap, pages)
    add_gaps(kb, fmap, pages)
    add_personas(kb, tours, pages)
    add_zips(kb, pages)
    add_signals(kb)
    add_jobs(kb, pages)
    idx = s("dataset", "index")
    kb.node(idx, "hub", "Base Brain: knowledge index",
            "Start here: the story, the two submission docs and the main datasets.",
            "Hub of Base Brain, the app knowledge base. Story spine: story.html, docs/SUBMISSION.md, docs/SUBMISSION_FORM.md, "
            "and the datasets " + ", ".join(SPINE_DATASETS) + ".", "docs/KNOWLEDGE_BASE.md")
    for t in (s("page", "story"), s("doc", "docs-submission"), s("doc", "docs-submission-form"),
              *[s("dataset", d) for d in SPINE_DATASETS]):
        kb.edge(idx, t, "spine", "store/kb.py SPINE")
    # Doc describes the doc-level dataset link only when that doc exists.
    kb.edges = {k: v for k, v in kb.edges.items() if (k[0] in kb.nodes) and (k[1] in kb.nodes or k[1].startswith("commit:"))}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    with con:
        # Replace only the node types this file owns; other writers (store/faq.py, store/learn.py) keep their rows.
        mine = ",".join("?" * len(OWN_TYPES))
        con.execute(f"DELETE FROM kb_edges WHERE src IN (SELECT slug FROM kb_nodes WHERE type IN ({mine}))", OWN_TYPES)
        con.execute(f"DELETE FROM kb_nodes WHERE type IN ({mine})", OWN_TYPES)
        con.executemany("INSERT OR REPLACE INTO kb_nodes VALUES (?,?,?,?,?,?,?)",
                        [(n["slug"], n["type"], n["title"], n["summary"], n["body"], n["repo_path"], now) for n in kb.nodes.values()])
        con.executemany("INSERT OR REPLACE INTO kb_edges VALUES (?,?,?,?)", [(a, b, t, src) for (a, b, t), src in sorted(kb.edges.items())])
    con.close()
    export(kb, now)
    return kb


def export(kb, now):
    fixes = {}
    for (a, b, t), src in kb.edges.items():
        if t == "fixed_by":
            fixes[a] = src
    nodes = [dict(slug=n["slug"], short=n["slug"][len(PREFIX):], type=n["type"], title=n["title"], summary=n["summary"],
                  path=n["repo_path"], **({"fixed_by": fixes[n["slug"]]} if n["slug"] in fixes else {}))
             for n in sorted(kb.nodes.values(), key=lambda n: (n["type"], n["slug"]))]
    edges = [dict(src=a, dst=b, type=t) for (a, b, t) in sorted(kb.edges) if not b.startswith("commit:")]
    spine = [b for (a, b, t) in sorted(kb.edges) if t == "spine"] + [s("dataset", "index")]
    data = {"built_at": now, "source": "data/fleet.db kb_nodes, kb_edges (store/kb.py)", "prefix": PREFIX,
            "spine": spine, "nodes": nodes, "edges": edges}
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)


# ---------- retrieval ----------

def toks(text):
    return [t for t in re.findall(r"[a-z0-9$%]+(?:\.\d+)?", text.lower()) if t not in STOP and len(t) > 1]


def kb_search(question, k=5, db=DB):
    """Token overlap (idf weighted; title x3, summary x2, body x1) plus one-hop neighbours of each hit.
    Returns [{slug, type, title, summary, text, path, score, via, links:[{dir, type, slug, title}]}]."""
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT slug, type, title, summary, body, repo_path FROM kb_nodes").fetchall()
        edges = con.execute("SELECT src, dst, type FROM kb_edges").fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    q = set(toks(question))
    if not q or not rows:
        return []
    docs = {r[0]: (set(toks(r[2])), set(toks(r[3])), set(toks(r[4]))) for r in rows}
    df = {t: sum(1 for d in docs.values() if t in d[0] | d[1] | d[2]) for t in q}
    n = len(rows)
    idf = {t: math.log(1 + n / (1 + df[t])) for t in q}
    score = {}
    for slug, (ti, su, bo) in docs.items():
        sc = sum(idf[t] * (3 * (t in ti) + 2 * (t in su) + (t in bo)) for t in q)
        if sc > 0:
            score[slug] = sc
    info = {r[0]: r for r in rows}
    links = {}
    for a, b, t in edges:
        links.setdefault(a, []).append(("out", t, b))
        links.setdefault(b, []).append(("in", t, a))
    top = sorted(score, key=lambda x: -score[x])[:k]
    out, seen = [], set()

    def pack(slug, sc, via):
        r = info[slug]
        return dict(slug=slug, type=r[1], title=r[2], summary=r[3], text=r[4][:1500], path=r[5], score=round(sc, 2), via=via,
                    links=[dict(dir=d, type=t, slug=o, title=info[o][2] if o in info else o)
                           for d, t, o in links.get(slug, [])[:25]])

    for slug in top:
        out.append(pack(slug, score[slug], None))
        seen.add(slug)
    extra = []
    for slug in top:
        for d, t, o in links.get(slug, []):
            if o in info and o not in seen:
                seen.add(o)
                extra.append((score.get(o, 0) + score[slug] * 0.3, o, slug))
    for sc, o, via in sorted(extra, reverse=True)[:k]:
        out.append(pack(o, sc, via))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    if a.search:
        for r in kb_search(a.search, a.k):
            print(f"{r['score']:6.2f} {r['type']:8} {r['slug'][len(PREFIX):]:40} {r['title'][:60]}" + (f"  (via {r['via'][len(PREFIX):]})" if r["via"] else ""))
        return
    kb = build()
    by = {}
    for n in kb.nodes.values():
        by[n["type"]] = by.get(n["type"], 0) + 1
    eb = {}
    for (_, _, t) in kb.edges:
        eb[t] = eb.get(t, 0) + 1
    print(f"kb: {len(kb.nodes)} nodes {by}; {len(kb.edges)} edges {eb}; wrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
