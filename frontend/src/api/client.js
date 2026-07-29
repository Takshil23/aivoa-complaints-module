/**
 * Backend client.
 *
 * The chat and upload endpoints are streaming POSTs, so they are read with
 * `fetch` + a ReadableStream rather than `EventSource` (which only does GET).
 */

const BASE = '/api';

async function postJson(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

export const openSession = (sessionId) => postJson('/session', { sessionId });
export const resetSession = (sessionId) => postJson('/session/reset', { sessionId });
export const commitComplaint = (sessionId) =>
  postJson('/complaints/commit', { sessionId });
export const runAiFeature = (feature, sessionId) =>
  postJson(`/ai/${feature}`, { sessionId });

export async function fetchLedger() {
  const res = await fetch(`${BASE}/complaints`);
  if (!res.ok) throw new Error('Could not load the ledger');
  return res.json();
}

/**
 * Read an SSE body, invoking `onEvent` for each `data:` frame.
 */
async function consumeStream(response, onEvent) {
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    let detail = `Request failed (${response.status})`;
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {
      /* keep the generic message */
    }
    throw new Error(detail);
  }
  if (!response.body) throw new Error('Streaming is not supported by this browser.');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let split;
    while ((split = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          onEvent(JSON.parse(raw));
        } catch {
          /* ignore a malformed frame rather than killing the stream */
        }
      }
    }
  }
}

export async function streamChat({ sessionId, message }, onEvent) {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId, message }),
  });
  return consumeStream(response, onEvent);
}

export async function streamUpload({ sessionId, file }, onEvent) {
  const form = new FormData();
  form.append('file', file);
  if (sessionId) form.append('sessionId', sessionId);

  const response = await fetch(`${BASE}/documents/stream`, {
    method: 'POST',
    body: form,
  });
  return consumeStream(response, onEvent);
}
