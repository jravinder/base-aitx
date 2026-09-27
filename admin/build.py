"""Build web/data/admin.json for web/admin.html. Stdlib only.

Every value comes from a file in this repo, from git, or from `gh` (repo jravinder/base-fleet-archive).
Judgment values (track strength, agent roles) come from admin/tracks.json and admin/agents.json
and are labelled "judgment" in the output.

python3 admin/build.py
"""

import glob
import gzip
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "web", "data", "admin.json")
REPO = "jravinder/base-fleet-archive"  # issues and gaps live in the archive repo
CT = timezone(timedelta(hours=-5))  # CDT on Sep 27 2026
DEADLINE = datetime(2026, 9, 27, 11, 0, tzinfo=CT)
NOW = datetime.now(timezone.utc)


def p(*a):
    return os.path.join(ROOT, *a)


def load(path):
    try:
        with open(p(path)) as f:
            return json.load(f)
    except Exception:
        return None


def run(cmd):
    try:
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""


def mtime(path):
    try:
        return datetime.fromtimestamp(os.path.getmtime(p(path)), timezone.utc)
    except OSError:
        return None


def iso(dt):
    return dt.astimezone(CT).strftime("%Y-%m-%dT%H:%M") if dt else None


def day(s):
    """'2026-09-26' -> end of that day in CT (a date-only stamp is treated as fetched that day)."""
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").replace(hour=12, tzinfo=CT)
    except Exception:
        return None


def csv_rows(path):
    try:
        with open(p(path)) as f:
            return sum(1 for _ in f) - 1
    except OSError:
        return None


# ---------- 1. Data feeds ----------

def log_lines():
    try:
        return open(p("data/live/collect.log")).read().splitlines()
    except OSError:
        return []


LOG = log_lines()


def log_last(key):
    """Last collect.log line for a feed key: (stamp, ok|FAIL) or None."""
    for line in reversed(LOG):
        parts = line.split()
        if len(parts) >= 3 and parts[2] == key:
            return parts[0], parts[1]
    return None


