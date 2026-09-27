"""Control tower server. Runs the fleet sim live, one interval every TICK seconds, in memory.

GET  /state            fleet snapshot: hour, prices, every node, feeders, queue by tier, revenue by tier, events
GET  /node/<id>        one node, for the member view
GET  /jobs/<id>        one job: queued | running on node N | done
POST /jobs             {"tier": "member|business|base|partner|external", "origin": <node id>}   -> {"id": ...}
POST /kill             {"kind": "node|region|scheduler", "target": <id | region | null>}
Static files from web/ plus explicitly allowlisted recorded datasets. All jobs are simulated.

python3 -m sim.server [--nodes 50] [--seed 7] [--tick 2] [--port 8732]
"""

import argparse
import json
import os
import random
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from sim import fleet, network

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
WEB = os.path.join(ROOT, "web")
PUBLIC_DATA = frozenset({
    "house/cohort.json", "house/cohort.sample.json", "house/public_buildings.json",
    "panel/pred_gemini.jsonl", "panel/pred_gemma4.jsonl", "panel/pred_gemma4_flickr.jsonl",
    "data/members.json", "data/members.fixture.json", "data/funnel.json", "data/zcta.geojson",
    "brain/questions.json", "brain/questions.fixture.json", "brain/pred.jsonl",
})
WEB_EXTENSIONS = frozenset({".html", ".css", ".js", ".mjs", ".json", ".svg", ".png",
                            ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".ttf"})
MAX_BODY_BYTES = 16 * 1024
lock = threading.Lock()
state = {"snap": None, "events": [], "jobs": {}, "inbox": [], "n": 0}


def snapshot(s, feeder_of, feeders):
    nodes = []
    for nd in s["nodes"]:
        nodes.append({"id": nd.id, "region": nd.region, "feeder": feeder_of.get(nd.id), "alive": nd.alive,
                      "soc": round(nd.soc, 3), "kwh": round(nd.kwh(), 1),
                      "battery": s["row"]["actions"].get(nd.id) if s["row"]["actions"].get(nd.id) in ("charge", "discharge", "dead") else "idle",
                      "gpu": s["row"]["gpu_actions"].get(nd.id, "idle"),
                      "job": {"id": nd.job[0]["id"], "tier": nd.job[0]["tier"], "hours_left": nd.job[1]} if nd.job else None})
    by_tier = {k: 0 for k in fleet.TIERS}
    for j in s["queue"]:
        by_tier[j["tier"]] += 1
    r = s["result"]
    return {"t": s["t"], "hour_of_day": s["t"] % 24, "day": s["t"] // 24 + 1,
            "grid_price": s["row"]["grid"], "gpu_price": s["row"]["gpu"], "margin_this_hour": s["row"]["margin"],
            "nodes": nodes,
            "feeders": {f: {"nodes": ids, "export_kw": round(s["export"].get(f, 0.0), 1), "cap_kw": fleet.FEEDER_EXPORT_KW} for f, ids in feeders.items()},
            "region_alive": s["region_alive"], "scheduler_alive": s["scheduler_alive"],
            "queue": {"total": len(s["queue"]), "by_tier": by_tier},
            "revenue": {"power": r["revenue_power"], "compute": r["revenue_compute"], "by_tier": r["by_tier"]},
            "failover": {"ok": r["failover_ok"], "none": r["failover_none"], "gpu_hours_lost": r["gpu_hours_lost"]},
            "discharges_capped": r["discharges_capped"],
            "history": [{"t": x["t"], "grid": x["grid"], "margin": x["margin"]} for x in r["log"][-72:]]}


