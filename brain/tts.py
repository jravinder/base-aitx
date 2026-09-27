"""Kokoro-82M speech for Base Fleet (the same local voice as RefereAI: af_heart, Apache-2.0).

Two uses:
  python -m brain.tts --serve 8744            # POST /tts {"text": "..."} -> audio/mpeg, cached on disk
  python -m brain.tts --render texts.json     # write web/audio/<key>.mp3 + web/audio/manifest.json

The key is FNV-1a 32-bit of the normalized text (trim, single spaces), in hex.
web/speak.js computes the same key, so a pre-rendered clip plays on the static site.

Kokoro needs Python 3.12 or earlier: uv venv -p 3.12 .venv-tts && uv pip install kokoro soundfile
plus the spaCy model en_core_web_sm. ffmpeg converts WAV to MP3.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VOICE = "af_heart"
RATE = 24000
CACHE = ROOT / "data" / "live" / "tts"
AUDIO = ROOT / "web" / "audio"
MAX_CHARS = 1200

_pipe = None
_lock = threading.Lock()


def normalize(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def key(text):
    h = 0x811C9DC5
    for b in normalize(text).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def pipeline():
    global _pipe
    if _pipe is None:
        from kokoro import KPipeline
        _pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    return _pipe


def synth_mp3(text, out):
    """Render text to an MP3 file at out."""
    import numpy as np
    import soundfile as sf
    with _lock:  # one model, one render at a time
        chunks = [a for _, _, a in pipeline()(normalize(text), voice=VOICE)]
    audio = np.concatenate(chunks)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".wav") as wav:
        sf.write(wav.name, audio, RATE)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav.name,
                        "-ac", "1", "-b:a", "48k", str(out)], check=True)
    return out


def cached(text):
    out = CACHE / f"{key(text)}.mp3"
    if not out.exists():
        synth_mp3(text, out)
    return out


def render(texts):
    """Pre-render a list of texts into web/audio and update the manifest."""
    manifest_path = AUDIO / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for i, text in enumerate(texts, 1):
        text = normalize(text)
        if not text or len(text) > MAX_CHARS:
            continue
        k = key(text)
        out = AUDIO / f"{k}.mp3"
        if not out.exists():
            synth_mp3(text, out)
        manifest[k] = f"{k}.mp3"
        print(f"{i}/{len(texts)} {k} {text[:60]}", flush=True)
    manifest_path.write_text(json.dumps(dict(sorted(manifest.items())), indent=0))
    print(f"manifest: {len(manifest)} clips in {AUDIO}")


class Handler(BaseHTTPRequestHandler):
    def cors(self):
        origin = self.headers.get("Origin", "")
        if re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$", origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/tts"):
            return self.fail(404, "use POST /tts")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            text = normalize(json.loads(self.rfile.read(n) or b"{}").get("text", ""))
        except (ValueError, json.JSONDecodeError):
            return self.fail(400, "send JSON {\"text\": \"...\"}")
        if not text or len(text) > MAX_CHARS:
            return self.fail(400, f"text must be 1 to {MAX_CHARS} characters")
        body = cached(text).read_bytes()
        self.send_response(200)
        self.cors()
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=86400")
        self.end_headers()
        self.wfile.write(body)

    def fail(self, code, msg):
        body = json.dumps({"error": msg}).encode()
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", type=int)
    ap.add_argument("--render", help="JSON file with a list of texts")
    a = ap.parse_args()
    if a.render:
        render(json.loads(Path(a.render).read_text()))
    elif a.serve:
        pipeline()  # load once before the first request
        print(f"tts server on http://localhost:{a.serve}/tts (Kokoro-82M, {VOICE})", flush=True)
        ThreadingHTTPServer(("127.0.0.1", a.serve), Handler).serve_forever()
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
