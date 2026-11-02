#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.92 · 家园强制横屏（不再"弹动"）

用户反馈：家园强制横屏，每次一进/一出家园，整页都会弹一下（空白一会儿，然后整块弹回来）。

真机上量到的两个原因（都跟"旋转"没关系，是"什么时候改尺寸/什么时候藏东西"）：

① 桌面被藏起来 → 回来要重新布局 + 重新栅格化
   `html:not(.jh-home-on) #jh-home{display:none}` 是进家园 800ms 后被 syncHomeClass()
   摘掉 class 触发的：整本 13 万行桌面 iframe 从"没有布局盒"变成"重新排一遍"。
   退出家园时又要反过来做一次，`teHomeLeave` 还先把所有 .pg 的 on 摘干净再加回来，
   中间有一段"没有任何页面是 on"的空档 → 实测退出后 0~500ms 是空白帧（截图只有 12KB），
   然后整块桌面才拍上去。
   改法：
     · 不再 display:none，改成只关可见性（visibility:hidden）—— 布局一直留着；
     · 家园开着的时候（html.te-home-open）强制保持可见 + 不接指针：
       桌面在家园底下**继续画着**，退出时一个字节都不用重排；
     · teHomeLeave 改成"先把上一页加回 on、同时立刻把 jh-home-on 摆正"，
       再也不等 800ms 一次的 syncHomeClass；
     · 家园期间把桌面文档里的 @keyframes 暂停（animation-play-state:paused），
       省下被盖住那层的持续重绘，退出时原地恢复（不重播、不跳）。

② 家园 iframe 先按竖屏排一遍，转 90° 后又排一遍
   7.85 是"先进家园、再转"：iframe 视口 430×932 → 932×430，编辑器 resize() 把整间屋子
   重新缩放一次，看到的就是"画面跳一下"。现在：
     · 盒子建出来（还没进 DOM）就先按横屏算好宽高，再 display:block，
       iframe 的**第一次**布局就是横屏；
     · 尺寸记住（data-fit），resize 连着来也只在真的变了才写样式；
     · 打字中（焦点在输入框 / 家园 iframe 里）一律不重算几何 —— 软键盘改 innerHeight，
       不能让家园每打一个字就重排一次。

