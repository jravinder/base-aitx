"""Judgments as data: every typed guess the project makes, with a confidence and a route. Stdlib only.

A judgment is one typed value (bool, enum, int) about one subject, plus the confidence of the
method that made it. The route comes from the confidence only, with the thresholds in ROUTES.

Sources:
  permit  category          data/mirror/energy_permits.csv.gz via the permits table (house/mirror.py rules;
                            confidence per rule in RULE_CONFIDENCE below)
  house   guessable fields  house/cohort.json (confidence values written by the cohort builder)
  photo   photo_type        panel/pred_gemini.jsonl, panel/pred_gemma4_flickr.jsonl (the model's own
                            confidence; last row per file when a file ran twice)
  zip     territory_status  data/funnel.json rows (zip confidence HIGH/MEDIUM/LOW -> house/funnel.py CONF_WEIGHT)

  python3 -m store.judgments          refill the judgments table in data/fleet.db and write web/data/judgments.json
store/build.py calls fill() on every build.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DB = os.path.join(ROOT, "data", "fleet.db")
FEED = os.path.join(ROOT, "web", "data", "judgments.json")
COMPARE = os.path.join(ROOT, "data", "live", "judge_compare.json")
sys.path.insert(0, ROOT)

# The routing rule. One place. confidence >= auto -> auto; >= review -> model review; else human.
ROUTES = {"auto": 0.85, "review": 0.70}
# Who the human is, per subject type.
HUMAN = {"permit": "engineer", "house": "member confirm", "photo": "retake", "zip": "engineer"}


def route(confidence):
    if confidence is None or confidence < ROUTES["review"]:
        return "human"
    return "auto" if confidence >= ROUTES["auto"] else "review"


# Permit category rules (house/mirror.py categorize). The mirror does not store the description, so the
# confidence comes from which rule gave the category and whether work_class agrees with it.
ENERGY_AUX = {"battery", "solar", "solar_battery"}
RULE_CONFIDENCE = [
    # (test, confidence, name)
    (lambda c, w: c in ENERGY_AUX and w == "Auxiliary Power", 0.95,
     "strong: work_class Auxiliary Power agrees with a battery or PV keyword"),
    (lambda c, w: c == "panel_upgrade" and w == "Upgrade", 0.92,
     "strong: work_class Upgrade plus an upgrade keyword (first rule in categorize)"),
    (lambda c, w: c in ("generator", "ev_charger", "panel_upgrade") and w == "Auxiliary Power", 0.72,
     "weak: keyword and work_class Auxiliary Power point to different things"),
    (lambda c, w: c in ("battery", "solar_battery", "generator", "ev_charger"), 0.87,
     "keyword: a specific term (battery, Powerwall, generator, EV charger), work_class neutral"),
    (lambda c, w: c == "solar", 0.80,
     "broad keyword: solar via PV or modules plus inverter, work_class not Auxiliary Power"),
    (lambda c, w: c == "panel_upgrade", 0.75,
     "broad regex: upgrade or 200 amp wording, work_class not Upgrade"),
    (lambda c, w: True, 0.40,
     "fallback: no category rule matched (other_electrical)"),
]


def rule_confidence(category, work_class):
    for test, conf, name in RULE_CONFIDENCE:
        if test(category, work_class):
            return conf, name


SCHEMA = """
CREATE TABLE IF NOT EXISTS judgments (subject_type TEXT, subject_id TEXT, field TEXT, value TEXT, value_type TEXT,
  confidence REAL, method TEXT, route TEXT, source TEXT, PRIMARY KEY (subject_type, subject_id, field, method));
