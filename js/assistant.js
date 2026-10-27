/*
 * "Ask perinatal-ews": an AI assistant that answers questions about the published
 * results by calling the data tools in ews-tools.js (tool use / function calling).
 *
 * - Runs entirely in the browser. The reader supplies their own Anthropic API key;
 *   it is sent only to api.anthropic.com, kept for this tab by default, and never
 *   stored on any perinatal-ews server (there is none).
 * - The model can only see what the tools return, so answers are grounded in the
 *   same numbers as the bulletin. After each answer, every figure is checked
 *   against the tool results and any figure that cannot be matched is shown.
 * - Without a key, the deterministic county and state briefs still work.
 */
(function () {
  'use strict';
  const MODELS = { 'claude-sonnet-5-5': 'Claude Sonnet 5.5', 'claude-haiku-5-5': 'Claude Haiku 5.5 (faster, cheaper)' };
  const SYSTEM = `You are the assistant for perinatal-ews, an open-source early-warning tool for county maternal and newborn health in the United States, built by Karan Tejpal.
You answer questions from public health staff, researchers and the public about the published results: CDC WONDER natality data, 2016-2024, for 578 counties with 100,000+ residents, four indicators (late or no prenatal care, preterm birth, low birth weight, gestational hypertension), payer subgroups, a next-year forecast, a comparison with similar counties, and county context on overdose deaths, opioid treatment for pregnant and postpartum patients, delivery hospitals and adult health.

Rules:
- Always use the tools to get numbers. Never state a rate, count, risk or ranking that a tool did not return. If the tools do not have it, say so.
- Give rates as percentages with one decimal, and say which year they refer to.
- Flags are statistical signals for local follow-up, not confirmed problems; say so when you report flags.
- When a tool result carries a reporting_caveat or reporting_caveats for an indicator you report (gestational hypertension), state that caveat in one sentence with the result.
- When many counties in a state are flagged together, mention that it may be a state-wide change or a change in how the state records the item.
- County context describes places, not people. Never suggest that parents or any group are to blame, and do not claim causes; associations only.
- This is population surveillance. Do not give clinical or individual medical advice; refer people to a clinician for personal questions.
- Be concise: lead with the answer, then the key numbers, in plain language for a busy health department reader. Use short bullet lists only when comparing several counties.`;

  let D = null, history = [], busy = false;
  const $ = s => document.querySelector(s);
  const store = {
    get() { try { return sessionStorage.getItem('ews_key') || localStorage.getItem('ews_key') || ''; } catch { return ''; } },
    set(k, remember) {
      try { sessionStorage.setItem('ews_key', k); if (remember) localStorage.setItem('ews_key', k); else localStorage.removeItem('ews_key'); } catch { /* storage unavailable */ }
    },
    clear() { try { sessionStorage.removeItem('ews_key'); localStorage.removeItem('ews_key'); } catch { /* ignore */ } },
  };
  let memKey = '';
  const key = () => memKey || store.get();

  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    return n;
  }
  // Minimal, safe markdown: paragraphs, "- " bullets, **bold**. No HTML is ever injected.
  function md(text) {
    const box = el('div', { class: 'md' });
    let ul = null;
    const inline = s => { const p = el('span'); s.split(/(\*\*[^*]+\*\*)/).forEach(t => p.append(/^\*\*.+\*\*$/.test(t) ? el('b', { text: t.slice(2, -2) }) : t)); return p; };
    for (const line of text.split('\n')) {
      const m = line.match(/^\s*[-*•]\s+(.*)/);
      if (m) { if (!ul) { ul = el('ul'); box.append(ul); } ul.append(el('li', {}, inline(m[1]))); continue; }
      ul = null;
      const h = line.match(/^#{1,4}\s+(.*)/);
      if (h) box.append(el('p', {}, el('b', { text: h[1] })));
      else if (line.trim()) box.append(el('p', {}, inline(line)));
    }
    return box;
  }

  async function callClaude(messages) {
    const tools = window.EWS.TOOLS.map(({ name, description, input_schema }) => ({ name, description, input_schema }));
    const r = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-api-key': key(), 'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true' },
      body: JSON.stringify({ model: $('#ai-model').value, max_tokens: 1500, system: SYSTEM, tools, messages }),
    });
    if (!r.ok) {
      let msg = `${r.status}`;
      try { const j = await r.json(); msg = (j.error && j.error.message) || msg; } catch { /* keep status */ }
      if (r.status === 401) msg = 'The API key was not accepted. Check it and try again.';
      if (r.status === 429) msg = 'Rate limit reached. Wait a moment and try again.';
      throw new Error(msg);
    }
    return r.json();
  }

  async function ask(question) {
    if (busy || !question.trim()) return;
    if (!key()) { $('#ai-status').textContent = 'Add an API key above to use the assistant, or use the briefs below without one.'; return; }
    busy = true; $('#ai-send').disabled = true;
    const log = $('#ai-log');
    log.append(el('div', { class: 'msg user' }, el('p', { text: question })));
    const turn = el('div', { class: 'msg bot' });
    const steps = el('div', { class: 'steps' });
    turn.append(steps); log.append(turn);
    $('#ai-status').textContent = 'Thinking…';
    const msgs = history.concat([{ role: 'user', content: question }]);
    const results = [];
    try {
      for (let i = 0; i < 8; i++) {
        const res = await callClaude(msgs);
        msgs.push({ role: 'assistant', content: res.content });
        const calls = res.content.filter(b => b.type === 'tool_use');
        if (res.stop_reason !== 'tool_use' || !calls.length) {
          const text = res.content.filter(b => b.type === 'text').map(b => b.text).join('\n').trim();
          turn.append(md(text || 'No answer was returned.'));
          const unmatched = window.EWS.checkNumbers(text, results);
          turn.append(el('p', { class: 'check ' + (unmatched.length ? 'warn' : 'ok'), text: unmatched.length
            ? `Check these figures against the county pages; they could not be matched to the data the assistant looked up: ${unmatched.join(', ')}.`
            : results.length ? 'Every figure in this answer matches the published data the assistant looked up.' : 'No data was looked up for this answer.' }));
          history = msgs;
          break;
        }
        const out = [];
        for (const c of calls) {
          const t = window.EWS.TOOLS.find(x => x.name === c.name);
          let r;
          try { r = t ? t.run(D, c.input || {}) : { error: 'Unknown tool' }; } catch (e) { r = { error: String(e.message || e) }; }
          results.push(r);
          const argText = Object.values(c.input || {}).join(', ');
          steps.append(el('span', { class: 'step', text: `${c.name.replace(/_/g, ' ')}${argText ? ': ' + argText : ''}` }));
          out.push({ type: 'tool_result', tool_use_id: c.id, content: JSON.stringify(r) });
        }
        msgs.push({ role: 'user', content: out });
        $('#ai-status').textContent = 'Looking up the data…';
      }
      $('#ai-status').textContent = '';
    } catch (e) {
      turn.append(el('p', { class: 'check warn', text: 'Could not get an answer: ' + (e.message || e) }));
      $('#ai-status').textContent = '';
    } finally {
      busy = false; $('#ai-send').disabled = false; log.scrollTop = log.scrollHeight;
    }
  }

  function renderKeyState() {
    const has = !!key();
    $('#ai-key-row').hidden = has; $('#ai-key-set').hidden = !has;
  }

  window.initAssistant = function (data) {
    D = data;
    const sel = $('#ai-model');
    for (const [id, label] of Object.entries(MODELS)) sel.append(el('option', { value: id, text: label }));
    renderKeyState();
    $('#ai-key-save').addEventListener('click', () => {
      const k = $('#ai-key').value.trim(); if (!k) return;
      memKey = k; store.set(k, $('#ai-remember').checked); $('#ai-key').value = ''; renderKeyState();
      $('#ai-status').textContent = 'Key added. Ask a question.';
    });
    $('#ai-key-clear').addEventListener('click', () => { memKey = ''; store.clear(); renderKeyState(); });
    $('#ai-form').addEventListener('submit', e => { e.preventDefault(); const q = $('#ai-q').value; $('#ai-q').value = ''; ask(q); });
    document.querySelectorAll('[data-q]').forEach(b => b.addEventListener('click', () => ask(b.dataset.q)));
    $('#ai-reset').addEventListener('click', () => { history = []; $('#ai-log').textContent = ''; });

    // Briefs without a key
    const bsel = $('#brief-state');
    for (const s of [...new Set(D.counties.map(c => c.state))].sort()) bsel.append(el('option', { value: s, text: window.EWS.STATE_NAMES[s] || s }));
    $('#brief-go').addEventListener('click', () => {
      const out = $('#brief-out'); out.textContent = '';
      const cq = $('#brief-county').value.trim();
      if (cq) {
        const c = window.EWS.findCounty(D, cq) || D.counties.find(x => `${x.name}, ${x.state}`.toLowerCase().includes(cq.toLowerCase()));
        out.append(el('p', { text: c ? window.EWS.countyBrief(D, c) : 'County not found. Try "Hampden, MA" or a 5-digit FIPS code.' }));
      } else if (bsel.value) out.append(el('p', { text: window.EWS.stateBrief(D, bsel.value) }));
    });
  };
})();
