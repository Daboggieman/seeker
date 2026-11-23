/* Seeker options page — engine URL + token into chrome.storage.local, with a
 * "Test" probe (authed /v1/sources — proves reachability AND token in one call,
 * same reasoning as the mobile client's Test button). */
(function () {
  'use strict';
  const $ = function (id) { return document.getElementById(id); };
  const msg = $('msg');

  function setMsg(text, cls) {
    msg.textContent = text;
    msg.className = cls || '';
  }

  chrome.storage.local.get(['baseUrl', 'token'], function (stored) {
    $('baseUrl').value = stored.baseUrl || 'https://search-engine-2.taile24e8b.ts.net';
    if (stored.token) $('token').value = stored.token;
  });

  $('save').addEventListener('click', function () {
    const baseUrl = $('baseUrl').value.trim().replace(/\/+$/, '');
    const token = $('token').value;
    if (!baseUrl) { setMsg('Engine URL is empty.', 'err'); return; }
    chrome.storage.local.set({ baseUrl: baseUrl, token: token }, function () {
      setMsg('Saved.', 'ok');
    });
  });

  $('test').addEventListener('click', async function () {
    setMsg('Testing…', '');
    try {
      const res = await chrome.runtime.sendMessage({ type: 'seeker:probe' });
      if (res && res.ok) setMsg('✓ engine reachable — ' + res.count + ' source(s)', 'ok');
      else setMsg('✗ ' + (res && res.error ? res.error.code + ' — ' + res.error.message : 'unknown error'), 'err');
    } catch (err) {
      setMsg('✗ ' + (err && err.message ? err.message : String(err)), 'err');
    }
  });
})();
