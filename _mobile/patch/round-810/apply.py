#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.09 · 设置里加一个「环境自检」——把屏幕/缩放的真实数字摆出来

背景：8.08 修了"APK 里整页放大 1.9 倍"（WebView 的 screen 报物理像素），
但用户装完截图显示是反过来的：桌面缩成左上角一小块、下面大片空白。
这说明同一个环境里还有第二个比例问题，而我在容器里看不到 APK 的 WebView 真相。

不再猜 —— 在 App 里加一行「环境自检」，点开就显示这些数字（不需要 URL 参数，APK 里也能点）：

    innerWidth × innerHeight、devicePixelRatio、visualViewport(宽/高/scale)、
    screen(宽/高)、<meta viewport> 的当前值、<html> 的 zoom、--z、
    #jh-home 的矩形与 transform、桌面 iframe 的 innerWidth/Height、UA

用法：
    python3 _mobile/patch/round-810/apply.py
    python3 _mobile/build.py --install
    bash _apk/repack-assets.sh 8.09
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round810'
MARK = 'r810-envinfo'


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
    print('已经是 8.09 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 自检面板函数
SCRIPT = r'''<script id="r810-envinfo">
/* ===== 8.09 · 环境自检（设置里点一下就能看，APK 里也能用） ================= */
(function(){
  if(window.teEnvInfo) return;
  function _r(el){ try{ var b=el.getBoundingClientRect(); return [Math.round(b.left),Math.round(b.top),Math.round(b.width),Math.round(b.height)]; }catch(e){ return null; } }
  function collect(){
    var o={};
    try{
      o['innerWidth × innerHeight'] = innerWidth + ' × ' + innerHeight;
      o['devicePixelRatio'] = devicePixelRatio;
      o['visualViewport'] = window.visualViewport
        ? (Math.round(visualViewport.width) + ' × ' + Math.round(visualViewport.height) + '  scale ' + (+visualViewport.scale).toFixed(3))
        : '（没有）';
      o['screen'] = screen.width + ' × ' + screen.height + '  avail ' + screen.availWidth + ' × ' + screen.availHeight;
      var m=document.querySelector('meta[name="viewport"]');
      o['meta viewport'] = m ? String(m.getAttribute('content')) : '（无）';
      o['html zoom'] = getComputedStyle(document.documentElement).zoom;
      o['html --tbz'] = getComputedStyle(document.documentElement).getPropertyValue('--tbz').trim() || '-';
      o['__everVer'] = window.__everVer || '-';
      o['纯手机锁定 / 关锁'] = (window.__tePhoneLock?'是':'否') + ' / ' + (window.__teLockOff?'关':'开');
      var box=document.getElementById('jh-home');
      if(box){
        o['#jh-home 矩形'] = _r(box).join(', ');
        o['#jh-home transform'] = getComputedStyle(box).transform;
        o['#jh-home 数据'] = 'tw ' + box.dataset.tw + ' · th ' + box.dataset.th + ' · s ' + box.dataset.scale + ' · fit ' + box.dataset.fit;
      }
      var f=document.getElementById('jh-frame');
      if(f){
        try{
          o['桌面 iframe 视口'] = f.contentWindow.innerWidth + ' × ' + f.contentWindow.innerHeight;
          var d=f.contentDocument.documentElement;
          o['桌面 data-mh/view/fit'] = d.getAttribute('data-mh') + ' / ' + d.getAttribute('data-view') + ' / ' + d.getAttribute('data-fit');
          o['桌面 --z'] = getComputedStyle(d).getPropertyValue('--z').trim() || '-';
        }catch(e){ o['桌面 iframe'] = '读不到'; }
      }
      o['UA'] = String(navigator.userAgent||'').slice(0,160);
    }catch(e){ o['错误'] = String(e); }
    return o;
  }
  window.teEnvInfo = function(){
    var o=collect(), body='';
    for(var k in o){
      body += '<div style="display:flex;gap:8px;padding:6px 0;border-bottom:1px dashed rgba(200,170,180,.35)">'
        + '<span style="flex:0 0 42%;color:#a98a90;font-size:11px">'+k+'</span>'
        + '<span style="flex:1;color:#4c3a3f;font-size:11.5px;word-break:break-all;font-family:ui-monospace,Menlo,monospace">'+String(o[k])+'</span></div>';
    }
    var ov=document.createElement('div');
    ov.style.cssText='position:fixed;inset:0;z-index:2147483003;background:rgba(60,35,45,.35);display:flex;align-items:flex-end;justify-content:center;padding:0 8px calc(8px + env(safe-area-inset-bottom,0px))';
    ov.innerHTML='<div style="width:100%;max-width:560px;max-height:82vh;overflow:auto;background:linear-gradient(180deg,#fffdfa,#fbf3f1);border:1.5px solid rgba(236,159,186,.6);border-radius:16px 16px 8px 8px;padding:14px 16px 18px;box-shadow:0 -10px 30px -16px rgba(120,70,96,.5)">'
      +'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><b style="flex:1;font-size:14px;color:#6a4545">环境自检</b>'
      +'<span data-x="1" style="font-size:20px;line-height:1;color:#c48a82;padding:2px 8px">×</span></div>'
      +'<div style="color:#8a7a7a;font-size:10.5px;margin-bottom:8px">截图这一页发我，就能定位"比例不对"到底是哪一层</div>'
      +body+'</div>';
    ov.addEventListener('click', function(e){
      if(e.target===ov || (e.target.getAttribute && e.target.getAttribute('data-x'))) ov.remove();
    });
    document.body.appendChild(ov);
    return true;
  };
})();
</script>
'''
src = rep1(src, '</body>', SCRIPT + '</body>', '</body>')

# ================================================================ ② 设置里加一行
OLD_GROUPS = """    { t:'图片', en:'MEDIA', rows:[
      { t:'发过的所有图片存档', s:'聊天里发过的每一张', v:'图库', ic:'archive', c:'#c96a90', k:'图片 存档 相册 photos 图库 清理', run:function(){ openRecentImgs(); } },
      { t:'AI 生成的图存放地点', s:'生成图存在哪、可清理', v:'路径', ic:'sparkle', c:'#8264b5', k:'ai 生成 图 存放 路径 位置 清理', run:function(){ aiImgInfo(); } }
    ]}
  ];"""
NEW_GROUPS = """    { t:'图片', en:'MEDIA', rows:[
      { t:'发过的所有图片存档', s:'聊天里发过的每一张', v:'图库', ic:'archive', c:'#c96a90', k:'图片 存档 相册 photos 图库 清理', run:function(){ openRecentImgs(); } },
      { t:'AI 生成的图存放地点', s:'生成图存在哪、可清理', v:'路径', ic:'sparkle', c:'#8264b5', k:'ai 生成 图 存放 路径 位置 清理', run:function(){ aiImgInfo(); } }
    ]},
    /* ★ 8.09：屏幕 / 缩放的真实数字摆出来（排查"比例不对"用） */
    { t:'诊断', en:'DIAG', rows:[
      { t:'环境自检', s:'屏幕尺寸 / 缩放 / 桌面盒子', v:'查看', ic:'gauge', c:'#7f8fa6', k:'环境 自检 诊断 分辨率 缩放 dpr 视口 debug', run:function(){ try{ window.teEnvInfo&&teEnvInfo(); }catch(e){} } }
    ]}
  ];"""
src = rep1(src, OLD_GROUPS, NEW_GROUPS, '设置加自检行')

write(SHELL, src)
print('已打补丁 8.09：设置 → 诊断 → 环境自检')
print('下一步：python3 _mobile/build.py --install && bash _apk/repack-assets.sh 8.09')
