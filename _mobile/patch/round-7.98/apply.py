#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.98 · 给"整页弹动"装一个远程现场记录（只在 ?diag=1 时生效）

无头里怎么点都不复现，只能让真机自己把现场发回来。打开
    http://192.168.188.210:8901/ever.html?phone=1&diag=1
之后，任何一次"弹动"都会把下面这些发到本机的 8931 端口（`_diag.log`）：

  · box  —— #jh-home 的矩形偏离视口的瞬间：矩形 / 内联样式 / tw,th,scale,fit
  · mh   —— 桌面文档 <html data-mh/data-view> 变化的瞬间：前后值 + iframe 视口
  · rs   —— 外层 window resize：innerWidth/Height、visualViewport
  · irs  —— 桌面 iframe 里的 resize：它的 innerWidth/Height
  · dpr  —— 启动时一次性上报：dpr、screen、viewport、UA

最多发 80 条就停（防止刷屏）。平时（没有 ?diag=1）这段代码一次都不跑。
诊断完把参数去掉即可，代码留着不影响正常使用。

用法：
    python3 _mobile/patch/round-7.98/apply.py
    python3 _mobile/build.py --install
    # 另一头：
    python3 _diag_server.py 8931     （已经在跑）
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round98'
MARK = 'r98-diag'


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
    print('已经是 7.98 版，跳过（要重打先 --revert）')
    sys.exit(0)

SCRIPT = r'''<script id="r98-diag">
/* ===== 7.98 · 远程现场记录（只有 ?diag=1 才跑）================================
   目的：把真机上"整页弹到右下角"那一瞬的几何发回来。无头里点不出来。
   打开 ?diag=1，任何异常都会发到 <本机>:8931/log（`_diag.log`）。
   ========================================================================== */
(function(){
  if(!/[?&]diag=1/.test(location.search||'')) return;
  if(window.__r98diag) return; window.__r98diag=1;

  var HOST=(location.hostname||'127.0.0.1')+':8931';
  var sent=0, MAX=80, t0=performance.now();
  function send(k, d){
    if(sent>=MAX) return; sent++;
    try{
      var q='?k='+encodeURIComponent(k)+'&t='+Math.round(performance.now()-t0)+
            '&d='+encodeURIComponent(String(d||'')).slice(0,700);
      (new Image()).src='http://'+HOST+'/log'+q+'&_='+Date.now();
    }catch(e){}
  }
  function R(el){ try{ var r=el.getBoundingClientRect(); return [Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)]; }catch(e){ return null; } }

  /* 启动信息 */
  try{
    send('dpr', JSON.stringify({
      dpr:devicePixelRatio, vw:innerWidth, vh:innerHeight,
      sw:screen.width, sh:screen.height,
      vv:(window.visualViewport?[Math.round(visualViewport.width),Math.round(visualViewport.height),+visualViewport.scale.toFixed(3)]:null),
      zoom:(getComputedStyle(document.documentElement).zoom||'1'),
      ua:String(navigator.userAgent||'').slice(0,120),
      url:String(location.href).slice(0,140)
    }));
  }catch(e){}

  /* 外层 resize / 可视视口变化 */
  window.addEventListener('resize', function(){
    send('rs', JSON.stringify({iw:innerWidth, ih:innerHeight,
      vv:(window.visualViewport?[Math.round(visualViewport.width),Math.round(visualViewport.height),+visualViewport.scale.toFixed(3)]:null)}));
  }, true);
  try{
    if(window.visualViewport) visualViewport.addEventListener('resize', function(){
      send('vv', JSON.stringify({w:Math.round(visualViewport.width), h:Math.round(visualViewport.height),
        s:+visualViewport.scale.toFixed(3), ox:Math.round(visualViewport.offsetLeft), oy:Math.round(visualViewport.offsetTop)}));
    });
  }catch(e){}

  /* #jh-home 盒子：只在"和视口对不上"的时候上报 */
  try{
    var box=document.getElementById('jh-home');
    if(box){
      new MutationObserver(function(){
        try{
          var r=box.getBoundingClientRect();
          var off=(Math.abs(r.left)>3||Math.abs(r.top)>3||
                   Math.abs(r.width-innerWidth)>3||Math.abs(r.height-innerHeight)>3);
          if(!off) return;
          send('box', JSON.stringify({
            r:[Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)],
            iw:innerWidth, ih:innerHeight,
            style:String(box.getAttribute('style')||'').slice(0,240),
            tw:box.dataset.tw, th:box.dataset.th, sc:box.dataset.scale, fit:box.dataset.fit,
            fs:!!(document.fullscreenElement||document.webkitFullscreenElement),
            cls:document.documentElement.className.slice(0,70)
          }));
        }catch(e){}
      }).observe(box,{attributes:true,attributeFilter:['style']});
    }
  }catch(e){}

  /* 桌面文档：data-mh / data-view / data-size 变了（= 整本换排版）就上报 */
  try{
    var fr=document.getElementById('jh-frame');
    function watchInner(){
      try{
        var d=fr&&fr.contentDocument;
        if(!d||!d.documentElement) return false;
        var root=d.documentElement;
        var last={mh:root.getAttribute('data-mh'), view:root.getAttribute('data-view'), size:root.getAttribute('data-size')};
        new MutationObserver(function(){
          try{
            var now={mh:root.getAttribute('data-mh'), view:root.getAttribute('data-view'), size:root.getAttribute('data-size')};
            if(now.mh===last.mh && now.view===last.view && now.size===last.size) return;
            send('mh', JSON.stringify({from:last, to:now,
              iw:fr.contentWindow.innerWidth, ih:fr.contentWindow.innerHeight,
              vw:innerWidth, vh:innerHeight}));
            last=now;
          }catch(e){}
        }).observe(root,{attributes:true,attributeFilter:['data-mh','data-view','data-size']});
        try{
          fr.contentWindow.addEventListener('resize', function(){
            send('irs', JSON.stringify({iw:fr.contentWindow.innerWidth, ih:fr.contentWindow.innerHeight,
              x:fr.contentWindow.scrollX, y:fr.contentWindow.scrollY}));
          }, true);
        }catch(e){}
        return true;
      }catch(e){ return false; }
    }
    if(!watchInner()){ var n=0, iv=setInterval(function(){ if(watchInner()||++n>40) clearInterval(iv); }, 500); }
  }catch(e){}
})();
</script>
'''
src = rep1(src, '</body>', SCRIPT + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 7.98：?diag=1 时把现场发到本机 8931（_diag.log）')
print('下一步：python3 _mobile/build.py --install')
