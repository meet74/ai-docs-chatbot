// Renders the demo page with the widget open against a running server (make demo).
// Usage: node scripts/screenshots.js [baseUrl]
const { chromium } = require('playwright');
const path = require('path');

const base = process.argv[2] || 'http://localhost:8000';
const out = (n) => path.join(__dirname, '..', 'assets', n);

async function ask(page, text) {
  await page.locator('.bar input').fill(text);
  await page.locator('.bar button[type=submit]').click();
  await page.waitForFunction(() => {
    const root = document.querySelector('[data-docs-chat]').shadowRoot;
    return !root.querySelector('.typing') && root.querySelector('.bar button').disabled === false;
  });
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 }, deviceScaleFactor: 2 });
  await page.goto(base + '/demo');
  await page.locator('.launcher').click();

  await ask(page, 'How much is a root canal on a molar?');
  await page.screenshot({ path: out('demo-answer.png') });

  await ask(page, 'How much do dental implants cost?');
  await page.screenshot({ path: out('demo-handoff.png') });
  await browser.close();
  console.log('saved assets/demo-answer.png and assets/demo-handoff.png');
})();
