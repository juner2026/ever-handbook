/* Ever · 自助退役的 service worker（v8.65）
   ==========================================================================
   为什么把它做成"自杀"：
     这轮反复出现的白屏，根源都是 SW 缓存了 17MB 单文件页面、而且写出的是**截断内容**
     （实测只存进 128KB），下次就把半截页面当正常页面发出去。
     与其继续和它斗，不如让它退役：
       · 页面交回浏览器自己的 HTTP 缓存（GitHub Pages 给 max-age=600，够用）；
       · 静态小资源也不需要它——本来就走浏览器缓存。
     代价：不能再"安装成 App"（少一个图标入口），但换来"打开就能用"。

   ★ 这个文件以后不要再往里加缓存逻辑。真要离线能力，另外开一个 scope 做，
     别动 /ever-handbook/ 这个站点的根。
*/
self.addEventListener('install', (e) => { self.skipWaiting(); });

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (x) {}
    try { await self.registration.unregister(); } catch (x) {}
    try {
      const cs = await self.clients.matchAll({ type: 'window' });
      cs.forEach((c) => { try { c.navigate(c.url); } catch (x) {} });
    } catch (x) {}
  })());
});

/* 不拦任何请求 */
