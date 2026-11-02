#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.93 · 用户气泡半透明（跟 AI 一样）/ 设置页顶栏真磨砂 / 思考链带上工具调用 / 页面别再弹

用户这一轮的原话：
  「AI调用工具没有显示在思考链，用户气泡不是透明的，用户气泡和AI气泡不一样，
    页面会莫名其妙弹动，基本上页面废了每点一下都弹动，设置页的顶栏不是磨砂的，
    还有点全屏珍珠会黑屏一阵」

逐条对应：

① 用户气泡 → 跟 AI 气泡**一模一样**（量过计算样式）
   AI 气泡实测：background rgba(255,255,255,.44)、backdrop blur(.6px) saturate(1.1)、
   radius 16px、color rgb(112,89,97)、shadow rgba(120,70,96,.75) 0 10px 26px -22px。
   用户气泡实测：background color(srgb .99 .94 .96 / .93)（基本不透明）+ 4 条 7.85/7.87/7.91
   叠出来的 inset 描边。这里用同一条选择器把用户气泡写成和 AI 一样的透明磨砂。
   选择器必须带 `html body #p-chat×3 #chatBody`（和 7.91 那条同权重）才不会被打回去。

② 设置页顶栏 → 真磨砂
   `.st2-nav` 原来 `background:#fbf8f5!important` **不透明**，backdrop-filter 等于摆设。
   改成 rgba(251,248,245,.62)，夜间 rgba(22,18,19,.62)，blur 保留。

③ 思考链里没有工具调用 → 实时那条路径在渲染时就把数据挂上
   7.91 是在**点开**思考链时才顺兄弟节点找 `.tool-call`，实际用起来还是翻不到
   （工具条有可能是后插的、或者在 `.bbl` 里、或者兄弟超过 6 个）。
   现在改成渲染即挂：
     · chatSend 插入 thoughtHtml(tpId) 之后记下 `window.__liveTpId`；
     · `_toolCallsHtml(calls)` 每次被调用，就把这批调用**合并**进那个思考块的 `data-tools`；
     · 回复结束时（_chatReplyDone）清掉，避免串到下一轮；
     · `tpToggle` 读到的行文字改成「类型 · 内容」，没耗时就不显示秒数。

④ 页面莫名其妙弹动（每点一下都弹）→ `layout()` 幂等
   实测：`#jh-home` 的 style 会被反复重写（同一组值），来源是 layout() 在
   开屏看护 / resize / 轮询里被连着叫；每次重写还会 `calibrate()` 把盒子改成小数像素，
   下一次 layout() 又整回整数 —— 这就在"整块桌面"上来回抖。
   现在 layout() 先算签名（left|top|w|h|transform），一样就**一个样式都不写**，
   也不 calibrate / snapDesk；calibrate 改完盒子的结果能留住（不再被下一次 layout 打回原形）。
   relayoutDesk 也不再无条件往 iframe 里 dispatch resize —— 只有盒子尺寸真的变了才发，
   不然每点一下桌面都要整本重排一次。

