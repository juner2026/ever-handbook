#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.08 · APK（WebView）里整套被放大 1.9 倍 —— 判"手机/平板"用错了 screen

用户在 APK 里打开：「比例错误」。复现出来了（Playwright 模拟 APK 环境：
`app.local` 域名、viewport 393×838、但 WebView 里 `screen` 报的是物理像素 1080×2412）：

    {"screen":[1080,2412],"iw":393,"ih":838,
     "phoneLock":false,"lockOff":true,
     "hz":"1.9",              ← <html> 被加了 zoom:1.9，整页放大 1.9 倍
     "meta":"width=device-width,initial-scale=1,..."}

两条判定都读了 `screen`，而 Android WebView 的 `screen.width/height` 经常是**物理像素**
（1080×2412，短边 1080 > 560）→ 这台手机被当成平板 →

- `__teLockPortrait` 的 `PHONE=false`；
- tbFit 走平板分支：`s = min(1080/520, 1.9) = 1.9` → `setMeta(initial-scale)` 或 `html{zoom:1.9}`
  → **整页放大 1.9 倍**，就是用户看到的"比例错误"。

改法：判定改成**以 CSS 视口（innerWidth/innerHeight）为准**，screen 只作兜底。

1. tbFit：`devW()/devH()` 优先 `innerWidth/innerHeight`；
2. `__teLockPortrait`：短边取 `min(innerWidth,innerHeight)`，取不到才退 screen；
3. 顺带把阈值统一成 600（和 tbFit 的 PHONE_SHORT 一致）。

用法：
    python3 _mobile/patch/round-809/apply.py
    python3 _mobile/build.py --install
    bash _apk/repack-assets.sh 8.08
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round809'
MARK = 'r809-innerw'


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


def rep1(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit('锚点 %s 出现 %d 次（应为 1）' % (label, n))
    return text.replace(old, new)


if '--revert' in sys.argv:
    if os.path.exists(BAK):
        shutil.copy2(BAK, SHELL)
        print('还原', os.path.basename(SHELL))
    else:
        print('没有备份，跳过')
    sys.exit(0)

src = read(SHELL)

if not os.path.exists(BAK):
    shutil.copy2(SHELL, BAK)
    print('已备份 →', os.path.basename(BAK))

if MARK in src:
    print('已经是 8.08 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① tbFit：用 CSS 视口
OLD_DEV = """  function devW(){ return Math.round(screen.width  || window.innerWidth  || 0); }
  function devH(){ return Math.round(screen.height || window.innerHeight || 0); }"""
NEW_DEV = """  /* ★ 8.08：**先看 CSS 视口**（innerWidth/innerHeight），screen 只作兜底。
     Android WebView 的 screen.width/height 经常是物理像素（1080×2412）——
     拿它判"平板"，手机就会被放大到 1.9 倍（APK 里"比例错误"就是这么来的）。 */
  function devW(){ return Math.round(window.innerWidth  || screen.width  || 0); }
  function devH(){ return Math.round(window.innerHeight || screen.height || 0); }"""
src = rep1(src, OLD_DEV, NEW_DEV, 'devW/devH')

# ================================================================ ② 锁屏脚本：短边也用 CSS 视口
OLD_PHONE = """  var PHONE=false;
  try{
    var sw=(window.screen&&screen.width)||0, sh=(window.screen&&screen.height)||0;
    PHONE = !!(sw&&sh&&Math.min(sw,sh)<=560);
  }catch(e){}"""
NEW_PHONE = """  var PHONE=false;
  try{
    /* ★ 8.08：短边以 CSS 视口为准（WebView 的 screen 是物理像素，会把手机判成平板）。
       取不到才退 screen。阈值和 tbFit 的 PHONE_SHORT 统一成 600。 */
    var _pw=(window.innerWidth||0)||((window.screen&&screen.width)||0);
    var _ph=(window.innerHeight||0)||((window.screen&&screen.height)||0);
    PHONE = !!(_pw&&_ph&&Math.min(_pw,_ph)<=600);
  }catch(e){}"""
src = rep1(src, OLD_PHONE, NEW_PHONE, 'PHONE 判定')

write(SHELL, src)
print('已打补丁 8.08：手机/平板判定改用 CSS 视口（修 APK 里 1.9 倍放大）')
print('下一步：python3 _mobile/build.py --install && bash _apk/repack-assets.sh 8.08')
