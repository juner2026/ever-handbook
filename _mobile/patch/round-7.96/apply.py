#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.96 · 树上那枚「群聊」吊牌打开的是单聊页 —— 修路由

用户原话：「树上提示的群聊是单聊界面」「手机上链接的那个是单聊界面」。

查到根因（`_mobile/src/patch/m2-apps.js` 第 21 节）：

    var TREE_OPEN = {
      ..., group: 'app:chat', ...
    };

手帐桌面那棵树上的 7 枚吊牌，原始 key 是裸的（star/home/map/group…），
m2 补丁给它们补 `app:` 前缀时，**把 group 写成了 app:chat** —— 于是点「群聊」
走的是单聊页。旁边那条"直连兜底"更直接：`parent.nav('chat')`。

改法：
  ① `group: 'app:group'`；
  ② 树吊牌的点击改成调父页面的 `jhOpenKey(key)` —— 让外壳用**同一张 MAP** 决定
     开哪个页面（group→gcOpen、roster→aiInfoOpen、stickers→stkOpen…），
     不再由桌面这边硬编码 `nav('chat')`；
  ③ 外壳新增 `window.jhOpenKey`；`jh:nav` 的 MAP 查找补一条 `MAP[k]`（剥掉 app: 之后的 key），
     顺手把 roster / stickers 这类也只认裸 key 的入口修好。

用法：
    python3 _mobile/patch/round-7.96/apply.py
    python3 _mobile/patch/round-7.96/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
M2 = os.path.join(ROOT, '_mobile/src/patch/m2-apps.js')
BAK_SHELL = SHELL + '.bak-before-round96'
BAK_M2 = M2 + '.bak-before-round96'
MARK = 'r96-treegroup'


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
    for p, b in ((SHELL, BAK_SHELL), (M2, BAK_M2)):
        if os.path.exists(b):
            shutil.copy2(b, p)
            print('还原', os.path.basename(p))
    sys.exit(0)

src = read(SHELL)
m2 = read(M2)

if not os.path.exists(BAK_SHELL):
    shutil.copy2(SHELL, BAK_SHELL)
    print('已备份 →', os.path.basename(BAK_SHELL))
if not os.path.exists(BAK_M2):
    shutil.copy2(M2, BAK_M2)
    print('已备份 →', os.path.basename(BAK_M2))

if MARK in m2:
    print('已经是 7.96 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 群聊吊牌：改成 app:group
OLD_TREE = """    roster: 'app:roster', group: 'app:chat', stk: 'app:stk', stickers: 'app:stk',"""
NEW_TREE = """    /* ★ 7.96：这里原来写的是 app:chat —— 树上那枚「群聊」吊牌因此打开的是**单聊页**。
       群聊的入口是外壳的 gcOpen()，对应的 key 就是 group。 */
    roster: 'app:roster', group: 'app:group', stk: 'app:stk', stickers: 'app:stk',"""
m2 = rep1(m2, OLD_TREE, NEW_TREE, 'TREE_OPEN group')

# ================================================================ ② 吊牌点击交给外壳的 jhOpenKey
OLD_DIRECT = """        c.addEventListener('click', function (e) {
          var page = String(c.getAttribute('data-open') || '').replace(/^app:/, '');
          if (!page) return;
          var fn = null;
          try { fn = window.parent && window.parent.nav; } catch (x) {}
          if (typeof fn === 'function') {
            e.preventDefault(); e.stopPropagation();
            if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            try { fn.call(window.parent, page); } catch (x) {}
          }
        }, true);"""
NEW_DIRECT = """        c.addEventListener('click', function (e) {
          var key = String(c.getAttribute('data-open') || '');
          var page = key.replace(/^app:/, '');
          if (!page) return;
          var par = null; try { par = window.parent; } catch (x) {}
          if (!par) return;
          /* ★ 7.96：先问外壳「这个 key 该开哪儿」——外壳用同一张 MAP：
             group→gcOpen()、roster→aiInfoOpen()、stickers→stkOpen()、home→家园…
             以前这里硬编码 parent.nav(page)：nav 只认页面 id，
             group / roster / stickers 这些没有页面的 key 会掉回首页或者干脆开错页。 */
          var ok = null;
          try { ok = par.jhOpenKey; } catch (x) {}
          var fn = null;
          try { fn = par.nav; } catch (x) {}
          if (typeof ok === 'function') {
            e.preventDefault(); e.stopPropagation();
            if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            try { ok.call(par, key); } catch (x) {}
            return;
          }
          if (typeof fn === 'function') {
            e.preventDefault(); e.stopPropagation();
            if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            try { fn.call(par, page); } catch (x) {}
          }
        }, true);"""
m2 = rep1(m2, OLD_DIRECT, NEW_DIRECT, '吊牌直连跳转')

# ================================================================ ③ 外壳：jhOpenKey + MAP 裸 key 兜底
OLD_GO = """  function go(v){
    if(!v) return;"""
NEW_GO = """  /* ★ 7.96：桌面（iframe）里点任何入口都可以只报一个 key，由这里按同一张表决定开哪儿。
     树上的吊牌就是走这条路 —— 以前桌面那边硬编码 nav('chat')，于是「群聊」开成了单聊。 */
  window.jhOpenKey=function(key){
    try{
      var k=String(key||'');
      if(!k) return false;
      if(k.indexOf('app:')===0) k=k.slice(4);
      if(JH_FN[k]){ try{ JH_FN[k](); }catch(e){} return true; }
      var v=MAP[k]||MAP['app:'+k];
      if(!v){ try{ toast('这个入口还没接上：'+k); }catch(e){} return false; }
      if(v==='home'){ try{ frame&&frame.contentWindow&&frame.contentWindow.postMessage({t:'jh:home'},'*'); }catch(e){} return true; }
      go(v);
      return true;
    }catch(e){ return false; }
  };

  function go(v){
    if(!v) return;"""
src = rep1(src, OLD_GO, NEW_GO, 'jhOpenKey')

# jh:nav 的 MAP 查找也补裸 key（原来只查 MAP[d.key]，'app:group' 查不到就没反应）
OLD_MAPLOOK = """    var v=MAP[d.key];
    if(!v){ return; }"""
NEW_MAPLOOK = """    var v=MAP[d.key]||MAP[k];   /* 7.96：app:xxx 剥掉前缀后也要能查到 */
    if(!v){ return; }"""
src = rep1(src, OLD_MAPLOOK, NEW_MAPLOOK, 'MAP 裸 key')

write(SHELL, src)
write(M2, m2)
print('已打补丁 7.96：树上「群聊」吊牌 → gcOpen()；吊牌统一走 jhOpenKey；MAP 支持裸 key')
print('下一步：python3 _mobile/build.py --install')