def ticker(n, seed, tick):
    nodes, feeders = network.build(n, random.Random(seed))
    feeder_of = {x["id"]: x["feeder"] for x in nodes}
    stream = fleet.stream(n, seed, network=(nodes, feeders), inbox=state["inbox"], endless=True)
    while True:
        # Consume commands and publish their effects atomically with API submissions.
        with lock:
            try:
                s = next(stream)
            except StopIteration:
                return
            state["snap"] = snapshot(s, feeder_of, feeders)
            running, pending = {}, {}
            for nd in s["nodes"]:
                for job in ([nd.job] if nd.job else []) + nd.jobs:
                    running[job[0]["id"]] = (nd.id, job[1])
                if nd.next_job:
                    pending[nd.next_job[0]["id"]] = nd.next_job[1]
            queued = {j["id"] for j in s["queue"]}
            queued.update(c["job"]["id"] for c in state["inbox"] if "job" in c)
            for jid, j in state["jobs"].items():
                if jid in running:
                    node, hours = running[jid]
                    j.update(status="running", node=node, hours_left=hours)
                elif jid in pending:
                    # A busy neighbor has accepted the checkpoint but has not started it.
                    j.update(status="queued", node=None, hours_left=pending[jid])
                elif jid in queued:
                    j.update(status="queued", node=None)
                    j.pop("hours_left", None)
                elif j["status"] == "running" or "hours_left" in j:
                    j["status"] = "done"
                    j.pop("hours_left", None)
        time.sleep(tick)


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlsplit(self.path).path
        with lock:
            snap = state["snap"]
            if p == "/state":
                return self.send_json({**snap, "events": state["events"][-20:]} if snap else {"t": -1})
            if p.startswith("/node/"):
                value = p[6:]
                if not value.isascii() or not value.isdecimal() or len(value) > 10:
                    return self.send_json({"error": "node id must be a nonnegative integer"}, 400)
                nid = int(value)
                if snap is None:
                    return self.send_json({"error": "simulation is starting"}, 503)
                nd = next((x for x in snap["nodes"] if x["id"] == nid), None)
                mine = [j for j in state["jobs"].values() if j["origin"] == nid]
                return self.send_json({"node": nd, "feeder": snap["feeders"].get(nd["feeder"]) if nd else None, "jobs": mine,
                                       "grid_price": snap["grid_price"], "t": snap["t"]}) if nd else self.send_json({"error": "no node"}, 404)
            if p.startswith("/jobs/"):
                j = state["jobs"].get(p[6:])
                return self.send_json(j) if j else self.send_json({"error": "no job"}, 404)
        return super().do_GET()

    def send_head(self):
        """Serve public assets only, including for HEAD; never list repo directories."""
        path = unquote(urlsplit(self.path).path)
        parts = path.lstrip("/").split("/")
        if "\x00" in path or "\\" in path or any(p.startswith(".") for p in parts):
            self.send_error(404)
            return None
        relative = "/".join(parts)
        if relative in PUBLIC_DATA:
            base = ROOT
        else:
            base = WEB
            if relative.startswith("web/"):
                relative = relative[4:]
            if not relative:
                relative = "index.html"
            if os.path.splitext(relative)[1].lower() not in WEB_EXTENSIONS:
                self.send_error(404)
                return None
        filename = os.path.join(base, relative)
        # Reject symlinks as well as traversal, including links to secrets inside the repo.
        if (os.path.commonpath((os.path.abspath(base), os.path.abspath(filename))) != os.path.abspath(base)
                or os.path.realpath(filename) != os.path.abspath(filename) or not os.path.isfile(filename)):
            self.send_error(404)
            return None
        try:
            f = open(filename, "rb")
        except OSError:
            self.send_error(404)
            return None
        stat = os.fstat(f.fileno())
        self.send_response(200)
        content_type = "application/x-ndjson" if filename.endswith(".jsonl") else self.guess_type(filename)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        return f

    def do_POST(self):
        p = urlsplit(self.path).path
        if p not in ("/jobs", "/kill"):
            return self.send_json({"error": "no route"}, 404)
        if self.headers.get("Transfer-Encoding"):
            return self.send_json({"error": "transfer encoding is not supported"}, 400)
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return self.send_json({"error": "invalid content length"}, 400)
        if n < 0:
            return self.send_json({"error": "invalid content length"}, 400)
        if n > MAX_BODY_BYTES:
            return self.send_json({"error": "request body too large"}, 413)
        raw = self.rfile.read(n)
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, UnicodeError):
            return self.send_json({"error": "body must be valid JSON"}, 400)
        if len(raw) != n or not isinstance(body, dict):
            return self.send_json({"error": "body must be a complete JSON object"}, 400)
        with lock:
            snap = state["snap"]
            if snap is None:
                return self.send_json({"error": "simulation is starting"}, 503)
            t = snap["t"]
            nodes = {nd["id"]: nd for nd in snap["nodes"]}
            if p == "/kill":
                kind, target = body.get("kind"), body.get("target")
                if kind not in ("node", "region", "scheduler"):
                    return self.send_json({"error": "kind must be node, region or scheduler"}, 400)
                if kind == "node" and (type(target) is not int or target not in nodes):
                    return self.send_json({"error": "target must be an existing node id"}, 400)
                if kind == "region" and (not isinstance(target, str) or target not in snap["region_alive"]):
                    return self.send_json({"error": "target must be an existing region"}, 400)
                if kind == "scheduler" and target is not None:
                    return self.send_json({"error": "scheduler target must be null"}, 400)
                state["inbox"].append({"kill": (kind, target)})
                state["events"].append({"t": t, "kind": kind, "target": target})
                return self.send_json({"ok": True, "at": t + 1})
            if p == "/jobs":
                tier = body.get("tier", "external")
                if not isinstance(tier, str) or tier not in fleet.TIERS:
                    return self.send_json({"error": f"tier must be one of {list(fleet.TIERS)}"}, 400)
                origin = body.get("origin", 0)
                if type(origin) is not int or origin not in nodes:
                    return self.send_json({"error": "origin must be an existing node id"}, 400)
                state["n"] += 1
                jid = f"api{state['n']}"
                feeder = nodes[origin]["feeder"]
                job = {"id": jid, "origin": origin, "feeder": feeder, "tier": tier}
                state["inbox"].append({"job": job})
                state["jobs"][jid] = {"id": jid, "tier": tier, "origin": origin, "status": "queued", "node": None, "submitted_at": t}
                return self.send_json({"id": jid, "status": "queued", "rate": fleet.TIERS[tier]["rate"]})
        return self.send_json({"error": "no route"}, 404)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tick", type=float, default=2.0)
    ap.add_argument("--port", type=int, default=8732)
    a = ap.parse_args()
    threading.Thread(target=ticker, args=(a.nodes, a.seed, a.tick), daemon=True).start()
    print(f"control tower on http://localhost:{a.port}/tower.html  (one hour every {a.tick}s)")
    ThreadingHTTPServer(("", a.port), H).serve_forever()
