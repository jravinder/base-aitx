"""Run brain/questions.json through answer.py for one member, write brain/pred.jsonl.

A GAP question is correct only if the answer starts with "GAP".
A non-GAP question is correct if the expected numbers or key words appear in the answer.

Usage: python3 -m brain.score [member_id]
"""
import json
import os
import re
import sys

from brain.answer import answer, ollama_up, tokens

HERE = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(HERE, "questions.json")
QUESTIONS_FIXTURE = os.path.join(HERE, "questions.fixture.json")
PRED = os.path.join(HERE, "pred.jsonl")


def load_questions():
    path = QUESTIONS if os.path.exists(QUESTIONS) else QUESTIONS_FIXTURE
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "questions" in data:
        data = data["questions"]
    qs = []
    for i, q in enumerate(data):
        exp = q.get("expected") or q.get("answer") or q.get("expected_answer") or q.get("answer_from_record") or ""
        qs.append({"id": q.get("id", f"q{i + 1:02d}"), "question": q["question"], "expected": str(exp)})
    return qs, path


def judge(expected, got):
    is_gap = expected.strip().upper().startswith("GAP")
    if is_gap:
        return "gap_correct" if got.startswith("GAP") else "wrong"
    if got.startswith("GAP"):
        return "wrong"
    nums = set(re.findall(r"\d+(?:\.\d+)?", expected)) - {"2026"}
    if nums:
        got_nums = set(re.findall(r"\d+(?:\.\d+)?", got))
        hit = len(nums & got_nums)
        return "correct" if hit >= min(2, len(nums)) else "wrong"
    exp_t = tokens(expected) - {"from", "record"}
    return "correct" if len(exp_t & tokens(got)) >= max(1, len(exp_t) // 2) else "wrong"


def main(member_id="m001"):
    qs, qpath = load_questions()
    up = ollama_up()
    print(f"questions: {qpath}\nollama gemma4:e4b: {'up' if up else 'DOWN, using rules'}")
    counts = {"correct": 0, "gap_correct": 0, "wrong": 0}
    with open(PRED, "w") as out:
        for q in qs:
            got, used, engine = answer(member_id, q["question"], use_ollama=up)
            verdict = judge(q["expected"], got)
            counts[verdict] += 1
            rec = {"id": q["id"], "member_id": member_id, "question": q["question"], "expected": q["expected"],
                   "answer": got, "sections": used, "engine": engine, "verdict": verdict}
            out.write(json.dumps(rec) + "\n")
            print(f"{q['id']} {verdict:12s} {got[:90]}")
    n = len(qs)
    print(f"\ncorrect {counts['correct']} / GAP-correct {counts['gap_correct']} / wrong {counts['wrong']}  "
          f"= {counts['correct'] + counts['gap_correct']}/{n}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "m001")
