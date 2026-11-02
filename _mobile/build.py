#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ever.html 构建管线（源码 → 单文件）

为什么要有它
------------
ever.html 是「外壳 + 一段 1.1MB 的转义桌面文档（window.__JH_DOC）」拼起来的。
直接拿编辑器改这个 7.8MB 单文件，很容易：① 把转义符改坏 ② 把两个文件改成不同版本
③ 贴图（base64 贴纸/字体）在复制粘贴时被截断。

所以拆成两份**可读源码**，每次由本脚本拼回单文件：

    _mobile/src/shell.html     外壳（桌面文档处留 __JH_DOC_PLACEHOLDER__）
    _mobile/src/jh-doc.html    桌面文档（明文，9200 行）
    _mobile/src/patch/*.css|js 新增的移动端模块（按顺序注入桌面文档 </body> 前）

用法：
    python3 _mobile/build.py            # 构建到 _mobile/out/ever-mobile.html
    python3 _mobile/build.py --install  # 另外覆盖 ever.html（自动备份）并同步打包源

任何一步对不上就直接报错退出，宁可不产出，也不产出一份坏的。
"""
import base64
import json
import os
import re
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, '_mobile', 'src')
OUT = os.path.join(ROOT, '_mobile', 'out')
PLACEHOLDER = '__JH_DOC_PLACEHOLDER__'
MARK_BEGIN = '<!--M2-INJECT-BEGIN-->'
MARK_END = '<!--M2-INJECT-END-->'

PATCH_ORDER = ['m2-apps.css', 'desk-paper.css', 'm2-apps.js']


IMG_EXT = ('png', 'jpg', 'jpeg', 'webp', 'gif')
FONT_EXT = ('woff2', 'woff', 'ttf', 'otf')

# 独立子页面（iframe 里的那几本"书"）。它们各自是一份 html，
# 打包后塞进 window.__M2_INLINE，这样只拷 ever.html 也能打开。
# 只放小页面：星露谷整个目录 434MB、家园 14MB，塞不进来。
INLINE_PAGES = ['aset/diary/book.html']
ASSET_RE = re.compile(r'aset/[A-Za-z0-9_/.\-]+\.(?:%s)' % '|'.join(IMG_EXT + FONT_EXT), re.I)


def recode_image(raw, ext):
    """把内联的图片压一遍（页面已经 19MB，vivo 浏览器打开就闪退，图是最大头）。
    · 带透明的（贴纸/勾线）→ WebP 无损，通常比 PNG 小
    · 照片/平涂 → WebP q86
    压完更大的话就原样返回，不做负优化。"""
    try:
        from PIL import Image
        import io as _io
        im = Image.open(_io.BytesIO(raw))
        im.load()
        alpha = (im.mode in ('RGBA', 'LA')) or (im.mode == 'P' and 'transparency' in im.info)
        out = _io.BytesIO()
        if alpha:
            im.save(out, 'WEBP', lossless=True, quality=100, method=6)
        else:
            im.convert('RGB').save(out, 'WEBP', quality=86, method=6)
        data = out.getvalue()
        if len(data) < len(raw) * 0.92:
            return data, 'webp'
    except Exception:
        pass
    return raw, ext


def inline_assets(text, label=''):
    """把 aset/ 下的图片换成 data: URL —— 这样「只有一个 html」拷到手机上，
    珍珠、书皮、唱片、头像都还在，不会再出现「贴图没了」。
    只处理图片；aset/*.html 那种 iframe 页面（家园编辑器/日记本）不内联，仍要文件夹。"""
    seen = {}
    total = [0, 0]

    def repl(m):
        rel = m.group(0)
        if rel in seen:
            return seen[rel]
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            return rel
        try:
            raw = open(path, 'rb').read()
        except OSError:
            return rel
        ext = rel.rsplit('.', 1)[-1].lower()
        if ext not in FONT_EXT and '--no-recompress' not in sys.argv:
            raw, ext = recode_image(raw, ext)
        if ext in FONT_EXT:
            # 字体也内联：思源宋体子集，页面上所有中文都靠它（见 m2-apps.css 的 @font-face）
            uri = 'data:font/%s;base64,%s' % (ext, base64.b64encode(raw).decode('ascii'))
        else:
            mime = {'jpg': 'jpeg'}.get(ext, ext)
            uri = 'data:image/%s;base64,%s' % (mime, base64.b64encode(raw).decode('ascii'))
        seen[rel] = uri
        total[0] += 1
        total[1] += len(raw)
        return uri

    out = ASSET_RE.sub(repl, text)
    if total[0]:
        print('   内联%s图片 %d 个，原 %.2f MB → 约 %.2f MB'
              % (label, total[0], total[1] / 1048576.0, total[1] * 4 / 3 / 1048576.0))
    return out


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)


def strip_injection(doc):
    """把上一次注入的模块删掉，保证反复构建不会叠加。"""
    i = doc.find(MARK_BEGIN)
    if i < 0:
        return doc
    j = doc.find(MARK_END, i)
    if j < 0:
        raise SystemExit('注入标记只有开头没有结尾，源码被改坏了：' + MARK_BEGIN)
    return doc[:i] + doc[j + len(MARK_END):]



def inline_pages():
    """把 INLINE_PAGES 里的子页面打成 data:text/html，页面内部的相对图片也换成 data: URI。"""
    out = {}
    for rel in INLINE_PAGES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        html = read(p)
        base = os.path.dirname(p)

        def repl(m):
            name = m.group(0)
            ap = os.path.join(base, name)
            if not os.path.exists(ap):
                return name
            raw = open(ap, 'rb').read()
            ext = name.rsplit('.', 1)[-1].lower()
            mime = {'jpg': 'jpeg'}.get(ext, ext)
            return 'data:image/%s;base64,%s' % (mime, base64.b64encode(raw).decode('ascii'))

        html = re.sub(r'book-[a-z]+\.png', repl, html)
        out[rel] = 'data:text/html;base64,' + base64.b64encode(html.encode('utf-8')).decode('ascii')
        print('   内联子页面 %s（%.0f KB → %.0f KB data URI）'
              % (rel, os.path.getsize(p) / 1024.0, len(out[rel]) / 1024.0))
    return out

def build_patch():
    css, js = [], []
    for name in PATCH_ORDER:
        p = os.path.join(SRC, 'patch', name)
        if not os.path.exists(p):
            raise SystemExit('缺少补丁文件：' + p)
        body = read(p)
        if '</script' in body or '</style' in body:
            raise SystemExit('%s 里出现了闭合标签，会提前截断注入块：%s' % (name, p))
        if name.endswith('.css'):
            css.append('/* ==== %s ==== */\n%s' % (name, body))
        else:
            js.append('/* ==== %s ==== */\n%s' % (name, body))
    block = [MARK_BEGIN]
    if css:
        block.append('<style id="m2-css">\n' + '\n'.join(css) + '\n</style>')
    if js:
        block.append('<script id="m2-js">\n' + '\n'.join(js) + '\n</script>')
    block.append(MARK_END)
    return '\n'.join(block)


