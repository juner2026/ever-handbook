#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.01 · 真机现场找到了：`?phone=1` 没真的"当手机"，平板缩放两套模式在反复切

8.00 之前加的 `?diag=1` 打点，用户在手机上打开后回传的第一条就说明问题：

    {"dpr":2.9486,"vw":700,"vh":413,"sw":1050,"sh":700,"vv":[700,413,1.5],"zoom":"1",
     "ua":"...Android 16; PA2573 ... wv) AppleWebKit/537.36 ... Version/4.0 ..."}

这台机的 `screen` 报的是 **1050×700**（短边 700 > 560），于是：

- `__teLockPortrait` 把 **PHONE 判成 false** → `?phone=1` 白写了，冻结/锁定全走平板分支；
- tbFit 的 `apply()` 走"横屏平板"分支：`s=min(1050/600,1.5)=1.5`
  → `setMeta('width=700,initial-scale=1.5')`（正好对上 innerWidth=700 / 页面 scale=1.5）；
- `appScale()` 读 meta 的 initial-scale = **1.5** → `layout()` 写 `width=1050 + scale(0.667)`；
- 这套 meta/zoom 之间还有一条"meta 生效不了就退回 zoom"的校验，回退又会改 innerWidth，
  resize 又触发 apply() —— **两套模式来回切，每切一次整页重排**。

用户看到的"整个画面弹动"就是这两套缩放机制在原地打架。

改法（三处，都围绕"`?phone=1` 就老老实实 1:1 画手机版"）：

1. `__teLockPortrait`：`?phone=1` / `te-force-phone` → **PHONE 强制 true**，
   并且 `OFF=true`（不做"冻结竖屏"那套 —— 横过来就让桌面按横屏正常铺满）；
2. tbFit 的 `apply()`：`?phone=1` → 永远 `setMeta(BASE); setZoom(1); mode='off'`，
   不进平板缩放分支；
3. `appScale()`：`?phone=1` → 直接返回 `{s:1,zoom:false}`，不再信 meta/zoom。

另外给 tbFit 的 meta↔zoom 兜底加了一条**防抖**：2 秒内来回切超过 2 次就
停用缩放（回到 BASE + zoom off），不再无限拉锯。

用法：
    python3 _mobile/patch/round-801/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round801'