CREATE INDEX IF NOT EXISTS judgments_route ON judgments(subject_type, route);
"""


def vtype(field, value):
    if field.startswith("has_"):
        return "bool"
    if field.endswith(("_amps", "_years")) or field == "year_built":
        return "int"
    return "enum"


def text(v):
    if v is None:
        return "unknown"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def permit_rows(con):
    out = []
    for pn, cat, wc in con.execute("SELECT permit_number, category, work_class FROM permits"):
        conf, _ = rule_confidence(cat, wc)
        out.append(("permit", pn, "category", cat, "enum", conf, "rules", route(conf),
                    "data/mirror/energy_permits.csv.gz"))
    return out


def house_rows():
    p = os.path.join(ROOT, "house/cohort.json")
    out = []
    for i, h in enumerate(json.load(open(p)), 1):
        sid = f"{h['zip']}-{i:02d}"  # no street address in the feed
        for g in h.get("guessable", []):
            c = g.get("confidence")
            out.append(("house", sid, g["field"], text(g.get("value")), vtype(g["field"], g.get("value")), c,
                        "rules", route(c), "house/cohort.json"))
        yb = h.get("year_built")
        if isinstance(yb, dict) and yb.get("confidence") is not None:
            out.append(("house", sid, "year_built", text(yb.get("lower_bound")), "int", yb["confidence"],
                        "rules", route(yb["confidence"]), "house/cohort.json"))
    return out


# Used only when a prediction row has no confidence of its own.
PHOTO_METHOD_CONF = {"gemini": 0.85, "gemma4": 0.70}


def photo_rows():
    out = []
    for f, method in (("panel/pred_gemini.jsonl", "gemini"), ("panel/pred_gemma4_flickr.jsonl", "gemma4")):
        last = {}
        for line in open(os.path.join(ROOT, f)):
            if line.strip():
                r = json.loads(line)
                last[r["file"]] = r
        for name, r in last.items():
            c = r.get("confidence")
            c = PHOTO_METHOD_CONF[method] if c is None else float(c)
            out.append(("photo", name, "photo_type", r.get("photo_type") or "unknown", "enum", c, method,
                        route(c), f))
    return out


def zip_rows():
    from house.funnel import CONF_WEIGHT
    out = []
    for r in json.load(open(os.path.join(ROOT, "data/funnel.json")))["rows"]:
        c = CONF_WEIGHT[r["confidence"]]
        out.append(("zip", r["zip"], "territory_status", r["status"], "enum", c, "rules", route(c), "data/funnel.json"))
    return out


def fill(con):
    con.executescript(SCHEMA)
    con.execute("DELETE FROM judgments")
    rows = permit_rows(con) + house_rows() + photo_rows() + zip_rows()
    con.executemany("INSERT OR REPLACE INTO judgments VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


TYPES = ["permit", "house", "photo", "zip"]


def feed(con):
    counts = {t: {"auto": 0, "review": 0, "human": 0} for t in TYPES}
    for t, r, n in con.execute("SELECT subject_type, route, count(*) FROM judgments GROUP BY 1, 2"):
        counts[t][r] = n
    # Sample for the table: every non-permit judgment, and permits spread over the confidence tiers.
    sample = [list(r) for r in con.execute(
        "SELECT subject_type, subject_id, field, value, value_type, confidence, method, route FROM judgments "
        "WHERE subject_type <> 'permit' ORDER BY subject_type, confidence")]
    for _, conf, _ in RULE_CONFIDENCE:
        sample += [list(r) for r in con.execute(
            "SELECT subject_type, subject_id, field, value, value_type, confidence, method, route FROM judgments "
            "WHERE subject_type='permit' AND confidence=? ORDER BY subject_id DESC LIMIT 6", (conf,))]
    tiers = []
    for _, conf, name in RULE_CONFIDENCE:
        n = con.execute("SELECT count(*) FROM judgments WHERE subject_type='permit' AND confidence=?", (conf,)).fetchone()[0]
        tiers.append({"rule": name, "confidence": conf, "route": route(conf), "rows": n})
    # Check against the cohort builder's own list of fields to confirm with the member.
    member = sum(len(h.get("confirm_with_member", [])) for h in json.load(open(os.path.join(ROOT, "house/cohort.json"))))
    compare = json.load(open(COMPARE)) if os.path.exists(COMPARE) else None
    return {
        "_meta": {"built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "source": "data/fleet.db judgments table (store/judgments.py)",
                  "rows": sum(sum(v.values()) for v in counts.values()),
                  "sample_cols": ["subject_type", "subject_id", "field", "value", "value_type", "confidence",
                                  "method", "route"]},
        "thresholds": ROUTES, "human": HUMAN, "counts": counts, "permit_rules": tiers,
        "cohort_confirm_with_member": member, "sample": sample, "judge_compare": compare,
    }


def main():
    con = sqlite3.connect(DB)
    n = fill(con)
    d = feed(con)
    with open(FEED, "w") as f:
        json.dump(d, f, separators=(",", ":"))
    print(f"judgments: {n:,} rows -> {os.path.relpath(FEED, ROOT)}")
    for t, v in d["counts"].items():
        print(f"  {t:7s} auto {v['auto']:>6,}  review {v['review']:>6,}  human {v['human']:>6,}")


if __name__ == "__main__":
    main()
