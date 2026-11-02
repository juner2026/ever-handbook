#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.97 · 思考链：把「原文」两个字的按钮删掉，思考正文留着

用户澄清：「我的意思不是思考链去掉，是思考链右上角那个原文两个字去掉」。

7.95 理解错了 —— 把面板里的思考正文一起去掉了，只留时间轴。
这一版改回来：

  · 思考链面板恢复显示：工具调用时间轴 + 思考正文（`mdToHtml(raw)`）；
  · 右上角那个 `原文` 按钮**整块删掉**（不是隐藏，是 markup 里不要了）；
  · `tpPanelToggleRaw()` 函数留着（没人调用就是死代码，删了怕别处还引着），
    相关取值都做了空判断。

用法：
    python3 _mobile/patch/round-7.97/apply.py
    python3 _mobile/patch/round-7.97/apply.py --revert
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SHELL = os.path.join(ROOT, '_mobile/src/shell.html')
BAK = SHELL + '.bak-before-round97'
MARK = 'r97-rawbtn'


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
    print('已经是 7.97 版，跳过（要重打先 --revert）')
    sys.exit(0)

# ================================================================ ① 思考正文回到面板
OLD_TP = """  /* ★ 7.95（用户要求）：面板里**只**画工具调用时间轴，不再显示思考原文。
     没有工具调用就给一句提示，别把整段 reasoning 铺上来。 */
  if(pb) pb.innerHTML = tl || '<i style="color:var(--tec13,#cf9bb0)">（这次没有工具调用）</i>';"""
NEW_TP = """  /* ★ 7.97：面板里 = 工具调用时间轴 + 思考正文（7.95 误把正文去掉了）。
     右上角那个「原文」按钮不要了，所以正文就是唯一的文字内容。 */
  if(pb) pb.innerHTML = tl + (raw ? mdToHtml(raw) : '<i style="color:var(--tec13,#cf9bb0)">（这次没有思考链）</i>');"""
src = rep1(src, OLD_TP, NEW_TP, '思考正文恢复')

# ================================================================ ② 「原文」按钮整块删掉
OLD_BTN = """    <!-- ★ 7.95：思考原文已按用户要求去掉，这个按钮也就没用了 -->
    <div class="tpanel-raw" id="tpanelRawBtn" onclick="tpPanelToggleRaw()" style="display:none">原文</div>"""
NEW_BTN = """    <!-- ★ 7.97：用户要的是「把『原文』这两个字去掉」，按钮整块删掉（7.95 只是隐藏了） -->"""
src = rep1(src, OLD_BTN, NEW_BTN, '原文按钮删除')

write(SHELL, src)
print('已打补丁 7.97：思考链恢复正文 / 「原文」按钮整块删掉')
print('下一步：python3 _mobile/build.py --install')
