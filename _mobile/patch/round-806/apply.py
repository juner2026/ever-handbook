#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.06 · 夜间模式下设置页顶栏像"一块黑长方形"，不像磨砂

用户：「设置夜景栏，不是磨砂，是一块特别奇怪的长方形」。

量到的实际值（夜间 + 有壁纸）：

    #p-set .st2-nav   background: rgba(22,18,19,.62)  backdrop-filter: blur(16px) saturate(1.2)
    #p-set .st2-veil  夜间渐变 0.72/0.34/0.30/0.72（近黑）
    #p-set            背景 #171314（不透明）

0.62 的黑压在"近黑的遮罩 + 壁纸"上，模糊几乎看不出层次 → 视觉上就是一条边缘生硬的黑块。
白天 0.62 是"米白压米白"，正好能看出磨砂；夜间要反过来把底压薄。

改法：
  · 夜间顶栏改成**渐变 + 更低的透明度**（.40 → .22），模糊加大（20px / saturate 1.4），
    并加一条很淡的下沿高光，边缘不再是硬切；
  · 有壁纸时再薄一档（.30 → .16），让壁纸的颜色真正透上来。
  · 白天那套（.62 米白）不动。

用法：
    python3 _mobile/patch/round-806/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round806'
MARK = 'r806-nightnav'


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
    print('已经是 8.06 版，跳过（要重打先 --revert）')
    sys.exit(0)

CSS = r'''<style id="r806-nightnav">
/* ============================================================
   8.06 · 夜间设置页顶栏：真磨砂（原来像一块黑长方形）
   0.62 的黑压在近黑遮罩上，模糊看不出层次 → 压薄 + 加大模糊 + 下沿渐变
   ============================================================ */
html body.te-night #p-set .st2-nav{
  background:linear-gradient(180deg,
    rgba(22,18,19,.40) 0%,
    rgba(22,18,19,.30) 62%,
    rgba(22,18,19,.22) 100%)!important;
  -webkit-backdrop-filter:blur(20px) saturate(1.4)!important;
  backdrop-filter:blur(20px) saturate(1.4)!important;
  box-shadow:0 1px 0 rgba(255,255,255,.06), 0 10px 24px -22px rgba(0,0,0,.9)!important;
}
/* 有壁纸时再薄一档，让壁纸的颜色透上来 */
html body.te-night #p-set.has-setwp .st2-nav,
html body.te-night #p-set#p-set.has-setwp .st2-nav{
  background:linear-gradient(180deg,
    rgba(22,18,19,.30) 0%,
    rgba(22,18,19,.20) 60%,
    rgba(22,18,19,.14) 100%)!important;
  -webkit-backdrop-filter:blur(24px) saturate(1.5)!important;
  backdrop-filter:blur(24px) saturate(1.5)!important;
}
</style>
'''
src = rep1(src, '</body>', CSS + '</body>', '</body>')

write(SHELL, src)
print('已打补丁 8.06：夜间设置页顶栏改真磨砂（渐变 + 更薄 + 更大模糊）')
print('下一步：python3 _mobile/build.py --install')