def log_stamp(s):
    for fmt in ("%Y%m%dT%H%MZ", "%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt)
            return d.replace(tzinfo=timezone.utc) if fmt == "%Y%m%dT%H%MZ" else d.replace(hour=12, tzinfo=CT)
        except ValueError:
            pass
    return None


def status(job, cadence_h, fetched, last_log):
    if job == "one-time":
        return "manual"
    if last_log and last_log[1] == "FAIL":
        return "fail"
    if fetched is None:
        return "stale"
    return "stale" if (NOW - fetched).total_seconds() > 2 * cadence_h * 3600 else "ok"


def ercot_live(feed):
    files = sorted(glob.glob(p("data/live/ercot", feed, "*.json.gz")))
    last = log_last(feed)
    fetched = log_stamp(last[0]) if last and last[1] == "ok" else None
    if files and not fetched:
        fetched = datetime.fromtimestamp(os.path.getmtime(files[-1]), timezone.utc)
    return fetched, len(files), last


def feeds():
    rows = []

    def add(name, url, script, cadence, cadence_h, job, fetched, fetched_from, count, count_label, last_log=None, note=""):
        rows.append({
            "name": name, "url": url, "script": script, "cadence": cadence, "job": job,
            "last_fetched": iso(fetched), "fetched_from": fetched_from,
            "age_h": round((NOW - fetched).total_seconds() / 3600, 1) if fetched else None,
            "rows": count, "rows_label": count_label,
            "last_log": " ".join(last_log) if last_log else None,
            "status": status(job, cadence_h, fetched, last_log), "note": note,
        })

    dash = "https://www.ercot.com/api/1/services/read/dashboards/{}.json"
    for feed, cad, h in [("system-wide-prices", "hourly at :07", 1), ("supply-demand", "hourly at :07", 1),
                         ("fuel-mix", "hourly at :07", 1), ("daily-prc", "daily at 12 UTC", 24)]:
        fetched, n, last = ercot_live(feed)
        add(f"ERCOT {feed}", dash.format(feed), "collect/ercot_feeds.sh", cad, h, "com.basefleet.ercot",
            fetched, "data/live/collect.log", n, "snapshots in data/live/ercot/" + feed, last,
            "" if n else "No snapshot yet. Collector installed today; this feed runs once a day at 12 UTC.")

    snaps = sorted(glob.glob(p("data/ercot/*.json")))
    newest = max((os.path.getmtime(f) for f in snaps), default=None)
    add("ERCOT dashboards, full set", "https://www.ercot.com/gridmktinfo/dashboards", "grid/ercot_system.js",
        "one pull", None, "one-time", datetime.fromtimestamp(newest, timezone.utc) if newest else None,
        "file mtime", len({os.path.basename(f).rsplit("-2", 1)[0] for f in snaps}), "feeds in data/ercot/")

    dam = sorted(glob.glob(p("data/ercot-dam-*.json")))
    add("ERCOT DAM prices, daily snapshots", "https://www.ercot.com/api/1/services/read/dashboards/system-wide-prices.json",
        "grid/ercot_live.js", "one pull per day", None, "one-time",
        max((mtime(os.path.relpath(f, ROOT)) for f in dam), default=None), "file mtime", len(dam), "days in data/ercot-dam-*.json")

    add("ERCOT DAM archive (report 13060)", "https://www.ercot.com/misapp/GetReports.do?reportTypeId=13060",
        "grid/ercot_archive.py", "annual archive", None, "one-time", mtime("data/ercot_dam_hourly_2025_2026.csv"),
        "file mtime", csv_rows("data/ercot_dam_hourly_2025_2026.csv"), "hours")

    add("ERCOT load history", "https://www.ercot.com/gridinfo/load/load_hist", "none in repo (see grid/LOAD.md)",
        "annual", None, "one-time", mtime("data/ercot_load_hourly_2024_2026.csv"), "file mtime",
        csv_rows("data/ercot_load_hourly_2024_2026.csv"), "hours")

    pz = load("data/permits_by_zip.json") or {}
    last = log_last("house.permits_by_zip")
    add("Austin permits by zip", pz.get("source"), "house/permits_by_zip.py", "daily 06:15", 24, "com.basefleet.daily",
        log_stamp(last[0]) if last and last[1] == "ok" else mtime("data/permits_by_zip.json"),
        "data/live/collect.log", len(pz.get("rows", [])), "zips", last)

    mk = load("data/market.json") or {}
    last = log_last("house.market")
    fetched = log_stamp(last[0]) if last and last[1] == "ok" else day(mk.get("fetched_at", ""))
    add("Austin permits, Base market", "https://data.austintexas.gov/resource/3syk-w9eu.json", "house/market.py",
        "daily 06:15", 24, "com.basefleet.daily", fetched, "data/live/collect.log",
        (mk.get("base_totals") or {}).get("total"), "Base permits 2026", last)

    dm = load("data/demographics.json") or {}
    last = log_last("demographics")
    add("ACS demographics", "https://api.censusreporter.org", "house/demographics.py", "monthly, 2nd 06:30", 24 * 31,
        "com.basefleet.monthly", day(dm.get("fetched_at", "")), "fetched_at", len(dm.get("rows", [])), "zips", last,
        dm.get("vintage", ""))

    pt = load("data/ptc_tdu.json") or {}
    add("Power to Choose, utility per zip", "http://api.powertochoose.org/api/PowerToChoose/plans", "house/territory.py",
        "one pull", None, "one-time", day(pt.get("fetched", "")), "fetched", len(pt.get("zips", {})), "zips")

    zc = load("data/zcta.geojson") or {}
    add("ZCTA boundaries", "https://tigerweb.geo.census.gov (2020 ZCTA layer)", "none in repo (see docs/STAR_AREAS.md)",
        "static", None, "one-time", mtime("data/zcta.geojson"), "file mtime", len(zc.get("features", [])), "zip polygons")

    pb = load("house/public_buildings.json") or {}
    add("Public buildings", "data.austintexas.gov tc36-hn4j, 8dff-2vkt; data.texas.gov hzek-udky",
        "house/public_buildings.py", "one pull", None, "one-time", mtime("house/public_buildings.json"), "file mtime",
        pb.get("count_total"), "sites")

    fd = load("data/feeders.json") or {}
    zips = fd.get("zips", {})
    zl = zips.values() if isinstance(zips, dict) else zips
    fsrc = fd.get("source", "")
    m = re.search(r"fetched (\d{4}-\d\d-\d\d)", fsrc)
    add("OSM substations", "https://overpass-api.de (OpenStreetMap, ODbL)", "house/feeders.py", "one pull", None,
        "one-time", day(m.group(1)) if m else mtime("data/feeders.json"), "source field" if m else "file mtime",
        sum(len(z.get("substations", [])) for z in zl), "substations")

    ou = load("data/outages_snapshot.json") or {}
    add("Outage snapshot (Kubra)", "https://kubra.io/stormcenter (Austin Energy, Oncor)", "none in repo", "live only, no history",
        None, "one-time", mtime("data/outages_snapshot.json"), "file mtime", len(ou.get("snapshots", [])), "snapshots")

    corpus = sorted(glob.glob(p("faq/corpus/*.md")))
    add("Base public pages (FAQ corpus)", "https://basepowercompany.com", "manual copy (see faq/FAQ.md)", "one pull",
        None, "one-time", max((datetime.fromtimestamp(os.path.getmtime(f), timezone.utc) for f in corpus), default=None),
        "file mtime", len(corpus), "pages")

    add("WCAD appraisal", "https://search.wcad.org", "house/wcad.js via house/appraisal.py", "on demand, per address", None,
        "one-time", None, "not stored", None, "local only, output not stored", note="Manual, local only. Owner names stripped.")
    return rows


# ---------- 2. Pages ----------

def gh_issues():
    out = run(["gh", "issue", "list", "-R", REPO, "--state", "all", "--limit", "300",
               "--json", "number,title,state,author,body,createdAt,closedAt"])
    cache = p("admin", ".gh_issues.json")
    try:
        issues = json.loads(out)
        with open(cache, "w") as f:
            json.dump(issues, f)
        return issues
    except Exception:  # gh not authed (for example under launchd): use the last good pull
        return load("admin/.gh_issues.json") or []


ISSUES = gh_issues()


def is_gap(i):
    return i["title"].startswith("Gap:")


GAPS_OUT = os.path.join(ROOT, "web", "data", "gaps.json")
HUNT = 54  # the umbrella issue for the gap hunt


def gaps_json():
    rows = [{"number": i["number"], "title": i["title"], "state": i["state"].lower(),
             "body": (i.get("body") or "")[:600], "closed": (i.get("closedAt") or "")[:10] or None,
             "hunt": i["number"] == HUNT}
            for i in ISSUES if is_gap(i) or i["number"] == HUNT]
    rows.sort(key=lambda r: -r["number"])
    gaps = [r for r in rows if not r["hunt"]]
    data = {"built_at": iso(NOW), "source": "gh issue list -R " + REPO + " (titles that start with 'Gap:', and #54)",
            "found": len(gaps), "fixed": sum(1 for r in gaps if r["state"] == "closed"),
            "open": [r["number"] for r in gaps if r["state"] == "open"], "issues": rows}
    with open(GAPS_OUT, "w") as f:
        json.dump(data, f, indent=1)
    return data


def text(path):
    try:
        return open(p(path)).read()
    except OSError:
        return ""


def strip(h):
    import html as H
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h))).strip()


