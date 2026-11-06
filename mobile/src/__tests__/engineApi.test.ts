// Unit tests for the engine API client — request shaping, auth header, error mapping.

import {EngineError, health, listSources, search} from '../engineApi';

const fetchMock = jest.fn();
globalThis.fetch = fetchMock as unknown as typeof fetch;

function okJson(body: unknown) {
  return {
    ok: true,
    status: 200,
    text: async () => JSON.stringify(body),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
});

describe('search', () => {
  it('POSTs query/top_k to /v1/search with bearer auth and X-Request-Id, omitting empty filters', async () => {
    fetchMock.mockResolvedValueOnce(okJson({results: []}));
    await search('http://engine:8420', 'tok', {query: 'tailscale sidecar', topK: 3});
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://engine:8420/v1/search');
    expect(init.method).toBe('POST');
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer tok');
    expect(headers['X-Request-Id']).toMatch(/[0-9a-f-]{36}/);
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({query: 'tailscale sidecar', top_k: 3, filters: undefined});
  });

  it('sends filters.source_id when sourceIds are given', async () => {
    fetchMock.mockResolvedValueOnce(okJson({results: []}));
    await search('http://engine:8420', 'tok', {
      query: 'q',
      sourceIds: ['fs-home', 'gdrive-personal'],
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.filters).toEqual({source_id: ['fs-home', 'gdrive-personal']});
  });

  it('maps the engine error shape {detail:{code,message}} to EngineError', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 401,
      text: async () =>
        JSON.stringify({detail: {code: 'UNAUTHORIZED', message: 'missing or invalid bearer token'}}),
    });
    await expect(search('http://engine:8420', 'bad', {query: 'q'})).rejects.toMatchObject({
      name: 'EngineError',
      status: 401,
      code: 'UNAUTHORIZED',
      message: 'missing or invalid bearer token',
    }) as unknown as EngineError;
  });

  it('falls back to a generic EngineError on non-JSON error bodies (proxy 404s)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      text: async () => 'Not Found',
    });
    await expect(search('http://engine:8420', 'tok', {query: 'q'})).rejects.toMatchObject({
      status: 404,
      code: 'ENGINE_ERROR',
    });
  });
});

describe('listSources', () => {
  it('GETs /v1/sources with bearer auth and parses the record list', async () => {
    fetchMock.mockResolvedValueOnce(
      okJson([{id: 'fs-home', type: 'fs', root_path: '/sources/home', last_synced_at: null, status: 'ok'}]),
    );
    const sources = await listSources('http://engine:8420/', 'tok');
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://engine:8420/v1/sources'); // trailing slash trimmed
    expect(init.method).toBe('GET');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    expect(sources).toHaveLength(1);
    expect(sources[0].id).toBe('fs-home');
  });
});

describe('health', () => {
  it('GETs /v1/health anonymously (no Authorization header)', async () => {
    fetchMock.mockResolvedValueOnce(okJson({status: 'ok'}));
    await health('http://engine:8420');
    const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});
