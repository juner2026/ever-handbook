#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.95 · 思考链只留工具时间轴 / 家园聊天窗能拖 / 桌面"弹到右下角"自检纠偏

用户这一轮的反馈：
  「家园聊天页移动不了，屏幕依旧会弹动影响体验，弹动如图（整页跑到右下角），
    基本点任何都会，那个思考链的原文给去掉，现在这版的群聊显示的是单聊界面」

① 思考链：去掉思考原文，只留工具调用时间轴
   `tpToggle()` 原来把「时间轴 + mdToHtml(思考原文)」一起塞进面板；用户要的是只看
   调用了什么工具。现在面板里只画时间轴；没有工具调用就显示一句提示。
   「原文」按钮一并藏掉（没原文可看了）。

② 家园聊天窗拖不动：宿主的坐标被转了两遍
   `#teHome4` 在竖屏下是 rotate(90deg) 的，聊天窗是它的子节点，`HQ.off` 是**宿主局部坐标**。
   但 `hqClampPos()` 拿 `getBoundingClientRect()`（**屏幕坐标**）去夹这个局部偏移：
   转了 90° 之后屏幕 x 和局部 y 混在一起，可移动范围被算错 —— 拖起来就像"拖不动/弹回去"。
   现在按宿主有没有转 90° 分别换算：屏幕位移 (sx,sy) ↔ 局部位移 (sy,-sx)，
   先把屏幕上的合法范围算出来，再换回局部坐标夹一次。

③ "整页弹到右下角"（用户截图）自检 + 纠偏
   `#jh-home` 是 fixed inset:0 的整屏盒子，正常情况下它的 getBoundingClientRect() 必须
   等于视口 (0,0,innerWidth,innerHeight)。用户截图里那块明显是"被放大/被挪走"的状态，
   而且是能截图留住的持续状态 —— 也就是某个瞬间 `layout()` 把 width/height/transform
   写成了一组对不上的值（fit / freeze 基准 / appScale 任意一个取到脏值都会这样）。
   这次不去赌具体哪一步脏了，直接加自检：
     · 每 250ms + resize + 点按后各查一次盒子矩形；
     · 一旦发现偏离视口 >3px（或 scale/fit 明显异常）→ 把冻结基准复位成当前视口，
       清掉 layout 的签名缓存，重新 layout 一次；
     · 顺手把当时的现场（盒子的 style、视口、appScale、freeze 基准）写进
       localStorage['te_bad_layout']，下次真出问题可以直接读出来定位。

用法：
    python3 _mobile/patch/round-7.95/apply.py
    python3 _mobile/patch/round-7.95/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round95'