def pages():
    sub = text("docs/SUBMISSION.md")
    story = text("web/story.html")
    beats = defaultdict(list)
    for li in story.split('<li class="beat">')[1:]:
        li = li.split("</ol>")[0]
        n = re.search(r'<div class="n">(\d+)</div>', li)
        t = re.search(r'<div class="t">([\s\S]*?)</div>', li)
        for pg in sorted(set(re.findall(r"([a-z]+)\.html", li))):
            beats[pg].append(f"{n.group(1)}. {strip(t.group(1))}" if n and t else "")
    shots = sorted(os.path.basename(f) for f in glob.glob(p("docs/shots/*.png")))
    rows = []
    for f in sorted(glob.glob(p("web/*.html"))):
        stem = os.path.basename(f)[:-5]
        rel = f"web/{stem}.html"
        s = open(f).read()
        title = re.search(r"<title>([^<]*)", s)
        m = re.search(r"`/?web/" + stem + r"\.html`[^:\n]*:\s*([^\n]+)", sub)
        purpose, psrc = None, None
        if m:
            first = m.group(1).split(". ")[0].rstrip(".")
            purpose, psrc = (first if len(first) >= 12 else m.group(1).rstrip(".")), "docs/SUBMISSION.md"
        md = re.search(r'<meta name="description" content="([^"]+)"', s)
        if md:
            purpose, psrc = md.group(1), rel + " meta description"
        else:
            body = re.sub(r"<(script|style)[\s\S]*?</\1>", "", s[s.find("<body"):])
            for para in re.findall(r"<p>([\s\S]*?)</p>", body):
                t = strip(para)
                if len(t) > 20:
                    purpose, psrc = t.split(". ")[0].rstrip("."), rel + " first paragraph"
                    break
            if not purpose:
                h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", body)
                purpose, psrc = (strip(h1.group(1)), rel + " h1") if h1 else (None, None)
        if re.search(r'fetch\("/state"|fetch\(`/node', s):
            runs = "local only (python3 -m sim.server)"
        elif "localhost:11434" in s:
            runs = "static; free text needs local Ollama"
        else:
            runs = "static"
        log = run(["git", "log", "-1", "--format=%ad|%an|%(trailers:key=Claude-Session,valueonly)", "--date=format:%Y-%m-%d %H:%M", "--", rel]).strip()
        parts = (log.split("|") + ["", "", ""])[:3] if log else [None, None, ""]
        author = {"Builder": "Grokbot"}.get(parts[1], "Ravi's account" if parts[1] else parts[1])
        if "Import Codex" in run(["git", "log", "-1", "--format=%s", "--", rel]):
            author = "Codex"
        elif parts[2].strip():
            author = "Claude session"
        shot = [x for x in shots if x == stem + ".png"] + [x for x in shots if x.startswith(stem + "-")]
        gaps = [{"n": i["number"], "title": i["title"]} for i in ISSUES
                if i["state"] == "OPEN" and is_gap(i) and re.search(r"\b" + stem + r"\.html\b", (i.get("body") or "") + i["title"])]
        rows.append({
            "file": stem + ".html", "title": title.group(1).strip() if title else stem,
            "purpose": purpose[:1].upper() + purpose[1:] if purpose else None, "purpose_from": psrc,
            "beats": beats.get(stem, []), "runs": runs,
            "last_commit": parts[0] or "uncommitted", "author": author or "uncommitted",
            "shot": ("../docs/shots/" + shot[0]) if shot else None, "shots": len(shot), "gaps": gaps,
        })
    return rows


