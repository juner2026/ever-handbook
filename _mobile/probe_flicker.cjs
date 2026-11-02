/* 7.98 排查：用 CDP 录帧 + 每帧快照 DOM，抓"整页弹到右下角"的那一帧到底发生了什么
   node _mobile/probe_flicker.cjs
*/
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const OUT = '/sdcard/Download/WeiXin/_mobile/shots/flicker';
const URL = 'http://127.0.0.1:8901/ever.html?phone=1&splash=off';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',
    args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 430, height: 932 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36',
  });
  const p = await ctx.newPage();
  p.on('pageerror', e => console.log('PAGEERROR', e.message));
  await p.goto(URL, { waitUntil: 'load', timeout: 120000 });
  await p.waitForTimeout(4500);
  for (const fr of p.frames()) { try { await fr.evaluate(() => { try { TEsplash && TEsplash.dismiss(); } catch (e) {} }); } catch (e) {} }
  await p.waitForTimeout(900);

  // 在页面里装一个"事件流水"：样式变化 + resize + layout 调用
  await p.evaluate(() => {
    window.__ev = [];
    const t0 = performance.now();
    const push = (k, v) => window.__ev.push({ t: Math.round(performance.now() - t0), k: k, v: v });
    const box = document.getElementById('jh-home');
    new MutationObserver(ms => {
      ms.forEach(m => {
        const r = box.getBoundingClientRect();
        push('style', {
          rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
          style: String(box.getAttribute('style') || '').slice(0, 260),
          tw: box.dataset.tw, th: box.dataset.th, sc: box.dataset.scale, fit: box.dataset.fit,
        });
      });
    }).observe(box, { attributes: true });
    window.addEventListener('resize', () => push('resize', [innerWidth, innerHeight]));
    try {
      const f = document.getElementById('jh-frame');
      f.contentWindow.addEventListener('resize', () => push('inner-resize', [f.contentWindow.innerWidth, f.contentWindow.innerHeight]));
    } catch (e) {}
    const orig = window.__jhRelayout;
    if (orig) window.__jhRelayout = function () { push('relayout', null); return orig.apply(this, arguments); };
    window.__evRead = () => { const a = window.__ev.slice(); window.__ev.length = 0; return a; };
  });

  const cdp = await ctx.newCDPSession(p);
  const frames = [];
  cdp.on('Page.screencastFrame', async (f) => {
    const idx = frames.length;
    frames.push({ idx, data: f.data, ts: f.metadata && f.metadata.timestamp });
    try { await cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }); } catch (e) {}
    // 每帧立刻取一次状态（跟帧序号绑在一起）
    try {
      const st = await p.evaluate(() => {
        const b = document.getElementById('jh-home');
        const r = b.getBoundingClientRect();
        const f = document.getElementById('jh-frame');
        let iw = null, ih = null;
        try { iw = f.contentWindow.innerWidth; ih = f.contentWindow.innerHeight; } catch (e) {}
        return {
          rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
          tr: getComputedStyle(b).transform, tw: b.dataset.tw, th: b.dataset.th,
          sc: b.dataset.scale, fit: b.dataset.fit, iv: iw + 'x' + ih,
          cls: document.documentElement.className.slice(0, 60),
        };
      });
      frames[idx].st = st;
    } catch (e) { frames[idx].st = { err: String(e).slice(0, 60) }; }
  });
  await cdp.send('Page.startScreencast', { format: 'png', quality: 70, maxWidth: 430, maxHeight: 932, everyNthFrame: 1 });
  await p.waitForTimeout(300);

  // 一串操作：点桌面不同位置 / 打开页面再回首页，逼出抖动
  const acts = [
    async () => p.mouse.click(215, 420),
    async () => p.waitForTimeout(700),
    async () => p.evaluate(() => window.nav && window.nav('chat')),
    async () => p.waitForTimeout(700),
    async () => p.evaluate(() => window.nav && window.nav('home')),
    async () => p.waitForTimeout(700),
    async () => p.mouse.click(215, 300),
    async () => p.waitForTimeout(700),
    async () => p.mouse.click(400, 500),
    async () => p.waitForTimeout(900),
  ];
  for (const a of acts) await a();
  await p.waitForTimeout(400);
  await cdp.send('Page.stopScreencast').catch(() => {});
  const ev = await p.evaluate(() => window.__evRead());

  // 存帧 + 找"异常帧"（和最多数帧差异大的）
  const sizes = [];
  frames.forEach((f, i) => {
    fs.writeFileSync(path.join(OUT, 'f' + String(i).padStart(3, '0') + '.png'), Buffer.from(f.data, 'base64'));
    sizes.push(Buffer.from(f.data, 'base64').length);
  });
  const med = sizes.slice().sort((a, b) => a - b)[Math.floor(sizes.length / 2)];
  console.log('帧数', frames.length, '中位字节', med);
  const odd = frames.filter((f, i) => sizes[i] < med * 0.55);
  console.log('异常帧数', odd.length);
  odd.slice(0, 12).forEach(f => {
    console.log('  #' + f.idx, sizes[f.idx], JSON.stringify(f.st));
  });
  console.log('--- 事件流水（样式写入 / resize / relayout）---');
  ev.slice(0, 40).forEach(e => console.log('  t=' + e.t, e.k, JSON.stringify(e.v).slice(0, 200)));
  await browser.close();
})();
