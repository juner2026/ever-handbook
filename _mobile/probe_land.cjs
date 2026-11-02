/* 7.92 验收：横屏几何稳定性 / 击穿测试 / 小窗拖动 / ?land=0
   node _mobile/probe_land.cjs
*/
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const path = require('path');
const OUT = '/sdcard/Download/WeiXin/_mobile/shots';
const BASE = 'http://127.0.0.1:8901/ever.html?phone=1&splash=off';

(async () => {
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',
    args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-dev-shm-usage'],
  });

  async function open(w, h, url) {
    const ctx = await browser.newContext({
      viewport: { width: w, height: h }, deviceScaleFactor: 1, isMobile: true, hasTouch: true,
      userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36',
    });
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(url || BASE, { waitUntil: 'load', timeout: 120000 });
    await p.waitForTimeout(4200);
    for (const fr of p.frames()) { try { await fr.evaluate(() => { try { window.TEsplash && TEsplash.dismiss(); } catch (e) {} }); } catch (e) {} }
    await p.waitForTimeout(900);
    return { ctx, p, errs };
  }

  const state = (p) => p.evaluate(() => {
    const b = document.getElementById('teHome4');
    const f = document.getElementById('teH4frame');
    let cv = null, iw = null, ih = null;
    try {
      const d = f.contentWindow;
      iw = d.innerWidth; ih = d.innerHeight;
      const c = d.document.getElementById('cv') || d.document.querySelector('canvas');
      if (c) cv = [c.width, c.height, Math.round(c.clientWidth), Math.round(c.clientHeight)];
    } catch (e) {}
    const r = b.getBoundingClientRect();
    const el = document.elementFromPoint(Math.round(innerWidth / 2), Math.round(innerHeight / 2));
    const el2 = document.elementFromPoint(40, Math.round(innerHeight / 2));
    return {
      box: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      tr: getComputedStyle(b).transform, disp: getComputedStyle(b).display,
      iw, ih, cv,
      topCenter: el ? (el.id || el.tagName) : null,
      topLeft: el2 ? (el2.id || el2.tagName) : null,
      vw: innerWidth, vh: innerHeight,
    };
  });

  // ---------- A. 竖着拿手机：进家园 → 应该已经是横屏（不转视口）
  let { ctx, p, errs } = await open(430, 932);
  await p.evaluate(() => window.teHomeEnter());
  await p.waitForTimeout(2200);
  console.log('A 竖屏进家园     ', JSON.stringify(await state(p)));

  // 击穿：点房间中间（canvas 里的地毯区域），看是不是真的点进 iframe
  await p.mouse.click(215, 466);
  await p.waitForTimeout(200);

  // ---------- B. 手机物理转成横屏（视口 932×430）：家园画面不该再重排
  const before = await state(p);
  await p.setViewportSize({ width: 932, height: 430 });
  await p.waitForTimeout(900);
  const after = await state(p);
  console.log('B 转成横屏后     ', JSON.stringify(after));
  console.log('   canvas 是否被重排:', before.cv && after.cv ? (before.cv.join() === after.cv.join() ? '否（一样）' : '是 ' + before.cv + '→' + after.cv) : '取不到');
  await p.screenshot({ path: path.join(OUT, 'land-B-physical-landscape.png') });

  // ---------- C. 再转回竖屏：仍然 932×430，不重排
  await p.setViewportSize({ width: 430, height: 932 });
  await p.waitForTimeout(900);
  const back = await state(p);
  console.log('C 转回竖屏后     ', JSON.stringify(back));
  console.log('   canvas 是否被重排:', after.cv && back.cv ? (after.cv.join() === back.cv.join() ? '否（一样）' : '是 ' + after.cv + '→' + back.cv) : '取不到');
  await p.screenshot({ path: path.join(OUT, 'land-C-back-portrait.png') });

  // ---------- D. 小窗拖动（宿主转了 90°，拖动方向要对）
  const drag = await p.evaluate(() => {
    const w = document.getElementById('hqWin');
    if (!w) return 'no-hqWin';
    const t0 = w.style.transform;
    return { t0, rect: JSON.stringify(w.getBoundingClientRect()) };
  });
  console.log('D 家园小窗       ', JSON.stringify(drag));
  const head = await p.$('#hqHead');
  if (head) {
    const box = await head.boundingBox();
    if (box) {
      await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await p.mouse.down();
      for (let i = 1; i <= 8; i++) await p.mouse.move(box.x + box.width / 2 + i * 6, box.y + box.height / 2 + i * 3);
      await p.mouse.up();
      await p.waitForTimeout(300);
      const t1 = await p.evaluate(() => { const w = document.getElementById('hqWin'); return w ? w.style.transform : null; });
      console.log('   拖动后 transform:', t1);
    }
  }
  // 退出家园：桌面必须立刻在
  await p.evaluate(() => window.teHomeLeave());
  await p.waitForTimeout(60);
  const lv = await p.evaluate(() => {
    const jh = document.getElementById('jh-home');
    return { jhDisp: getComputedStyle(jh).display, jhVis: getComputedStyle(jh).visibility,
      cls: document.documentElement.className, e4: getComputedStyle(document.getElementById('teHome4')).display };
  });
  console.log('E 退出家园 +60ms ', JSON.stringify(lv));
  await p.screenshot({ path: path.join(OUT, 'land-E-after-leave.png') });
  if (errs.length) console.log('   ERRORS:', [...new Set(errs)].slice(0, 4).join(' | '));
  await ctx.close();

  // ---------- F. ?land=0 关掉横屏
  ({ ctx, p, errs } = await open(430, 932, BASE + '&land=0'));
  await p.evaluate(() => window.teHomeEnter());
  await p.waitForTimeout(1500);
  console.log('F ?land=0 进家园 ', JSON.stringify(await state(p)));
  await p.screenshot({ path: path.join(OUT, 'land-F-land0.png') });
  await ctx.close();

  await browser.close();
})();
