// POST /api/read-photo  {image: base64 JPEG (resized by the page), mime, shot}
// Checks one checklist photo with Gemini, using the shot prompt in web/data/photo-shots.json.
// The key comes from GEMINI_API_KEY on the server only; it never reaches the page, the response or the logs.
const MODEL = process.env.GEMINI_MODEL || 'gemini-3.8-flash';
const MAX_BYTES = 4 * 1024 * 1024;
const SHOTS = require('../web/data/photo-shots.json');
const { human } = require('./_turnstile');
// Same shot-aware prompt as brain/ask.py and the page: judge only what this checklist shot asks for.
function prompt(shot) {
  const id = Object.hasOwn(SHOTS.shots, shot) ? shot : SHOTS.default;
  const s = SHOTS.shots[id];
  return { id, text: SHOTS.prompt.replace('{label}', s.label).replace('{asks}', s.asks) };
}
const TYPES = ['panel_open', 'panel_closed', 'meter_exterior', 'other'];

function send(res, code, obj) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(obj));
}

async function readBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  if (typeof req.body === 'string') return JSON.parse(req.body);
  const chunks = [];
  let size = 0;
  for await (const c of req) { size += c.length; if (size > MAX_BYTES * 1.4) throw Object.assign(new Error('large'), { code: 413 }); chunks.push(c); }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

function shape(out, seconds, shot) {
  const amps = Number.isInteger(out.main_breaker_amps) && out.main_breaker_amps >= 30 && out.main_breaker_amps <= 600 ? out.main_breaker_amps : null;
  return {
    photo_type: TYPES.includes(out.photo_type) ? out.photo_type : 'other',
    manufacturer: typeof out.brand === 'string' && out.brand.trim() ? out.brand.trim().slice(0, 40) : null,
    main_breaker_amps: amps,
    usable: out.pass === true,
    retake_reason: typeof out.retake_reason === 'string' ? out.retake_reason.slice(0, 300) : null,
    confidence: typeof out.confidence === 'number' ? Math.max(0, Math.min(1, out.confidence)) : null,
    shot,
    model: MODEL,
    seconds
  };
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'use POST' });
  const key = process.env.GEMINI_API_KEY;
  if (!key) return send(res, 503, { error: 'reading unavailable' });
  if (!(await human(req))) return send(res, 403, { error: 'bot check failed' });
  let body;
  try { body = await readBody(req); } catch (e) { return send(res, e.code === 413 ? 413 : 400, { error: e.code === 413 ? 'image too large' : 'body must be JSON' }); }
  const image = typeof body.image === 'string' ? body.image.replace(/^data:[^,]*,/, '') : '';
  const mime = /^image\/(jpeg|png|webp)$/.test(body.mime) ? body.mime : 'image/jpeg';
  if (!image || !/^[A-Za-z0-9+/=\s]+$/.test(image)) return send(res, 400, { error: 'image must be base64' });
  if (Math.floor(image.length * 3 / 4) > MAX_BYTES) return send(res, 413, { error: 'image too large' });
  const p = prompt(body.shot);
  const t0 = Date.now();
  try {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
      body: JSON.stringify({
        contents: [{ parts: [{ text: p.text }, { inline_data: { mime_type: mime, data: image } }] }],
        generationConfig: { responseMimeType: 'application/json', temperature: 0 }
      }),
      signal: AbortSignal.timeout(45000)
    });
    if (!r.ok) return send(res, 502, { error: 'reading failed', status: r.status });
    const data = await r.json();
    const text = data?.candidates?.[0]?.content?.parts?.map(p => p.text || '').join('') || '';
    const out = JSON.parse(text);
    return send(res, 200, shape(out && typeof out === 'object' ? out : {}, Math.round((Date.now() - t0) / 100) / 10, p.id));
  } catch {
    return send(res, 502, { error: 'reading failed' });
  }
};