# ---------- 3. Tracks ----------

def dig(ref):
    path, _, key = ref.partition(":")
    d = load(path)
    for k in key.split("."):
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return None
    return d


def tracks():
    t = load("admin/tracks.json") or {"tracks": []}
    sub = text("docs/SUBMISSION.md")
    entries = defaultdict(list)
    for letter, block in re.findall(r"^## ([A-Z])\. [^\n]*\n([\s\S]*?)(?=^## |\Z)", sub, re.M):
        m = re.search(r"^Tracks: ([^\n]+)", block, re.M)
        if m:
            for name in m.group(1).rstrip(".").split(","):
                entries[name.strip()].append(letter)
    by_n = {i["number"]: i for i in ISSUES}
    out = []
    for tr in t["tracks"]:
        ev = []
        for e in tr.get("evidence", []):
            v = e.get("value")
            src = e.get("source", "")
            if e.get("from"):
                live = dig(e["from"])
                if live is not None:
                    if isinstance(live, float):
                        live = f"${live:,.0f} a year" if "total" in e["from"] else live
                    v = f"{live} of {dig(e['of'])}" if e.get("of") else str(live)
                    src = e["from"].split(":")[0]
            ev.append({"page": e["page"], "label": e["label"], "value": v, "source": src})
        iss = [{"n": n, "title": by_n[n]["title"], "gap": is_gap(by_n[n])}
               for n in tr.get("issues", []) if n in by_n and by_n[n]["state"] == "OPEN"]
        out.append({"name": tr["name"], "entry": entries.get(tr["name"], []), "evidence": ev,
                    "weak_spot": tr.get("weak_spot"), "open_issues": iss,
                    "strength": tr.get("strength"), "strength_is": "judgment"})
    return out


# ---------- 4. Agents ----------

