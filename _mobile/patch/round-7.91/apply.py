#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.91 · 全屏黑 / 思考链工具调用 / 米色主题气泡 + 交接条

① 点全屏黑一段时间
   → 黑是桌面 iframe 按新视口**重排**那一帧。现在：进/退全屏先盖米色遮罩，
     **同时把重排冻住 1.2 秒**（复用 7.82 的 `__teKbHoldUntil` 闸门），
     遮罩撤掉前在后台补偿一次 `__jhRelayout()`。用户看到的是米色一闪，不再黑。

② 工具调用没显示在思考链
   → 之前只给「历史重进」那条渲染路径挂了 `data-tools`，**实时回复**走的是另一条路径
     （L19662 的 tpId），根本没数据。现在 `tpToggle()` 里加兜底：
     没有 data-tools 时，顺着这个思考块往后找那条 `.tool-call` 块，把里面的条目读出来当时间轴。

③ 米色主题下用户气泡不是白色
   → 之前是「主题色 24% + 白 78%」，米色主题下就偏米。改成**白为主**：
     白 90% + 主题色 10%，米色≈白、粉色≈极淡粉。

用法：
    python3 _mobile/patch/round-7.91/apply.py
    python3 _mobile/patch/round-7.91/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round91'
MARK = 'r91-fix'


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
    print('已经是 7.91 版，跳过')
    sys.exit(0)

# ---------------------------------------------------------------- ① 全屏：遮罩 + 冻重排
old = '''  t=setTimeout(function(){ try{ d.style.opacity='0'; }catch(e){} setTimeout(function(){ try{ d.remove(); }catch(e){} }, 260); }, 620);'''
new = '''  /* 7.91：遮罩期间把桌面重排冻住（1.2s），撤遮罩前在后台补排一次 —— 双保险 */
  try{ window.__teKbHoldUntil = Date.now() + 1200; }catch(e){}
  setTimeout(function(){ try{ window.__jhRelayout && window.__jhRelayout(); }catch(e){} }, 950);
  t=setTimeout(function(){ try{ d.style.opacity='0'; }catch(e){} setTimeout(function(){ try{ d.remove(); }catch(e){} }, 280); }, 1150);'''
src = rep1(src, old, new, '遮罩时长')

# ---------------------------------------------------------------- ② 时间轴兜底：读兄弟节点里的工具条
old = '''    var rawTools=wrap&&wrap.getAttribute('data-tools');'''
new = '''    var rawTools=wrap&&wrap.getAttribute('data-tools');
    /* 7.91 兜底：实时回复那条路径没挂 data-tools —— 顺着一族节点往后找 `.tool-call` 块，
       把里面的「类型 / 内容」读出来当时间轴（没有耗时就不显示秒数）。 */
    if(!rawTools && wrap){
      var sib=wrap.nextElementSibling, guard=0;
      while(sib && guard++<6){
        var tc=sib.classList && sib.classList.contains('tool-call') ? sib : sib.querySelector && sib.querySelector('.tool-call');
        if(tc){
          var rows=[];
          tc.querySelectorAll('.tool-item').forEach(function(it){
            var ty=it.querySelector('.tool-item-type'), bd=it.querySelector('.tool-item-body');
            var txt=String((bd&&bd.textContent)||(ty&&ty.textContent)||'').replace(/\\s+/g,' ').trim();
            txt=txt.replace(/已执行|执行中|失败/g,'').trim();
            if(txt) rows.push({l:txt, ms:0});
          });
          if(!rows.length){
            var bt=tc.querySelector('.tool-bar-text');
            if(bt) rows.push({l:String(bt.textContent||'').trim(), ms:0});
          }
          if(rows.length) rawTools=encodeURIComponent(JSON.stringify(rows));
          break;
        }
        sib=sib.nextElementSibling;
      }
    }'''
src = rep1(src, old, new, '时间轴兜底')

CSS = r'''<style id="r91-fix">
/* ③ 用户气泡：白为主 + 一点主题色（米色主题≈白，粉色主题≈极淡粉） */
html body #p-chat#p-chat#p-chat #chatBody .msg.me .bbl{
  background-color:rgba(255,255,255,.86)!important;
  background-image:none!important;
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,.9),
    inset 0 2px 1px -1px rgba(255,255,255,.95),
    0 10px 22px -20px rgba(120,70,95,.55)!important;
}
@supports (background-color: color-mix(in srgb, red 20%, white)){
  html body #p-chat#p-chat#p-chat #chatBody .msg.me .bbl{
    background-color:color-mix(in srgb, var(--te-accent) 10%, rgba(255,255,255,.92))!important;
    box-shadow:
      inset 0 0 0 1px color-mix(in srgb, var(--te-accent) 16%, rgba(255,255,255,.7)),
      inset 0 2px 1px -1px rgba(255,255,255,.95),
      0 10px 22px -20px rgba(120,70,95,.45)!important;
  }
}
</style>
'''
src = rep1(src, '</body>', CSS + '</body>', '</body>')

write(SHELL, src)
print('已打补丁：全屏遮罩+冻重排 / 时间轴兜底 / 白气泡')
print('下一步：python3 _mobile/build.py --install')
