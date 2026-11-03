/* Ever · 网页版 PWA 的 service worker（v8.64 · 只做安全的事）
   ==========================================================================
   背景（这几轮踩过的坑，都写在这儿省得再犯）：
     1. app.html/doc.html/js 和 ever.html 两套并存 → 入口一改就互相覆盖；
     2. 把 "/"（跳转页）和 ever.html 共用一个缓存 key → 跳转页自循环 → 白屏；
     3. 在 SW 里给 17MB 的 ever.html 做缓存写入 → 实测会写出**截断的**内容
        （只存进 128KB），下次直接把它当页面发出去 → 页面彻底坏掉。
   --------------------------------------------------------------------------
   所以现在只做两件事：
     a) 静态小资源（图片/字体/css/js）cache-first —— 它们小、写缓存不会出问题；
     b) **页面请求一律走网络**，交给浏览器自己的 HTTP 缓存
        （GitHub Pages 给 ever.html 的是 cache-control: max-age=600，
         10 分钟内再打开就是浏览器缓存命中，不会再下 9.5MB）。
     c) 额外留一个 kill-switch：?nosw=1 打开页面会注销 SW 并清缓存（应急用）。
   这个 SW 仍然存在（保留"可安装成应用"的能力），只是不再碰大文件。
*/
const VER = 'ever-864';

self.addEventListener('install', (e) => { self.skipWaiting(); });

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== VER).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let u;
  try { u = new URL(req.url); } catch (x) { return; }
  if (u.origin !== self.location.origin) return;          /* 第三方 / 本机助手不碰 */

  /* 应急开关：?nosw=1 → 注销自己，并清掉本 SW 建的缓存 */
  if (u.search.indexOf('nosw=1') >= 0) {
    e.respondWith((async () => {
      try { const rs = await self.registration.unregister(); } catch (x) {}
      try { const keys = await caches.keys(); await Promise.all(keys.map((k) => caches.delete(k))); } catch (x) {}
      return Response.redirect(u.href.replace('nosw=1', 'nosw=0'), 302);
    })());
    return;
  }

  /* 页面：不拦，直接用浏览器 HTTP 缓存 + 网络（大文件缓存交给浏览器最可靠） */
  const isPage = req.mode === 'navigate' ||
                 u.pathname.endsWith('/') ||
                 u.pathname.endsWith('/ever.html') ||
                 u.pathname.endsWith('/index.html');
  if (isPage) return;                                      /* 让浏览器自己处理 */

  /* 静态小资源：cache-first */
  if (/\.(png|jpe?g|webp|gif|svg|woff2?|ttf|otf|css|js)$/i.test(u.pathname)) {
    e.respondWith((async () => {
      const c = await caches.open(VER);
      const hit = await c.match(req, { ignoreSearch: true });
      if (hit) return hit;
      try {
        const r = await fetch(req);
        if (r && r.ok && r.status === 200) {
          const job = c.put(req, r.clone()).catch(() => {});
          try { e.waitUntil(job); } catch (x) {}
        }
        return r;
      } catch (x) { return new Response('', { status: 504 }); }
    })());
  }
});