def agents():
    raw = run(["git", "log", "--name-only", "--date=format:%Y-%m-%d %H:%M",
               "--format=@@%H|%an|%ae|%ad|%P|%(trailers:key=Claude-Session,valueonly,separator=%x20)|%s"])
    stats = defaultdict(lambda: {"commits": 0, "files": set(), "folders": Counter(), "last": None, "refs": set()})
    key = None
    for line in raw.splitlines():
        if line.startswith("@@"):
            h, an, ae, ad, parents, trailer, subj = line[2:].split("|", 6)
            if len(parents.split()) > 1:
                key = "merges"
            elif trailer.strip():
                key = "claude"
            elif an == "Builder":
                key = "builder"
            elif an == "depth":
                key = "depth"
            elif ae.endswith("users.noreply.github.com"):
                key = "web"
            else:
                key = "ravi"
            s = stats[key]
            s["commits"] += 1
            s["last"] = max(s["last"] or "", ad)
            s["refs"].update(int(n) for n in re.findall(r"#(\d+)", subj))
        elif line.strip() and key:
            stats[key]["files"].add(line.strip())
            stats[key]["folders"][line.strip().split("/")[0] if "/" in line else "(root)"] += 1
    meta = (load("admin/agents.json") or {}).get("agents", {})
    authors = Counter(i["author"]["login"] for i in ISSUES)
    gap_nums = {i["number"] for i in ISSUES if is_gap(i)}
    out = []
    for k in ["claude", "builder", "depth", "web", "ravi", "merges"]:
        s = stats.get(k)
        if not s:
            continue
        m = meta.get(k, {})
        out.append({
            "key": k, "label": m.get("label", k), "role": m.get("role"), "help": m.get("help"),
            "notable": m.get("notable", []), "text_is": "hand-edited, admin/agents.json",
            "commits": s["commits"], "files": len(s["files"]),
            "top_folders": [f"{f} ({n})" for f, n in s["folders"].most_common(3)],
            "last_active": s["last"],
            "gaps_referenced": sorted(s["refs"] & gap_nums),
        })
    return out, dict(authors)


# ---------- 0. Signals ----------

def signals():
    """web/data/signals.json from store/signals.py: latest fired signals and the rule list."""
    s = load("web/data/signals.json")
    if not s:
        return None
    return {"built_at": s.get("built_at"), "fired_now": s.get("fired_now"), "latest": s.get("latest", [])[:12],
            "latest_total": len(s.get("latest", [])),
            "rules": [{k: r.get(k) for k in ("name", "threshold", "rule", "source", "fired_now", "now")} for r in s.get("rules", [])]}


def learning():
    """web/data/learning.json from store/learn.py: member questions, answered share, proposals."""
    d = load("web/data/learning.json")
    if not d:
        return None
    w = d.get("week", {})
    return {"generated": d.get("generated"), "asked": w.get("asked"), "answered": w.get("answered"),
            "by_path": w.get("by_path"), "signal": d.get("signal"),
            "proposals": len(d.get("proposals", [])),
            "pending": sum(1 for p in d.get("proposals", []) if p.get("status") == "proposed"),
            "base_support": len(d.get("base_support", []))}


def main():
    fd = feeds()
    pg = pages()
    ag, issue_authors = agents()
    open_gaps = [{"n": i["number"], "title": i["title"]} for i in ISSUES if i["state"] == "OPEN" and is_gap(i)]
    left = DEADLINE - NOW
    data = {
        "built_at": iso(NOW),
        "sources": "files in repo, git log, gh issue list -R " + REPO,
        "summary": {
            "feeds": dict(Counter(r["status"] for r in fd)),
            "pages": len(pg),
            "open_gaps": open_gaps,
            "gaps_total": sum(1 for i in ISSUES if is_gap(i)),
            "issues_open": sum(1 for i in ISSUES if i["state"] == "OPEN"),
            "deadline": DEADLINE.isoformat(),
            "hours_left": round(left.total_seconds() / 3600, 1),
            "days_left": left.days,
        },
        "signals": signals(),
        "learning": learning(),
        "feeds": fd, "pages": pg, "tracks": tracks(), "agents": ag,
        "issue_authors": issue_authors,
        "commits_total": int(run(["git", "rev-list", "--count", "HEAD"]).strip() or 0),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    g = gaps_json()
    print(f"gaps.json: found {g['found']}, fixed {g['fixed']}, open {g['open']}")
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"admin.json: feeds {data['summary']['feeds']}, pages {len(pg)}, open gaps {len(open_gaps)}, issues {len(ISSUES)}")


if __name__ == "__main__":
    main()