用法：
    python3 _mobile/patch/round-7.92/apply.py
    python3 _mobile/patch/round-7.92/apply.py --revert
    python3 _mobile/build.py --install
    node _mobile/smoke.cjs /sdcard/Download/WeiXin/ever.html
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round92'
MARK = 'r92-home-land'


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
    print('已经是 7.92 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 桌面不再 display:none
OLD_CSS = 'html:not(.jh-home-on) #jh-home{display:none!important}'
NEW_CSS = '''/* ★ 7.92：**不再**用 display:none 藏桌面。
   藏起来 = 这 13 万行桌面下次显示时要重新布局 + 重新栅格化（真机实测退出家园后
   0~500ms 是空白帧，然后整块"弹"回原位）。只关可见性，布局一直在，回来只重画。 */
html:not(.jh-home-on) #jh-home{visibility:hidden!important;pointer-events:none!important}
/* 家园开着的时候桌面继续挂着画（家园那层是不透明的），退出时零重排 */
html.te-home-open #jh-home{display:block!important;visibility:visible!important;pointer-events:none!important}
/* ★ 7.92：家园横过来之后，它自己的「返回」正好落在屏幕右上角 —— 也就是全屏珍珠的位置，
   珍珠 z-index 比什么都高，一点就先吃掉了。家园期间先把珍珠收起来（退家园立刻回来）。 */
html.te-home-open #everFsPearl{display:none!important}'''
src = rep1(src, OLD_CSS, NEW_CSS, 'jh-home 显隐')

# ================================================================ ①.5 桌面层固定成常驻合成层
OLD_WC = '''#jh-home{position:fixed;left:0;top:0;z-index:6;transform-origin:0 0;overflow:hidden;
  overflow:hidden;background:#fdf5f3}'''
NEW_WC = '''#jh-home{position:fixed;left:0;top:0;z-index:6;transform-origin:0 0;overflow:hidden;
  overflow:hidden;background:#fdf5f3;
  /* ★ 7.92：桌面这层靠 transform 缩放，合成器每次重排/重画都要按新比例重新栅格化。
     真机上出现过"整页忽然放大到右下角一帧再回去"（旧比例的栅格被 1:1 贴上来）。
     固定成一个常驻合成层，比例就不再中途换。 */
  will-change:transform}'''
src = rep1(src, OLD_WC, NEW_WC, 'jh-home 合成层')

# ================================================================ ② 盒子一建出来就按横屏量好
OLD_BUILD = '''  box.appendChild(frame);
  document.body.appendChild(box);'''
NEW_BUILD = '''  box.appendChild(frame);
  /* ★ 7.92：进 DOM **之前**就把横屏几何算好（此刻没有布局盒，写样式零成本），
     这样 iframe 的第一次布局就是横屏视口，不会"先竖后横"地跳一下。 */
  try{ window.__m2HomeFit && window.__m2HomeFit(box); }catch(e){}
  document.body.appendChild(box);'''
src = rep1(src, OLD_BUILD, NEW_BUILD, 'build 预量横屏')

# resize 监听：换成幂等版（尺寸没变不写样式、打字中不动）
OLD_RS = """  /* 视口变化时重新摆一次（竖屏旋转 / 横屏铺满） */
  window.addEventListener('resize', function(){
    try{ if(box && getComputedStyle(box).display!=='none' && window.__m2ForceLandscape) window.__m2ForceLandscape(box); }catch(e){}"""
NEW_RS = """  /* 视口变化时重新摆一次（竖屏旋转 / 横屏铺满）。
     ★ 7.92：用幂等的 __m2HomeFit —— 尺寸没变时一个样式都不写，
     打字中（软键盘改 innerHeight）直接跳过，家园画面不会跟着抖。 */
  window.addEventListener('resize', function(){
    try{ if(box && getComputedStyle(box).display!=='none' && window.__m2HomeFit) window.__m2HomeFit(box); }catch(e){}"""
src = rep1(src, OLD_RS, NEW_RS, 'resize 幂等')

# ================================================================ ③ 进家园：先横屏、再露脸，并冻住桌面
OLD_ENTER = """  if(!frame.getAttribute('src')) frame.src=('aset/home4/editor.html?v='+encodeURIComponent(window.__everVer||'1'));
  box.style.display='block'; OPEN=true;"""
NEW_ENTER = """  if(!frame.getAttribute('src')) frame.src=('aset/home4/editor.html?v='+encodeURIComponent(window.__everVer||'1'));
  /* ★ 7.92 顺序很重要：先横屏量尺寸，再 display:block。
     反过来 = iframe 先按竖屏 430×932 排一遍，再被转成 932×430 → 编辑器 resize()
     把整间屋子重新缩一次（用户看到的"画面跳一下"）。 */
  try{ window.__m2HomeFit && window.__m2HomeFit(box); }catch(e){}
  box.style.display='block'; OPEN=true;
  /* 桌面那层被盖住了：暂停它的 @keyframes，别在底下一直重绘（退出时原地恢复） */
  try{ window.__teHomeHold && window.__teHomeHold(true); }catch(e){}"""
src = rep1(src, OLD_ENTER, NEW_ENTER, 'teHomeEnter 先量后显示')

# ================================================================ ④ 退家园：立刻摆正桌面，不等 800ms
OLD_LEAVE = """  try{ document.body.classList.remove('te-in-home'); }catch(e){}
  try{ document.documentElement.classList.remove('te-home-open'); }catch(e){}
  try{
    document.querySelectorAll('.pg').forEach(function(e){ e.classList.remove('on'); });
    var back=document.getElementById(_prevPg)||document.getElementById('p-home');
    if(back) back.classList.add('on');
  }catch(e){}
  return true;
};"""
NEW_LEAVE = """  try{ document.body.classList.remove('te-in-home'); }catch(e){}
  try{
    /* ★ 7.92：先**把上一页加回 on**，再摘别的 —— 顺序反过来会有一瞬"没有任何页面是 on"。
       顺手立刻把 jh-home-on 摆正：以前靠 800ms 一次的 syncHomeClass 慢慢放回来，
       桌面的布局/栅格化来不及，用户看到"空白一会儿 + 整块弹回来"。 */
    var back=document.getElementById(_prevPg)||document.getElementById('p-home');
    if(back) back.classList.add('on');
    document.querySelectorAll('.pg').forEach(function(e){ if(e!==back) e.classList.remove('on'); });
    document.documentElement.classList.toggle('jh-home-on', !!(back && back.id==='p-home'));
    /* 桌面动画原地恢复（暂停过，不会从第 0 帧重播） */
    window.__teHomeHold && window.__teHomeHold(false);
  }catch(e){}
  /* te-home-open 最后摘：摘早了这一帧桌面会被判成"不可见" */
  try{ document.documentElement.classList.remove('te-home-open'); }catch(e){}
  return true;
};"""
src = rep1(src, OLD_LEAVE, NEW_LEAVE, 'teHomeLeave 立即摆正')

# ================================================================ ④.5 不在首页时把桌面动画暂停
OLD_SYNC = '''  function syncHomeClass(){
    var on=false;
    try{ on=!!document.querySelector('#p-home.on'); }catch(e){}
    document.documentElement.classList.toggle('jh-home-on', on);
  }'''
NEW_SYNC = '''  function syncHomeClass(){
    var on=false;
    try{ on=!!document.querySelector('#p-home.on'); }catch(e){}
    document.documentElement.classList.toggle('jh-home-on', on);
    /* ★ 7.92：#jh-home 现在只是"看不见"（不再 display:none，见上面的 CSS 注释），
       不在首页时顺手把桌面文档里的 @keyframes 暂停，别在后台空转；回首页原地恢复。 */
    try{ window.__teHomeHold && window.__teHomeHold(!on); }catch(e){}
  }'''
src = rep1(src, OLD_SYNC, NEW_SYNC, 'syncHomeClass 暂停桌面动画')

# ================================================================ ⑤ 新脚本：横屏几何 + 桌面冻结
SCRIPT = r'''<script id="r92-home-land">
/* ===== 7.92 · 家园强制横屏（不弹版）==========================================
   ① 尺寸只在"真的变了"的时候重算：<meta viewport> / 地址栏 / 键盘都会连着发 resize，
      每次都重设 width/height 会让家园反复重排。
   ② 打字中一律不重算：焦点在输入框（或直接在家园 iframe 里）时 innerHeight 变得很厉害，
      那是软键盘，不是真的换了个屏幕。
   ③ 旋转只动 #teHome4 这一层（外层 fixed 容器）：不碰 requestFullscreen、
      不动手帐桌面、不动 App 其它页面。竖着拿手机时整块横过来铺满；
      手机本身横过来时视口已经是 932×430，和旋转后的尺寸**完全一样** → 再转一次零重排。
   ?land=0 可以整体关掉（出问题时用来对照）。
   ========================================================================== */
(function(){
  if(window.__r92Home) return; window.__r92Home=1;
  var OFF = /[?&]land=0/.test(location.search || '');

  window.__m2HomeFit = function(box, force){
    box = box || document.getElementById('teHome4');
    if(!box || OFF) return false;
    var vw = window.innerWidth || 0, vh = window.innerHeight || 0;
    if(!vw || !vh) return false;

    /* 打字中：几何一律不动（键盘改的是 innerHeight，家园画面不能跟着重排）。
       注意：点一下房间，document.activeElement 会变成**家园 iframe 本身**，
       那不是打字 —— 要进去看它里面的 activeElement 才算。 */
    var typing = false;
    try{
      var ae = document.activeElement;
      function isField(el){ return !!(el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)); }
      if(isField(ae)) typing = true;
      else if(ae && ae.tagName === 'IFRAME'){
        try{ typing = isField(ae.contentDocument && ae.contentDocument.activeElement); }catch(e){}
      }
    }catch(e){}
    if(!force && typing) return false;

    var cls = (vh > vw) ? 'P' : 'L';           /* 视口是竖的 / 横的 */
    if(!force && box.__fitCls === cls && box.__fitW === vw &&
       Math.abs(vh - (box.__fitH || 0)) < 140) return false;
    box.__fitCls = cls; box.__fitW = vw; box.__fitH = vh;

    if(cls === 'P'){
      /* 竖着拿：整块转 90° 铺满；iframe 因此拿到 vh×vw 的横屏视口 */
      box.style.transformOrigin = '0 0';
      box.style.transform = 'rotate(90deg)';
      box.style.left = vw + 'px'; box.style.top = '0px';
      box.style.right = 'auto'; box.style.bottom = 'auto';
      box.style.width = vh + 'px'; box.style.height = vw + 'px';
    }else{
      /* 本来就横着：直接铺满，不转 */
      box.style.transform = 'none';
      box.style.left = '0px'; box.style.top = '0px';
      box.style.right = '0px'; box.style.bottom = '0px';
      box.style.width = 'auto'; box.style.height = 'auto';
    }
    return true;
  };

  /* 家园覆盖桌面期间：把桌面文档里的 @keyframes 暂停（不是 animation:none —— 那会从第 0 帧重播）。
     样式只注入一次；退出时摘 class 原地恢复。 */
  window.__teHomeHold = function(on){
    try{
      var f = document.getElementById('jh-frame');
      var d = f && f.contentDocument;
      if(!d || !d.documentElement) return;
      if(!d.getElementById('teHomeHoldCss')){
        var s = d.createElement('style');
        s.id = 'teHomeHoldCss';
        s.appendChild(d.createTextNode(
          'html.te-home-hold *,html.te-home-hold *::before,html.te-home-hold *::after{'
          + 'animation-play-state:paused!important}'));
        (d.head || d.documentElement).appendChild(s);
      }
      d.documentElement.classList.toggle('te-home-hold', !!on);
    }catch(e){}
  };
})();
</script>
'''
src = rep1(src, '</body>', SCRIPT + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 7.92：家园强制横屏（先量后显示）/ 桌面不再藏起来 / 退出立即摆正')
print('下一步：python3 _mobile/build.py --install')