def main():
    install = '--install' in sys.argv

    doc = read(os.path.join(SRC, 'jh-doc.html'))
    shell = read(os.path.join(SRC, 'shell.html'))
    if PLACEHOLDER not in shell:
        raise SystemExit('shell.html 里找不到 %s' % PLACEHOLDER)

    # 1) 桌面文档：清掉旧注入，插入新模块
    doc = strip_injection(doc)
    m = re.search(r'</body>\s*</html>\s*$', doc)
    if not m:
        raise SystemExit('jh-doc.html 结尾不是 </body></html>，不敢插')
    doc = doc[:m.start()] + build_patch() + '\n' + doc[m.start():]

    # 1.45) 子页面内联：日记本等 iframe 页面打成 data:text/html
    if '--no-inline' not in sys.argv:
        pages = inline_pages()
        if pages:
            shell = shell.replace('window.__M2_INLINE={};',
                                  'window.__M2_INLINE=' + json.dumps(pages) + ';')

    # 1.5) 图片内联：让「一个 html」也能带着珍珠/书皮/唱片走
    if '--no-inline' not in sys.argv:
        doc = inline_assets(doc, '桌面文档')
        shell = inline_assets(shell, '外壳')

    # 2) 转成 JS 字符串字面量。用 json.dumps 是唯一可靠的办法：
    #    < > 转 \u003c 再转义，换行转 \n，引号转 \"，保证浏览器解析出来逐字节一致。
    # shell.html 里已经写好了 window.__JH_DOC="__JH_DOC_PLACEHOLDER__" 这对引号，
    # 所以这里只取 json 字符串字面量的**内部**（去掉首尾两个引号）。
    lit = json.dumps(doc)[1:-1]
    for ch in ('<', '>', '&'):
        lit = lit.replace(ch, '\\u%04x' % ord(ch))
    # json.dumps 会把 U+2028/2029 原样留着，旧 JS 引擎里会断行，一起转掉
    lit = lit.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

    # 版本号：页脚 verTag() 读 window.__everVer。原来写死 7.32，用户分不清新旧，
    # 现在带上构建时间戳（7.33-20261031-0655），页脚一眼可核对。
    VER_BASE = '8.07'
    version = time.strftime('%y%m%d-%H%M')
    stamp_full = time.strftime('%Y%m%d-%H%M')
    ver = '%s-%s' % (VER_BASE, stamp_full)
    out = shell.replace(PLACEHOLDER, lit)
    out = out.replace('window.__everVer="6.62-web"',
                      'window.__everVer="%s-mobile"' % ver)
    write(os.path.join(OUT, 'ever-mobile.html'), out)

    # 3) 自检：把产出再解析一遍，确认桌面文档能原样还原
    raw = read(os.path.join(OUT, 'ever-mobile.html'))
    KEY = 'window.__JH_DOC="'
    i = raw.index(KEY) + len(KEY)
    j = raw.index('"</script>', i)
    back = json.loads('"' + raw[i:j] + '"')
    if back != doc:
        raise SystemExit('自检失败：还原出来的桌面文档和源码不一致')
    print('OK  桌面文档 %d 字符 / %d 行' % (len(doc), doc.count('\n') + 1))
    print('OK  单文件 %.2f MB' % (len(out.encode('utf-8')) / 1048576.0))

    # 4) 备份 + 落地
    if install:
        stamp = time.strftime('%Y%m%d-%H%M')
        for target in ('ever.html', 'TidalEcho-手帐桌面.html'):
            p = os.path.join(ROOT, target)
            if os.path.exists(p):
                bak = p + '.bak-before-m2-%s' % stamp
                shutil.copy2(p, bak)
                print('备份', os.path.basename(bak))
            body = out
            if target != 'ever.html':
                body = body.replace('window.__everVer="%s-mobile"' % ver,
                                    'window.__everVer="%s-desktop"' % ver)
            write(p, body)
            print('写入', target)
    else:
        print('（没加 --install，只产出 _mobile/out/ever-mobile.html）')


if __name__ == '__main__':
    main()
