/* Ever · 网页版 PWA 的 service worker（8.55）
   ------------------------------------------------------------------
   目标三条：
     1. 打开秒进：ever.html 是 17MB 单文件（Pages gzip 后仍有 9.5MB），绝不能每次重下；
     2. 发版能立刻看到：只多问一个几十字节的 v.txt，版本变了才拉新的；
     3. 断网也能看已经加载过的部分。

   策略：
     · 页面（navigate / ever.html / index.html）
         → 缓存优先；命中缓存后**只**取 /v.txt（几十字节）比对 BUILD：
             版本没变 → 直接给缓存（秒开，不再重下 9.5MB）
             版本变了 → 拉一次新页面、更新缓存，这次就返回新的
     · 图片/字体/css/js → cache-first
     · 其它 → 走网络

   ★ 8.55 为什么改：8.54 试过"网络优先"，结果手机上每次打开都重下 9.5MB，
     慢网下表现就是"卡在开屏"。缓存优先 + 版本探针才是正解。

   发版时改两个地方：VER（换缓存桶，清旧）和 BUILD（必须等于 v.txt 里那行）。
*/
const VER = 'ever-860';
const BUILD = '8.59-split';

const PRECACHE = [
  './',
  './app.html',
  './doc.html',
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

/* ★ 8.56：根地址（/ 或 index.html）与 ever.html?v=… 共用**同一个缓存条目**，
   不然 17MB 的页面会在设备上存两份。内容本来就是同一份（index.html 是 ever.html 的副本）。 */
const PAGE_KEY = new URL('./app.html', self.location).href;

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
                 u.pathname.endsWith('/app.html') ||
                 u.pathname.endsWith('/doc.html') ||
                 u.pathname.endsWith('/index.html');

  if (isPage) {
    e.respondWith((async () => {
      const c = await caches.open(VER);
      const key = new Request(PAGE_KEY);
      const hit = await c.match(key);
      if (!hit) {
        try {
          const r = await fetch(req);
          if (r && r.ok) c.put(key, r.clone()).catch(() => {});
          return r;
        } catch (x) {
          return new Response('离线，且这台设备还没缓存过页面。', {
            status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
        }
      }
      const id = await remoteBuild();
      if (id && id !== BUILD) {
        try {
          const r = await fetch(req, { cache: 'no-cache' });
          if (r && r.ok) { c.put(key, r.clone()).catch(() => {}); return r; }
        } catch (x) {}
      }
      return hit;
    })());
    return;
  }

  if (/\.(png|jpe?g|webp|gif|svg|woff2?|ttf|otf|css|js)$/i.test(u.pathname)) {
    e.respondWith((async () => {
      const c = await caches.open(VER);
      const hit = await c.match(req);
      if (hit) return hit;
      try {
        const r = await fetch(req);
        if (r && r.ok) c.put(req, r.clone()).catch(() => {});
        return r;
      } catch (x) { return new Response('', { status: 504 }); }
    })());
    return;
  }
});
