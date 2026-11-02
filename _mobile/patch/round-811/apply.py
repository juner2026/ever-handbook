#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.10 · 开屏期间"冻结重排"把盒子锁死在错误尺寸 → 桌面缩成左上角一小块

用户截图：开屏那张「Ever / 手帐 JOURNAL」纸卡只占屏幕左上角约 1/4，下面一片白，
一直停在那儿（toast 还在跳）。

链路：
1. `layout()` 里有一道 6.51 加的闸门 ——
   `if(box.dataset.tw && !window.__jhSplashDone && !window.__everSplashTimeout) return;`
   开屏播放期间**冻结重排**（为了不让开屏动画被重排打乱）。
2. 如果盒子第一次量尺寸时视口还没稳定（WebView 首屏 / 慢网络 / 地址栏动画），
   `box.dataset.tw` 会被写成一个小值（比如 100 多）。
3. 之后每次 `layout()` 都被闸门挡住 → 盒子一直是小的 →
   桌面 iframe 只有 100 多像素宽，里面 92vw 的开屏纸卡就成了左上角的小卡片。
4. 7.95 加的自检纠偏 `__jhRelayout()` 也走 `layout()`，同样被这道闸门挡住 —— 所以修不动。

改法：
1. `layout(force)`：`force` 为真时**跳过**开屏冻结（自检纠偏用它）；
2. `__jhRelayout(force)` 透传；
3. 冻结本身加个硬上限：最多冻 2.5 秒（原来要等 `jh:splash-done`，最坏 9~12 秒）；
4. 7.95 的自检：盒子明显不对时用 `__jhRelayout(true)`，一次就改得动。

用法：
    python3 _mobile/patch/round-811/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round811'
MARK = 'r811-force-layout'


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
    print('已经是 8.10 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① layout(force) + 冻结上限
OLD = """  function layout(){
    if(!box) return;
    /* ★ 6.51：开屏动画播放期间冻结重排。
       进全屏（或地址栏收起）会改视口尺寸 → 立刻重排 → 桌面上正在播的开屏动画
       按旧尺寸定了位，一重排就"乱跳"（用户报的 bug）。
       策略：第一次照常排；之后若开屏还没结束（没收到 jh:splash-done 且未超 12s），先不动，
       等它播完再补一次 layout。 */
    try{
      if(box.dataset.tw && !window.__jhSplashDone && !window.__everSplashTimeout){
        window.__everLayoutPending = 1;
        return;
      }
    }catch(e){}"""
NEW = """  function layout(force){
    if(!box) return;
    /* ★ 6.51：开屏动画播放期间冻结重排。
       进全屏（或地址栏收起）会改视口尺寸 → 立刻重排 → 桌面上正在播的开屏动画
       按旧尺寸定了位，一重排就"乱跳"（用户报的 bug）。
       策略：第一次照常排；之后若开屏还没结束（没收到 jh:splash-done 且未超 12s），先不动，
       等它播完再补一次 layout。
       ★ 8.10：两条补充 ——
         (a) `force` 为真时无条件重排（自检纠偏用，否则修不动）；
         (b) 冻结最多 2.5 秒（原来要等 jh:splash-done，最坏 9~12 秒；首屏量歪了就会一直卡着）。 */
    try{
      if(!window.__everLayoutAt) window.__everLayoutAt = Date.now();
      var _frozen = (Date.now() - window.__everLayoutAt) < 2500;
      if(!force && box.dataset.tw && _frozen && !window.__jhSplashDone && !window.__everSplashTimeout){
        window.__everLayoutPending = 1;
        return;
      }
    }catch(e){}"""
src = rep1(src, OLD, NEW, 'layout(force)')

# ================================================================ ② __jhRelayout 透传 force
OLD_RL = """  window.__jhRelayout=function(){ try{ layout(); }catch(e){} };"""
NEW_RL = """  window.__jhRelayout=function(force){ try{ layout(force);

    /* 8.10：强制重排时顺手把"冻结"标记清掉，免得后面又被挡住 */
    if(force){ try{ window.__jhSplashDone = 1; window.__everLayoutPending = 0; }catch(e){} }
  }catch(e){} };"""
src = rep1(src, OLD_RL, NEW_RL, '__jhRelayout(force)')

# ================================================================ ③ 自检纠偏用 force
OLD_GUARD = """      try{ box.__laySig=''; }catch(e){}
      try{ window.__jhRelayout && window.__jhRelayout(); }catch(e){}"""
NEW_GUARD = """      try{ box.__laySig=''; }catch(e){}
      /* ★ 8.10：必须带 force —— 不带的话会被"开屏冻结"挡住，盒子永远修不回来 */
      try{ window.__jhRelayout && window.__jhRelayout(true); }catch(e){}"""
src = rep1(src, OLD_GUARD, NEW_GUARD, 'guard 用 force')

write(SHELL, src)
print('已打补丁 8.10：layout(force) 绕过开屏冻结 + 冻结上限 2.5s + 自检用 force')
print('下一步：python3 _mobile/build.py --install')
