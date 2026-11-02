#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.00 · 思考链里要出现**所有**工具调用（拍一拍 / 打赏 / 表情包这些也算）

用户：「AI 调用工具没出现在思考链里……侧边栏系统提示词里列的所有工具调用都要出现，
比如拍一拍、打赏、发表情包」。

原因：拍一拍 / 打赏 / 发表情包 / 旅行 / 明信片这几类调用，在落盘和实时两条渲染路径里
都被**过滤掉了**（它们不该在聊天流里占一张卡片，这个过滤是对的），但同一份过滤后的
数组又被拿去生成思考链的时间轴 —— 于是这几类永远不出现在思考链里。

    // 历史重进（17444）
    calls = calls.filter(c => c.type!=='pat' && c.type!=='tip' && c.type!=='sticker');
    ...后面拿 calls 生成 data-tools      ← 过滤后的
    // 实时（19552）
    var _showCalls = toolCalls.filter(c => ... pat/tip/sticker/travel/postcard ...);
    _toolCallsHtml(_showCalls)            ← 过滤后的

改法：**聊天流照旧过滤，思考链用全量**。

  ① 外壳新暴露 `window.__tpTools(id, calls)`：把一批调用合并进该思考块的 `data-tools`；
  ② `_toolCallsHtml()` 内部改为调用它（原来那段内联逻辑抽出来）；
  ③ 历史重进：过滤前先留一份全量 `_allCalls`，`data-tools` 用全量的；
  ④ 实时：`var toolCalls=_pt2.calls;` 之后立刻 `__tpTools(window.__liveTpId, toolCalls)`，
     不等 `_showCalls`（那样拍一拍/打赏永远进不来）。

用法：
    python3 _mobile/patch/round-800/apply.py
    python3 _mobile/patch/round-800/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round800'
MARK = 'r800-alltools'


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
    print('已经是 8.00 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① __tpTools + _toolCallsHtml 复用
OLD_HOOK = """function _toolCallsHtml(calls){
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
        var o={t:String(c.type||''), l:String(c.content||c.tool||c.srv||c.item||c.name||c.stk||''), ms:(+c.ms||0)};
        var k=(o.l||'')+'#'+(o.ms||0);
        if(!_seen[k]){ _seen[k]=1; _arr.push(o); }
      });
      _tp.setAttribute('data-tools', encodeURIComponent(JSON.stringify(_arr)));
    }
  }catch(e){}"""
NEW_HOOK = """/* ★ 8.00：把一批工具调用合并进某个思考块的 data-tools（去重、多轮累加）。
   拍一拍 / 打赏 / 发表情包 这些在聊天流里不画卡片，但思考链里必须出现 ——
   所以调用方要拿**全量** calls 来喂这里。 */
window.__tpTools=function(id, calls){
  try{
    if(!id || !calls || !calls.length) return;
    var _tp=document.getElementById('tp_'+id);
    if(!_tp) return;
    var _arr=[];
    try{ var _p=_tp.getAttribute('data-tools'); if(_p) _arr=JSON.parse(decodeURIComponent(_p))||[]; }catch(e){}
    var _seen={};
    _arr.forEach(function(c){ _seen[(c.l||'')+'#'+(c.ms||0)]=1; });
    calls.forEach(function(c){
      var o={t:String(c.type||''), l:String(c.content||c.tool||c.srv||c.item||c.name||c.stk||''), ms:(+c.ms||0)};
      var k=(o.l||'')+'#'+(o.ms||0);
      if(!_seen[k]){ _seen[k]=1; _arr.push(o); }
    });
    _tp.setAttribute('data-tools', encodeURIComponent(JSON.stringify(_arr)));
  }catch(e){}
};
function _toolCallsHtml(calls){
  if(!calls||!calls.length) return '';
  try{ window.__tpTools(window.__liveTpId, calls); }catch(e){}"""
src = rep1(src, OLD_HOOK, NEW_HOOK, '__tpTools 抽取')

# ================================================================ ② 历史重进：data-tools 用全量
OLD_HIST = """    if(side==='ai'){
      try{ calls=calls.filter(function(c){ return c.type!=='pat' && c.type!=='tip' && c.type!=='sticker'; }); }catch(e){}
      var rid='tr'+Date.now().toString(36)+Math.floor(Math.random()*1000);
      b.insertAdjacentHTML('beforeend',thoughtHtml(rid));
      tpFinish(rid,m.reasoning?String(m.reasoning):'');
      /* 7.89：把这条消息的工具调用挂到思考块上，展开 Thought process 时画成时间轴 */
      try{
        if(calls&&calls.length){
          var _tw=document.getElementById('tp_'+rid);
          if(_tw){
            _tw.setAttribute('data-tools', encodeURIComponent(JSON.stringify(calls.map(function(c){
              return {t:String(c.type||''), l:String(c.content||c.tool||c.srv||c.item||c.name||c.stk||''), ms:(+c.ms||0)};
            }))));
          }
        }
      }catch(e){}
    }"""
NEW_HIST = """    if(side==='ai'){
      /* ★ 8.00：先把**全量**留一份 —— 思考链要用全量，聊天流才过滤掉不该出卡片的 */
      var _allCalls=null;
      try{ _allCalls=(calls||[]).slice(); }catch(e){ _allCalls=null; }
      try{ calls=calls.filter(function(c){ return c.type!=='pat' && c.type!=='tip' && c.type!=='sticker'; }); }catch(e){}
      var rid='tr'+Date.now().toString(36)+Math.floor(Math.random()*1000);
      b.insertAdjacentHTML('beforeend',thoughtHtml(rid));
      tpFinish(rid,m.reasoning?String(m.reasoning):'');
      /* 7.89 / 8.00：把这条消息的**全部**工具调用挂到思考块上（拍一拍、打赏、表情包也算），
         展开 Thought process 时画成时间轴。 */
      try{
        var _tlCalls=(_allCalls&&_allCalls.length)?_allCalls:calls;
        if(_tlCalls&&_tlCalls.length){
          var _tw=document.getElementById('tp_'+rid);
          if(_tw){
            _tw.setAttribute('data-tools', encodeURIComponent(JSON.stringify(_tlCalls.map(function(c){
              return {t:String(c.type||''), l:String(c.content||c.tool||c.srv||c.item||c.name||c.stk||''), ms:(+c.ms||0)};
            }))));
          }
        }
      }catch(e){}
    }"""
src = rep1(src, OLD_HIST, NEW_HIST, '历史 data-tools 全量')

# ================================================================ ③ 实时：拿到全量立刻挂
OLD_LIVE = """    var _pt2=parseToolCalls(fullText);
    var toolCalls=_pt2.calls;
    var cleanText=_pt2.clean;"""
NEW_LIVE = """    var _pt2=parseToolCalls(fullText);
    var toolCalls=_pt2.calls;
    /* ★ 8.00：立刻把**全量**挂到本轮思考块 —— 拍一拍 / 打赏 / 表情包 / 旅行 / 明信片
       在聊天流里不画卡片（下面 _showCalls 会滤掉），但思考链里必须出现。 */
    try{ window.__tpTools(window.__liveTpId, toolCalls); }catch(e){}
    var cleanText=_pt2.clean;"""
src = rep1(src, OLD_LIVE, NEW_LIVE, '实时全量挂载')

write(SHELL, src)
print('已打补丁 8.00：思考链时间轴改用全量工具调用（含拍一拍/打赏/表情包/旅行/明信片）')
print('下一步：python3 _mobile/build.py --install')
