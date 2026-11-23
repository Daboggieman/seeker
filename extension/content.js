/*
 * Seeker MV3 content script — search overlay.
 *
 * Injected on <all_urls> at document_idle; builds nothing until first toggled
 * (Alt+Shift+S via chrome.commands -> background -> this message). Everything
 * renders inside a CLOSED shadow root so the host page cannot read the user's
 * results (ADR-0003). Search calls go through the background worker — this
 * script never touches the token.
 */
(function () {
  'use strict';
  if (window.__seekerContentLoaded) return;
  window.__seekerContentLoaded = true;

  let host = null;
  let root = null;
  let els = null;
  let sourcesCache = null;        // [{id,title}] chips
  let selectedSource = null;      // null = All
  let queryToken = 0;             // bumps per search; stale renders dropped

  const STYLES = [
    ':host{all:initial}',
    '.scrim{position:absolute;inset:0;background:rgba(12,15,22,.45);pointer-events:auto;',
    '  display:flex;justify-content:center;align-items:flex-start;padding:9vh 16px 16px;}',
    '.panel{width:min(660px,100%);background:#161a22;color:#e8eaf0;border-radius:12px;',
    '  box-shadow:0 18px 60px rgba(0,0,0,.5);font:14px/1.45 system-ui,-apple-system,sans-serif;overflow:hidden;}',
    'input.q{box-sizing:border-box;width:100%;padding:14px 16px;font-size:15px;color:#e8eaf0;',
    '  background:#10141c;border:none;outline:none;}',
    'input.q::placeholder{color:#5f6b85}',
    '.chips{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px 0;}',
    '.chip{font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid #2a3140;',
    '  background:#1a2029;color:#aab3c5;cursor:pointer;user-select:none;}',
    '.chip.on{background:#2b3a55;border-color:#3d5a8a;color:#dfe7f5;}',
    '.results{max-height:52vh;overflow:auto;padding-bottom:4px;}',
    '.hit{padding:10px 14px;border-top:1px solid #232936;cursor:pointer;}',
    '.hit:hover,.hit:focus{background:#1c2230;outline:none;}',
    '.hit .t{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}',
    '.hit .p{color:#8b93a7;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;}',
    '.hit .s{color:#5f6b85;font-size:11px;margin-top:2px;max-height:2.9em;overflow:hidden;}',
    '.hit .sc{color:#7d9bd6;font-size:11px;float:right;}',
    '.status{padding:8px 14px;color:#8b93a7;font-size:12px;border-top:1px solid #232936;}',
    '.status.err{color:#e08b8b;}',
  ].join('');

  const MARKUP = [
    '<style>' + STYLES + '</style>',
    '<div class="scrim">',
    '  <div class="panel" role="dialog" aria-label="Seeker search">',
    '    <input class="q" type="text" placeholder="Search your indexed files…  (Enter to search, Esc to close)" spellcheck="false">',
    '    <div class="chips"></div>',
    '    <div class="results"></div>',
    '    <div class="status"></div>',
    '  </div>',
    '</div>',
  ].join('');

  function send(type, extra) {
    const msg = Object.assign({ type: type }, extra || {});
    return chrome.runtime.sendMessage(msg);
  }

  function ensureDom() {
    if (host) return;
    host = document.createElement('div');
    host.id = 'seeker-overlay-host';
    host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
    root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = MARKUP;

    const panel = root.querySelector('.panel');
    const input = root.querySelector('input.q');
    const chips = root.querySelector('.chips');
    const results = root.querySelector('.results');
    const status = root.querySelector('.status');
    els = { panel: panel, input: input, chips: chips, results: results, status: status };

    root.querySelector('.scrim').addEventListener('mousedown', function (e) {
      if (e.target === root.querySelector('.scrim')) close();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { close(); }
      else if (e.key === 'Enter') { runSearch(input.value); }
    });
    chips.addEventListener('click', function (e) {
      const chip = e.target.closest('.chip');
      if (!chip) return;
      selectedSource = chip.dataset.source || null;
      renderChips();
      if (input.value.trim()) runSearch(input.value);
    });
    results.addEventListener('click', function (e) {
      const hit = e.target.closest('.hit');
      if (!hit) return;
      copyText(hit.dataset.path || '', function () {
        setStatus('Copied path: ' + (hit.dataset.path || ''), false);
      });
    });
    document.documentElement.appendChild(host);
  }

  function setStatus(text, isErr) {
    els.status.textContent = text;
    els.status.className = 'status' + (isErr ? ' err' : '');
  }

  function renderChips() {
    els.chips.textContent = '';
    const mk = function (label, id) {
      const c = document.createElement('span');
      c.className = 'chip' + ((selectedSource || null) === id ? ' on' : '');
      c.dataset.source = id || '';
      c.textContent = label;
      els.chips.appendChild(c);
    };
    mk('All', null);
    (sourcesCache || []).forEach(function (s) { mk(s.title, s.id); });
  }

  async function refreshChips() {
    try {
      const res = await send('seeker:sources');
      sourcesCache = (res && res.ok ? res.sources : []).map(function (s) {
        return { id: s.id, title: s.id };
      });
    } catch (err) {
      sourcesCache = [];
    }
    renderChips();
  }

  async function runSearch(q) {
    const query = (q || '').trim();
    if (!query) { els.results.textContent = ''; setStatus('Type a query and press Enter.', false); return; }
    const my = ++queryToken;
    els.results.textContent = '';
    setStatus('Searching…', false);
    let res;
    try {
      res = await send('seeker:search', { query: query, sourceIds: selectedSource ? [selectedSource] : undefined });
    } catch (err) {
      if (my !== queryToken) return;
      setStatus('Extension error: ' + (err && err.message ? err.message : err), true);
      return;
    }
    if (my !== queryToken) return; // a newer search superseded this one
    if (!res || !res.ok) {
      const e = res && res.error ? res.error : {};
      setStatus('✗ ' + (e.code || 'ERROR') + (e.message ? ' — ' + e.message : ''), true);
      return;
    }
    renderResults(res.results || []);
    setStatus((res.results || []).length + ' results · ' + res.elapsedMs + ' ms', false);
  }

  function renderResults(results) {
    els.results.textContent = '';
    if (!results.length) {
      const none = document.createElement('div');
      none.className = 'hit';
      none.style.cursor = 'default';
      none.textContent = 'No results.';
      els.results.appendChild(none);
      return;
    }
    results.forEach(function (r) {
      const hit = document.createElement('div');
      hit.className = 'hit';
      hit.dataset.path = r.path || '';
      hit.setAttribute('role', 'button');
      hit.tabIndex = 0;

      const sc = document.createElement('span');
      sc.className = 'sc';
      sc.textContent = typeof r.score === 'number' ? r.score.toFixed(2) : '';
      hit.appendChild(sc);

      const t = document.createElement('div');
      t.className = 't';
      t.textContent = r.title || r.path || '(untitled)';
      hit.appendChild(t);

      const p = document.createElement('div');
      p.className = 'p';
      p.textContent = r.path || '';
      hit.appendChild(p);

      if (r.snippet) {
        const s = document.createElement('div');
        s.className = 's';
        s.textContent = r.snippet;
        hit.appendChild(s);
      }
      els.results.appendChild(hit);
    });
  }

  function copyText(text, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text, done); });
    } else {
      fallbackCopy(text, done);
    }
  }
  function fallbackCopy(text, done) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* best effort */ }
    document.body.removeChild(ta);
    done();
  }

  function open() {
    ensureDom();
    host.style.display = 'block';
    if (!sourcesCache) refreshChips();
    els.input.focus();
    els.input.select();
  }
  function close() {
    host.style.display = 'none';
    queryToken++; // drop in-flight renders
  }
  function toggle() {
    if (host && host.style.display === 'block') close();
    else open();
  }

  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === 'seeker:toggle') toggle();
  });
})();
