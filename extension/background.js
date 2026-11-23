/*
 * Seeker MV3 background — classic script (no static imports) so the same file
 * runs as a Chrome service worker and a Firefox MV3 event page via importScripts.
 *
 * Holds the engine URL + bearer token (chrome.storage.local) and does every
 * engine call: the content script never sees the token and the page never sees
 * either (ADR-0003). Standing rule 11: nothing here logs the token or result
 * content.
 */
importScripts('lib/engine-api.js');
const API = self.SeekerApi;

async function getSettings() {
  const stored = await chrome.storage.local.get(['baseUrl', 'token']);
  return {
    baseUrl: stored.baseUrl || API.DEFAULT_BASE_URL,
    token: stored.token || '',
  };
}

async function doSearch(msg) {
  const t0 = Date.now();
  try {
    const s = await getSettings();
    const data = await API.search(s.baseUrl, s.token, {
      query: msg.query,
      topK: 20,
      sourceIds: msg.sourceIds,
    });
    return { ok: true, results: (data && data.results) || [], elapsedMs: Date.now() - t0 };
  } catch (err) {
    return {
      ok: false,
      error: { status: err.status || 0, code: err.code || 'ERROR', message: err.message || String(err) },
      elapsedMs: Date.now() - t0,
    };
  }
}

async function doSources() {
  const s = await getSettings();
  const sources = await API.listSources(s.baseUrl, s.token);
  return { ok: true, sources: sources || [] };
}

// Options-page "Test" — proves reachability AND token in one authed call
// (same reasoning as the mobile client's Test button, docs 13).
async function doProbe() {
  const s = await getSettings();
  const sources = await API.listSources(s.baseUrl, s.token);
  return { ok: true, count: (sources || []).length };
}

chrome.action.onClicked.addListener(function () {
  chrome.runtime.openOptionsPage();
});

chrome.commands.onCommand.addListener(function (cmd) {
  if (cmd !== 'toggle-seeker') return;
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    const tab = tabs && tabs[0];
    if (tab && typeof tab.id === 'number') {
      chrome.tabs.sendMessage(tab.id, { type: 'seeker:toggle' }).catch(function () {
        // Page without the content script (chrome://, store pages) — ignore.
      });
    }
  });
});

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || typeof msg.type !== 'string' || msg.type.indexOf('seeker:') !== 0) return false;
  (async function () {
    try {
      if (msg.type === 'seeker:search') sendResponse(await doSearch(msg));
      else if (msg.type === 'seeker:sources') sendResponse(await doSources());
      else if (msg.type === 'seeker:probe') sendResponse(await doProbe());
      else sendResponse({ ok: false, error: { code: 'BAD_MESSAGE', message: 'unknown type ' + msg.type } });
    } catch (err) {
      sendResponse({
        ok: false,
        error: { status: err.status || 0, code: err.code || 'ERROR', message: err.message || String(err) },
      });
    }
  })();
  return true; // keep the channel open for the async sendResponse
});
