# Ever · 手帐 App（单文件 + 资源）

一台手机上的「AI 手帐」：桌面是一本手帐，里面是聊天、日记、家园、星海、记忆……
整个页面是**一个 HTML**（17MB，贴纸/字体/珍珠都内联成 data URI），
旁边 `aset/` 是没法内联的那几页素材（家园编辑器、日记本、纸张、字体）。

> 当前版本：**8.07-20261102-1018-mobile**

## 目录

```
ever.html                 ← 成品（构建产物，单文件）
aset/                     ← 子页面素材：家园 aset/home4、日记 aset/diary、纸/字体 aset/paper|fonts …
_mobile/src/shell.html    ← 外壳源码（App 的 UI：首页/聊天/设置…）
_mobile/src/jh-doc.html   ← 手帐桌面源码（iframe 里那一本）
_mobile/src/patch/        ← 注入桌面文档的移动端模块（css/js）
_mobile/patch/round-*/    ← 每一轮的补丁脚本（可 --revert）
_mobile/build.py          ← 构建：两份源码 + 补丁 → ever.html（含图片/字体内联）
_mobile/smoke.cjs 等      ← 无头验收脚本（Playwright）
docs/                     ← 各轮交接条（问题、根因、实测、回滚方式）
```

## 构建

```bash
python3 _mobile/build.py            # 产出 _mobile/out/ever-mobile.html
python3 _mobile/build.py --install  # 另外覆盖 ever.html（自动备份）并同步 TidalEcho-手帐桌面.html
node _mobile/smoke.cjs "$PWD/ever.html"   # 冒烟：点按 → 全屏 → 翻页 → 应用抽屉 → 退出
```

依赖：Python 3（构建期用 Pillow 压图，可选）、Node + Playwright（只有跑验收脚本需要）。

## 手机上怎么用

1. **本机预览服务**（局域网里任何设备都能开）
   ```bash
   sh 启动本地预览.sh          # 0.0.0.0:8901，会打印局域网地址
   ```
   打开 `http://<这台机的IP>:8901/ever.html?phone=1`。

2. **做成 App**：`manifest.webmanifest` 是 `display:fullscreen`，
   浏览器里「添加到主屏幕」就是全屏 App，没有地址栏。

3. **APK**：历史上打过（`_apk/` 里是 WebView 外壳工程和签名脚本），
   需要 JDK17 + android-34 + aapt/apksigner/zipalign；素材必须打进 `assets/`，
   否则 WebView 的 `file://` 读不到同目录图片（贴纸全白就是这么来的）。

## 已修的主要问题（详见 docs/）

- `?phone=1` 被当成平板 → 平板缩放（meta initial-scale ↔ CSS zoom）来回切，整页弹动；
- `data-fit` 被两处代码来回写 → `.app` 钉在 50%/50%，整页跑到右下角；
- 家园强制横屏改成"先量后显示"，进出家园不再空白/跳动；
- 用户气泡 = AI 气泡（半透明磨砂）；设置页顶栏磨砂（含夜间）；
- 思考链时间轴显示**全部**工具调用（拍一拍 / 打赏 / 发表情包 …）；
- 树上「群聊」吊牌开成单聊页（`app:chat` → `app:group`）；
- 去掉全屏珍珠（改成 App 内沉浸后没用了）。

## 已知限制

- `星露谷/`（434MB 的游戏目录）**不在这个仓库里**，所以从仓库里打开星露谷会白屏；
  需要的话单独发布成 Release 压缩包。
- 聊天记录 / 贴纸 / 家园布置存在浏览器 localStorage + IndexedDB 里，
  换设备请用「设置 → 导出备份 / 导入备份」。
