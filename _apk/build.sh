set -e
export JAVA_HOME=/tmp/apk/jdk-17.0.2
export PATH=$JAVA_HOME/bin:/usr/bin:$PATH
PLAT=/tmp/apk/android-34/android.jar
D8JAR=/tmp/apk/android-14/lib/d8.jar
cd /tmp/apk/proj
rm -rf build && mkdir -p build/gen build/classes build/dex

echo "① aapt 打包资源与清单"
aapt package -f -M AndroidManifest.xml -S res -I $PLAT -J build/gen -F build/base.apk --min-sdk-version 21 --target-sdk-version 34

echo "② javac"
javac -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath $PLAT -cp $PLAT -d build/classes \
  build/gen/R.java src/com/tidalecho/app/MainActivity.java src/com/tidalecho/app/TeFS.java src/com/tidalecho/app/TeKeepAlive.java src/com/tidalecho/app/EverWatchService.java 2>/dev/null || \
javac -nowarn -encoding UTF-8 -source 8 -target 8 -cp $PLAT -d build/classes \
  build/gen/R.java src/com/tidalecho/app/MainActivity.java src/com/tidalecho/app/TeFS.java src/com/tidalecho/app/TeKeepAlive.java src/com/tidalecho/app/EverWatchService.java

echo "③ d8 → classes.dex"
java -cp $D8JAR com.android.tools.r8.D8 --lib $PLAT --min-api 21 --output build/dex \
  build/classes/com/tidalecho/app/*.class
ls -la build/dex/

echo "④ 组装（base.apk + classes.dex + assets）"
cd build && cp base.apk unsigned.apk
python3 - <<'PY'
import zipfile, os
apk='/tmp/apk/proj/build/unsigned.apk'
add=[('/tmp/apk/proj/build/dex/classes.dex','classes.dex')]
root='/tmp/apk/proj/assets'
for dp,_,fs in os.walk(root):
    for f in fs:
        p=os.path.join(dp,f)
        add.append((p, 'assets/'+os.path.relpath(p, root)))
with zipfile.ZipFile(apk,'a',zipfile.ZIP_DEFLATED) as z:
    for src,arc in add:
        z.write(src, arc)
print('塞入 %d 个文件' % len(add))
PY
cd /tmp/apk/proj

echo "⑤ zipalign + 签名"
keytool -genkeypair -keystore /tmp/apk/te.keystore -alias te -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass tidalecho -keypass tidalecho -dname "CN=TidalEcho, O=Home" 2>/dev/null || true
zipalign -f -p 4 build/unsigned.apk build/aligned.apk
apksigner sign --ks /tmp/apk/te.keystore --ks-pass pass:tidalecho --key-pass pass:tidalecho \
  --v1-signing-enabled true --v2-signing-enabled true --out /tmp/apk/TidalEcho.apk build/aligned.apk
apksigner verify --print-certs /tmp/apk/TidalEcho.apk | head -4
ls -la /tmp/apk/TidalEcho.apk
