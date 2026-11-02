#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.05 · 去掉右上角那颗「全屏珍珠」

用户：「把那颗珍珠给去掉，珍珠没用了」。

7.94 选 b 之后珍珠只是"切 App 内沉浸"，而 PWA 打开本来就是真全屏，手机上又不需要它；
收藏位置和手帐的「设置」丝带贴得很近，还挡过家园的「返回」。直接删掉。

删除内容：
  · 外壳里创建 `#everFsPearl` 的那一整块（含 pointerdown/pointerup/click、
    fullscreenchange 同步、appendChild）；
  · 所有针对 `#everFsPearl` 的 CSS（te-home-open / te-immersive / te-inner-page /
    body:has(...) 那几条）。

保留（不删，避免连锁）：
  · `tpPanelClose` 之类无关逻辑；
  · 7.87 那个"按下珍珠先盖遮罩"的 pointerdown 判断 —— 元素不存在，永远不会命中；
  · `te-immersive` 类与它的样式（现在没有入口去切换，留着无副作用，
    以后想加别的入口还能用）。

用法：
    python3 _mobile/patch/round-805/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round805'
MARK = 'r805-nopearl'


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
    print('已经是 8.05 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 删掉创建代码
OLD = """        var pearl=document.createElement('div');
        pearl.id='everFsPearl';
        pearl.setAttribute('role','button');
        pearl.setAttribute('aria-label','全屏');
        pearl.style.cssText='position:fixed;right:8px;top:8px;width:28px;height:28px;z-index:2147483002;'+
          'border-radius:50%;background:url(aset/ui/pearl.png) center/cover no-repeat;'+
          'box-shadow:0 5px 16px rgba(120,100,80,.38), inset 0 -1px 2px rgba(255,255,255,.7);'+
          'cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none;'+
          'transition:transform .14s ease, box-shadow .14s ease, opacity .2s ease';
        function _isFs(){ return !!(document.fullscreenElement||document.webkitFullscreenElement); }
        pearl.addEventListener('pointerdown', function(){ pearl.style.transform='scale(.92)'; });
        pearl.addEventListener('pointerup', function(){ pearl.style.transform=''; });
        pearl.addEventListener('click', function(){
          /* ★ 7.94（用户选 b）：**不再** requestFullscreen。
             真全屏会重建系统窗口，露出来的那 1~2 帧是系统合成器的黑，
             网页里的遮罩盖不住（用户："点全屏珍珠会黑屏一阵"）。
             改成 App 内沉浸：收起 App 自己的底部栏 / 翻页浮标，桌面铺满；再点一下复原。
             装到桌面（PWA，manifest display:fullscreen）时本来就是真全屏，这条不影响它。 */
          var on=false;
          try{ on=document.documentElement.classList.toggle('te-immersive'); }catch(e){}
          try{ pearl.setAttribute('aria-label', on?'退出沉浸':'沉浸（收起 App 的栏）'); }catch(e){}
        });
        function _fsSync(){ pearl.style.opacity = _isFs() ? '0' : '.95'; pearl.style.pointerEvents = _isFs() ? 'none' : 'auto'; }
        document.addEventListener('fullscreenchange',_fsSync);
        document.addEventListener('webkitfullscreenchange',_fsSync);
        document.body.appendChild(pearl);
        setTimeout(_fsSync, 300);
      }catch(e){}"""
NEW = """        /* ★ 8.05（用户要求）：去掉右上角那颗「全屏珍珠」。
           7.94 选 b 之后它只是切 App 内沉浸；PWA 打开本来就全屏，手机上用不上，
           位置还和手帐的「设置」丝带挤在一起、挡过家园的「返回」。
           整块删掉 —— 不建元素、不挂监听、不 append。 */
      }catch(e){}"""
src = rep1(src, OLD, NEW, '删珍珠创建')

# ================================================================ ② 清掉相关 CSS
OLD_CSS1 = """/* ★ 7.92：家园横过来之后，它自己的「返回」正好落在屏幕右上角 —— 也就是全屏珍珠的位置，
   珍珠 z-index 比什么都高，一点就先吃掉了。家园期间先把珍珠收起来（退家园立刻回来）。 */
html.te-home-open #everFsPearl{display:none!important}"""
NEW_CSS1 = """/* ★ 8.05：全屏珍珠已删除，这条规则作废（保留注释说明来龙去脉） */"""
src = rep1(src, OLD_CSS1, NEW_CSS1, '删 CSS te-home-open')

OLD_CSS2 = """html.te-immersive #everFsPearl{opacity:.42!important}
html.te-immersive #everFsPearl:active{opacity:.9!important}"""
NEW_CSS2 = """/* ★ 8.05：珍珠已删除，沉浸状态不再需要调它的透明度 */"""
src = rep1(src, OLD_CSS2, NEW_CSS2, '删 CSS te-immersive')

OLD_CSS3 = """body:has(#p-whisper.on) #everFsPearl,
body:has(#p-games.on) #everFsPearl{display:none!important;}"""
NEW_CSS3 = """/* ★ 8.05：珍珠已删除（原：悄悄话 / 游戏页把它藏起来） */"""
n3 = src.count(OLD_CSS3)
if n3 == 1:
    src = src.replace(OLD_CSS3, NEW_CSS3)
else:
    print('（注意：body:has(#everFsPearl) 那条锚点出现 %d 次，跳过）' % n3)

OLD_CSS4 = """html.te-inner-page #everFsPearl{display:none!important;}"""
NEW_CSS4 = """/* ★ 8.05：珍珠已删除（原：内页把它藏起来） */"""
src = rep1(src, OLD_CSS4, NEW_CSS4, '删 CSS te-inner-page')

write(SHELL, src)
print('已打补丁 8.05：全屏珍珠（#everFsPearl）整块删除，连带 CSS 规则')
print('下一步：python3 _mobile/build.py --install')
