/* Shot all 6 README frames from the demo dashboard on :3101 + mockups.
   Run from ~/projects/claude-code-webui (has puppeteer): */
const puppeteer = require('/home/saunalserver/projects/claude-code-webui/node_modules/puppeteer');
const path = require('path');

const OUT = '/home/saunalserver/projects/shortlist/docs/img';
const BASE = 'http://localhost:3101';
const MOCK = '/home/saunalserver/projects/shortlist/demo/mock';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--force-color-profile=srgb'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await page.evaluateOnNewDocument(() => {
    const s = document.createElement('style');
    s.textContent = '::-webkit-scrollbar{display:none!important}';
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s));
  });

  // ① found — terminal mockup
  await page.goto('file://' + MOCK + '/found.html', { waitUntil: 'networkidle0' });
  await sleep(300);
  await page.screenshot({ path: OUT + '/found.png' });
  console.log('found.png');

  // ③ digest — telegram mockup
  await page.goto('file://' + MOCK + '/digest.html', { waitUntil: 'networkidle0' });
  await sleep(300);
  await page.screenshot({ path: OUT + '/digest.png' });
  console.log('digest.png');

  // ④ review — queue
  await page.goto(BASE + '/pipeline/jobs', { waitUntil: 'networkidle0' });
  await page.waitForSelector('table tbody tr', { timeout: 15000 });
  await sleep(600);
  await page.screenshot({ path: OUT + '/review.png' });
  console.log('review.png');

  // ② match — job detail panel on the 9/10 job
  await page.evaluate(() => {
    const row = [...document.querySelectorAll('table tbody tr')].find((r) => r.textContent.includes('Northwind'));
    row.click();
  });
  await page.waitForFunction(() => document.body.textContent.includes('Fit Reasoning'), { timeout: 15000 });
  await sleep(500);
  await page.screenshot({ path: OUT + '/match.png' });
  console.log('match.png');

  // ⑤ track — kanban
  await page.goto(BASE + '/kanban', { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => /interview|bookmarked/i.test(document.body.textContent), { timeout: 20000 });
  await sleep(1200);
  await page.screenshot({ path: OUT + '/track.png', fullPage: true });
  console.log('track.png');

  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