用法：
    python3 _mobile/patch/round-7.93/apply.py
    python3 _mobile/patch/round-7.93/apply.py --revert
    python3 _mobile/build.py --install
    node _mobile/smoke.cjs /sdcard/Download/WeiXin/ever.html
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round93'
MARK = 'r93-fix'


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
    print('已经是 7.93 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ④ layout() 幂等
OLD_LAY = """    box.dataset.tw=String(w); box.dataset.th=String(h);
    box.dataset.scale=String(s);
    box.style.left=(IN.l+EDGE)+'px';
    box.style.top=(IN.t+EDGE)+'px';
    box.style.width=w+'px';
    box.style.height=h+'px';
    box.dataset.fit=String(fit);
    box.style.transform=(window.__m2WrapT?window.__m2WrapT('scale('+(fit/s)+')'):'scale('+(fit/s)+')');
    if(fit<1){                      /* 缩小后居中，别贴在左上角 */
      box.style.left=Math.round((innerWidth-w*fit)/2)+'px';
      box.style.top=Math.round((innerHeight-h*fit)/2)+'px';
    }
    calibrate();"""
NEW_LAY = """    box.dataset.tw=String(w); box.dataset.th=String(h);
    box.dataset.scale=String(s);
    box.dataset.fit=String(fit);
    var _L=(IN.l+EDGE), _T=(IN.t+EDGE);
    if(fit<1){                      /* 缩小后居中，别贴在左上角 */
      _L=Math.round((innerWidth-w*fit)/2);
      _T=Math.round((innerHeight-h*fit)/2);
    }
    var _TR=(window.__m2WrapT?window.__m2WrapT('scale('+(fit/s)+')'):'scale('+(fit/s)+')');
    /* ★ 7.93：尺寸 / 位置 / 缩放**一样就一个样式都不写**。
       layout() 会被开屏看护、resize、轮询连着叫几十次；每次都重写全屏 iframe 的
       width/height/transform，还会被 calibrate() 改成小数像素、下一次又整回整数，
       整块桌面就在那儿来回抖 —— 用户看到的就是"莫名其妙弹一下"。 */
    var _sig=_L+'|'+_T+'|'+w+'|'+h+'|'+_TR;
    if(box.__laySig===_sig) return;
    box.__laySig=_sig;
    box.style.left=_L+'px';
    box.style.top=_T+'px';
    box.style.width=w+'px';
    box.style.height=h+'px';
    box.style.transform=_TR;
    calibrate();"""
src = rep1(src, OLD_LAY, NEW_LAY, 'layout 幂等')

# relayoutDesk：只有盒子尺寸真的变了，才往 iframe 里 dispatch resize
OLD_RL = """  function relayoutDesk(){
    if(kbHolding()) return;   /* 7.82：键盘刚弹/刚收，别重排（黑闪） */
    try{ layout(); }catch(e){}
    setTimeout(function(){ try{ layout(); calibrate(); }catch(e){} }, 120);
    setTimeout(function(){ try{ calibrate(); }catch(e){} }, 600);
    try{ frame&&frame.contentWindow&&frame.contentWindow.dispatchEvent(new Event('resize')); }catch(e){}
    setTimeout(function(){ try{ frame&&frame.contentWindow&&frame.contentWindow.dispatchEvent(new Event('resize')); }catch(e){} }, 450);
  }"""
NEW_RL = """  function relayoutDesk(){
    if(kbHolding()) return;   /* 7.82：键盘刚弹/刚收，别重排（黑闪） */
    var _before=null;
    try{ _before=box&&(box.dataset.tw+'x'+box.dataset.th+'@'+box.dataset.scale+'@'+box.dataset.fit); }catch(e){}
    try{ layout(); }catch(e){}
    setTimeout(function(){ try{ layout(); calibrate(); }catch(e){} }, 120);
    setTimeout(function(){ try{ calibrate(); }catch(e){} }, 600);
    /* ★ 7.93：以前这里**无条件**往桌面 iframe 里 dispatch 一次 resize ——
       那本 13 万行的桌面每次都会整本重新排版（用户："每点一下都弹动"）。
       现在只有盒子尺寸真的变了才发；没变就什么都不做。 */
    function _changed(){
      try{ return !_before || _before!==(box.dataset.tw+'x'+box.dataset.th+'@'+box.dataset.scale+'@'+box.dataset.fit); }catch(e){ return true; }
    }
    if(!_changed()) return;
    try{ frame&&frame.contentWindow&&frame.contentWindow.dispatchEvent(new Event('resize')); }catch(e){}
    setTimeout(function(){ if(_changed()){ try{ frame&&frame.contentWindow&&frame.contentWindow.dispatchEvent(new Event('resize')); }catch(e){} } }, 450);
  }"""
src = rep1(src, OLD_RL, NEW_RL, 'relayoutDesk 条件化')

# ================================================================ ③ 实时路径：把工具调用挂到思考块
OLD_SEND = """  b.insertAdjacentHTML('beforeend', thoughtHtml(tpId));"""
NEW_SEND = """  b.insertAdjacentHTML('beforeend', thoughtHtml(tpId));
  /* ★ 7.93：记住这一轮的思考块，_toolCallsHtml 渲染时把工具调用挂上去 */
  try{ window.__liveTpId=tpId; }catch(e){}"""
src = rep1(src, OLD_SEND, NEW_SEND, 'chatSend 记录 __liveTpId')

OLD_TCH = """function _toolCallsHtml(calls){
  if(!calls||!calls.length) return '';"""
NEW_TCH = """function _toolCallsHtml(calls){
  if(!calls||!calls.length) return '';
  /* ★ 7.93：渲染这一刻就把这批调用并进本轮思考块的 data-tools（去重、多轮累加），
     不用再靠点开时去猜兄弟节点 —— 实时回复那条路径以前就是这么丢的。 */
  try{
    var _tp=window.__liveTpId && document.getElementById('tp_'+window.__liveTpId);
    if(_tp && calls && calls.length){
      var _arr=[];
      try{ var _p=_tp.getAttribute('data-tools'); if(_p) _arr=JSON.parse(decodeURIComponent(_p))||[]; }catch(e){}
      var _seen={};
      _arr.forEach(function(c){ _seen[(c.l||'')+'#'+(c.ms||0)]=1; });
      calls.forEach(function(c){
        var o={t:String(c.type||''), l:String(c.content||c.tool||c.srv||c.item||''), ms:(+c.ms||0)};
        var k=(o.l||'')+'#'+(o.ms||0);
        if(!_seen[k]){ _seen[k]=1; _arr.push(o); }
      });
      _tp.setAttribute('data-tools', encodeURIComponent(JSON.stringify(_arr)));
    }
  }catch(e){}"""
src = rep1(src, OLD_TCH, NEW_TCH, '_toolCallsHtml 挂 data-tools')

# 回复结束清掉，别串到下一轮
OLD_DONE = """function _chatReplyDone(){"""
NEW_DONE = """function _chatReplyDone(){
  try{ window.__liveTpId=null; }catch(e){}"""
src = rep1(src, OLD_DONE, NEW_DONE, '_chatReplyDone 清理')

# tpToggle：行文字「类型 · 内容」，中间加分隔
OLD_ROW = """            var ty=it.querySelector('.tool-item-type'), bd=it.querySelector('.tool-item-body');
            var txt=String((bd&&bd.textContent)||(ty&&ty.textContent)||'').replace(/\\s+/g,' ').trim();
            txt=txt.replace(/已执行|执行中|失败/g,'').trim();
            if(txt) rows.push({l:txt, ms:0});"""
NEW_ROW = """            var ty=it.querySelector('.tool-item-type'), ct=it.querySelector('.tool-item-content');
            var _ty=String((ty&&ty.textContent)||'').replace(/\\s+/g,' ').trim();
            var _ct=String((ct&&ct.textContent)||'').replace(/\\s+/g,' ').trim();
            var txt=_ty&&_ct?(_ty+' · '+_ct):(_ty||_ct);
            txt=txt.replace(/已执行|执行中|没跑成|失败/g,'').trim();
            if(txt) rows.push({l:txt, ms:0});"""
src = rep1(src, OLD_ROW, NEW_ROW, 'tpToggle 行文字')

# 时间轴行首带上工具类型（调用 MCP / 发送动态 …）
OLD_TL = '''        tl='<div class="r88-tl">'+arr.map(function(c){
          var sec=c.ms>0?('<em>'+(c.ms/1000).toFixed(1)+'s</em>'):'';
          var lab=(c.l||c.t||'工具调用');
          return '<div class="r88-row"><i></i><span>'+apiEsc(lab)+'</span>'+sec+'</div>';
        }).join('')+'</div>';'''
NEW_TL = '''        /* 7.93：行首带上"这是什么工具"（调用 MCP / 发送动态 …），后面跟具体内容 */
        var TY={mcp:'调用 MCP',post:'发送动态',comment:'评论动态',letter:'写信',summarize:'总结对话',
          ai_diary:'写 AI 日记',diary_comment:'评论日记',note:'贴便签',hello:'改首页标语',anniv:'查纪念日',
          divine:'占卜',pat:'拍一拍',tip:'打赏',book:'翻开书',rd:'共读卡',travel:'去旅行',postcard:'寄明信片',
          image:'图片',sticker:'表情',file:'文件',flow:'工作流',memorize:'记忆',recall:'回想',forget:'忘掉',
          rename:'改群名',tool:'工具调用'};
        tl='<div class="r88-tl">'+arr.map(function(c){
          var sec=c.ms>0?('<em>'+(c.ms/1000).toFixed(1)+'s</em>'):'';
          var lab=(c.l||c.t||'工具调用');
          if(c.t && TY[c.t] && String(c.l||'').indexOf(TY[c.t])!==0) lab=TY[c.t]+(c.l?(' · '+c.l):'');
          return '<div class="r88-row"><i></i><span>'+apiEsc(lab)+'</span>'+sec+'</div>';
        }).join('')+'</div>';'''
src = rep1(src, OLD_TL, NEW_TL, '时间轴类型标签')

# ================================================================ ①② 样式：气泡 + 设置页顶栏
CSS = r'''<style id="r93-fix">
/* ============================================================
   7.93 ①② 用户气泡 = AI 气泡（半透明磨砂）／ 设置页顶栏真磨砂
   ============================================================ */

/* ---------- ① 用户气泡：和 AI 气泡同一套数值 ----------
   AI 实测：rgba(255,255,255,.44) + blur(.6px) saturate(1.1) + 16px 圆角 +
            shadow rgba(120,70,96,.75) 0 10px 26px -22px + color rgb(112,89,97) */
html body #p-chat#p-chat#p-chat #chatBody .msg.me .bbl,
html body #p-chat#p-chat#p-chat #gcMsgs .msg.me .bbl{
  background:rgba(255,255,255,.44)!important;
  background-image:none!important;
  -webkit-backdrop-filter:blur(.6px) saturate(1.1)!important;
  backdrop-filter:blur(.6px) saturate(1.1)!important;
  box-shadow:rgba(120,70,96,.75) 0px 10px 26px -22px!important;
  border:0!important;
  border-radius:16px!important;
  color:rgb(112,89,97)!important;
}
/* 群聊页容器不在 #p-chat 里的情况：再给一条同等效果的 */
html body #gcMsgs .msg.me .bbl{
  background:rgba(255,255,255,.44)!important;
  background-image:none!important;
  -webkit-backdrop-filter:blur(.6px) saturate(1.1)!important;
  backdrop-filter:blur(.6px) saturate(1.1)!important;
  box-shadow:rgba(120,70,96,.75) 0px 10px 26px -22px!important;
  border:0!important;
  border-radius:16px!important;
  color:rgb(112,89,97)!important;
}

/* ---------- ② 设置页顶栏：不透明底 → 半透明，磨砂才看得见 ---------- */
html body #p-set .st2-nav{
  background:rgba(251,248,245,.62)!important;
  -webkit-backdrop-filter:blur(16px) saturate(1.25)!important;
  backdrop-filter:blur(16px) saturate(1.25)!important;
}
html body.te-night #p-set .st2-nav{
  background:rgba(22,18,19,.62)!important;
  -webkit-backdrop-filter:blur(16px) saturate(1.2)!important;
  backdrop-filter:blur(16px) saturate(1.2)!important;
}
</style>
'''
src = rep1(src, '</body>', CSS + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 7.93：用户气泡=AI气泡 / 设置页顶栏磨砂 / 思考链挂工具调用 / layout 幂等')
print('下一步：python3 _mobile/build.py --install')
