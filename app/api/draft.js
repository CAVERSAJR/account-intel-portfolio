// POST /api/draft — streams a live model draft as server-sent events: start, token*, stage, done | error.
import { ApiError, MAX_BODY_BYTES, MAX_RESPONSE_BYTES, MAX_TOKENS, MODEL, PROVIDER_URL, SYSTEM_PROMPT, TIMEOUT_MS,
  constrainHeld, constrainNetNew, motionPolicy, rateLimit, validateModelResponse, validateRequest } from './_lib/guard.js';

const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
const fail = e => new Response(JSON.stringify({ error: e instanceof ApiError ? e.message : 'The request could not be completed.' }),
  { status: e instanceof ApiError ? e.status : 500, headers: JSON_HEADERS });

// Same reminder the local server sends: name the evidence that is the seller's own account record.
function scenarioNote(body) {
  const ids = body.evidence.filter(item => item.kind === 'scenario').map(item => item.id);
  if (!ids.length) return '';
  return "For this account these evidence IDs are the seller's own account records: " + ids.join(', ')
    + ". Use their numbers (usage, spend, satisfaction, open issues) where they matter, as internal account data. Never call them fictional, illustrative or a scenario.";
}

function sameOrigin(request) {
  const origin = request.headers.get('origin');
  if (!origin) return true;
  try { return new URL(origin).host === request.headers.get('host'); } catch { return false; }
}

export async function POST(request) {
  let body, policy, key;
  try {
    if (!sameOrigin(request)) throw new ApiError(403, 'Cross-origin requests are not allowed.');
    key = (process.env.DEEPSEEK_API_KEY || '').trim();
    if (!key) throw new ApiError(503, 'AI is not connected on this site.');
    if (!(request.headers.get('content-type') || '').startsWith('application/json')) throw new ApiError(415, 'Send application/json.');
    const raw = await request.text();
    if (!raw || Buffer.byteLength(raw, 'utf8') > MAX_BODY_BYTES) throw new ApiError(413, 'The request body exceeds the allowed size.');
    try { body = JSON.parse(raw); } catch { throw new ApiError(400, 'The request must contain valid JSON.'); }
    validateRequest(body);
    policy = motionPolicy(body.account_id);
    rateLimit((request.headers.get('x-forwarded-for') || 'unknown').split(',')[0].trim());
  } catch (e) { return fail(e); }

  const enc = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const emit = (name, value) => controller.enqueue(enc.encode(`event: ${name}\ndata: ${JSON.stringify(value)}\n\n`));
      const abort = new AbortController(); const timer = setTimeout(() => abort.abort(), TIMEOUT_MS);
      const started = Date.now();
      emit('start', { model: MODEL, sources: body.evidence.length });
      try {
        const res = await fetch(PROVIDER_URL, {
          method: 'POST', signal: abort.signal, redirect: 'error',
          headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: MODEL, temperature: 0.2, max_tokens: MAX_TOKENS, stream: true,
            stream_options: { include_usage: true }, response_format: { type: 'json_object' }, thinking: { type: 'disabled' },
            messages: [{ role: 'system', content: SYSTEM_PROMPT + scenarioNote(body) },
              { role: 'user', content: JSON.stringify({ ...body, account_policy: policy }) }] }),
        });
        if (!res.ok || !res.body) throw new ApiError(502, 'The model provider could not complete this request.');
        const reader = res.body.getReader(), dec = new TextDecoder();
        let buf = '', content = '', finish = null, usage = {};
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let nl;
          while ((nl = buf.indexOf('\n')) >= 0) {
            const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
            if (!line.startsWith('data:')) continue;
            const data = line.slice(5).trim();
            if (data === '[DONE]') continue;
            const chunk = JSON.parse(data);
            if (chunk.usage && typeof chunk.usage === 'object') usage = chunk.usage;
            const choice = chunk.choices?.[0];
            const delta = choice?.delta?.content;
            if (typeof delta === 'string' && delta) {
              content += delta;
              if (Buffer.byteLength(content, 'utf8') > MAX_RESPONSE_BYTES) throw new ApiError(502, 'The model response exceeded the allowed size.');
              emit('token', { t: delta });
            }
            if (choice?.finish_reason) finish = choice.finish_reason;
          }
        }
        if (finish !== 'stop') throw new ApiError(502, 'The model did not return a complete plan. Try again.');
        emit('stage', { stage: 'checking' });
        let parsed;
        try { parsed = JSON.parse(content); } catch { throw new ApiError(502, 'The model returned an invalid response. The prior plan is unchanged.'); }
        let result = validateModelResponse(parsed, body);
        result = constrainNetNew(constrainHeld(result, policy), policy, body);
        result.provider = 'deepseek';
        result.elapsed_ms = Date.now() - started;
        const safe = {};
        for (const k of ['prompt_tokens', 'completion_tokens']) if (Number.isInteger(usage[k]) && usage[k] >= 0) safe[k] = usage[k];
        if (Object.keys(safe).length) result.usage = safe;
        emit('done', result);
      } catch (e) {
        emit('error', { error: e instanceof ApiError ? e.message : e?.name === 'AbortError'
          ? 'The model request timed out after 30 seconds. The prior plan is unchanged.' : 'The model provider is unavailable. The prior plan is unchanged.' });
      } finally {
        clearTimeout(timer); controller.close();
      }
    },
  });
  return new Response(stream, { headers: { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}

export function GET() { return fail(new ApiError(405, 'Use POST.')); }
