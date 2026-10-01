"""Build web/data/permit_jev.json, the figures on the Permits page (judgments.html). Stdlib only.

Inputs, all already in the repo:
  data/mirror/energy_permits.csv.gz   34,334 Austin energy permits (the mirror store/judgments.py reads)
  data/mirror/category_check.csv      150 permits checked by hand against the rule category
  web/data/judgments.json             judge_compare: gemma4:e4b on the 100 lowest-confidence permits
Confidence and route come from store/judgments.py (rule_confidence, route), so the counts match judgments.json.

Run from the repo root: python3 web/data/build_permit_jev.py
"""
import csv, gzip, json, math, os, sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from store.judgments import RULE_CONFIDENCE, rule_confidence, route  # noqa: E402

CATS = ["solar", "battery", "solar_battery", "generator", "ev_charger", "panel_upgrade", "other_electrical"]


def wilson(k, n, z=1.96):
    if not n:
        return [0, 0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def main():
    permits = list(csv.DictReader(gzip.open(os.path.join(ROOT, "data/mirror/energy_permits.csv.gz"), "rt")))
    P = {p["permit_number"]: p for p in permits}
    for p in permits:
        p["conf"], p["rule"] = rule_confidence(p["category"], p["work_class"])
        p["route"] = route(p["conf"])

    # Routing by category (FIG. 6) and permit-weighted rule confidence per category (FIG. 2 predicted; FIG. 1 uses judgments.json).
    cat_route = {c: Counter() for c in CATS}
    cat_conf = defaultdict(float)
    for p in permits:
        cat_route[p["category"]][p["route"]] += 1
        cat_conf[p["category"]] += p["conf"]

    # Hand check (FIG. 2 observed, FIG. 4 calibration).
    check = list(csv.DictReader(open(os.path.join(ROOT, "data/mirror/category_check.csv"))))
    by_cat, by_tier = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in check:
        ok = int(r["correct"])
        by_cat[r["rule_category"]][0] += ok
        by_cat[r["rule_category"]][1] += 1
        t = P[r["permit_number"]]["conf"]
        by_tier[t][0] += ok
        by_tier[t][1] += 1

    J = json.load(open(os.path.join(ROOT, "web/data/judgments.json")))["judge_compare"]
    hand = {r["permit_number"]: r for r in check}
    traced = []
    for r in J["rows"]:
        if r["permit"] in hand:
            p = P[r["permit"]]
            traced.append({**r, "true_category": hand[r["permit"]]["true_category"],
                           "issue_date": p["issue_date"], "applied_date": p["applied_date"], "zip": p["zip"],
                           "work_class": p["work_class"], "status": p["status"], "rule_name": p["rule"]})

    tiers = sorted({c for _, c, _ in RULE_CONFIDENCE}, reverse=True)
    out = {
        "_meta": {"source": ["data/mirror/energy_permits.csv.gz", "data/mirror/category_check.csv",
                             "web/data/judgments.json judge_compare"],
                  "builder": "web/data/build_permit_jev.py",
                  "issue_dates": [min(p["issue_date"] for p in permits), max(p["issue_date"] for p in permits)]},
        "n": len(permits),
        "categories": [{"cat": c, "n": sum(cat_route[c].values()),
                        "auto": cat_route[c]["auto"], "review": cat_route[c]["review"], "human": cat_route[c]["human"],
                        "predicted": round(cat_conf[c] / max(1, sum(cat_route[c].values())), 3),
                        "checked": by_cat[c][1], "correct": by_cat[c][0], "ci": wilson(by_cat[c][0], by_cat[c][1])}
                       for c in CATS],
        "tiers": [{"conf": t, "route": route(t), "permits": sum(1 for p in permits if p["conf"] == t),
                   "checked": by_tier[t][1], "correct": by_tier[t][0], "ci": wilson(by_tier[t][0], by_tier[t][1])}
                  for t in tiers],
        "check": {"n": len(check), "correct": sum(int(r["correct"]) for r in check)},
        "model": {"sample": J["sample"], "model": J["model"],
                  "confident_disagree": sum(1 for r in J["rows"] if r["confidence"] >= 0.9 and r["value"] != r["rules"]),
                  "confident": sum(1 for r in J["rows"] if r["confidence"] >= 0.9),
                  "pairs": Counter(f'{r["rules"]}>{r["value"]}' for r in J["rows"]),
                  "conf_hist": Counter(str(r["confidence"]) for r in J["rows"]),
                  "work_class": Counter(P[r["permit"]]["work_class"].strip() for r in J["rows"]),
                  "traced": traced},
    }
    path = os.path.join(ROOT, "web/data/permit_jev.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
