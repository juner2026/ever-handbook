#!/bin/bash
# ============================================================================
# 从源码快照恢复（只解到临时目录，不动你现在的工作区）
# 用法：  bash _apk/restore.sh _发布/源码快照-4.07-20261020-1333.tar.gz
#         bash _apk/restore.sh            # 不给参数就列出现有的快照
# ============================================================================
set -e
ROOT=/sdcard/Download/WeiXin
SNAPDIR="$ROOT/_备份/_恢复"
SNAP="$1"

if [ -z "$SNAP" ]; then
  echo "现有快照："
  ls -1 "$ROOT/_发布/"源码快照-*.tar.gz 2>/dev/null || echo "  （无）"
  ls -1 /sdcard/Documents/TidalEcho-存档/源码快照/*.tar.gz 2>/dev/null | sed 's/^/  Documents: /'
  echo
  echo "用法：bash _apk/restore.sh <文件名>"
  exit 0
fi
if [ ! -f "$SNAP" ]; then
  # 允许只给文件名，去三个地方找
  for d in "$ROOT/_发布" "/sdcard/Documents/TidalEcho-存档/源码快照" "/root/releases/snapshots"; do
    [ -f "$d/$SNAP" ] && SNAP="$d/$SNAP" && break
  done
fi
[ -f "$SNAP" ] || { echo "✗ 找不到快照：$1"; exit 1; }

TS=$(date +%Y%m%d-%H%M%S)
OUT="$SNAPDIR/$TS"
mkdir -p "$OUT"
tar xzf "$SNAP" -C "$OUT"
echo "✓ 已解到：$OUT"
echo
echo "确认没问题后自己覆盖回去（示例）："
echo "  cp -a \"$OUT/TidalEcho-手帐桌面.html\" \"$ROOT/TidalEcho-手帐桌面.html\""
echo "  cp -a \"$OUT/家园v4-客厅/日记本.html\" \"$ROOT/家园v4-客厅/日记本.html\""
echo
echo "要重新出包：bash _apk/release.sh"
