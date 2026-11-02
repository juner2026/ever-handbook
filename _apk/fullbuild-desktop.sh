set -e
SRC=/sdcard/Download/WeiXin/TidalEcho-手帐桌面.html
P=/tmp/apk/proj
echo "⓪ 语法闸门"
node --input-type=module -e '
import fs from "fs";
const html=fs.readFileSync("/sdcard/Download/WeiXin/TidalEcho-手帐桌面.html","utf8");
const scripts=[...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
let bad=0; scripts.forEach((c,i)=>{ try{ new Function(c);}catch(e){ bad++; console.log("  ✗ 第"+(i+1)+"块: "+String(e.message).slice(0,90)); } });
if(bad){ console.log("  语法错误 "+bad+" 处，已中止打包"); process.exit(1); }
console.log("  ✓ "+scripts.length+" 个 script 块语法通过");
' || exit 1
echo "⓪.5 同步星露谷（★ 以前漏了这步，包里可能还是旧的游戏）"
rm -rf "$P/assets/aset/starvalley"
mkdir -p "$P/assets/aset"
cp -a "/sdcard/Download/WeiXin/星露谷" "$P/assets/aset/starvalley"
md5sum "$P/assets/aset/starvalley/index.html" "/sdcard/Download/WeiXin/星露谷/index.html" | awk '{print "   "$1}'
echo "⓪.5b 同步家园编辑器（★ 以前 proj/assets/aset/home4 是 10-21 的陈旧副本，改了不进包）"
if [ -d "/sdcard/Download/WeiXin/aset/home4" ]; then
  rm -rf "$P/assets/aset/home4"
  cp -a "/sdcard/Download/WeiXin/aset/home4" "$P/assets/aset/home4"
  md5sum "$P/assets/aset/home4/editor.html" "/sdcard/Download/WeiXin/aset/home4/editor.html" | awk '{print "   "$1}'
fi
echo "⓪.6 同步原生源码（★ 以前 proj/src 和仓库 _apk/src 是两份，仓库那份停更在 10-10）"
mkdir -p "$P/src/com/tidalecho/app"
cp -f /sdcard/Download/WeiXin/_apk/src/com/tidalecho/app/*.java "$P/src/com/tidalecho/app/" 2>/dev/null || true
ls -1 "$P/src/com/tidalecho/app/" | tr '\n' ' '; echo
echo "① 生成 index.html（素材目录换成 ASCII）"
python3 - <<'PY'
import re
s=open('/sdcard/Download/WeiXin/TidalEcho-手帐桌面.html',encoding='utf-8').read()
s=s.replace('家园素材/','aset/home/').replace('ai-chat-paper-assets/','aset/paper/')
# ★ 5.96：把真实版本号注进包里（源码里是 "dev" 占位）——
# 这样界面/诊断行/星露谷 iframe 的破缓存参数都能对上"到底装的是哪一版"
try:
    man=open('/sdcard/Download/WeiXin/_apk/AndroidManifest.xml',encoding='utf-8').read()
    m=re.search(r'android:versionName="([\d.]+)"',man)
    ver=m.group(1) if m else 'dev'
    s=s.replace('window.__everVer="dev"','window.__everVer="%s"'%ver)
    print('   注入版本号:', ver)
except Exception as e:
    print('   版本号注入失败:', e)
open('/tmp/apk/proj/assets/index.html','w',encoding='utf-8').write(s)
print('   index.html %.1f MB' % (len(s.encode())/1048576))
PY
echo "①.5 同步清单"
cp "/sdcard/Download/WeiXin/_apk/AndroidManifest.xml" $P/AndroidManifest.xml
grep -o 'versionName="[0-9.]*"' $P/AndroidManifest.xml | head -1
echo "② 编译 + 签名"
bash /tmp/apk/build.sh | tail -4
cp /tmp/apk/TidalEcho.apk "/sdcard/Download/WeiXin/Ever-测试版.apk"
ls -la "/sdcard/Download/WeiXin/Ever-测试版.apk" | awk '{printf "   手机上: %.1f MB\n",$5/1048576}'
