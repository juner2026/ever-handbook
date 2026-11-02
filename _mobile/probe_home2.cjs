/* 家园横屏「页面弹动」排查探针 v2
   node _mobile/probe_home2.cjs <mode>
     base    7.91 现状：进家园 → 退家园
     rot     进家园后再转 90°（7.85 的做法）
     pre     先 warm + 先转好尺寸再显示（新方案预览）
   输出：动画帧矩形变化 / layout-shift / 截图序列（_mobile/shots/h2-<mode>-*.png）
*/
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const fs = require('fs');
const path = require('path');

const mode = process.argv[2] || 'base';
const W = parseInt(process.env.VW || '430', 10);
const H = parseInt(process.env.VH || '932', 10);
const URL = process.env.URL || (process.env.FILE
  ? 'file://' + process.env.FILE + '?phone=1&splash=off'
  : 'http://127.0.0.1:8901/ever.html?phone=1&splash=off');
const OUT = '/sdcard/Download/WeiXin/_mobile/shots';

const INSTALL = () => {
  window.__shifts = [];
  try {
    new PerformanceObserver((l) => {
      l.getEntries().forEach(e => window.__shifts.push({
        v: +e.value.toFixed(4), t: Math.round(e.startTime),
        src: (e.sources || []).map(s => s.node ? (s.node.id || s.node.className || s.node.nodeName) : '?').join(','),
        prev: e.previousRect && [Math.round(e.previousRect.x), Math.round(e.previousRect.y), Math.round(e.previousRect.width), Math.round(e.previousRect.height)],
        cur: e.currentRect && [Math.round(e.currentRect.x), Math.round(e.currentRect.y), Math.round(e.currentRect.width), Math.round(e.currentRect.height)],
      }));
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}
  window.__sig = function () {
    const e4 = document.getElementById('teHome4');
    const jh = document.getElementById('jh-home');
    const f4 = document.getElementById('teH4frame');
    const r = e4 ? e4.getBoundingClientRect() : null;
    const j = jh ? jh.getBoundingClientRect() : null;
    let h4 = null;
    try { h4 = f4 && f4.contentWindow ? [f4.contentWindow.innerWidth, f4.contentWindow.innerHeight] : null; } catch (e) {}
    return JSON.stringify({
      e4: r ? [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] : null,
      tr: e4 ? getComputedStyle(e4).transform : null,
      disp: e4 ? getComputedStyle(e4).display : null,
      jh: j ? [Math.round(j.left), Math.round(j.top), Math.round(j.width), Math.round(j.height)] : null,
      jhd: jh ? getComputedStyle(jh).display : null,
      h4: h4,
      cls: document.documentElement.className.replace(/\s+/g, ' ').slice(0, 90),
      iw: innerWidth, ih: innerHeight,
    });
  };
  window.__rec = function (dur) {
    return new Promise(res => {
      const out = []; let last = null; const t0 = performance.now();
      (function tick() {
        const s = window.__sig();
        if (s !== last) { out.push(Object.assign({ t: Math.round(performance.now() - t0) }, JSON.parse(s))); last = s; }
        if (performance.now() - t0 < dur) requestAnimationFrame(tick); else res(out);
      })();
    });
  };
  // 桌面 iframe 里也装一个 layout-shift 监听
  window.__installInner = function () {
    const f = document.getElementById('jh-frame');
    try {
      const d = f.contentWindow;
      d.__shifts = d.__shifts || [];
      new d.PerformanceObserver((l) => {
        l.getEntries().forEach(e => d.__shifts.push({ v: +e.value.toFixed(4), t: Math.round(e.startTime) }));
      }).observe({ type: 'layout-shift', buffered: true });
    } catch (e) {}
  };
  window.__innerShifts = function () {
    try { return document.getElementById('jh-frame').contentWindow.__shifts || []; } catch (e) { return []; }
  };
  window.__shiftsRead = function () { const s = window.__shifts.slice(); window.__shifts.length = 0; return s; };
  true;
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',
    args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, deviceScaleFactor: 1, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36',
  });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('CONSOLE: ' + m.text().slice(0, 160)); });

  await p.goto(URL, { waitUntil: 'load', timeout: 120000 });
  await p.waitForTimeout(4000);
  for (const fr of p.frames()) { try { await fr.evaluate(() => { try { window.TEsplash && TEsplash.dismiss(); } catch (e) {} }); } catch (e) {} }
  await p.waitForTimeout(1200);
  await p.evaluate(INSTALL);
  await p.evaluate(() => { try { window.__installInner(); } catch (e) {} });
  await p.waitForTimeout(300);

  const shots = [];
  const shot = async (n) => {
    const f = path.join(OUT, `h2-${mode}-${n}.png`);
    await p.screenshot({ path: f }).catch(() => {});
    shots.push(f);
  };
  const readShifts = async (tag) => {
    const top = await p.evaluate(() => window.__shiftsRead());
    const inner = await p.evaluate(() => { const s = window.__innerShifts(); try { window.__innerShiftsReset && window.__innerShiftsReset(); } catch (e) {} return s; });
    console.log(`--[${tag}] CLS(top)=${top.reduce((a, b) => a + b.v, 0).toFixed(4)} ${JSON.stringify(top.slice(0, 8))}`);
    console.log(`--[${tag}] CLS(desk)=${inner.reduce((a, b) => a + b.v, 0).toFixed(4)} ${JSON.stringify(inner.slice(0, 8))}`);
  };

  await shot('00-idle');
  await readShifts('idle');

  // ---- 进家园
  if (mode === 'pre') {
    await p.evaluate(() => {
      try { window.teHome.warm && window.teHome.warm(); } catch (e) {}
      const box = document.getElementById('teHome4');
      // 先按横屏算好盒子几何（此时还 display:none，没有布局成本）
      window.__m2ForceLandscape(box);
    });
    await p.waitForTimeout(700);
  }
  const tEnterStart = Date.now();
  await p.evaluate((m) => {
    window.teHomeEnter();
    if (m === 'rot') { const box = document.getElementById('teHome4'); window.__m2ForceLandscape(box); }
  }, mode);
  await shot('01-enter+0');
  const enterRec = await p.evaluate(() => window.__rec(2600));
  await readShifts('enter');
  await shot('02-enter+2.6s');
  console.log('==== [%s] ENTER 变化帧 %d ====', mode, enterRec.length);
  enterRec.forEach(o => console.log(`t=${o.t} e4=${JSON.stringify(o.e4)} tr=${o.tr} disp=${o.disp} jh=${JSON.stringify(o.jh)} jhd=${o.jhd} h4=${JSON.stringify(o.h4)} cls="${o.cls}"`));

  await p.waitForTimeout(500);
  await shot('03-hold');

  // ---- 退家园
  await p.evaluate(() => window.teHomeLeave());
  const leaveShots = [0, 90, 180, 300, 500, 800, 1200];
  let idx = 0;
  for (const ms of leaveShots) {
    if (idx > 0) await p.waitForTimeout(ms - leaveShots[idx - 1]);
    await shot('04-leave+' + ms + 'ms');
    idx++;
  }
  const leaveRec = await p.evaluate(() => window.__rec(1600));
  await readShifts('leave');
  await shot('05-leave+end');
  console.log('==== [%s] LEAVE 变化帧 %d ====', mode, leaveRec.length);
  leaveRec.forEach(o => console.log(`t=${o.t} e4=${JSON.stringify(o.e4)} tr=${o.tr} disp=${o.disp} jh=${JSON.stringify(o.jh)} jhd=${o.jhd} h4=${JSON.stringify(o.h4)} cls="${o.cls}"`));

  if (errs.length) console.log('==== ERRORS ====\n' + [...new Set(errs)].slice(0, 10).join('\n'));
  console.log('SHOTS ' + shots.length);
  await browser.close();
})();
