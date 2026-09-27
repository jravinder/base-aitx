/* Base Fleet voice: the Kokoro-82M voice (af_heart), the same local voice as RefereAI.
   BaseVoice.speak(text, {onend}) plays, in order of preference:
     1. a pre-rendered clip in audio/ (listed in audio/manifest.json, works on the static site)
     2. on localhost, the local voice server (python -m brain.tts --serve 8744);
        on the hosted site, Gemini text-to-speech via /api/tts (6 s budget, cached per line)
     3. the browser's own voice
   BaseVoice.stop() stops whatever is playing. The key matches brain/tts.py: FNV-1a 32-bit of the
   trimmed, single-spaced text. */
(() => {
  "use strict";
  const SERVER = "http://localhost:8744/tts";
  const base = new URL("audio/", document.currentScript ? document.currentScript.src : location.href);
  const CLOUD = new URL("/api/tts", location.href).href;
  const isLocal = () => /^(localhost|127\.0\.0\.1)$/.test(location.hostname);
  const cloudCache = new Map();
  let manifest = null, audio = null, token = 0, serverUp = null, cloudUp = null;

  const normalize = t => String(t).replace(/\s+/g, " ").trim();
  function key(text) {
    let h = 0x811c9dc5;
    for (const b of new TextEncoder().encode(normalize(text))) h = Math.imul(h ^ b, 0x01000193) >>> 0;
    return h.toString(16).padStart(8, "0");
  }

  async function loadManifest() {
    if (manifest) return manifest;
    try {
      const r = await fetch(new URL("manifest.json", base), {cache: "no-store"});
      manifest = r.ok ? await r.json() : {};
    } catch { manifest = {}; }
    return manifest;
  }

  async function fromServer(text) {
    if (serverUp === false || !isLocal()) return null;
    try {
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 15000);
      const r = await fetch(SERVER, {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({text: normalize(text)}), signal: ctl.signal});
      clearTimeout(timer);
      serverUp = r.ok;
      return r.ok ? URL.createObjectURL(await r.blob()) : null;
    } catch { serverUp = false; return null; }
  }

  async function fromCloud(text) {
    if (cloudUp === false || isLocal()) return null;
    if (cloudCache.has(text)) return cloudCache.get(text);
    try {
      const human = window.BaseHuman ? await window.BaseHuman.token() : "";
      const ctl = new AbortController();
      const timer = setTimeout(() => ctl.abort(), 6000);
      const r = await fetch(CLOUD, {method: "POST", headers: {"Content-Type": "application/json", "cf-turnstile-response": human},
        body: JSON.stringify({text}), signal: ctl.signal});
      if (!r.ok) { clearTimeout(timer); if (r.status === 404 || r.status === 503) cloudUp = false; return null; }
      const blob = await r.blob();
      clearTimeout(timer);
      if (!/audio/.test(blob.type || r.headers.get("Content-Type") || "")) return null;
      const url = URL.createObjectURL(blob);
      cloudCache.set(text, url);
      return url;
    } catch { return null; }
  }

  function browserVoice(text, onend) {
    if (!("speechSynthesis" in window)) { if (onend) onend(); return; }
    const u = new SpeechSynthesisUtterance(normalize(text));
    u.rate = 0.95;
    if (onend) u.onend = onend;
    speechSynthesis.speak(u);
  }

  function stop() {
    token++;
    if (audio) { audio.pause(); audio = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
  }

  async function speak(text, opts = {}) {
    stop();
    const mine = token;
    const t = normalize(text);
    if (!t) return;
    const m = await loadManifest();
    const k = key(t);
    const src = m[k] ? new URL(m[k], base).href : (await fromServer(t)) || (await fromCloud(t));
    if (mine !== token) return; // a newer speak() or stop() won
    if (!src) return browserVoice(t, opts.onend);
    audio = new Audio(src);
    audio.onended = () => { if (mine === token && opts.onend) opts.onend(); };
    audio.play().catch(() => { if (mine === token) browserVoice(t, opts.onend); });
  }

  window.BaseVoice = {speak, stop, key, available: true};
})();
