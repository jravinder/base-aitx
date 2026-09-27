// POST /api/tts  {text}  -> audio/wav
// Speaks one voice-guide line with Gemini text-to-speech, for lines that have no pre-rendered clip.
// The key comes from GEMINI_API_KEY on the server only; it never reaches the page, the response or the logs.
// Model ids: https://ai.google.dev/gemini-api/docs/speech-generation
const MODEL = process.env.GEMINI_TTS_MODEL || 'gemini-3.8-flash-tts';
const VOICE = process.env.GEMINI_TTS_VOICE || 'Kore';
const MAX_CHARS = 400;

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
  for await (const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

// Gemini returns raw 24 kHz 16-bit mono PCM; a browser <audio> needs a RIFF/WAV header.
function wav(pcm, rate = 24000) {
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + pcm.length, 4); h.write('WAVE', 8);
  h.write('fmt ', 12); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34);
  h.write('data', 36); h.writeUInt32LE(pcm.length, 40);
  return Buffer.concat([h, pcm]);
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'use POST' });
  const key = process.env.GEMINI_API_KEY;
  if (!key) return send(res, 503, { error: 'voice unavailable' });
  let body;
  try { body = await readBody(req); } catch { return send(res, 400, { error: 'body must be JSON' }); }
  const text = typeof body.text === 'string' ? body.text.replace(/\s+/g, ' ').trim() : '';
  if (!text) return send(res, 400, { error: 'text required' });
  if (text.length > MAX_CHARS) return send(res, 413, { error: 'text too long' });
  try {
    const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
      body: JSON.stringify({
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ['AUDIO'],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: VOICE } } }
        }
      }),
      signal: AbortSignal.timeout(20000)
    });
    if (!r.ok) return send(res, 502, { error: 'voice failed', status: r.status });
    const data = await r.json();
    const part = data?.candidates?.[0]?.content?.parts?.find(p => p.inlineData || p.inline_data);
    const b64 = (part?.inlineData || part?.inline_data)?.data;
    if (!b64) return send(res, 502, { error: 'voice failed' });
    let audio = Buffer.from(b64, 'base64');
    const mime = (part.inlineData || part.inline_data).mimeType || '';
    if (audio.subarray(0, 4).toString() !== 'RIFF') audio = wav(audio, Number((/rate=(\d+)/.exec(mime) || [])[1]) || 24000);
    res.statusCode = 200;
    res.setHeader('Content-Type', 'audio/wav');
    res.setHeader('Cache-Control', 'public, max-age=86400');
    res.end(audio);
  } catch {
    return send(res, 502, { error: 'voice failed' });
  }
};
