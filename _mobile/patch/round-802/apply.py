#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.02 · diag 升级：改看"画面里面"到底是哪一层在动

8.00 的 diag 只盯外层（#jh-home 盒子 + iframe 视口 + data-mh）。真机回传里
外层盒子一直是对的（没有一条 box 记录），但用户看到的画面确实偏了 ——
说明动的是**桌面文档内部**（纸页 / 轨道 / 它自己的缩放）。

这一版把探针伸进 iframe，每 400ms 记一次快照，任意一项变了就打点：

  外层：innerWidth/Height、visualViewport(scale/offset)、#jh-home 矩形
  内层：iframe 的 innerWidth/Height、<html> 的 data-mh/data-view/data-size/zoom/--z、
        body 的 transform、#pg-home > .track 的 scrollLeft/scrollWidth、
        #pg-home .page.on 的矩形与 transform、.app / .screen 的 transform

打点走同一套（`http://<本机>:8931/log`），最多 120 条。

用法：
    python3 _mobile/patch/round-802/apply.py
    python3 _mobile/build.py --install
    # 手机上打开：…/ever.html?phone=1&diag=1
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round802'
MARK = 'r802-deepdiag'


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
    print('已经是 8.02 版，跳过（要重打先 --revert）')
    sys.exit(0)

PATCH = r'''<script id="r802-deepdiag">
/* ===== 8.02 · 深层现场记录（只有 ?diag=1 才跑）=============================
   8.00 只盯外层盒子；真机上外层一直是对的，说明动的是桌面文档内部。
   这里每 400ms 快照一次"外层 + 内层"，谁变了就上报。
   ========================================================================== */
(function(){
  if(!/[?&]diag=1/.test(location.search||'')) return;
  if(window.__r802diag) return; window.__r802diag=1;

  var HOST=(location.hostname||'127.0.0.1')+':8931';
  var sent=0, MAX=120, t0=performance.now();
  function send(k,d){
    if(sent>=MAX) return; sent++;
    try{ (new Image()).src='http://'+HOST+'/log?k='+encodeURIComponent(k)+'&t='+Math.round(performance.now()-t0)+
      '&d='+encodeURIComponent(String(d||'')).slice(0,900)+'&_='+Date.now(); }catch(e){}
  }
  function rect(el){ try{ var r=el.getBoundingClientRect(); return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]; }catch(e){ return null; } }

  function snap(){
    var o={};
    try{
      o.iw=innerWidth; o.ih=innerHeight;
      o.vv=window.visualViewport?[Math.round(visualViewport.width),Math.round(visualViewport.height),
        +visualViewport.scale.toFixed(3),Math.round(visualViewport.offsetTop)]:null;
      var box=document.getElementById('jh-home');
      o.box=box?rect(box):null;
      o.boxT=box?getComputedStyle(box).transform:null;
      var f=document.getElementById('jh-frame');
      if(f){
        var w=f.contentWindow, d=f.contentDocument;
        o.fw=w.innerWidth; o.fh=w.innerHeight;
        o.fdpr=+String(w.devicePixelRatio||1).slice(0,5);
        if(d&&d.documentElement){
          var r=d.documentElement;
          o.mh=r.getAttribute('data-mh'); o.view=r.getAttribute('data-view'); o.size=r.getAttribute('data-size');
          var cs=w.getComputedStyle(r);
          o.hz=cs.zoom; o.z=(cs.getPropertyValue('--z')||'').trim();
          o.bodyT=d.body?w.getComputedStyle(d.body).transform:null;
          var tr=d.querySelector('#pg-home > .track')||d.querySelector('.track');
          if(tr) o.tr=[Math.round(tr.scrollLeft),Math.round(tr.scrollWidth),Math.round(tr.clientWidth)];
          var pg=d.querySelector('#pg-home .page.on')||d.querySelector('.page.on');
          if(pg) o.pg=rect(pg);
          var ap=d.querySelector('.app'); if(ap) o.appT=w.getComputedStyle(ap).transform;
          var sc=d.querySelector('#pg-home > .track > .screen')||d.querySelector('.screen');
          if(sc) o.scT=w.getComputedStyle(sc).transform;
        }
      }
    }catch(e){ o.err=String(e).slice(0,60); }
    return o;
  }

  var last=JSON.stringify(snap());
  setInterval(function(){
    try{
      var s=JSON.stringify(snap());
      if(s===last) return;
      var a=JSON.parse(last), b=JSON.parse(s), diff={};
      Object.keys(b).forEach(function(k){ if(JSON.stringify(a[k])!==JSON.stringify(b[k])) diff[k]=[a[k],b[k]]; });
      last=s;
      send('d', JSON.stringify(diff));
    }catch(e){}
  }, 400);
})();
</script>
'''
src = rep1(src, '</body>', PATCH + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 8.02：diag 升级为"外层+内层"的变化快照')
print('下一步：python3 _mobile/build.py --install')
