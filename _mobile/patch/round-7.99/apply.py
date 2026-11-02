#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""7.99 · 桌面不再因为"一帧的视口抖动"把整本手帐换成平板排版

真机现场（7.98 的打点脚本在无头里复现出来的那条链）：

    盒子某一帧变宽（860） → 桌面 iframe 的 innerWidth 变成 860
    → m2 的 autoMh() 判定"短边 ≥ 560" → <html data-mh="tablet" data-view="tablet">
    → **整本手帐按平板排版重排**（平板版把纸页挪到右下、桌面大片留白）
    → 下一帧盒子恢复 430 → 又切回 phone → 再重排一次

用户看到的"整个画面弹动、整页跑到右下角再回来"就是这个模式翻来翻去。
无头里我手动把盒子改成 860×1864，日志里立刻出现
`mh: phone→tablet (iw 860)` 再 `tablet→phone (iw 215/430)` —— 完全对上。

改法（只动模式判定，不碰排版公式）：

  ① 手机上（外壳 `__tePhoneLock` 为真，或 localStorage 里有 te-force-phone）
     **永久钉成 phone**，不再看视口大小；
  ② 平板/别的环境：候选模式要**连续两次一致（间隔 ≥ 350ms）**才真的切，
     一帧的抖动过不了这一关；
  ③ 记录每次切换的现场到 `window.__mhLog`（最多 20 条），
     带 ?diag=1 时也会打点到 8931。

用法：
    python3 _mobile/patch/round-7.99/apply.py
    python3 _mobile/build.py --install
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
M2 = os.path.join(ROOT, '_mobile/src/patch/m2-apps.js')
BAK = M2 + '.bak-before-round99'
MARK = 'r99-mhstable'


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
        shutil.copy2(BAK, M2)
        print('还原', os.path.basename(M2))
    else:
        print('没有备份，跳过')
    sys.exit(0)

m2 = read(M2)

if not os.path.exists(BAK):
    shutil.copy2(M2, BAK)
    print('已备份 →', os.path.basename(BAK))

if MARK in m2:
    print('已经是 7.99 版，跳过（要重打先 --revert）')
    sys.exit(0)

OLD = """  var WIDE_MIN = 560;
  function autoMh() {
    var WIDE_MIN2 = 560;
    var saved = LS.get('te-journal-layout');
    if (saved !== 'phone' && saved !== 'tablet') saved = '';
    var w = window.innerWidth || 360, h = window.innerHeight || 640;
    var want0 = saved || (Math.min(w, h) < WIDE_MIN ? 'phone' : 'tablet');
    var want = want0;
    
    if (root.getAttribute('data-mh') !== want) {
      root.setAttribute('data-mh', want);
      try { window.dispatchEvent(new Event('resize')); } catch (e) {}
    }
  }"""
NEW = """  var WIDE_MIN = 560;
  var _mhCand = null, _mhAt = 0, _mhLog = [];
  /* ★ 7.99：模式切换要"稳"。
     真机上出过这个事故：某一帧视口临时变成 860 → 短边 ≥ 560 → 整本手帐切成平板排版
     （平板版把纸页挪到右下、桌面大片留白）→ 下一帧又切回来。用户看到的就是
     "整个画面弹动、整页跑到右下角再回来"。
     现在：手机上永久钉 phone；别的环境要求候选值连续两次一致（≥350ms）才真的切。 */
  function mhLog(o) {
    try {
      _mhLog.push(o);
      if (_mhLog.length > 20) _mhLog.shift();
      window.__mhLog = _mhLog;
    } catch (e) {}
  }
  function autoMh() {
    var saved = LS.get('te-journal-layout');
    if (saved !== 'phone' && saved !== 'tablet') saved = '';
    var w = window.innerWidth || 360, h = window.innerHeight || 640;
    var want0 = saved || (Math.min(w, h) < WIDE_MIN ? 'phone' : 'tablet');

    /* ① 手机上钉死 */
    var pin = false;
    try {
      pin = !!(window.parent && window.parent.__tePhoneLock) || LS.get('te-force-phone') === '1';
    } catch (e) {}
    if (pin) want0 = 'phone';

    /* ② 抖动防护：候选值要连续两次一致才切 */
    var now = Date.now();
    var cur = root.getAttribute('data-mh');
    if (want0 !== cur) {
      if (_mhCand !== want0 || now - _mhAt < 350) {
        mhLog({ t: now, cand: want0, cur: cur, w: w, h: h, applied: 0, pin: pin });
        _mhCand = want0; _mhAt = now;
        return;
      }
    }
    _mhCand = want0; _mhAt = now;

    if (cur !== want0) {
      mhLog({ t: now, cand: want0, cur: cur, w: w, h: h, applied: 1, pin: pin });
      root.setAttribute('data-mh', want0);
      try { root.setAttribute('data-view', want0); } catch (e) {}
      try { window.dispatchEvent(new Event('resize')); } catch (e) {}
    }
  }"""
m2 = rep1(m2, OLD, NEW, 'autoMh 稳定化')

write(M2, m2)
print('已打补丁 7.99：桌面模式切换钉死/防抖（手机上恒为 phone）')
print('下一步：python3 _mobile/build.py --install')
