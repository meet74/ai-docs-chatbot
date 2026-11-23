// Renders assets/cover.png from eval/results/mock.json and the test count.
const { chromium } = require('playwright');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const res = JSON.parse(fs.readFileSync(path.join(root, 'eval/results/mock.json'), 'utf8'));
const collected = execSync(path.join(root, '.venv/bin/python') + ' -m pytest --collect-only -q', { cwd: root }).toString();
const pyTests = parseInt((collected.match(/(\d+) tests? collected/) || [])[1], 10);
const pct = (x) => Math.round(x * 100) + '%';
const refused = Math.round(res.refusal_correct * res.out_of_scope);

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}
body{width:1600px;height:1200px;background:#0d1b2a;color:#e8eef4;font-family:Inter,Helvetica,Arial,sans-serif;position:relative;overflow:hidden}
.left{position:absolute;left:80px;top:100px;width:680px}
.tag{color:#2ec4b6;font-size:22px;letter-spacing:2px;text-transform:uppercase;font-weight:600}
h1{font-size:84px;line-height:1.02;margin:22px 0 26px;font-weight:700}
.sub{font-size:30px;line-height:1.4;color:#b7c4d1}
.stats{display:flex;gap:18px;margin-top:56px}
.tile{flex:1;background:#14283d;border:1px solid #1f3a56;border-radius:16px;padding:22px 20px}
.tile b{display:block;font-size:56px;color:#2ec4b6;font-weight:700}
.tile span{font-size:19px;color:#b7c4d1;line-height:1.3;display:block;margin-top:6px}
.chips{display:flex;flex-wrap:wrap;gap:12px;margin-top:48px}
.chip{border:1px solid #2ec4b6;color:#2ec4b6;border-radius:999px;padding:8px 18px;font-size:20px}
.phone{position:absolute;right:70px;top:90px;width:620px;height:1020px;background:#f5f7f8;border-radius:28px;box-shadow:0 30px 80px rgba(0,0,0,.5);overflow:hidden;color:#1c2733}
.top{background:#1f7a5c;color:#fff;padding:24px 28px}.top b{font-size:28px}.top small{display:block;font-size:18px;opacity:.85;margin-top:4px}
.body{padding:24px;display:flex;flex-direction:column;gap:16px}
.m{padding:16px 20px;border-radius:18px;font-size:24px;line-height:1.4;max-width:84%}
.u{align-self:flex-end;background:#1f7a5c;color:#fff}
.b{background:#fff;border:1px solid #dde3e7}
.c{margin-top:12px;padding-top:10px;border-top:1px solid #e6ebee;font-size:18px;color:#506070}
.n{align-self:center;background:#fff7e0;border:1px solid #f0dca0;font-size:19px;color:#6b5400;padding:10px 18px;border-radius:14px}
.btn{align-self:center;border:2px solid #1f7a5c;color:#1f7a5c;border-radius:30px;padding:8px 22px;font-size:20px;margin-top:6px}
</style></head><body>
<div class="left">
  <div class="tag">Sahajix</div>
  <h1>AI Docs Chatbot</h1>
  <div class="sub">Answers customer questions only from your own documents, cites the source, says "I don't know", and hands off to a person. Website widget and WhatsApp.</div>
  <div class="stats">
    <div class="tile"><b>${pct(res.retrieval_hit_at_3)}</b><span>retrieval hit@3 on ${res.answerable} questions</span></div>
    <div class="tile"><b>${refused}/${res.out_of_scope}</b><span>trick and out-of-scope questions refused</span></div>
    <div class="tile"><b>${pyTests}</b><span>pytest tests, offline</span></div>
  </div>
  <div class="chips"><span class="chip">FastAPI</span><span class="chip">BM25</span><span class="chip">Claude API</span><span class="chip">WhatsApp Cloud API</span><span class="chip">n8n</span><span class="chip">Shadow DOM widget</span></div>
</div>
<div class="phone">
  <div class="top"><b>Maple Grove Dental</b><small>Answers come from our own documents</small></div>
  <div class="body">
    <div class="m u">How much is a root canal on a molar?</div>
    <div class="m b">Root canal treatment is priced by tooth position. Molar: $1,290. A crown is usually needed after a root canal on a molar.<div class="c"><b>Sources</b><br>Services and Prices › Root canal treatment</div></div>
    <div class="m u">How much do dental implants cost?</div>
    <div class="m b">I don't know the answer to that from our documents. I have passed this conversation to our team. Someone will follow up during opening hours.</div>
    <div class="n">A team member has been notified (reference H-9DAF2BF0).</div>
    <div class="btn">Talk to a human</div>
  </div>
</div>
</body></html>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } });
  await page.setContent(html);
  await page.screenshot({ path: path.join(root, 'assets/cover.png') });
  await browser.close();
  console.log('saved assets/cover.png', { pyTests, hit3: res.retrieval_hit_at_3 });
})();
