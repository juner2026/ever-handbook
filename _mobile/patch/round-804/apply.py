#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8.04 · "整页弹到右下角"真凶：data-fit 被两处代码来回写，手机规则又把居中 transform 抹了

真机/浏览器回传的 diag 里抓到这条（同一台机、同一页面，隔几秒一次）：

    d {"pg":[[525,351,1050,577], [0,42,1050,577]]}    ← 页面从"半屏处"跳回左上
    d {"pg":[[0,42,1238,649], [619,388,1238,649]]}    ← 又跳回半屏处
    d {"pg":[[619,388,1238,649], [0,42,1238,649]]}    ← 再跳回来

525 = 1050/2、619 = 1238/2 → 页面的左边缘正好落在 **50%** 处，就是用户截图里
"整页跑到右下角"的样子。两个 CSS 撞在一起：

    /* 平板预览：1180×760 的本子缩进屏幕 */
    html[data-fit="1"] .app{ width:1180px;height:760px;position:fixed;top:50%;left:50%;
                             transform:translate(-50%,-50%) scale(var(--fit,1)); }

    /* 手机版：铺满 */
    html[data-mh="phone"] .app{ width:100%!important;height:100dvh!important;
                                transform:none!important }        ← 把居中用的 translate 抹了

于是当 `data-fit="1"` 且 `data-mh="phone"` 同时成立时，`.app` 就成了
"钉在 50%/50%、宽 100% 的固定盒子" → 页面右下半屏、左上大片空白。

而 `data-fit` 正好被两处代码来回写：

  · 外壳的 teForcePhone（`?phone=1`）：**每 60/200/600/1200/2400/4000ms + 每次 resize 都写 `data-fit="1"`**
  · 桌面的 applyLayout()（resize 时跑）：手机模式下写 `data-fit="0"`

→ 两边拉锯，每切一次页面就在"左上"和"右下半屏"之间跳一次 = **弹跳**。

改法（两处都改，缺一不可）：

1. `?phone=1` 是"强制**手机版**"，不是"小屏看平板"，所以 teForcePhone 里
   `data-fit` 改成写 **"0"**（不再写 1）；
2. 桌面 CSS：`html[data-mh="phone"] .app` 加上 `:not([data-fit="1"])` ——
   万一日后又有谁把 fit 打开，也不会再出现"钉在 50%/50%"的坏状态
   （那时会老老实实变成居中的 1180×760 画布，而不是半个屏幕跑外面）。

用法：
    python3 _mobile/patch/round-804/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
DOC = os.path.join(ROOT, '_mobile/src/jh-doc.html')
BAK_S = SHELL + '.bak-before-round804'
BAK_D = DOC + '.bak-before-round804'
MARK = 'r804-datafit'


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
    for p, b in ((SHELL, BAK_S), (DOC, BAK_D)):
        if os.path.exists(b):
            shutil.copy2(b, p)
            print('还原', os.path.basename(p))
    sys.exit(0)

shell = read(SHELL)
doc = read(DOC)

if not os.path.exists(BAK_S):
    shutil.copy2(SHELL, BAK_S)
    print('已备份 →', os.path.basename(BAK_S))
if not os.path.exists(BAK_D):
    shutil.copy2(DOC, BAK_D)
    print('已备份 →', os.path.basename(BAK_D))

if MARK in shell:
    print('已经是 8.04 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 外壳：不要再写 data-fit="1"
OLD_SET = """  function set(el){
    try{
      el.setAttribute('data-mh','phone');
      el.setAttribute('data-view','phone');
      el.setAttribute('data-fit','1');
    }catch(e){}
  }"""
NEW_SET = """  function set(el){
    try{
      el.setAttribute('data-mh','phone');
      el.setAttribute('data-view','phone');
      /* ★ 8.04：这里原来写的是 "1" —— 那是"小屏看平板布局（1180×760 缩放）"的开关，
         和"强制手机版"正好相反。它每 60/200/600/1200/2400/4000ms + 每次 resize 都被写一遍，
         而桌面自己的 applyLayout() 在手机模式下又把它写回 "0" → 两边拉锯，
         页面在"左上"和"右下半屏"之间来回跳（用户截图那个"整页弹到右下角"）。
         强制手机版就该是 "0"。 */
      el.setAttribute('data-fit','0');
    }catch(e){}
  }"""
shell = rep1(shell, OLD_SET, NEW_SET, 'force-phone data-fit')

# ================================================================ ② 桌面：手机规则不要抹掉 fit 画的居中 transform
OLD_CSS = """html[data-mh="phone"] .app{width:100%!important;height:100dvh!important;transform:none!important}"""
NEW_CSS = """/* ★ 8.04：加 :not([data-fit="1"]) —— fit 模式（1180×760 画布）靠 translate(-50%,-50%) 居中，
   这条 transform:none!important 会把居中抹掉，盒子就钉在 50%/50%，整页跑到右下半屏。
   （6.39 在 scrapbook/editorial 上修过一次同样的问题，这里漏了。） */
html[data-mh="phone"]:not([data-fit="1"]) .app{width:100%!important;height:100dvh!important;transform:none!important}"""
doc = rep1(doc, OLD_CSS, NEW_CSS, 'phone .app fit 互斥')

write(SHELL, shell)
write(DOC, doc)
print('已打补丁 8.04：?phone=1 不再写 data-fit=1；手机版 .app 规则与 fit 互斥')
print('下一步：python3 _mobile/build.py --install')
