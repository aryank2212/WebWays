// Browser test for the Create tab. Needs the stack from `scripts/e2e.py --keep` and Playwright:
//   NODE_PATH=/path/to/node_modules CHROME=/usr/bin/google-chrome node scripts/ui_e2e.js <tmpdir-printed-by-e2e>
// Verifies: folder pick -> junk filtered -> torrent made in-browser with NO default trackers -> seeded through the
// daemon with the same infohash -> a second daemon downloads it -> .torrent inspector (incl. multi-file path shim).
const { chromium } = require('playwright');
const fs = require('fs'), os = require('os'), path = require('path'), crypto = require('crypto');
const CLI = 'http://127.0.0.1:18781', PUB = 'http://127.0.0.1:18782';
const assert = (c, m) => { if (!c) { console.error('FAIL:', m); process.exit(1); } console.log('  ok -', m); };
const api = async (base, tok, method, p, body) => {
  const r = await fetch(base + p, { method, headers: { Authorization: 'Bearer ' + tok, ...(body ? { 'Content-Type': 'application/json' } : {}) }, body: body && JSON.stringify(body) });
  return r.json();
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), 'webways-ui-'));
  const album = path.join(work, 'album'); fs.mkdirSync(path.join(album, 'disc1'), { recursive: true });
  fs.writeFileSync(path.join(album, 'a.bin'), crypto.randomBytes(300_000));
  fs.writeFileSync(path.join(album, 'disc1', 'b.bin'), crypto.randomBytes(120_000));
  fs.writeFileSync(path.join(album, '.DS_Store'), 'junk');

  const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ acceptDownloads: true, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  const problems = [];
  page.on('response', (r) => { if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) problems.push(m.text()); });
  page.on('pageerror', (e) => problems.push('pageerror ' + e.message));

  await page.goto(CLI + '/#token=tok-cli');
  await page.click('nav button:has-text("Create")');

  console.log('1. folder -> torrent');
  await page.setInputFiles('[data-testid=dir-input]', album);
  await page.waitForSelector('text=2 files');            // .DS_Store is skipped at pick time
  await page.waitForFunction(() => document.querySelector('input[placeholder="shown to downloaders"]').value === 'album');
  const picked = await page.textContent('p.small:has-text("file")');
  await page.click('button:has-text("Create torrent")');
  await page.waitForSelector('[data-testid=result]');
  const infohash = await page.textContent('[data-testid=infohash]');
  const magnet = await page.inputValue('[data-testid=magnet]');
  assert(/^[0-9a-f]{40}$/.test(infohash), 'got a 40-hex infohash ' + infohash);
  assert(magnet.startsWith('magnet:?xt=urn:btih:' + infohash) && !/[?&]tr=/.test(magnet), 'magnet has no tracker (no default announces)');
  assert(!/DS_Store/.test(await page.textContent('[data-testid=result]')), 'junk file not in result');

  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('button:has-text("Download .torrent")')]);
  const torrentPath = path.join(work, 'made.torrent'); await dl.saveAs(torrentPath);
  assert(dl.suggestedFilename() === 'album.torrent' && fs.statSync(torrentPath).size > 100, '.torrent downloaded as album.torrent');

  console.log('2. seed from this device');
  await page.click('button:has-text("Seed from this device")');
  await page.waitForSelector('text=Seeding.', { timeout: 30000 });
  let t;
  for (let i = 0; i < 60; i++) { t = await api(CLI, 'tok-cli', 'GET', '/api/torrents/' + infohash); if (t.progress === 1 && ['seeding', 'finished'].includes(t.state)) break; await sleep(500); }
  assert(t.infohash === infohash && t.progress === 1, `daemon seeds the browser-made torrent with the same infohash (${t.state})`);

  console.log('3. second daemon downloads it');
  await api(PUB, 'tok-pub', 'POST', '/api/torrents', { infohash });
  await api(PUB, 'tok-pub', 'POST', `/api/torrents/${infohash}/peers`, { host: '127.0.0.1', port: 16881 });
  let d;
  for (let i = 0; i < 80; i++) { d = await api(PUB, 'tok-pub', 'GET', '/api/torrents/' + infohash); if (d.progress === 1) break; await sleep(500); }
  assert(d.progress === 1, 'peer downloaded 100% of the browser-made torrent');

  console.log('4. trackers are opt-in');
  await page.click('button:has-text("clear")');
  await page.setInputFiles('[data-testid=file-input]', path.join(album, 'a.bin'));
  await page.click('summary:has-text("Advanced")');
  await page.fill('textarea[placeholder^="udp://"]', 'udp://tracker.example.org:6969/announce');
  await page.click('button:has-text("Create torrent")');
  await page.waitForFunction(() => document.querySelector('[data-testid=magnet]')?.value.includes('tr='));
  assert((await page.inputValue('[data-testid=magnet]')).includes('tr=udp%3A%2F%2Ftracker.example.org'), 'explicit tracker lands in the magnet');
  await page.fill('textarea[placeholder^="udp://"]', 'ftp://bad');
  await page.click('button:has-text("Create torrent")');
  await page.waitForSelector('[role=alert]:has-text("Not a valid URL")');
  assert(true, 'invalid tracker URL is rejected');

  console.log('5. drag and drop + inspector');
  await page.click('button:has-text("clear")').catch(() => {});
  await page.evaluate(() => {
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(5000).fill(7)], 'dropped.bin'));
    document.querySelector('[data-testid=dropzone]').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  });
  await page.waitForSelector('text=dropped.bin');
  assert(true, 'a dropped file appears in the list');

  const b64 = fs.readFileSync(torrentPath).toString('base64');
  await page.evaluate((b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer(); dt.items.add(new File([bytes], 'x.torrent'));
    document.querySelector('[data-testid=inspector]').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  }, b64);
  await page.waitForSelector('[data-testid=inspect-result]');
  const shown = await page.textContent('[data-testid=inspect-result]');
  assert(shown.includes(infohash) && shown.includes('2 file(s)') && shown.includes('album'), 'dropped .torrent is parsed (name, hash, 2 files)');
  await page.fill('[data-testid=inspect-input]', infohash);
  await page.click('button:has-text("Inspect")');
  assert((await page.inputValue('[data-testid=inspector] textarea')).startsWith('magnet:?xt=urn:btih:' + infohash), 'bare infohash converts to a magnet');
  await page.fill('[data-testid=inspect-input]', 'not a magnet');
  await page.click('button:has-text("Inspect")');
  await page.waitForSelector('text=doesn’t look like');
  assert(true, 'garbage input gives a friendly error');

  assert(problems.length === 0, 'no console errors or failed requests ' + JSON.stringify(problems));
  await page.screenshot({ path: path.join(work, 'create.png'), fullPage: true });
  console.log('screenshot:', path.join(work, 'create.png'), '\nUI E2E PASS');
  await browser.close();
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
