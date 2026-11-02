#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.03 · diag 再加两路：页面类名切换 / 滚动复位（"弹跳"还可能是这两种）

用户那边还没回新的现场。除已有的几何快照，再补两路最容易造成"弹一下"的事件：

  ① `cla` —— 桌面里 `.page` 的 class 变化（`.on` 被重加 = 整页重新入场）
              以及 body 里 `.page/.sheet/.screen` 节点的增删；
  ② `scr` —— 滚动位置变化：`.page.on.scrollTop`、`#pg-home > .track` 的 scrollLeft、
              iframe 自己的 scrollY。

变化才上报，最多 150 条。

用法：
    python3 _mobile/patch/round-803/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round803'
MARK = 'r803-diag2'


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
    print('已经是 8.03 版，跳过（要重打先 --revert）')
    sys.exit(0)

PATCH = r'''<script id="r803-diag2">
/* ===== 8.03 · diag 追加：页面类名切换 / 滚动复位 ==========================
   只有 ?diag=1 才跑。打到 http://<本机>:8931/log
   ========================================================================== */
(function(){
  if(!/[?&]diag=1/.test(location.search||'')) return;
  if(window.__r803diag) return; window.__r803diag=1;

  var HOST=(location.hostname||'127.0.0.1')+':8931';
  var sent=0, MAX=150, t0=performance.now();
  function send(k,d){
    if(sent>=MAX) return; sent++;
    try{ (new Image()).src='http://'+HOST+'/log?k='+encodeURIComponent(k)+'&t='+Math.round(performance.now()-t0)+
      '&d='+encodeURIComponent(String(d||'')).slice(0,900)+'&_='+Date.now(); }catch(e){}
  }
  function watch(doc, win){
    try{
      /* ① .page 的 class 变化 + 节点增删 */
      var pages=doc.querySelectorAll('.page');
      function hookCls(el, tag){
        try{
          new win.MutationObserver(function(ms){
            ms.forEach(function(m){
              var r=null; try{ var b=el.getBoundingClientRect(); r=[Math.round(b.left),Math.round(b.top),Math.round(b.width),Math.round(b.height)]; }catch(e){}
              send('cla', JSON.stringify({id:el.id||tag, to:el.className, rect:r, t:Math.round(performance.now()-t0)}));
            });
          }).observe(el,{attributes:true,attributeFilter:['class','style']});
        }catch(e){}
      }
      pages.forEach(function(el,i){ hookCls(el, 'idx'+i); });
      try{
        new win.MutationObserver(function(ms){
          ms.forEach(function(m){
            [].slice.call(m.addedNodes||[]).forEach(function(n){
              if(n.nodeType===1 && /(^|\s)(page|sheet|screen)(\s|$)/.test(n.className||''))
                send('add', JSON.stringify({cls:String(n.className).slice(0,40), id:n.id||'', phase:'add'}));
            });
            [].slice.call(m.removedNodes||[]).forEach(function(n){
              if(n.nodeType===1 && /(^|\s)(page|sheet|screen)(\s|$)/.test(n.className||''))
                send('add', JSON.stringify({cls:String(n.className).slice(0,40), id:n.id||'', phase:'del'}));
            });
          });
        }).observe(doc.body,{childList:true,subtree:true});
      }catch(e){}

      /* ② 滚动位置变化 */
      var lastS='';
      setInterval(function(){
        try{
          var pg=doc.querySelector('#pg-home .page.on')||doc.querySelector('.page.on');
          var tr=doc.querySelector('#pg-home > .track')||doc.querySelector('.track');
          var s=JSON.stringify({
            pg:pg?[Math.round(pg.scrollTop),Math.round(pg.scrollHeight),Math.round(pg.clientHeight)]:null,
            tr:tr?[Math.round(tr.scrollLeft),Math.round(tr.clientWidth)]:null,
            wy:Math.round(win.scrollY||0), wx:Math.round(win.scrollX||0)
          });
          if(s!==lastS){ send('scr', s); lastS=s; }
        }catch(e){}
      }, 350);
    }catch(e){}
  }
  var n=0, iv=setInterval(function(){
    try{
      var f=document.getElementById('jh-frame');
      var d=f&&f.contentDocument, w=f&&f.contentWindow;
      if(d&&w&&d.body){ clearInterval(iv); watch(d,w); }
    }catch(e){}
    if(++n>60) clearInterval(iv);
  }, 500);
})();
</script>
'''
src = rep1(src, '</body>', PATCH + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 8.03：diag 追加页面类名切换 / 滚动复位')
print('下一步：python3 _mobile/build.py --install')
