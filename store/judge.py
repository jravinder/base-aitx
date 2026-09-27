"""Re-judge low-confidence permit categories with another backend and compare with the rules. Stdlib only.

Backends (same interface: judge(description, work_class) -> (value, confidence, input_tokens)):
  rules  house/mirror.py categorize() on the description; confidence from store/judgments.py RULE_CONFIDENCE
  gemma  local Ollama gemma4:e4b, think false, asked for JSON {"value", "confidence"}
  jev    TypeSafe System One API (Jev), documented at https://docs.typesafe.ai/api.md:
         POST https://api.typesafe.ai/v1/systemone, Authorization: Bearer $JEV_API_KEY,
         body {state, model: "jev-latest", questions: {category: {type: "choice", instructions, criteria}}};
         the answer carries choice, probabilities and confidence, and usage.input_tokens.
         The key comes from the environment only and is never printed or logged.

  python3 -m store.judge --backend gemma --sample 100

The mirror does not store descriptions, so the sample's descriptions are fetched from Socrata 3syk-w9eu
by permit number (kept in memory only). Writes data/live/judge_compare.json; re-run
python3 -m store.judgments to put the comparison in web/data/judgments.json.
"""

import argparse
import json
import os
import sqlite3
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

from house.mirror import CATEGORIES, categorize  # noqa: E402
from store.judgments import COMPARE, DB, route, rule_confidence  # noqa: E402

SODA = "https://data.austintexas.gov/resource/3syk-w9eu.json"
OLLAMA = "http://localhost:11434/api/chat"
GEMMA = "gemma4:e4b"
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_PRICE_PER_M_INPUT = 0.042  # USD per 1M input tokens, as published in the Astronomer post; output is free

DEFS = {
    "battery": "home battery or energy storage (Powerwall, ESS, IQ Battery)",
    "solar": "solar PV only, no battery",
    "solar_battery": "solar PV and a battery on the same permit",
    "generator": "standby or portable generator",
    "panel_upgrade": "service, meter or main panel upgrade or replacement",
    "ev_charger": "EV charger or EVSE",
    "other_electrical": "none of these",
}


class Rules:
    name = "rules"

    def judge(self, desc, work_class):
        cat = categorize(desc, work_class)
        return cat, rule_confidence(cat, work_class)[0], 0


