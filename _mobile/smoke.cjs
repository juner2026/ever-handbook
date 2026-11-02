/* 交互冒烟：node _mobile/smoke.cjs <file>
   点按 → 全屏 → 翻屏 → 应用抽屉 → 退出，全程抓 pageerror / 截图 */
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const fs = require('fs');

const FILE = process.argv[2] || '/sdcard/Download/WeiXin/_mobile/out/ever-mobile.html';
const OUT = '/sdcard/Download/WeiXin/_mobile/shots/';

(async () => {
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',
    args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 430, height: 860 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36',
  });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
  page.on('console', m => { const t = m.text(); if (m.type() === 'error' && !/ERR_CONNECTION_REFUSED|Access-Control-Allow-Origin/.test(t)) errs.push('CONSOLE: ' + t); });

  await page.goto('file://' + FILE + '?splash=off', { waitUntil: 'load', timeout: 120000 });
  await page.waitForTimeout(4200);
  for (const fr of page.frames()) {
    try { await fr.evaluate(() => { try { window.TEsplash && window.TEsplash.dismiss(); } catch (e) {} }); } catch (e) {}
  }
  await page.waitForTimeout(1200);

  const frEl = await page.$('#jh-frame');
  const d = await frEl.contentFrame();
  const state = async () => d.evaluate(() => {
    const on = [...document.querySelectorAll('.screen.on, .screen')].filter(e => e.offsetParent);
    return {
      screen: (document.querySelector('.screen.on') || {}).id || '',
      dots: [...document.querySelectorAll('#sdots .dot')].map(x => x.classList.contains('on') ? 1 : 0).join(''),
      page: (document.querySelector('.page.on') || {}).id || '',
      appsVis: (() => { const p = document.getElementById('pg-apps'); return !!(p && p.offsetParent); })(),
      mh: document.documentElement.getAttribute('data-mh'),
      scroll: (() => { const s = document.querySelector('.screen.on') || document.querySelector('.screen'); return s ? [s.scrollTop, s.scrollHeight] : null; })(),
    };
  });

  const log = async (tag) => {
    const s = await state();
    const fsFlag = await page.evaluate(() => !!(document.fullscreenElement || document.webkitFullscreenElement));
    console.log(tag, JSON.stringify({ ...s, fs: fsFlag }));
    await page.screenshot({ path: OUT + 'smoke-' + tag + '.png' });
  };

  await log('00-open');

  // 1) 第一次点按：应请求全屏
  await d.click('.screen .sheet, .screen', { position: { x: 30, y: 260 } }).catch(e => console.log('tap1', String(e).slice(0, 80)));
  await page.waitForTimeout(1200);
  await log('01-tap1');

  // 2) 翻到第 2 屏
  const dots = await d.$$('#sdots .dot');
  if (dots[1]) { await dots[1].click().catch(e => console.log('dot', String(e).slice(0, 80))); }
  await page.waitForTimeout(900);
  await log('02-dot2');
  if (dots[2]) { await dots[2].click().catch(e => {}); }
  await page.waitForTimeout(900);
  await log('03-dot3');

  // 3) 打开「应用」
  const rail = await d.$('#m2-bk-apps');
  if (rail) await rail.click().catch(e => console.log('rail', String(e).slice(0, 80)));
  await page.waitForTimeout(1200);
  await log('04-apps');

  // 4) 回首页（小圆点第 1 个 / 首页 tab）
  const back = await d.$('.ribbon [data-go="pg-home"]');
  if (back) await back.click().catch(e => {});
  await page.waitForTimeout(1000);
  await log('05-back-home');

  // 5) 滚动一下，看会不会被打回顶部
  await d.evaluate(() => { const s = document.querySelector('.screen'); if (s) s.scrollTop = 700; });
  await page.waitForTimeout(1400);
  await log('06-scrolled');

  console.log('== errors ==');
  console.log(errs.slice(0, 12).join('\n') || '(none)');
  await browser.close();
})();
