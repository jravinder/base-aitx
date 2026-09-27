"""Build web/data/qa.json from docs/qa/*.md for web/qa.html.

Run from the repo root: python3 web/data/build_qa.py
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QA = ROOT / "docs" / "qa"
SETS = {"business": "business.md", "grid": "grid-ai.md", "skeptic": "data-skeptic.md"}
SET_LABELS = {"business": "Business", "grid": "Grid and AI", "skeptic": "Skeptic"}
HEAD = re.compile(r"^#{2,3} (T?\d+)\. (.*)$")
FIELD = re.compile(r"^(?:- )?\*\*(Say|Proof|Limit|Show|Next week|Set|Number|Open|Never say):\*\*\s*(.*)$")
PATH = re.compile(r"`/?([\w./-]+\.(?:html|md|json|py|csv))[^`]*`")


def page_of(*texts):
    """First web page named in the texts, else the first file. Link is relative to web/."""
    paths = [m for t in texts if t for m in PATH.findall(t)]
    for p in paths:
        if p.startswith("web/") and p.endswith(".html"):
            return {"label": p, "href": p[4:]}
    if paths:
        p = paths[0]
        return {"label": p, "href": p[4:] if p.startswith("web/") else "../" + p}
    return None


def parse(path):
    cards, cur = [], None
    for line in path.read_text().splitlines():
        m = HEAD.match(line)
        if m:
            q = m.group(2)
            must = "MUST" in q
            q = re.sub(r"\s*\[MUST\]\s*|MUST NAIL\.\s*", " ", q).strip().strip('"').strip()
            cur = {"num": m.group(1), "q": q, "must": must}
            cards.append(cur)
            continue
        f = FIELD.match(line)
        if f and cur is not None:
            cur[f.group(1).lower().replace(" ", "_")] = f.group(2).strip()
    return cards


def main():
    out = []
    for key, fname in SETS.items():
        for c in parse(QA / fname):
            if not c.get("say"):
                continue
            limit = c.get("limit") or ("Not done yet. Next week: " + c["next_week"] if c.get("next_week") else "")
            out.append({"id": f"{key}-{c['num']}", "deck": "all", "set": key, "rank": int(c["num"]),
                        "q": c["q"], "must": c["must"], "say": c["say"], "number": c.get("proof", ""),
                        "limit": limit, "page": page_of(c.get("show"), c.get("say"), c.get("proof")),
                        "source": f"docs/qa/{fname}"})
    for c in parse(QA / "DRILL.md"):
        trap = c["num"].startswith("T")
        out.append({"id": ("trap-" if trap else "drill-") + c["num"], "deck": "trap" if trap else "drill",
                    "set": c.get("set", "").strip(), "rank": int(c["num"].lstrip("T")), "q": c["q"],
                    "must": False, "say": c.get("say", ""), "number": c.get("number", ""),
                    "limit": c.get("limit", ""), "never": c.get("never_say", ""),
                    "page": page_of(c.get("open"), c.get("number")), "source": "docs/qa/DRILL.md"})
    counts = {d: sum(1 for c in out if c["deck"] == d) for d in ("drill", "trap", "all")}
    data = {"built": "2026-09-26", "sources": ["docs/qa/DRILL.md"] + [f"docs/qa/{f}" for f in SETS.values()],
            "sets": SET_LABELS, "counts": counts, "cards": out}
    (ROOT / "web" / "data" / "qa.json").write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(counts)


if __name__ == "__main__":
    main()
