"""Learning loop: policy routing, scrubbing, grouping. No network, no model, no server."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from store import learn
from brain import ask


class Policy(unittest.TestCase):
    CASES = [("can I cancel my contract", "cancel"), ("How and when do I pay?", "pay-billing"),
             ("Do I own the battery?", "own-battery"), ("Does Base handle my HOA?", "hoa"),
             ("Can I get Base if I rent?", "renter"), ("When is a credit paid out?", "credit-payout")]

    def test_policy_topics(self):
        for q, topic in self.CASES:
            self.assertEqual(learn.policy(q)[0], topic, q)

    def test_policy_before_any_data_search(self):
        with patch.object(ask.templates, "match", side_effect=AssertionError("no data search")), \
             patch.object(ask, "cache_hit", return_value=None):
            for q, _ in self.CASES[:5]:
                r = ask.ask(q)
                self.assertEqual(r["path"], "base_support")
                self.assertTrue(r["answer"].startswith("Ask Base support."))

    def test_data_questions_are_not_policy(self):
        for q in ["who are the top contractors", "How many solar permits in 78745 in 2025?",
                  "how does the energy credit preview work", "what did my node earn this week"]:
            self.assertIsNone(learn.policy(q), q)


class Log(unittest.TestCase):
    def test_scrub_and_fields(self):
        with tempfile.TemporaryDirectory() as d, patch.object(learn, "LOG", os.path.join(d, "q.jsonl")):
            learn.log_question("My name is Jane Doe, I live at 1204 Oak Hollow Dr, email jd@x.com, ip 10.0.0.7",
                               "gap", page="ask.html", member_id="m001", seconds=0.2)
            with open(learn.LOG) as f:
                rec = json.loads(f.read())
        for bad in ("Jane", "1204 Oak", "jd@x.com", "10.0.0.7"):
            self.assertNotIn(bad, rec["question"])
        self.assertEqual(rec["answered"], False)
        self.assertEqual(set(rec), {"ts", "page", "question", "member_id", "path", "template", "answered",
                                    "critic_pass", "seconds", "answer"})

    def test_group(self):
        rows = [{"question": q, "ts": "2026-09-26T00:00:00Z"} for q in
                ["How many Base permits in 78745?", "how many base permits in 78745", "Can I cancel?"]]
        self.assertEqual(sorted(len(g["rows"]) for g in learn.group(rows)), [1, 2])


if __name__ == "__main__":
    unittest.main()
