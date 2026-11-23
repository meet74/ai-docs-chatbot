/*
 * Embeddable support chat widget. No dependencies, one file.
 *
 *   <script src="https://your-host/widget/chat.js"
 *           data-api="https://your-host" data-title="Maple Grove Dental"
 *           data-accent="#1f7a5c" defer></script>
 *
 * Everything from the server is written with textContent, never innerHTML, and the UI
 * lives in a shadow root so the host page's CSS cannot break it (or read from it).
 */
(function (root) {
  'use strict';

  var STYLE = [
    ':host{all:initial}',
    '*{box-sizing:border-box;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}',
    '.launcher{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;cursor:pointer;background:var(--accent);color:#fff;box-shadow:0 6px 20px rgba(0,0,0,.25);font-size:24px;z-index:2147483000}',
    '.panel{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 24px);height:520px;max-height:calc(100vh - 110px);background:#fff;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;z-index:2147483000;color:#1c2733}',
    '.panel.open{display:flex}',
    '.head{background:var(--accent);color:#fff;padding:12px 14px;display:flex;align-items:center;justify-content:space-between}',
    '.head b{font-size:15px}.head small{display:block;opacity:.85;font-size:11px;margin-top:2px}',
    '.close{background:none;border:0;color:#fff;font-size:20px;cursor:pointer;line-height:1}',
    '.log{flex:1;overflow-y:auto;padding:12px;background:#f5f7f8;display:flex;flex-direction:column;gap:8px}',
    '.msg{max-width:86%;padding:8px 11px;border-radius:12px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}',
    '.msg.user{align-self:flex-end;background:var(--accent);color:#fff;border-bottom-right-radius:3px}',
    '.msg.bot{align-self:flex-start;background:#fff;border:1px solid #dde3e7;border-bottom-left-radius:3px}',
    '.msg.note{align-self:center;background:#fff7e0;border:1px solid #f0dca0;font-size:12px;color:#6b5400}',
    '.cites{margin-top:6px;padding-top:6px;border-top:1px solid #e6ebee;font-size:11.5px;color:#506070;white-space:normal}',
    '.cites span{display:block;margin-top:2px}',
    '.bar{display:flex;gap:6px;padding:8px;border-top:1px solid #e3e8eb;background:#fff}',
    '.bar input{flex:1;border:1px solid #c9d2d8;border-radius:8px;padding:9px 10px;font-size:14px;min-width:0}',
    '.bar button{border:0;border-radius:8px;background:var(--accent);color:#fff;padding:0 14px;font-size:14px;cursor:pointer}',
    '.bar button:disabled{opacity:.5;cursor:default}',
    '.human{padding:6px 10px 10px;background:#fff;text-align:center}',
    '.human button{background:none;border:1px solid var(--accent);color:var(--accent);border-radius:16px;padding:5px 12px;font-size:12px;cursor:pointer}',
    '.typing{opacity:.6;font-style:italic}',
    'button:focus-visible,input:focus-visible{outline:2px solid #1b5fd1;outline-offset:1px}'
  ].join('\n');

  function el(doc, tag, cls, text) {
    var n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function newSessionId() {
    var c = root.crypto;
    if (c && c.randomUUID) return c.randomUUID().replace(/-/g, '');
    var s = '';
    for (var i = 0; i < 32; i++) s += Math.floor(Math.random() * 16).toString(16);
    return s;
  }

  function init(opts) {
    opts = opts || {};
    var doc = root.document;
    var api = (opts.api || '').replace(/\/$/, '');
    var title = opts.title || 'Chat with us';
    var storeKey = 'docs-chat-session';
    var sessionId;
    try {
      sessionId = root.sessionStorage.getItem(storeKey);
      if (!sessionId) { sessionId = newSessionId(); root.sessionStorage.setItem(storeKey, sessionId); }
    } catch (e) { sessionId = newSessionId(); }

    var host = el(doc, 'div');
    host.setAttribute('data-docs-chat', '');
    var shadow = host.attachShadow({ mode: 'open' });
    var style = el(doc, 'style', null, STYLE);
    shadow.appendChild(style);
    host.style.setProperty('--accent', opts.accent || '#1f7a5c');

    var launcher = el(doc, 'button', 'launcher', '\u{1F4AC}');
    launcher.setAttribute('aria-label', 'Open chat');
    var panel = el(doc, 'div', 'panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', title);

    var head = el(doc, 'div', 'head');
    var heading = el(doc, 'div');
    heading.appendChild(el(doc, 'b', null, title));
    heading.appendChild(el(doc, 'small', null, 'Answers come from our own documents'));
    var close = el(doc, 'button', 'close', '×');
    close.setAttribute('aria-label', 'Close chat');
    head.appendChild(heading);
    head.appendChild(close);

    var log = el(doc, 'div', 'log');
    log.setAttribute('role', 'log');
    log.setAttribute('aria-live', 'polite');

    var bar = el(doc, 'form', 'bar');
    var input = el(doc, 'input');
    input.type = 'text';
    input.maxLength = 1000;
    input.placeholder = 'Ask a question';
    input.setAttribute('aria-label', 'Your question');
    var send = el(doc, 'button', null, 'Send');
    send.type = 'submit';
    bar.appendChild(input);
    bar.appendChild(send);

    var human = el(doc, 'div', 'human');
    var humanBtn = el(doc, 'button', null, 'Talk to a human');
    humanBtn.type = 'button';
    human.appendChild(humanBtn);

    panel.appendChild(head);
    panel.appendChild(log);
    panel.appendChild(bar);
    panel.appendChild(human);
    shadow.appendChild(launcher);
    shadow.appendChild(panel);
    doc.body.appendChild(host);

    var busy = false;

    function scroll() { log.scrollTop = log.scrollHeight; }

    function addMessage(kind, text, citations) {
      var m = el(doc, 'div', 'msg ' + kind, text);
      if (citations && citations.length) {
        var box = el(doc, 'div', 'cites');
        box.appendChild(el(doc, 'strong', null, 'Sources'));
        citations.forEach(function (c) {
          var label = String(c.doc || '') + (c.section ? ' › ' + c.section : '');
          box.appendChild(el(doc, 'span', null, label));
        });
        m.appendChild(box);
      }
      log.appendChild(m);
      scroll();
      return m;
    }

    function setBusy(v) {
      busy = v;
      send.disabled = v;
      humanBtn.disabled = v;
    }

    function ask(text, requestHuman) {
      if (busy) return Promise.resolve();
      text = (text || '').trim();
      if (!text) return Promise.resolve();
      addMessage('user', text);
      var typing = addMessage('bot typing', 'Looking through our documents…');
      setBusy(true);
      return root.fetch(api + '/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId, request_human: !!requestHuman })
      }).then(function (r) {
        if (r.status === 429) {
          var e = new Error('rate'); e.rate = true; throw e;
        }
        if (!r.ok) throw new Error('http ' + r.status);
        return r.json();
      }).then(function (data) {
        typing.remove();
        // Only plain strings are read from the response; markup is never interpreted.
        addMessage('bot', typeof data.answer === 'string' ? data.answer : '', Array.isArray(data.citations) ? data.citations : []);
        if (data.handoff && data.handoff.id) {
          addMessage('note', 'A team member has been notified (reference ' + data.handoff.id + ').');
        }
      }).catch(function (e) {
        typing.remove();
        addMessage('bot', e && e.rate
          ? 'You are sending messages quickly. Please wait a moment and try again.'
          : 'Sorry, I could not reach the assistant. Please try again, or call the clinic.');
      }).then(function () { setBusy(false); });
    }

    function open() {
      panel.classList.add('open');
      launcher.setAttribute('aria-expanded', 'true');
      if (!log.firstChild) {
        addMessage('bot', opts.greeting || 'Hi! I can answer questions about our services, prices, hours and policies. What would you like to know?');
      }
      input.focus();
    }
    function shut() { panel.classList.remove('open'); launcher.setAttribute('aria-expanded', 'false'); launcher.focus(); }

    launcher.addEventListener('click', function () { panel.classList.contains('open') ? shut() : open(); });
    close.addEventListener('click', shut);
    panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') shut(); });
    bar.addEventListener('submit', function (e) {
      e.preventDefault();
      var v = input.value;
      input.value = '';
      ask(v, false);
    });
    humanBtn.addEventListener('click', function () { ask('I would like to talk to a person.', true); });

    return { host: host, shadow: shadow, open: open, close: shut, ask: ask, sessionId: sessionId };
  }

  function autoInit() {
    var s = root.document.currentScript || root.document.querySelector('script[data-api][src$="chat.js"]');
    if (!s || s.hasAttribute('data-manual')) return;
    var start = function () {
      init({ api: s.getAttribute('data-api') || '', title: s.getAttribute('data-title') || undefined,
             accent: s.getAttribute('data-accent') || undefined, greeting: s.getAttribute('data-greeting') || undefined });
    };
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start);
    else start();
  }

  root.DocsChat = { init: init };
  if (typeof module !== 'undefined' && module.exports) module.exports = { init: init };
  autoInit();
})(typeof window !== 'undefined' ? window : globalThis);
