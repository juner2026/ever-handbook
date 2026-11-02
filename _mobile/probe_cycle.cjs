/* 家园进/出两轮：第二轮（iframe 已经活着）是不是立刻出画面
   node _mobile/probe_cycle.cjs
*/
const { chromium } = require('/usr/local/lib/node_modules/playwright');
const path = require('path');
const OUT = '/sdcard/Download/WeiXin/_mobile/shots';
const URL = 'http://127.0.0.1:8901/ever.html?phone=1&splash=off';

(async () => {
  const browser = await chromium.launch({
    executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux/chrome',
    args: ['--no-sandbox', '--allow-file-access-from-files', '--disable-dev-shm-usage'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 430, height: 932 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Mobile Safari/537.36',
  });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('PAGEERROR: ' + e.message));
  await p.goto(URL, { waitUntil: 'load', timeout: 120000 });
  await p.waitForTimeout(4200);
  for (const fr of p.frames()) { try { await fr.evaluate(() => { try { window.TEsplash && TEsplash.dismiss(); } catch (e) {} }); } catch (e) {} }
  await p.waitForTimeout(900);

  const burst = async (tag, marks) => {
    let prev = 0;
    for (const ms of marks) {
      if (ms > prev) { await p.waitForTimeout(ms - prev); prev = ms; }
      await p.screenshot({ path: path.join(OUT, `cyc-${tag}+${ms}.png`) }).catch(() => {});
    }
  };
  // 第一轮
  await p.evaluate(() => window.teHomeEnter());
  await burst('r1enter', [0, 120, 300, 700, 1500]);
  await p.waitForTimeout(1800);
  await p.evaluate(() => window.teHomeLeave());
  await burst('r1leave', [0, 80, 200, 400]);
  await p.waitForTimeout(1000);
  // 第二轮（iframe 早已加载过）
  await p.evaluate(() => window.teHomeEnter());
  await burst('r2enter', [0, 40, 90, 160, 300]);
  await p.waitForTimeout(1500);
  await p.evaluate(() => window.teHomeLeave());
  await burst('r2leave', [0, 40, 90, 160, 300]);
  if (errs.length) console.log('ERRORS: ' + [...new Set(errs)].slice(0, 5).join(' | '));
  await browser.close();
})();