class Gemma:
    name = "gemma"

    def judge(self, desc, work_class):
        prompt = ("Classify this City of Austin electrical permit into one category.\n"
                  + "\n".join(f"- {k}: {v}" for k, v in DEFS.items())
                  + '\nReply with JSON only: {"value": "<category>", "confidence": <0 to 1>}. '
                  "confidence is how sure you are.\n\n"
                  f"work_class: {work_class}\ndescription: {desc[:600]}")
        body = json.dumps({"model": GEMMA, "think": False, "stream": False, "format": "json",
                           "options": {"temperature": 0},
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.loads(r.read())
        try:
            a = json.loads(out["message"]["content"])
            val, conf = str(a.get("value", "")).strip().lower(), float(a.get("confidence"))
        except (ValueError, TypeError, AttributeError):
            val, conf = "", 0.0
        if val not in CATEGORIES:
            val, conf = "other_electrical", 0.0
        return val, max(0.0, min(conf, 1.0)), out.get("prompt_eval_count", 0)


class Jev:
    name = "jev"

    def __init__(self):
        self.key = os.environ.get("JEV_API_KEY")
        if not self.key:
            raise SystemExit("jev backend: JEV_API_KEY is not set in the environment. "
                             "Endpoint is documented (POST https://api.typesafe.ai/v1/systemone); only the key is missing.")

    def judge(self, desc, work_class):
        body = json.dumps({
            "model": "jev-latest",
            "state": {"work_class": work_class, "description": desc[:2000]},
            "questions": {"category": {"type": "choice",
                                       "instructions": "Which kind of energy work does this Austin electrical permit cover?",
                                       "criteria": DEFS}}}).encode()
        req = urllib.request.Request(JEV_URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self.key})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:  # report status only; the request holds the key
            raise SystemExit(f"jev backend: HTTP {e.code} from {JEV_URL}")
        a = out["answers"]["category"]
        return a["choice"], float(a["confidence"]), out.get("usage", {}).get("input_tokens", 0)


BACKENDS = {"rules": Rules, "gemma": Gemma, "jev": Jev}


def descriptions(numbers):
    out = {}
    for i in range(0, len(numbers), 50):
        chunk = numbers[i:i + 50]
        where = "permit_number in (" + ",".join("'" + n.replace("'", "''") + "'" for n in chunk) + ")"
        url = SODA + "?" + urllib.parse.urlencode({"$select": "permit_number, description", "$where": where,
                                                    "$limit": 1000}, quote_via=urllib.parse.quote)
        req = urllib.request.Request(url, headers={"User-Agent": "base-fleet/store.judge"})
        with urllib.request.urlopen(req, timeout=120) as r:
            for row in json.loads(r.read()):
                out[row["permit_number"]] = row.get("description") or ""
    return out


def bucket(c):
    return f"{min(int(c * 10), 9) / 10:.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=BACKENDS, default="gemma")
    ap.add_argument("--sample", type=int, default=100)
    a = ap.parse_args()
    backend = BACKENDS[a.backend]()

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT j.subject_id, j.value, j.confidence, p.work_class FROM judgments j "
        "JOIN permits p ON p.permit_number = j.subject_id WHERE j.subject_type='permit' "
        "ORDER BY j.confidence, j.subject_id DESC LIMIT ?", (a.sample,)).fetchall()
    desc = descriptions([r[0] for r in rows])
    results, secs, tokens = [], [], 0
    for i, (pn, rule_val, rule_conf, wc) in enumerate(rows):
        t0 = time.time()
        val, conf, tok = backend.judge(desc.get(pn, ""), wc)
        secs.append(time.time() - t0)
        tokens += tok
        results.append({"permit": pn, "rules": rule_val, "rules_confidence": rule_conf,
                        "value": val, "confidence": round(conf, 3), "route": route(conf)})
        if i % 10 == 0:
            print(f"  {i}/{len(rows)} {pn} rules={rule_val} {a.backend}={val} ({conf:.2f})", file=sys.stderr)

    agree = sum(r["value"] == r["rules"] for r in results)
    out = {
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "backend": a.backend, "model": GEMMA if a.backend == "gemma" else a.backend,
        "sample": len(results), "missing_description": sum(1 for r in rows if not desc.get(r[0])),
        "picked": "lowest rules confidence first, then newest permit number",
        "agree_with_rules": agree, "agree_share": round(agree / max(len(results), 1), 3),
        "labels": dict(Counter(r["value"] for r in results).most_common()),
        "confidence_buckets": dict(sorted(Counter(bucket(r["confidence"]) for r in results).items())),
        "routes": dict(Counter(r["route"] for r in results)),
        "seconds_total": round(sum(secs), 1), "seconds_median": round(statistics.median(secs), 2) if secs else 0,
        "input_tokens": tokens,
        "token_note": "input tokens as counted by the backend (Ollama prompt_eval_count for gemma)",
        "jev_cost_usd": round(tokens / 1e6 * JEV_PRICE_PER_M_INPUT, 6),
        "jev_cost_all_permits_usd": round(tokens / max(len(results), 1) * con.execute(
            "SELECT count(*) FROM permits").fetchone()[0] / 1e6 * JEV_PRICE_PER_M_INPUT, 4),
        "jev_price": f"${JEV_PRICE_PER_M_INPUT} per 1M input tokens (Astronomer post); output free",
        "rows": results,
    }
    os.makedirs(os.path.dirname(COMPARE), exist_ok=True)
    with open(COMPARE, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
