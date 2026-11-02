#!/bin/bash
# ============================================================================
# 一次发布：升版本 → 构建 APK → 归档三份 → 源码快照 → 写索引
# ----------------------------------------------------------------------------
# 用法：  bash _apk/release.sh            # 版本号自动 +0.01（4.06 → 4.07）
#         bash _apk/release.sh 4.10       # 指定版本名
#
# 为什么要有它：这个工作目录（Download/WeiXin）会被手机的"微信/存储清理"
# 当成缓存清掉图片和 apk（html/js/md 留着）。所以每次构建都要：
#   ① 带版本+时间戳归档，永不覆盖、永不删除；
#   ② 在三个地方各留一份（工作区 / Documents 存档 / 容器 /root/releases）；
#   ③ 索引 + SHA256，丢了能对得上、能重建。
# ============================================================================
set -e
ROOT=/sdcard/Download/WeiXin
ARC="$ROOT/_发布"
MIRROR="/sdcard/Documents/TidalEcho-存档"
CTN="/root/releases"
VER_ARG="$1"

mkdir -p "$ARC" "$MIRROR/版本" "$MIRROR/源码快照" "$CTN" "$CTN/snapshots"

# ---------- ① 版本号 ----------
NEWVER=$(python3 - "$VER_ARG" <<'PY'
import re,sys
p='/sdcard/Download/WeiXin/_apk/AndroidManifest.xml'
s=open(p,encoding='utf-8').read()
arg=(sys.argv[1] or '').strip()
code=int(re.search(r'android:versionCode="(\d+)"',s).group(1))
name=re.search(r'android:versionName="([\d.]+)"',s).group(1)
if arg:
    ver=arg
else:
    parts=[int(x) for x in name.split('.')]
    if len(parts)==1: parts.append(0)
    parts[-1]+=1
    if parts[-1]>99: parts[-1]=0; parts[-2]+=1
    ver='%d.%02d'%(parts[0],parts[-1]) if len(parts)==2 else '.'.join(str(x) for x in parts)
code+=1
s=re.sub(r'android:versionCode="\d+"','android:versionCode="%d"'%code,s)
s=re.sub(r'android:versionName="[\d.]+"','android:versionName="%s"'%ver,s)
open(p,'w',encoding='utf-8').write(s)
print('%s\t%d'%(ver,code))
PY
)
VER=$(echo "$NEWVER" | cut -f1)
CODE=$(echo "$NEWVER" | cut -f2)
echo "▶ 版本：$VER（versionCode $CODE）"

# ---------- ② 构建 ----------
bash "$ROOT/_apk/fullbuild-desktop.sh" >/tmp/release-build.log 2>&1 || {
  echo "✗ 构建失败，最后 20 行："; tail -20 /tmp/release-build.log; exit 1; }
tail -3 /tmp/release-build.log

# ---------- ③ 归档三份 ----------
TS=$(date +%Y%m%d-%H%M)
BASE="Ever-${VER}-${TS}.apk"
cp "$ROOT/Ever-测试版.apk" "$ARC/$BASE"
cp "$ARC/$BASE" "$MIRROR/版本/$BASE"
cp "$ARC/$BASE" "$MIRROR/最新.apk"
cp "$ARC/$BASE" "$CTN/$BASE"
cp "$ARC/$BASE" "$CTN/latest.apk"
SIZE=$(stat -c%s "$ARC/$BASE")
HASH=$(sha256sum "$ARC/$BASE" | cut -d' ' -f1)
ROWHASH=$(echo "$HASH" | cut -c1-16)

# ---------- ④ 源码快照 ----------
SNAP="源码快照-${VER}-${TS}.tar.gz"
( cd "$ROOT" && tar czf "$ARC/$SNAP" \
    "TidalEcho-手帐桌面.html" "_apk/AndroidManifest.xml" "_apk/src" \
    "家园v4-客厅/日记本.html" "家园v4-客厅/日记本素材" \
    "_美化v2/工具/ux-fix.css" "_美化v2/工具/ux-fix.js" \
    $(ls *.md 2>/dev/null) 2>/dev/null || true )
[ -f "$ARC/$SNAP" ] && cp "$ARC/$SNAP" "$MIRROR/源码快照/$SNAP" && cp "$ARC/$SNAP" "$CTN/snapshots/$SNAP"

# ---------- ⑤ 索引 ----------
line="| $VER | $TS | $(python3 -c "print(f'{$SIZE/1048576:.1f} MB')") | \`$ROWHASH…\` | \`$BASE\` |"
for f in "$ARC/索引.md" "$MIRROR/索引.md"; do
  if [ ! -f "$f" ]; then
    printf '# Ever · 发布索引\n\n> 从 5.00 起产品名由「潮汐回响 / Tidal Echo」改为 **Ever**。\n> 更早的 4.x 归档（潮汐回响-*.apk）全部保留，未删除。\n\n| 版本 | 构建时间 | 大小 | SHA256 | 文件 |\n|---|---|---|---|---|\n' > "$f"
  fi
  echo "$line" >> "$f"
done
printf '%s  %s\n' "$HASH" "$BASE" > "$MIRROR/版本/$BASE.sha256"

# ---------- ⑤.5 自动清理：每个位置只留最近 3 个安装包 / 3 份源码快照 ----------
# 为什么要有它：整个游戏素材原样打进包，一个包 450MB；一天改二十轮就是 9GB，
# 磁盘被 100% 占满过一次（2026-10-23）。索引.md 仍然只增不减，历史记录不丢；
# 「最新.apk / latest.apk」永远跳过，它们是给人装的入口。
KEEP_APK=3
KEEP_SNAP=3
prune_apk(){
  local d="$1"
  [ -d "$d" ] || return 0
  ls -1t "$d"/*.apk 2>/dev/null \
    | grep -v '/最新\.apk$' | grep -v '/latest\.apk$' \
    | tail -n +$((KEEP_APK+1)) \
    | while read -r f; do rm -f "$f" "$f.sha256"; done
}
prune_snap(){
  local d="$1"
  [ -d "$d" ] || return 0
  ls -1t "$d"/源码快照-*.tar.gz 2>/dev/null \
    | tail -n +$((KEEP_SNAP+1)) \
    | while read -r f; do rm -f "$f"; done
}
prune_apk "$ARC"
prune_apk "$MIRROR/版本"
prune_apk "$CTN"
prune_snap "$ARC"
prune_snap "$MIRROR/源码快照"
prune_snap "$CTN/snapshots"

# ---------- ⑥ 汇总 ----------
echo
echo "✓ 已归档："
echo "   $ARC/$BASE"
echo "   $MIRROR/版本/$BASE"
echo "   $MIRROR/最新.apk   ← 手机被清以后从这里拿"
echo "   $CTN/$BASE"
echo "   SHA256 $HASH"
echo "   源码快照 $SNAP"
echo
echo "手机上：Documents/TidalEcho-存档/最新.apk"
