"""Permit routing: the checked-in feeds agree with the mirror and the rules. Stdlib + pytest."""
import csv, gzip, json, os, sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from store.judgments import ROUTES, RULE_CONFIDENCE, route, rule_confidence  # noqa: E402

load = lambda p: json.load(open(os.path.join(ROOT, p)))


def permits():
    return list(csv.DictReader(gzip.open(os.path.join(ROOT, "data/mirror/energy_permits.csv.gz"), "rt")))


def test_thresholds_route():
    assert route(ROUTES["auto"]) == "auto" and route(ROUTES["review"]) == "review" and route(0.4) == "human"
    assert len(RULE_CONFIDENCE) == 7


def test_mirror_reproduces_feed_counts():
    D = load("web/data/judgments.json")
    got = Counter(route(rule_confidence(p["category"], p["work_class"])[0]) for p in permits())
    assert dict(got) == D["counts"]["permit"]
    tiers = Counter(rule_confidence(p["category"], p["work_class"])[0] for p in permits())
    assert {r["confidence"]: r["rows"] for r in D["permit_rules"]} == dict(tiers)


def test_figures_match_feed():
    D, F = load("web/data/judgments.json"), load("web/data/permit_jev.json")
    c = D["counts"]["permit"]
    assert F["n"] == sum(c.values())
    for r in ("auto", "review", "human"):
        assert sum(k[r] for k in F["categories"]) == c[r]
    assert sum(t["checked"] for t in F["tiers"]) == F["check"]["n"]
    assert sum(t["correct"] for t in F["tiers"]) == F["check"]["correct"]
    J = D["judge_compare"]
    assert sum(r["value"] == r["rules"] for r in J["rows"]) == J["agree_with_rules"]
