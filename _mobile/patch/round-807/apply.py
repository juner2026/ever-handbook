#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.07 · 「存储体检」点一下展开、再点一下收起

用户：「我希望点一下那个存储体检可以收起，也可以重新点开」。

原来那行（`st2-row`）的 run 只会 `storageScan()` —— 面板 `#storagePanel` 一旦被填上就一直是
display:block，只能再点去刷新，收不起来。

改法：
  · 新增 `window.storageToggle()`：面板开着且已有内容 → 收起（display:none）；
    否则跑一次 `storageScan()`（它会填内容并展开，顺带把面板滚进视野）；
  · 那一行的 run 改成调 `storageToggle()`；
  · `_stPaint()` 展开时打上 `data-open="1"`，收起时清掉，方便别的逻辑判断状态。

用法：
    python3 _mobile/patch/round-807/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round807'
MARK = 'r807-toggle'


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
    print('已经是 8.07 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 新增 storageToggle
OLD_SCAN = """window._stCache=null;
function storageScan(){"""
NEW_SCAN = """window._stCache=null;
/* ★ 8.07（用户要求）：存储体检点一下展开、再点一下收起。
   面板已经展开且有内容 → 收起；否则重新扫一次（顺带把面板滚进视野）。 */
window.storageToggle=function(){
  try{
    var el=document.getElementById('storagePanel');
    if(el && el.style.display!=='none' && el.getAttribute('data-open')==='1'){
      el.style.display='none';
      el.setAttribute('data-open','0');
      return true;
    }
  }catch(e){}
  try{ storageScan(); }catch(e){}
  setTimeout(function(){
    try{
      var el=document.getElementById('storagePanel');
      if(el && el.style.display!=='none' && el.scrollIntoView) el.scrollIntoView({block:'nearest',behavior:'smooth'});
    }catch(e){}
  }, 260);
  return true;
};
function storageScan(){"""
src = rep1(src, OLD_SCAN, NEW_SCAN, 'storageToggle')

# ================================================================ ② _stPaint 展开时打标记
OLD_PAINT = """  el.style.display='block';
  el.innerHTML='<div style="white-space:pre-wrap;font-size:11px;color:var(--tec141,#8a7068);line-height:1.8">'"""
NEW_PAINT = """  el.style.display='block';
  el.setAttribute('data-open','1');
  el.innerHTML='<div style="white-space:pre-wrap;font-size:11px;color:var(--tec141,#8a7068);line-height:1.8">'"""
src = rep1(src, OLD_PAINT, NEW_PAINT, '_stPaint 标记')

# ================================================================ ③ 那一行改成 toggle
OLD_ROW = """    { t:'存储体检', s:'谁在占地方', ic:'gauge', c1:'#e2b183', c2:'#b97c46', k:'存储 体检 storage 清理 占用 空间', run:function(){ if(typeof storageScan==='function') storageScan(); } }"""
NEW_ROW = """    { t:'存储体检', s:'谁在占地方', ic:'gauge', c1:'#e2b183', c2:'#b97c46', k:'存储 体检 storage 清理 占用 空间', run:function(){ if(typeof storageToggle==='function') storageToggle(); else if(typeof storageScan==='function') storageScan(); } }"""
src = rep1(src, OLD_ROW, NEW_ROW, 'tile run 改 toggle')

write(SHELL, src)
print('已打补丁 8.07：存储体检可展开/收起')
print('下一步：python3 _mobile/build.py --install')
