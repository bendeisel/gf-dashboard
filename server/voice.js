// Voice dictation via Wispr Flow's REST transcription API.
// The browser records a clip, converts it to 16kHz mono 16-bit WAV, and POSTs the
// base64 here; we forward it to Wispr with the API key (which never leaves the server)
// and hand back the transcript for the terminal to paste. GET-equivalent: read-only,
// no state changed on our side.
//
// Config (.env): WISPR_API_KEY (required to enable voice), WISPR_API_URL (optional override).
// Key access is exclusive/enterprise — see https://api-docs.wisprflow.ai/

const DEFAULT_URL = 'https://platform-api.wisprflow.ai/api/v1/dash/api';

export function voiceConfigured() {
  return !!process.env.WISPR_API_KEY;
}

// The REST response shape isn't documented; the WebSocket API puts the transcript at
// body.text, so try that plus the other plausible spellings before giving up.
function extractText(obj) {
  if (obj == null) return '';
  if (typeof obj === 'string') return obj;
  const cands = [
    obj.text, obj.body?.text, obj.transcript, obj.transcription,
    obj.result?.text, obj.data?.text, obj.body?.transcript, obj.results?.[0]?.text,
  ];
  for (const c of cands) if (typeof c === 'string' && c.trim()) return c;
  return '';
}

export async function transcribe({ audioBase64, language }) {
  const key = process.env.WISPR_API_KEY;
  if (!key) { const e = new Error('voice_not_configured'); e.code = 'NO_KEY'; throw e; }

  const body = {
    audio: audioBase64,
    language: Array.isArray(language) && language.length ? language.slice(0, 1) : ['en'],
    context: {
      // app.type is an enum: email | ai | other. "other" avoids email-style formatting
      // so dictated shell/Claude commands come through clean.
      app: { name: 'GF Dashboard Terminal', type: 'other' },
      dictionary_context: [],
      textbox_contents: { before_text: '', selected_text: '', after_text: '' },
    },
  };

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  let resp;
  try {
    resp = await fetch(process.env.WISPR_API_URL || DEFAULT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
  } catch (err) {
    const e = new Error(err.name === 'AbortError' ? 'wispr_timeout' : 'wispr_unreachable');
    e.code = 'UPSTREAM'; e.detail = String(err.message || err); throw e;
  } finally {
    clearTimeout(timer);
  }

  const raw = await resp.text();
  if (!resp.ok) {
    const e = new Error(`wispr_${resp.status}`);
    e.code = 'UPSTREAM'; e.status = resp.status; e.detail = raw.slice(0, 500); throw e;
  }
  let json; try { json = JSON.parse(raw); } catch { json = raw; }
  return { text: extractText(json).trim(), raw: json };
}
