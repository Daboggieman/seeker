/* Tests for the extension's engine client (lib/engine-api.js) — node:test, CJS.
 * Run: node --test extension/tests/  (from the repo root) */
const test = require('node:test');
const assert = require('node:assert');
const API = require('../lib/engine-api.js');

test('normalizeBaseUrl: trims, strips trailing slashes, keeps https', () => {
  assert.strictEqual(API.normalizeBaseUrl('  https://engine.example.net/  '), 'https://engine.example.net');
  assert.strictEqual(API.normalizeBaseUrl('https://search-engine-2.taile24e8b.ts.net///'), 'https://search-engine-2.taile24e8b.ts.net');
  assert.strictEqual(API.normalizeBaseUrl('http://127.0.0.1:8420'), 'http://127.0.0.1:8420');
});

test('normalizeBaseUrl: rejects empty and non-http schemes', () => {
  assert.throws(() => API.normalizeBaseUrl(''), TypeError);
  assert.throws(() => API.normalizeBaseUrl('   '), TypeError);
  assert.throws(() => API.normalizeBaseUrl('ftp://x'), TypeError);
  assert.throws(() => API.normalizeBaseUrl('not a url'), TypeError);
});

test('buildHeaders: bearer only with token, request id always, content-type only with body', () => {
  const withToken = API.buildHeaders('tok', true);
  assert.strictEqual(withToken.Authorization, 'Bearer tok');
  assert.strictEqual(withToken['Content-Type'], 'application/json');
  assert.match(withToken['X-Request-Id'], /^[0-9a-f-]{36}$/);

  const anon = API.buildHeaders('', false);
  assert.strictEqual(anon.Authorization, undefined);
  assert.strictEqual(anon['Content-Type'], undefined);
  assert.match(anon['X-Request-Id'], /^[0-9a-f-]{36}$/);
});

test('requestId: v4 shape, unique across calls', () => {
  const a = API.requestId();
  const b = API.requestId();
  assert.match(a, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notStrictEqual(a, b);
});

test('parseDetail: maps the engine error shape, null on junk', () => {
  assert.deepStrictEqual(API.parseDetail({ detail: { code: 'UNAUTHORIZED', message: 'bad token' } }), { code: 'UNAUTHORIZED', message: 'bad token' });
  assert.strictEqual(API.parseDetail(null), null);
  assert.strictEqual(API.parseDetail({ detail: 'string detail' }), null);
  assert.strictEqual(API.parseDetail({ detail: {} }), null);
  assert.strictEqual(API.parseDetail({ foo: 1 }), null);
});

test('search body: top_k 20 default, filters only when sourceIds given', async () => {
  // Capture the body by stubbing fetch for both calls; restore afterwards.
  const calls = [];
  const origFetch = global.fetch;
  global.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { ok: true, status: 200, text: async () => JSON.stringify({ results: [] }) };
  };
  try {
    await API.search('http://127.0.0.1:9', 'tok', { query: 'needle' });
    const { url, init } = calls[0];
    assert.strictEqual(url, 'http://127.0.0.1:9/v1/search');
    const body = JSON.parse(init.body);
    assert.strictEqual(body.query, 'needle');
    assert.strictEqual(body.top_k, 20);
    assert.strictEqual(body.filters, undefined);

    await API.search('http://127.0.0.1:9', 'tok', { query: 'x', sourceIds: ['gsmhub'] });
    const body2 = JSON.parse(calls[1].init.body);
    assert.deepStrictEqual(body2.filters, { source_id: ['gsmhub'] });
  } finally {
    global.fetch = origFetch;
  }
});

test('search maps engine {"detail":{code,message}} to EngineError', async () => {
  const origFetch = global.fetch;
  global.fetch = async () => ({
    ok: false,
    status: 401,
    text: async () => JSON.stringify({ detail: { code: 'UNAUTHORIZED', message: 'missing or invalid bearer token' } }),
  });
  try {
    await API.search('http://127.0.0.1:9', 'bad', { query: 'x' });
    assert.fail('should have thrown');
  } catch (err) {
    assert.strictEqual(err.name, 'EngineError');
    assert.strictEqual(err.status, 401);
    assert.strictEqual(err.code, 'UNAUTHORIZED');
    assert.strictEqual(err.message, 'missing or invalid bearer token');
  } finally {
    global.fetch = origFetch;
  }
});

test('connection refused maps to NETWORK_ERROR with status 0', async () => {
  const err = await API.search('http://127.0.0.1:9', 'tok', { query: 'x' }).then(
    () => null,
    (e) => e,
  );
  assert.ok(err, 'should throw');
  assert.strictEqual(err.code, 'NETWORK_ERROR');
  assert.strictEqual(err.status, 0);
});

test('non-JSON error body maps to generic ENGINE_ERROR', async () => {
  const origFetch = global.fetch;
  global.fetch = async () => ({ ok: false, status: 502, text: async () => '<html>Bad Gateway</html>' });
  try {
    await API.search('http://127.0.0.1:9', 'tok', { query: 'x' });
    assert.fail('should have thrown');
  } catch (err) {
    assert.strictEqual(err.code, 'ENGINE_ERROR');
    assert.strictEqual(err.status, 502);
  } finally {
    global.fetch = origFetch;
  }
});

test('listSources GETs /v1/sources with bearer', async () => {
  const calls = [];
  const origFetch = global.fetch;
  global.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return { ok: true, status: 200, text: async () => JSON.stringify([{ id: 'gsmhub', type: 'filesystem', root_path: '/sources/home', last_synced_at: null, status: 'idle' }]) };
  };
  try {
    const sources = await API.listSources('http://127.0.0.1:9', 'tok');
    assert.strictEqual(calls[0].url, 'http://127.0.0.1:9/v1/sources');
    assert.strictEqual(calls[0].init.method, 'GET');
    assert.strictEqual(calls[0].init.headers.Authorization, 'Bearer tok');
    assert.strictEqual(sources[0].id, 'gsmhub');
  } finally {
    global.fetch = origFetch;
  }
});