MARK = 'r95-fix'


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
    print('已经是 7.95 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 思考链只留时间轴
OLD_TP = """  if(pb) pb.innerHTML = tl + (raw ? mdToHtml(raw) : '<i style="color:var(--tec13,#cf9bb0)">（这次没有思考链）</i>');"""
NEW_TP = """  /* ★ 7.95（用户要求）：面板里**只**画工具调用时间轴，不再显示思考原文。
     没有工具调用就给一句提示，别把整段 reasoning 铺上来。 */
  if(pb) pb.innerHTML = tl || '<i style="color:var(--tec13,#cf9bb0)">（这次没有工具调用）</i>';"""
src = rep1(src, OLD_TP, NEW_TP, '思考链只留时间轴')

# 「原文」按钮藏掉（面板里已经没有原文了）
OLD_RAWBTN = """    <div class="tpanel-raw" id="tpanelRawBtn" onclick="tpPanelToggleRaw()">原文</div>"""
NEW_RAWBTN = """    <!-- ★ 7.95：思考原文已按用户要求去掉，这个按钮也就没用了 -->
    <div class="tpanel-raw" id="tpanelRawBtn" onclick="tpPanelToggleRaw()" style="display:none">原文</div>"""
src = rep1(src, OLD_RAWBTN, NEW_RAWBTN, '原文按钮隐藏')

# ================================================================ ② 家园聊天窗拖动：rot 下的夹取
OLD_CLAMP = """function hqClampPos(){
  var win=document.getElementById('hqWin'); if(!win) return;
  var off=HQ.off||(HQ.off={x:0,y:0});
  win.style.transform='translate(0,0)';
  var r=win.getBoundingClientRect();
  var hb=hqHostRect();
  var pad=12;
  /* 底部让开一点家具条，但不至于把窗口顶到屏幕上方（横屏高度只有 430） */
  var bottomPad=6;   /* 7.90：横屏只有 430 高，原来留 68~96px → 窗口几乎顶满、拖不动 */
  var minX=hb.left+pad-r.left, maxX=hb.right-pad-r.width-r.left;
  var minY=hb.top+pad-r.top,  maxY=hb.bottom-bottomPad-r.height-r.top;
  if(maxX<minX) maxX=minX;
  if(maxY<minY) maxY=minY;
  off.x=Math.max(minX, Math.min(maxX, off.x));
  off.y=Math.max(minY, Math.min(maxY, off.y));
  win.style.transform='translate('+off.x+'px,'+off.y+'px)';
}"""
NEW_CLAMP = """function hqClampPos(){
  var win=document.getElementById('hqWin'); if(!win) return;
  var off=HQ.off||(HQ.off={x:0,y:0});
  win.style.transform='translate(0,0)';
  var r=win.getBoundingClientRect();
  var hb=hqHostRect();
  var pad=12;
  /* 底部让开一点家具条，但不至于把窗口顶到屏幕上方（横屏高度只有 430） */
  var bottomPad=6;   /* 7.90：横屏只有 430 高，原来留 68~96px → 窗口几乎顶满、拖不动 */
  var minX=hb.left+pad-r.left, maxX=hb.right-pad-r.width-r.left;
  var minY=hb.top+pad-r.top,  maxY=hb.bottom-bottomPad-r.height-r.top;
  if(maxX<minX) maxX=minX;
  if(maxY<minY) maxY=minY;
  /* ★ 7.95：`HQ.off` 是**宿主局部坐标**。家园竖着拿手机时宿主被 rotate(90deg)，
     局部 (x,y) 在屏幕上等于 (-y,x)。以前直接拿屏幕矩形去夹局部偏移，
     两套坐标混在一起 → 可动范围算错，拖起来像"拖不动 / 一松手弹回去"。
     现在先在屏幕上夹，再换回局部坐标。 */
  var rot=false;
  try{ rot=!!hqHostFrame().rot; }catch(e){}
  if(rot){
    var sx=Math.max(minX, Math.min(maxX, -off.y));   /* 当前屏幕位移 */
    var sy=Math.max(minY, Math.min(maxY,  off.x));
    off.x=sy; off.y=-sx;
  }else{
    off.x=Math.max(minX, Math.min(maxX, off.x));
    off.y=Math.max(minY, Math.min(maxY, off.y));
  }
  win.style.transform='translate('+off.x+'px,'+off.y+'px)';
}"""
src = rep1(src, OLD_CLAMP, NEW_CLAMP, 'hqClampPos 旋转换算')

# ================================================================ ③ 桌面盒子自检纠偏
SCRIPT = r'''<script id="r95-deskguard">
/* ===== 7.95 · 桌面盒子"弹到右下角"的自检与纠偏 ==============================
   #jh-home 是 position:fixed;inset:0 的整屏盒子 —— 正常状态下它的
   getBoundingClientRect() 必须等于 (0,0,innerWidth,innerHeight)。
   用户截图里那个"整页缩小跑到右下角"的状态，就是某一帧 layout() 把
   width/height/transform 写成了一组对不上的值（fit / freeze 基准 / appScale
   任意一个取到脏值都会这样），而且会一直停在那儿。

   这里不去赌哪一步脏了，直接盯结果：
     · 每 250ms / resize / 点按之后各查一次；
     · 偏离视口 >3px（或 scale、fit 明显异常）→ 复位冻结基准、清掉 layout 签名、
       重排一次；
     · 把现场写进 localStorage['te_bad_layout']，下次复现可以直接读出来定位。
   ========================================================================== */
(function(){
  if(window.__r95Guard) return; window.__r95Guard=1;
  var fixes=0, lastLog=0;

  function snap(why){
    try{
      var box=document.getElementById('jh-home'); if(!box) return;
      var r=box.getBoundingClientRect();
      var vw=window.innerWidth||0, vh=window.innerHeight||0;
      if(!vw||!vh) return;
      var sc=+box.dataset.scale||0, ft=+box.dataset.fit||0;
      var off=(Math.abs(r.left)>3||Math.abs(r.top)>3||
               Math.abs(r.width-vw)>3||Math.abs(r.height-vh)>3);
      var badVar=(!isFinite(sc)||sc<=0.2||sc>8||!isFinite(ft)||ft>1.02||ft<=0);
      if(!off && !badVar) return;

      /* 现场 */
      try{
        localStorage.setItem('te_bad_layout', JSON.stringify({
          at:new Date().toISOString(), why:why, fixes:fixes+1,
          rect:[r.left,r.top,r.width,r.height], vw:vw, vh:vh,
          style:String(box.getAttribute('style')||'').slice(0,300),
          tw:box.dataset.tw, th:box.dataset.th, scale:box.dataset.scale, fit:box.dataset.fit,
          freeze:window.__teFreeze?{w:window.__teFreeze.w,h:window.__teFreeze.h}:null,
          locked:!!window.__tePortraitLocked, lockOff:!!window.__teLockOff
        }));
      }catch(e){}

      /* 纠偏：冻结基准复位成"当前视口的竖版尺寸"，再清签名重排 */
      try{
        var FZ=window.__teFreeze; if(FZ){ FZ.w=Math.min(vw,vh); FZ.h=Math.max(vw,vh); }
      }catch(e){}
      try{ box.__laySig=''; }catch(e){}
      try{ window.__jhRelayout && window.__jhRelayout(); }catch(e){}
      fixes++;
      /* 连修 3 次还不对，就把盒子按视口硬钉一次（最兜底） */
      if(fixes>=3){
        try{
          box.style.transform='scale(1)';
          box.style.left='0px'; box.style.top='0px';
          box.style.width=vw+'px'; box.style.height=vh+'px';
          box.dataset.scale='1'; box.dataset.tw=String(vw); box.dataset.th=String(vh); box.dataset.fit='1';
          box.__laySig=[0,0,vw,vh,'scale(1)'].join('|');
        }catch(e){}
      }
    }catch(e){}
  }

  window.__teGuardCheck=function(why){ snap(why||'manual'); };
  setInterval(function(){ snap('tick'); }, 250);
  window.addEventListener('resize', function(){ setTimeout(function(){ snap('resize'); }, 120); }, {passive:true});
  window.addEventListener('orientationchange', function(){ setTimeout(function(){ snap('orient'); }, 300); }, {passive:true});
  document.addEventListener('pointerup', function(){ snap('tap'); }, true);
  try{ setTimeout(function(){ snap('boot'); }, 1500); }catch(e){}
})();
</script>
'''
src = rep1(src, '</body>', SCRIPT + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 7.95：思考链只留时间轴 / 家园聊天窗拖动修正 / 桌面盒子自检纠偏')
print('下一步：python3 _mobile/build.py --install')
