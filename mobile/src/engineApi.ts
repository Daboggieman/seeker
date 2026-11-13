// Typed client for the Seeker engine REST API — contract of record:
// docs/build_docs/03-api-design.md (shapes as implemented in engine/src/seeker/api/app.py).
// Thin by standing rule 2: plain fetch against /v1/*, bearer token on every call,
// no client-specific logic beyond transport.

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  title: string;
  path: string;
  snippet: string;
  score: number;
  source_id: string;
  page: number | null;
  position: number;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface SourceRecord {
  id: string;
  type: string;
  root_path: string;
  last_synced_at: string | null;
  status: string;
}

export interface SearchOptions {
  query: string;
  topK?: number;
  sourceIds?: string[];
  timeoutMs?: number;
}

/** Engine-side error, carrying the machine-readable code from `{"detail": {"code", "message"}}`. */
export class EngineError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'EngineError';
  }
}

/**
 * X-Request-Id per call — the engine echoes it on every response
 * (app.py request_id middleware). Hermes has no crypto.randomUUID, so roll a v4.
 */
function requestId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

async function call<T>(
  baseUrl: string,
  token: string,
  path: string,
  init: Omit<RequestInit, 'headers'>,
  tokenRequired: boolean,
  timeoutMs: number,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = {
    'X-Request-Id': requestId(),
    ...(init.body ? {'Content-Type': 'application/json'} : {}),
    ...(tokenRequired ? {Authorization: `Bearer ${token}`} : {}),
  };
  let res: Response;
  try {
    res = await fetch(`${baseUrl.replace(/\/+$/, '')}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    // Distinguish abort (timeout) from network failure for the UI layer.
    if (controller.signal.aborted) {
      throw new EngineError(0, 'TIMEOUT', `request to ${path} timed out after ${timeoutMs}ms`);
    }
    throw new EngineError(0, 'NETWORK_ERROR', `cannot reach engine at ${baseUrl}`);
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    // Non-JSON body (proxy error page, plain 404) — fall through to the generic branch.
  }

  if (!res.ok) {
    const detail = (parsed as {detail?: {code?: string; message?: string}} | null)?.detail;
    if (detail && typeof detail === 'object' && detail.code) {
      throw new EngineError(res.status, detail.code, detail.message ?? 'engine error');
    }
    throw new EngineError(res.status, 'ENGINE_ERROR', `HTTP ${res.status} from ${path}`);
  }
  return parsed as T;
}

/** Anonymous liveness probe (the only route without auth) — used for the settings "test" button. */
export function health(baseUrl: string, timeoutMs = 8000): Promise<unknown> {
  return call<unknown>(baseUrl, '', '/v1/health', {method: 'GET'}, false, timeoutMs);
}

export function listSources(
  baseUrl: string,
  token: string,
  timeoutMs = 15000,
): Promise<SourceRecord[]> {
  return call<SourceRecord[]>(baseUrl, token, '/v1/sources', {method: 'GET'}, true, timeoutMs);
}

export function search(
  baseUrl: string,
  token: string,
  {query, topK = 5, sourceIds, timeoutMs = 30000}: SearchOptions,
): Promise<SearchResponse> {
  const filters = sourceIds?.length ? {source_id: sourceIds} : undefined;
  return call<SearchResponse>(
    baseUrl,
    token,
    '/v1/search',
    {method: 'POST', body: JSON.stringify({query, top_k: topK, filters})},
    true,
    timeoutMs,
  );
}