MARK = 'r801-forcephone'


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
    print('已经是 8.01 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① PHONE 强制 / OFF
OLD_PHONE = """  var PHONE=false;
  try{
    var sw=(window.screen&&screen.width)||0, sh=(window.screen&&screen.height)||0;
    PHONE = !!(sw&&sh&&Math.min(sw,sh)<=560);
  }catch(e){}
  try{ if(/[?&]tablet=1/.test(location.search||'')) PHONE=false; }catch(e){}
  window.__tePhoneLock=PHONE;

  var OFF=!PHONE;
  try{ if(/[?&]nolock=1/.test(location.search||'')) OFF=true; }catch(e){}"""
NEW_PHONE = """  var PHONE=false;
  try{
    var sw=(window.screen&&screen.width)||0, sh=(window.screen&&screen.height)||0;
    PHONE = !!(sw&&sh&&Math.min(sw,sh)<=560);
  }catch(e){}
  /* ★ 8.01：`?phone=1` 就是"按手机画"。真机上（vivo WebView）screen 报 1050×700，
     短边 700 > 560 → PHONE 会被判成 false，`?phone=1` 白写，冻结/缩放全走平板分支，
     两套缩放来回切 = 用户看到的"整个画面弹动"。这里强制按手机处理。 */
  var _forcePhone=false;
  try{ _forcePhone=/[?&](phone=1|view=phone)/.test(location.search||'') || localStorage.getItem('te-force-phone')==='1'; }catch(e){}
  if(_forcePhone) PHONE=true;
  try{ if(/[?&]tablet=1/.test(location.search||'')){ PHONE=false; _forcePhone=false; } }catch(e){}
  window.__tePhoneLock=PHONE;

  var OFF=!PHONE;
  /* 8.01：?phone=1 时不做"冻结竖屏"（横过来就按横屏正常铺满，别把版面缩成一团） */
  if(_forcePhone) OFF=true;
  try{ if(/[?&]nolock=1/.test(location.search||'')) OFF=true; }catch(e){}"""
src = rep1(src, OLD_PHONE, NEW_PHONE, 'PHONE 强制')

# ================================================================ ② tbFit apply 一进来就退出
OLD_APPLY = """  function apply(){
    try{
      if(isMobile()){
        var w = devW(), h = devH();"""
NEW_APPLY = """  function apply(){
    try{
      /* ★ 8.01：?phone=1 → 永远 1:1 画手机版，不参与平板缩放判定。 */
      try{
        if(/[?&](phone=1|view=phone)/.test(location.search||'') || localStorage.getItem('te-force-phone')==='1'){
          setMeta(BASE); setZoom(1); mode='off'; return;
        }
      }catch(e){}
      if(isMobile()){
        var w = devW(), h = devH();"""
src = rep1(src, OLD_APPLY, NEW_APPLY, 'tbFit force-phone')

# ================================================================ ③ appScale 强制 1
OLD_SCALE = """  function appScale(){
    /* ① CSS zoom（桌面内核 / 不认 viewport meta 的环境）
       ② meta initial-scale（安卓 WebView / Chrome 手机+平板）
       ③ 都没有 → 1:1 */
    var z=1;"""
NEW_SCALE = """  function appScale(){
    /* ★ 8.01：?phone=1 → 一律 1:1。真机上 meta 的 initial-scale 会被平板缩放改成 1.5，
       读出来再乘回盒子宽度就会和 transform 打架（这就是弹动的来源）。 */
    try{
      if(/[?&](phone=1|view=phone)/.test(location.search||'') || localStorage.getItem('te-force-phone')==='1')
        return {s:1, zoom:false};
    }catch(e){}
    /* ① CSS zoom（桌面内核 / 不认 viewport meta 的环境）
       ② meta initial-scale（安卓 WebView / Chrome 手机+平板）
       ③ 都没有 → 1:1 */
    var z=1;"""
src = rep1(src, OLD_SCALE, NEW_SCALE, 'appScale force 1')

# ================================================================ ④ meta↔zoom 防抖
OLD_FALLBACK = """        /* 校验：若环境不认 viewport meta（桌面内核），布局宽度不会变成 L → 改用 zoom */
        setTimeout(function(){
          if(mode !== 'meta') return;
          var got = window.innerWidth || 0;
          if(!got) return;"""
NEW_FALLBACK = """        /* ★ 8.01：meta ↔ zoom 来回切的防抖。
           真机上出现过这种拉锯：meta 生效后 innerWidth 变了 → 校验认为"没生效" → 退回 zoom
           → zoom 又改 innerWidth → 下次 resize 再试 meta …… 每切一次整页重排。
           2 秒内切超过 2 次就彻底停用缩放（BASE + zoom off）。 */
        try{
          var _now=Date.now();
          if(!window.__tbFlip || _now-window.__tbFlip.t>2000) window.__tbFlip={t:_now,n:0};
          window.__tbFlip.n++;
          if(window.__tbFlip.n>2){
            setMeta(BASE); setZoom(1); mode='off';
            try{ console.log('[tbFit] 缩放模式来回切太多次，停用缩放'); }catch(e){}
            return;
          }
        }catch(e){}
        /* 校验：若环境不认 viewport meta（桌面内核），布局宽度不会变成 L → 改用 zoom */
        setTimeout(function(){
          if(mode !== 'meta') return;
          var got = window.innerWidth || 0;
          if(!got) return;"""
src = rep1(src, OLD_FALLBACK, NEW_FALLBACK, 'tbFit 防抖')

write(SHELL, src)
print('已打补丁 8.01：?phone=1 强制 1:1（PHONE/OFF/appScale/tbFit）+ meta↔zoom 防抖')
print('下一步：python3 _mobile/build.py --install')
