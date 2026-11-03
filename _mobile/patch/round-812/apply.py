#!/usr/bin/env python3
# round-812 / 8.61.1： #jh-home 铺满兜底（jh-plain）
#   用法： python3 _mobile/patch/round-812/apply.py            # 应用
#           python3 _mobile/patch/round-812/apply.py --revert   # 回退
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SHELL = os.path.join(HERE, '..', '..', 'src', 'shell.html')
CSS_OLD = '#jh-frame{width:100%;height:100%;border:0;display:block;background:#fdf5f3}'
CSS_NEW = ('/* ===== round-812: 盒子铺满兜底 */\n'
'html.jh-plain #jh-home{left:0!important;top:0!important;right:0!important;bottom:0!important;\n'
'  width:auto!important;height:auto!important;transform:none!important}\n' + CSS_OLD)
JS_OLD = 'var IN={t:0,r:0,b:0,l:0}, EDGE=0;'
JS_NEW = ('/* round-812 */\n'
'    try{\n'
'      var _r=document.documentElement, _pl=(s>0.995 && s<1.005 && fit>0.999);\n'
"      if(/[?&]plain=0/.test(location.search||'')) _pl=false;\n"
"      if(_pl) _r.classList.add('jh-plain'); else _r.classList.remove('jh-plain');\n"
'    }catch(e){}\n'
'    ' + JS_OLD)
s = open(SHELL, encoding='utf-8').read()
if '--revert' in sys.argv:
    a = s.count(CSS_NEW); b = s.count(JS_NEW)
    s = s.replace(CSS_NEW, CSS_OLD).replace(JS_NEW, JS_OLD)
    open(SHELL, 'w', encoding='utf-8').write(s)
    print('reverted css=%d js=%d' % (a, b))
else:
    if 'jh-plain #jh-home' in s and '_pl=(s>0.995' in s:
        print('already applied'); sys.exit(0)
    assert s.count(CSS_OLD) == 1 and s.count(JS_OLD) == 1, 'anchor not unique'
    s = s.replace(CSS_OLD, CSS_NEW).replace(JS_OLD, JS_NEW)
    open(SHELL, 'w', encoding='utf-8').write(s)
    print('applied')
