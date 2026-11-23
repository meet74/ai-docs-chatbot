const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const code = fs.readFileSync(path.join(__dirname, '..', 'chat.js'), 'utf8');

function setup(fetchImpl) {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://localhost/' });
  const w = dom.window;
  w.fetch = fetchImpl;
  w.eval(code);
  return w;
}

const reply = (body, status = 200) => () =>
  Promise.resolve({ ok: status < 300, status, json: () => Promise.resolve(body) });

const tick = () => new Promise((r) => setTimeout(r, 10));

test('renders inside a shadow root and opens on click', () => {
  const w = setup(reply({}));
  const chat = w.DocsChat.init({ api: '' });
  assert.ok(chat.shadow.querySelector('.panel'));
  assert.strictEqual(w.document.body.querySelector('.panel'), null, 'panel must not leak into the page DOM');
  chat.shadow.querySelector('.launcher').click();
  assert.ok(chat.shadow.querySelector('.panel').classList.contains('open'));
});

test('shows the answer with citations under it', async () => {
  const w = setup(reply({
    answer: 'A cleaning is $120.', confidence: 0.9, needs_human: false,
    citations: [{ doc: 'Services and Prices', section: 'Exams and cleanings' }],
  }));
  const chat = w.DocsChat.init({ api: '' });
  await chat.ask('How much is a cleaning?');
  await tick();
  const bots = chat.shadow.querySelectorAll('.msg.bot');
  const last = bots[bots.length - 1];
  assert.match(last.textContent, /A cleaning is \$120\./);
  assert.match(last.querySelector('.cites').textContent, /Services and Prices/);
  assert.match(last.querySelector('.cites').textContent, /Exams and cleanings/);
});

test('server text is never parsed as markup', async () => {
  const evil = '<img src=x onerror="window.pwned=1"><script>window.pwned=2</script>';
  const w = setup(reply({ answer: evil, citations: [{ doc: evil, section: evil }] }));
  const chat = w.DocsChat.init({ api: '' });
  await chat.ask('hello');
  await tick();
  assert.strictEqual(chat.shadow.querySelector('.log img'), null);
  assert.strictEqual(chat.shadow.querySelector('.log script'), null);
  assert.strictEqual(w.pwned, undefined);
  assert.ok(chat.shadow.querySelector('.log').textContent.includes(evil));
});

test('Talk to a human sends request_human and shows the handoff note', async () => {
  let sent;
  const w = setup((url, opts) => {
    sent = JSON.parse(opts.body);
    return reply({ answer: 'Of course.', citations: [], needs_human: true, handoff: { id: 'H-1234', status: 'created' } })();
  });
  const chat = w.DocsChat.init({ api: '' });
  chat.shadow.querySelector('.human button').click();
  await tick();
  assert.strictEqual(sent.request_human, true);
  assert.match(chat.shadow.querySelector('.msg.note').textContent, /H-1234/);
});

test('rate limit and network errors show a friendly message', async () => {
  const w = setup(reply({}, 429));
  const chat = w.DocsChat.init({ api: '' });
  await chat.ask('hi there');
  await tick();
  assert.match(chat.shadow.querySelector('.log').textContent, /quickly/);

  const w2 = setup(() => Promise.reject(new Error('offline')));
  const chat2 = w2.DocsChat.init({ api: '' });
  await chat2.ask('hi there');
  await tick();
  assert.match(chat2.shadow.querySelector('.log').textContent, /could not reach/);
});

test('uses the same session id for every message', async () => {
  const ids = [];
  const w = setup((url, opts) => { ids.push(JSON.parse(opts.body).session_id); return reply({ answer: 'ok', citations: [] })(); });
  const chat = w.DocsChat.init({ api: '' });
  await chat.ask('one');
  await tick();
  await chat.ask('two');
  await tick();
  assert.strictEqual(ids.length, 2);
  assert.strictEqual(ids[0], ids[1]);
  assert.match(ids[0], /^[A-Za-z0-9_-]{8,64}$/);
});
