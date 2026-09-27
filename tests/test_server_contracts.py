"""Server contracts without sockets, services, or external dependencies."""

import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sim import server


class ServerContracts(unittest.TestCase):
    def setUp(self):
        self.state = {"snap": {"t": 4, "nodes": [{"id": 0, "feeder": "f0"}],
                               "feeders": {"f0": {"nodes": [0]}},
                               "region_alive": {"north": True}, "grid_price": 0.1},
                      "events": [], "jobs": {}, "inbox": [], "n": 0}
        self.patch = patch.object(server, "state", self.state)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def request(self, path, body=None, method="GET", raw=None, headers=None):
        h = object.__new__(server.H)
        h.path, h.directory = path, server.WEB
        h.command, h.request_version = method, "HTTP/1.1"
        data = raw if raw is not None else json.dumps(body).encode()
        h.headers = headers if headers is not None else {"Content-Length": str(len(data))}
        h.rfile, h.wfile = io.BytesIO(data), io.BytesIO()
        response = {"headers": {}}
        h.send_response = lambda code, *a: response.update(status=code)
        h.send_header = lambda key, value: response["headers"].update({key: value})
        h.end_headers = lambda: None
        h.send_error = lambda code, *a: response.update(status=code)
        getattr(h, "do_" + method)()
        response["body"] = h.wfile.getvalue()
        return response

    def assert_error(self, response, code):
        self.assertEqual(response["status"], code)
        self.assertIn("error", json.loads(response["body"]))

    def test_job_submission_and_lookup(self):
        r = self.request("/jobs?demo=1", {"tier": "member", "origin": 0}, "POST")
        self.assertEqual(r["status"], 200)
        j = json.loads(r["body"])
        self.assertEqual(j, {"id": "api1", "status": "queued", "rate": 1.2})
        self.assertEqual(self.state["inbox"][0]["job"]["feeder"], "f0")
        r = self.request("/jobs/api1")
        self.assertEqual(json.loads(r["body"])["status"], "queued")
        self.assertEqual(len(json.loads(self.request("/node/0")["body"])["jobs"]), 1)

    def test_invalid_jobs_do_not_mutate_state(self):
        for origin in (-1, 1, 999, True, 0.5, "0", None, [], {}):
            with self.subTest(origin=origin):
                self.assert_error(self.request("/jobs", {"origin": origin}, "POST"), 400)
        for tier in ("bad", [], {}, None):
            with self.subTest(tier=tier):
                self.assert_error(self.request("/jobs", {"tier": tier}, "POST"), 400)
        self.assertEqual(self.state["n"], 0)
        self.assertEqual(self.state["inbox"], [])

    def test_kill_validation(self):
        for body in ({"kind": "node", "target": 49}, {"kind": "node", "target": -1},
                     {"kind": "node", "target": True}, {"kind": "node", "target": [0]},
                     {"kind": "region", "target": "missing"}, {"kind": "region", "target": []},
                     {"kind": "scheduler", "target": 0}, {"kind": []}):
            with self.subTest(body=body):
                self.assert_error(self.request("/kill", body, "POST"), 400)
        self.assertEqual(self.state["inbox"], [])
        self.assertEqual(self.state["events"], [])
        for kind, target in (("node", 0), ("region", "north"), ("scheduler", None)):
            self.state["inbox"].clear()
            r = self.request("/kill", {"kind": kind, "target": target}, "POST")
            self.assertEqual(json.loads(r["body"]), {"ok": True, "at": 5})

    def test_malformed_requests(self):
        for raw in (b"{", b"[]", b"null", b"1", b'"text"', b"\xff"):
            with self.subTest(raw=raw):
                self.assert_error(self.request("/jobs", method="POST", raw=raw), 400)
        for length in ("bad", "-1"):
            self.assert_error(self.request("/jobs", method="POST", headers={"Content-Length": length}), 400)
        self.assert_error(self.request("/jobs", method="POST", headers={"Content-Length": "999999"}), 413)
        self.assert_error(self.request("/jobs", method="POST", raw=b"{}", headers={"Content-Length": "3"}), 400)

    def test_startup_and_missing_resources(self):
        self.assert_error(self.request("/node/not-an-id"), 400)
        self.assert_error(self.request("/node/99"), 404)
        self.assert_error(self.request("/jobs/missing"), 404)
        self.assert_error(self.request("/unknown", {}, "POST"), 404)
        self.state["snap"] = None
        self.assertEqual(json.loads(self.request("/state")["body"]), {"t": -1})
        self.assert_error(self.request("/node/0"), 503)
        self.assert_error(self.request("/jobs", {}, "POST"), 503)
        self.assert_error(self.request("/kill", {"kind": "scheduler"}, "POST"), 503)

    def test_public_static_data_and_web_alias(self):
        for path in ("/house/cohort.json", "/house/cohort.sample.json", "/house/public_buildings.json",
                     "/data/members.json", "/data/members.fixture.json", "/data/funnel.json",
                     "/data/zcta.geojson", "/brain/questions.json", "/brain/questions.fixture.json", "/brain/pred.jsonl",
                     "/demo.html", "/web/demo.html", "/data/report.json", "/web/data/report.json",
                     "/web/assets/ibm-plex-sans-400.ttf", "/web/assets/jetbrains-mono-400.ttf"):
            with self.subTest(path=path):
                r = self.request(path)
                self.assertEqual(r["status"], 200)
                self.assertTrue(r["body"])
                head = self.request(path, method="HEAD")
                self.assertEqual(head["status"], 200)
                self.assertEqual(head["body"], b"")
                self.assertEqual(int(head["headers"]["Content-Length"]), len(r["body"]))

    def test_private_and_traversal_paths_are_not_served(self):
        for path in ("/.git/config", "/.env", "/sim/server.py", "/house/permits.py",
                     "/panel/manifest.json", "/brain/answer.py", "/data/austin_zips.json",
                     "/house/", "/data/", "/web/../house/cohort.json",
                     "/%2e%2e/house/cohort.json", "/house/%2e%2e/.env", "/web/%00.html"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 404)
                self.assertEqual(self.request(path, method="HEAD")["status"], 404)

    def test_symlink_cannot_escape_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            web = root / "web"
            web.mkdir()
            secret = root / "secret.json"
            secret.write_text('{"secret":true}')
            (web / "leak.json").symlink_to(secret)
            with patch.object(server, "WEB", str(web)):
                self.assertEqual(self.request("/leak.json")["status"], 404)
                self.assertEqual(self.request("/web/" + str(secret))["status"], 404)

    def run_frames(self, frames):
        with patch.object(server.network, "build", return_value=([], {})), \
             patch.object(server.fleet, "stream", return_value=iter(frames)), \
             patch.object(server, "snapshot", return_value={}), \
             patch.object(server.time, "sleep"):
            server.ticker(1, 7, 0)

    def node(self, job=None, pending=None, jobs=None):
        return SimpleNamespace(id=0, job=job, next_job=pending, jobs=jobs or [])

    def tracked(self, status="running"):
        j = {"id": "api1", "origin": 0, "tier": "member", "feeder": "f0"}
        self.state["jobs"]["api1"] = {**j, "status": status, "node": 0 if status == "running" else None}
        return j

    def test_requeue_is_not_completion(self):
        j = self.tracked()
        self.run_frames([{"nodes": [self.node()], "queue": [j]}])
        self.assertEqual(self.state["jobs"]["api1"]["status"], "queued")
        self.assertIsNone(self.state["jobs"]["api1"]["node"])

    def test_pending_handoff_preserves_progress(self):
        j = self.tracked()
        self.run_frames([{"nodes": [self.node(pending=[j, 1, 0])], "queue": []}])
        tracked = self.state["jobs"]["api1"]
        self.assertNotEqual(tracked["status"], "done")
        self.assertEqual(tracked["hours_left"], 1)
        self.run_frames([{"nodes": [self.node(job=[j, 1, 0])], "queue": []},
                         {"nodes": [self.node()], "queue": []}])
        self.assertEqual(tracked["status"], "done")
        self.assertNotIn("hours_left", tracked)

    def test_unconsumed_inbox_job_stays_queued(self):
        j = self.tracked("queued")
        self.state["inbox"].append({"job": j})
        self.run_frames([{"nodes": [self.node()], "queue": []}])
        self.assertEqual(self.state["jobs"]["api1"]["status"], "queued")

    def test_handoff_can_complete_in_first_resumed_interval(self):
        j = self.tracked()
        self.run_frames([{"nodes": [self.node(pending=[j, 1, 0])], "queue": []},
                         {"nodes": [self.node()], "queue": []}])
        self.assertEqual(self.state["jobs"]["api1"]["status"], "done")

    def test_real_simulator_restarts_killed_job_then_completes(self):
        j = self.tracked("queued")
        self.state["inbox"].append({"job": j})
        statuses = []

        class Finished(Exception):
            pass

        def after_tick(_):
            statuses.append(self.state["jobs"]["api1"]["status"])
            if len(statuses) == 1:
                self.state["inbox"].append({"kill": ("node", 0)})
            if len(statuses) == 7:
                raise Finished

        with patch.object(server.time, "sleep", side_effect=after_tick):
            with self.assertRaises(Finished):
                server.ticker(1, 7, 0)
        self.assertEqual(statuses, ["running", "queued", "queued", "queued", "running", "running", "done"])

    def test_running_and_completed_jobs(self):
        j = self.tracked("queued")
        self.run_frames([{"nodes": [self.node(job=[j, 2, 0])], "queue": []}])
        tracked = self.state["jobs"]["api1"]
        self.assertEqual((tracked["status"], tracked["node"], tracked["hours_left"]), ("running", 0, 2))
        self.run_frames([{"nodes": [self.node()], "queue": []}])
        self.assertEqual(tracked["status"], "done")

    def test_community_slots_are_running_jobs(self):
        j = self.tracked("queued")
        self.run_frames([{"nodes": [self.node(jobs=[[j, 2, 0]])], "queue": []}])
        self.assertEqual(self.state["jobs"]["api1"]["hours_left"], 2)


if __name__ == "__main__":
    unittest.main()
