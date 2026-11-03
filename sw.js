/* Ever · 网页版 PWA 的 service worker（v8.62 · 定版一套）
   ------------------------------------------------------------------
   一、只有一套产物：ever.html（单文件）+ aset/ + manifest + sw + v.txt。
      app.html / doc.html / js/ 那套拆包已经下架（文件从仓库删掉），不要再进入口。
   二、策略：**缓存优先 + 只查 50 字节版本号**
      · 页面：命中缓存后只取 ./v.txt 比对 BUILD；一样就直接给缓存（秒开），
        不一样才重新拉一次并更新缓存。这样"发版立刻生效"和"打开不重下 9.5MB"两头都要到了。
      · 图片/字体/css/js：cache-first。
   三、发版规矩（缺一个就会重现"每次重下"或"改了看不到"）：
        1) 换 VER（缓存桶名，旧桶在 activate 清掉）
        2) BUILD 改成新版本串
        3) v.txt 写**同一串**（必须一字不差）
      自验：连开两次，第二次必须 < 5 秒；否则就是这三处没对齐。
*/
const VER = 'ever-862';
const BUILD = '8.61.6';

const PRECACHE = [
  './',
  './v.txt',
  './manifest.webmanifest',
  './aset/pwa/icon-192.png',
  './aset/pwa/icon-512.png',
  './aset/pwa/icon-512-maskable.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(VER);
    await Promise.all(PRECACHE.map((u) => c.add(u).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== VER).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

async function remoteBuild() {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 2500);
    const r = await fetch('./v.txt?_=' + Date.now(), { cache: 'no-store', signal: ctl.signal });
    clearTimeout(t);
    if (!r.ok) return '';
    return (await r.text()).trim();
  } catch (x) { return ''; }
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  let u;
  try { u = new URL(req.url); } catch (x) { return; }
  if (u.origin !== self.location.origin) return;   /* 第三方接口 / 本机助手 一律不碰 */

  const isPage = req.mode === 'navigate' ||
                 u.pathname.endsWith('/') ||
                 u.pathname.endsWith('/ever.html') ||
                 u.pathname.endsWith('/index.html');

  if (isPage) {
    e.respondWith((async () => {
      const c = await caches.open(VER);
      /* 每个 URL 各存各的：/, /index.html, /ever.html 内容不同，绝不能共用一个 key
         （共用的那次直接导致了"跳转页自循环 → 白屏"） */
      const hit = await c.match(req, { ignoreSearch: true });
      const put = (r) => {
        if (!(r && r.ok && /text\/html/i.test(r.headers.get('content-type') || ''))) return;
        /* ★ 8.63：**必须 waitUntil**。不挂上去，SW 的 fetch 事件一结束，
           put 的写入就被掐断 —— 表现是"SW 是控制中，但页面永远命中不了缓存，每次重下 9.5MB"。 */
        const job = c.put(req, r.clone()).catch(() => {});
        try { e.waitUntil(job); } catch (x) {}
      };
      if (!hit) {
        try { const r = await fetch(req); put(r); return r; }
        catch (x) { return new Response('离线，且这台设备还没缓存过页面。', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }); }
      }
      const id = await remoteBuild();
      if (id && id !== BUILD) {
        try { const r = await fetch(req, { cache: 'no-cache' }); if (r && r.ok) { put(r); return r; } } catch (x) {}
      }
      return hit;
    })());
    return;
  }

  if (/\.(png|jpe?g|webp|gif|svg|woff2?|ttf|otf|css|js)$/i.test(u.pathname)) {
    e.respondWith((async () => {
      const c = await caches.open(VER);
      const hit = await c.match(req, { ignoreSearch: true });
      if (hit) return hit;
      try { const r = await fetch(req); if (r && r.ok) c.put(req, r.clone()).catch(() => {}); return r; }
      catch (x) { return new Response('', { status: 504 }); }
    })());
    return;
  }
});
