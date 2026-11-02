#!/bin/bash
# ============================================================================
# 只换素材的「重打包」：不编译、不需要 JDK/android.jar/d8
# ----------------------------------------------------------------------------
# 背景：完整的构建环境在容器 /tmp/apk（JDK17 + android-34 + d8 + build.sh），
#       2026-10-24 被 /tmp 清理掉了。如果这一轮只改了 HTML/JS（99% 的情况），
#       用这个脚本直接拿上一版 APK 换 assets 再签，几分钟出包。
#
# 用法：  bash _apk/repack-assets.sh 6.10 [_发布/Ever-6.09-xxx.apk]
#        版本号必须是 4 个字符（6.xx），因为二进制清单里是定长字符串，换长度会破坏 AXML。
#
# 依赖：系统 aapt / zipalign / apksigner / python3
# 密钥：_apk/keystore/te-2026.keystore（2026-10-24 新签名，见同目录 README）
# ============================================================================
set -e
ROOT=/sdcard/Download/WeiXin
VER="$1"
BASE="${2:-}"
KS="$ROOT/_apk/keystore/te-2026.keystore"
[ -n "$VER" ] || { echo "用法：bash _apk/repack-assets.sh 6.10 [基础APK]"; exit 1; }
[ ${#VER} -eq 4 ] || { echo "✗ 版本号必须 4 个字符（例如 6.10），当前：$VER"; exit 1; }
[ -f "$KS" ] || { echo "✗ 找不到密钥 $KS"; exit 1; }
if [ -z "$BASE" ]; then
  BASE=$(ls -1t "$ROOT"/_发布/Ever-*.apk | head -1)
fi
[ -f "$BASE" ] || { echo "✗ 找不到基础 APK：$BASE"; exit 1; }
TS=$(date +%Y%m%d-%H%M)
OUTDIR=/root/repack-$TS
OUT="$OUTDIR/Ever-$VER-$TS.apk"
mkdir -p "$OUTDIR"
echo "▶ 基础包：$BASE"
echo "▶ 目标版本：$VER（$TS）"

python3 - "$BASE" "$OUT" "$VER" <<'PY'
import sys, zipfile, re, os
base, out, ver = sys.argv[1], sys.argv[2], sys.argv[3]
ROOT='/sdcard/Download/WeiXin'
# ---- 1) 生成新 assets ----
s=open(ROOT+'/TidalEcho-手帐桌面.html',encoding='utf-8').read()
s=s.replace('家园素材/','aset/home/').replace('ai-chat-paper-assets/','aset/paper/')
s=s.replace('日记本素材/','aset/diary/')   # 6.20：日记本封面以前没重写，装机包里必然 404
s=s.replace('星露谷/index.html','aset/starvalley/index.html')   # 6.32：源码现在引用本地目录 星露谷/index.html（网页/file:// 才能拿到现行版+完整素材），打包时换成包内路径
man_txt=open(ROOT+'/_apk/AndroidManifest.xml',encoding='utf-8').read()
s=s.replace('window.__everVer="dev"','window.__everVer="%s"'%ver)
repl={
 'assets/index.html': s.encode('utf-8'),
 'assets/aset/starvalley/index.html': open(ROOT+'/星露谷/index.html','rb').read(),
 # 6.38：日记本界面以前没进 repl，装机包里一直是基础包的旧版
 'assets/aset/diary/book.html': open(ROOT+'/aset/diary/book.html','rb').read(),
 'assets/aset/home4/editor.html': open(ROOT+'/aset/home4/editor.html','rb').read(),
 # 6.20：日记本两张封面以前根本没进包（repack 只替换已存在的条目），补成「新条目」
 'assets/aset/diary/book-pink.png': open(ROOT+'/aset/diary/book-pink.png','rb').read(),
 'assets/aset/diary/book-blue.png': open(ROOT+'/aset/diary/book-blue.png','rb').read(),
}
# ---- 2) 二进制清单：versionName（UTF-16 定长替换）+ versionCode+1 ----
src=zipfile.ZipFile(base)
mf=bytearray(src.read('AndroidManifest.xml'))
# 用 aapt 读旧版本，再在字节流里做「同长度」UTF-16 替换
import subprocess
badging=subprocess.run(['aapt','dump','badging',base],capture_output=True,text=True).stdout
oldver=re.search(r"versionName='([^']+)'",badging).group(1)
oldcode=int(re.search(r"versionCode='(\d+)'",badging).group(1))
a=oldver.encode('utf-16-le'); b=ver.encode('utf-16-le')
assert len(a)==len(b), '版本号长度必须一致（4 字符）'
assert mf.count(a)==1, '清单里没找到唯一版本号串'
mf=bytearray(bytes(mf).replace(a,b))
pat=oldcode.to_bytes(4,'little')
assert mf.count(pat)==1, '清单里没找到唯一 versionCode'
mf=bytearray(bytes(mf).replace(pat,(oldcode+1).to_bytes(4,'little')))
repl['AndroidManifest.xml']=bytes(mf)
# ---- 3) 重写 zip（去掉旧签名，保留原有压缩方式）----
drop={'META-INF/TE.SF','META-INF/TE.RSA','META-INF/MANIFEST.MF'}
with zipfile.ZipFile(out,'w') as z:
    for it in src.infolist():
        if it.filename in drop: continue
        data=repl.get(it.filename)
        comp=zipfile.ZIP_DEFLATED if data is not None else it.compress_type
        if data is None: data=src.read(it.filename)
        zi=zipfile.ZipInfo(it.filename, date_time=it.date_time)
        zi.compress_type=comp; zi.external_attr=it.external_attr
        z.writestr(zi, data)
    # ---- 3.5) 新素材：zip 里原来没有的，追加进去（以前只替换不新增，新图永远进不了包）----
    _have=set(z.namelist())
    for _name in sorted(repl.keys()):
        if _name in _have: continue
        if _name == 'AndroidManifest.xml': continue
        _zi=zipfile.ZipInfo(_name, date_time=src.infolist()[0].date_time)
        _zi.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(_zi, repl[_name])
        print('   新增素材：', _name, len(repl[_name]), 'B')
print('   重打包完成：', out, os.path.getsize(out))
PY

echo "▶ zipalign + 签名（新密钥）"
zipalign -f -p 4 "$OUT" "$OUTDIR/aligned.apk"
apksigner sign --ks "$KS" --ks-pass pass:tidalecho --key-pass pass:tidalecho \
  --v1-signing-enabled true --v2-signing-enabled true --out "$OUT" "$OUTDIR/aligned.apk" 2>&1 | tail -2
aapt dump badging "$OUT" 2>/dev/null | head -1
apksigner verify --print-certs "$OUT" 2>/dev/null | grep -i "SHA-256 digest" | head -1
HASH=$(sha256sum "$OUT" | cut -d' ' -f1)
cp "$OUT" "$ROOT/_发布/Ever-$VER-$TS.apk"
echo "✓ 已出包：$ROOT/_发布/Ever-$VER-$TS.apk"
echo "  SHA256 $HASH"
echo "  ⚠️ 新签名不能覆盖旧包；确认要在手机上更新时，先导出备份再卸载重装。"
