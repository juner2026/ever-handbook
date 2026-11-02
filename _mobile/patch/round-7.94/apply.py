#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.94 · 全屏珍珠：选 b —— 不再 requestFullscreen，改 App 内沉浸

用户拍板选 (b)：
  「点全屏珍珠会黑屏一阵」的根因是 `requestFullscreen` 会重建系统窗口，
  露出来的那 1~2 帧是系统合成器的黑，网页里的遮罩（7.91/7.87 那套米色 cover）盖不住。
  (b) = 彻底不调 requestFullscreen，改成 App 内沉浸：

    · 点珍珠 → 给 <html> 挂 `te-immersive`：收藏 App 自己的底部 Tab 栏和翻页浮标，
      首页/各页的底部留白收窄，桌面照常铺满；再点一下复原。
    · 启动后第一次点按**不再自动进全屏**（那条路每次必黑一下，还顺带整本桌面重排）。
    · 珍珠在沉浸状态下变淡（仍可点），不隐藏 —— 不然没法退出来。
    · 装到桌面（PWA）打开时 manifest 是 display:fullscreen，本来就是真全屏、没有浏览器栏，
      这条改动对它没有影响。

用法：
    python3 _mobile/patch/round-7.94/apply.py
    python3 _mobile/patch/round-7.94/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round94'
MARK = 'r94-immersive'


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
    print('已经是 7.94 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ 珍珠：点了切沉浸，不进全屏
OLD_PEARL = """        pearl.addEventListener('click', function(){
          var el=document.documentElement;
          var fn=el.requestFullscreen||el.webkitRequestFullscreen||el.mozRequestFullScreen||el.msRequestFullscreen;
          if(!fn) return;
          try{ var p=fn.call(el); if(p&&p.catch) p.catch(function(){}); }catch(e){}
        });"""
NEW_PEARL = """        pearl.addEventListener('click', function(){
          /* ★ 7.94（用户选 b）：**不再** requestFullscreen。
             真全屏会重建系统窗口，露出来的那 1~2 帧是系统合成器的黑，
             网页里的遮罩盖不住（用户："点全屏珍珠会黑屏一阵"）。
             改成 App 内沉浸：收起 App 自己的底部栏 / 翻页浮标，桌面铺满；再点一下复原。
             装到桌面（PWA，manifest display:fullscreen）时本来就是真全屏，这条不影响它。 */
          var on=false;
          try{ on=document.documentElement.classList.toggle('te-immersive'); }catch(e){}
          try{ pearl.setAttribute('aria-label', on?'退出沉浸':'沉浸（收起 App 的栏）'); }catch(e){}
        });"""
src = rep1(src, OLD_PEARL, NEW_PEARL, '珍珠改沉浸')

# ================================================================ 不再自动进全屏
OLD_ATT = """  function attempt(){
    if(OFF||locked) return;
    if(isFs()){ askLock(); return; }"""
NEW_ATT = """  function attempt(){
    /* ★ 7.94：不再自动进全屏（用户选 b）。
       以前启动后第一次点按就 requestFullscreen：那一下必黑一帧，还顺带整本桌面重排
       （用户："每点一下都弹动"里有一部分就是它）。方向锁需要全屏才可能成功，这里放弃；
       锁不住时由 __teFreeze（锁死不转兜底）保证"转动时版式不变"。 */
    return;
    if(OFF||locked) return;
    if(isFs()){ askLock(); return; }"""
src = rep1(src, OLD_ATT, NEW_ATT, 'attempt 关掉')

# ================================================================ 沉浸样式
CSS = r'''<style id="r94-immersive">
/* ============================================================
   7.94 · App 内沉浸（不做 requestFullscreen）
   点珍珠 → html.te-immersive：收起 App 自己的栏，再点复原
   ============================================================ */
html.te-immersive .bar{display:none!important}
html.te-immersive #tePageNav{display:none!important}
html.te-immersive .scr{padding-bottom:calc(18px + env(safe-area-inset-bottom,0px))!important}
html.te-immersive #everFsPearl{opacity:.42!important}
html.te-immersive #everFsPearl:active{opacity:.9!important}
/* 沉浸时页面顶部的安全区照旧留出来，别钻到刘海底下 */
html.te-immersive .ch-hd{padding-top:calc(8px + env(safe-area-inset-top,0px))!important}
</style>
'''
src = rep1(src, '</body>', CSS + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 7.94：珍珠 = App 内沉浸（不再 requestFullscreen）/ 不再自动进全屏')
print('下一步：python3 _mobile/build.py --install')
