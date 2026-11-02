#!/bin/sh
# 推送到 GitHub
#   用法： GH_TOKEN=ghp_xxx GH_REPO=用户名/仓库名 sh push.sh
#   （token 只需 repo 写权限；仓库可以是空的，第一次推送会建 main 分支）
set -e
[ -n "$GH_TOKEN" ] || { echo "缺 GH_TOKEN"; exit 1; }
[ -n "$GH_REPO" ]  || { echo "缺 GH_REPO（例如 someone/ever-handbook）"; exit 1; }
cd "$(dirname "$0")"
git remote remove origin 2>/dev/null || true
git remote add origin "https://x-access-token:$GH_TOKEN@github.com/$GH_REPO.git"
git push -u origin HEAD:main
echo "✓ 已推送：https://github.com/$GH_REPO"
