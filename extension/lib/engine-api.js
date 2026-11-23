/*
 * Seeker — engine REST client for the browser extension.
 * Contract of record: docs/build_docs/03-api-design.md; shapes mirror
 * mobile/src/engineApi.ts (thin-shell standing rule 2: transport only, no
 * engine logic here, no client-specific logic in the engine).
 *
 * UMD so the same file serves node's test runner (module.exports) and the
 * background worker (importScripts -> root.SeekerApi).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.SeekerApi = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // This deployment's tailnet node (joined 2026-11-05; served over HTTPS via
  // `tailscale serve`, docs 13). Plain-http hosts work too (LAN debug).
  const DEFAULT_BASE_URL = 'https://search-engine-2.taile24e8b.ts.net';

  function normalizeBaseUrl(raw) {
    const s = String(raw == null ? '' : raw).trim().replace(/\/+$/, '');
    if (!s) throw new TypeError('engine URL is empty');
    let u;
    try {
      u = new URL(s);
    } catch (e) {
      throw new TypeError('not a URL: ' + s);
    }
    if (u.protocol !== 'https:' && u.protocol !== 'http:') {
      throw new TypeError('engine URL must be http(s): ' + s);
    }
    return s;
  }

  // X-Request-Id per call — the engine echoes it on every response.
  // crypto.randomUUID is unavailable in older workers, so roll a v4.
  function requestId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function buildHeaders(token, hasBody) {
    const h = { 'X-Request-Id': requestId() };
    if (hasBody) h['Content-Type'] = 'application/json';
    if (token) h['Authorization'] = 'Bearer ' + token;
    return h;
  }

  // {"detail":{"code","message"}} — the engine's error shape (docs 03).
  function parseDetail(parsed) {
    const d = parsed && typeof parsed === 'object' ? parsed.detail : null;
    if (d && typeof d === 'object' && d.code) {
      return { code: String(d.code), message: d.message != null ? String(d.message) : 'engine error' };
    }
    return null;
  }

  function EngineError(status, code, message) {
    this.name = 'EngineError';
    this.status = status;
    this.code = code;
    this.message = message;
  }
  EngineError.prototype = Object.create(Error.prototype);
  EngineError.prototype.constructor = EngineError;

  async function call(baseUrl, token, path, init, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, timeoutMs);
    let res;
    try {
      res = await fetch(normalizeBaseUrl(baseUrl) + path, {
        method: init.method,
        body: init.body,
        headers: buildHeaders(token, !!init.body),
        signal: controller.signal,
      });
    } catch (err) {
      // Distinguish abort (timeout) from network failure for the UI layer.
      if (controller.signal.aborted) {
        throw new EngineError(0, 'TIMEOUT', 'request to ' + path + ' timed out after ' + timeoutMs + 'ms');
      }
      throw new EngineError(0, 'NETWORK_ERROR', 'cannot reach engine at ' + baseUrl);
    } finally {
      clearTimeout(timer);
    }

    const text = await res.text();
    let parsed = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch (e) {
      // Non-JSON body (proxy error page, plain 404) — handled by the generic branch.
    }

    if (!res.ok) {
      const detail = parseDetail(parsed);
      if (detail) throw new EngineError(res.status, detail.code, detail.message);
      throw new EngineError(res.status, 'ENGINE_ERROR', 'HTTP ' + res.status + ' from ' + path);
    }
    return parsed;
  }

  // Anonymous liveness probe (the only route without auth) — options "Test".
  function health(baseUrl, timeoutMs) {
    return call(baseUrl, '', '/v1/health', { method: 'GET' }, timeoutMs || 8000);
  }

  function listSources(baseUrl, token, timeoutMs) {
    return call(baseUrl, token, '/v1/sources', { method: 'GET' }, timeoutMs || 15000);
  }

  function search(baseUrl, token, opts) {
    const o = opts || {};
    const filters = o.sourceIds && o.sourceIds.length ? { source_id: o.sourceIds } : undefined;
    return call(
      baseUrl,
      token,
      '/v1/search',
      { method: 'POST', body: JSON.stringify({ query: o.query, top_k: o.topK || 20, filters: filters }) },
      o.timeoutMs || 30000,
    );
  }

  return {
    DEFAULT_BASE_URL: DEFAULT_BASE_URL,
    normalizeBaseUrl: normalizeBaseUrl,
    requestId: requestId,
    buildHeaders: buildHeaders,
    parseDetail: parseDetail,
    EngineError: EngineError,
    health: health,
    listSources: listSources,
    search: search,
  };
});
