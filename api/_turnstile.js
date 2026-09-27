// Shared Cloudflare Turnstile check for the functions that spend the Gemini key.
// When TURNSTILE_SECRET is unset the check is skipped, so the site works before keys are added.
// Never logs the secret or the token.
const VERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify';

function clientIp(req) {
  const h = req.headers || {};
  return (h['cf-connecting-ip'] || String(h['x-forwarded-for'] || '').split(',')[0] || '').trim() || undefined;
}

// Returns true when the request may continue.
async function human(req, fetchImpl = fetch) {
  const secret = process.env.TURNSTILE_SECRET;
  if (!secret) return true;
  const token = String((req.headers || {})['cf-turnstile-response'] || '');
  if (!token) return false;
  const form = new URLSearchParams({ secret, response: token });
  const ip = clientIp(req);
  if (ip) form.set('remoteip', ip);
  try {
    const r = await fetchImpl(VERIFY, { method: 'POST', body: form, signal: AbortSignal.timeout(5000) });
    const d = await r.json();
    return d && d.success === true;
  } catch {
    return false;
  }
}

module.exports = { human };
