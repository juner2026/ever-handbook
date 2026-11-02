package com.tidalecho.app;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.DownloadListener;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import java.io.BufferedInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import android.widget.Toast;

/* TidalEcho 外壳：把整个单文件 App 连素材一起打进 APK 里跑，
   避免 Android 11+ 从文件管理器打开时"读不到同级文件"导致画面空白。

   ★ 后台保活：这个应用里有"自主心跳"（AI 自己找话说）、工作流定时唤醒、
     每 30 分钟写一次记忆 —— 全靠页面里的 JS 定时器。手机一进后台会遇到两道拦：
       ① 进程被系统回收            → TeKeepAlive 用前台服务 + 常驻通知顶住
       ② 屏幕关闭后 CPU 休眠，JS 定时器冻结 → TeKeepAlive 的 PARTIAL_WAKE_LOCK 顶住
     所以进应用就把服务拉起来；页面侧可以用 window.TidalEcho 查询/开关。 */
public class MainActivity extends Activity {
    private WebView web;
    private ValueCallback<Uri[]> filePathCallback;
    private static final int REQ_FILE = 1001;
    private static final int REQ_DIR  = 1002;
    private TeFS tefs;   /* 手机文件通道：让工作台和 AI 真能读写手机上的文件 */
    private static final int REQ_NOTI = 1003;   /* Android 13+ 的常驻通知权限 */
    private static final int REQ_GEO  = 1004;   /* 真实天气要的位置权限 */
    private static final int REQ_MIC  = 1005;   /* 通话语音输入要的麦克风权限 */
    /* ★ 录屏授权（陪你看屏幕）。任务书里写的是 1002，但 1002 已经被「选择文件夹」
       占用了 —— 复用会让人一选文件夹就被当成录屏结果，所以改成 1006。 */
    private static final int REQ_CAP  = 1006;

    /* ★ 原生选图（5.70）。为什么要自己弹相册，见 openImagePicker() 上面的注释。 */
    private static final int REQ_PICK_IMG = 1007;
    private static final int IMG_MAX = 1280;   /* 长边缩到这么多 */
    private static final int IMG_Q   = 80;     /* JPEG 质量 */
    /* 待送出去的原生图片（dataURL）。页面可能在中途被系统重载，
       所以不能"送一次就算完"，要留在队列里等页面重新载好再补送。 */
    private final ArrayList<String> pendingImgs = new ArrayList<String>();
    private int pendingTries = 0;
    private final android.os.Handler ui =
            new android.os.Handler(android.os.Looper.getMainLooper());

    /* 陪看（EverWatchService）用：页面推过来的接口配置 + Activity 的弱引用 */
    public static java.lang.ref.WeakReference<MainActivity> INSTANCE;
    private volatile String watchCfg = "";
    private volatile boolean overlayAsked = false;

    /* 页面在等这个位：拿到权限后要回调它 */
    private android.webkit.GeolocationPermissions.Callback geoCallback;
    private String geoOrigin;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        INSTANCE = new java.lang.ref.WeakReference<MainActivity>(this);
        /* ★ 5.72：先把版本写进诊断日志 —— 一眼就能确认手机上跑的到底是哪一版。
           前几轮最大的浪费就是「以为装了新版，其实跑的是旧页面」。 */
        try{
            android.content.pm.PackageInfo pi =
                getPackageManager().getPackageInfo(getPackageName(), 0);
            diag("=== 启动 Ever " + pi.versionName + " (" + pi.versionCode + ") ===");
        }catch(Throwable t){ diag("=== 启动（版本读不到）==="); }
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON,
                             WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        web = new WebView(this);
        FrameLayout root = new FrameLayout(this);
        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          /* localStorage：聊天记录/家园存档都在这儿 */
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setAllowFileAccessFromFileURLs(true);/* ★ 关键：允许 file:// 页面读同级素材 */
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setGeolocationEnabled(true);          /* ★ 真实天气要用定位 */
        s.setJavaScriptCanOpenWindowsAutomatically(true);
        s.setSupportMultipleWindows(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        /* ★ 手机文件通道（TeFS）。
           页面里 tfsHost() 优先找 window.OperitFS.op(op,path,content) ——
           原来那个接口没人实现，加上 WebView 不支持 showDirectoryPicker，
           手机上工作台永远显示「暂无可用通道」。这里把它补上。
           addJavascriptInterface 的方法都在 @JavascriptInterface 注解下，
           不注解的反射方法（getClass 之类）拿不到，避免老漏洞。 */
        tefs = new TeFS(this, web);
        tefs.load();
        web.addJavascriptInterface(tefs, "OperitFS");

        /* ★ 后台保活：把服务拉起来（幂等，重复调只是更新同一条通知） */
        TeKeepAlive.start(this);

        /* ★ 给页面用的开关。页面可以：
             window.TidalEcho.keepAliveOn()      → true/false 现在开着没
             window.TidalEcho.keepAlive(true)    → 开/关保活
             window.TidalEcho.batteryOk()        → 有没有加进电池白名单
             window.TidalEcho.askBattery()       → 弹系统"忽略电池优化"授权页
             window.TidalEcho.askNotify()        → 要通知权限（Android 13+）       */
        web.addJavascriptInterface(new Object() {
            @android.webkit.JavascriptInterface
            public boolean keepAliveOn() { return TeKeepAlive.alive; }

            @android.webkit.JavascriptInterface
            public boolean keepAlive(boolean on) {
                if (on) TeKeepAlive.start(MainActivity.this);
                else    TeKeepAlive.stop(MainActivity.this);
                return on;
            }

            @android.webkit.JavascriptInterface
            public boolean batteryOk() { return isIgnoringBatteryOptimizations(); }

            @android.webkit.JavascriptInterface
            public void askBattery() {
                runOnUiThread(new Runnable() { public void run() { requestIgnoreBattery(); } });
            }

            @android.webkit.JavascriptInterface
            public void askNotify() {
                runOnUiThread(new Runnable() { public void run() { askNotification(); } });
            }
        }, "TidalEcho");

        /* ============================================================
           ★ 陪你看屏幕（EverNative 桥）
           ------------------------------------------------------------
           给页面的接口（页面用 window.EverNative.xxx() 调）：
             startWatch()         → "need_overlay" / "starting"
             stopWatch()          → 停（停线程、关 ImageReader、撤悬浮层）
             showReply(txt)       → 一句反应显示到悬浮气泡上（2.8 秒淡出）
             setAvatar(dataUrl)   → 当前 AI 的头像（dataURL），悬浮层画的就是他本人
             setStyle(st)         → "danmu"（弹幕式）/ "quiet"（安静）
             hasOverlay()         → "1" / "0"
             openOverlaySettings()→ 跳系统「显示在其他应用上层」
             configure(json)      → {base,key,model,style}，页面启程/存设置时推过来
             frameDone()          → 一帧处理完了（背压开关，不调就停帧）
             isRunning()          → "1" / "0"（重启应用后按钮状态靠它对齐）

           为什么模型请求留在 WebView 里：接口配置（base/key/model/预设）全在页面
           localStorage，原生再读一遍只会读出两套、越用越分叉。原生只负责"看见"，
           "说话"交给页面里现成的 apiEff / apiUrl 那套。
           ============================================================ */
        EverWatchService.setWebView(web);
        web.addJavascriptInterface(new Object() {
            @android.webkit.JavascriptInterface
            public String startWatch() {
                try {
                    if (!EverWatchService.hasOverlay(MainActivity.this)) return "need_overlay";
                    runOnUiThread(new Runnable() { public void run() { requestCapture(); } });
                    return "starting";
                } catch (Throwable t) {
                    android.util.Log.e("TidalEcho", "startWatch: " + t);
                    return "error";
                }
            }

            @android.webkit.JavascriptInterface
            public void stopWatch() {
                try { EverWatchService.stop(MainActivity.this); } catch (Throwable t) {}
            }

            @android.webkit.JavascriptInterface
            public void showReply(String text) {
                try { EverWatchService.showReply(text); } catch (Throwable t) {}
            }

            /* ★ 头像：页面把当前 AI 的头像 dataURL 推过来（换 AI / 换头像会重推）。
               原生存成静态 Bitmap，悬浮层创建/刷新时直接用；拿不到就粉渐变圆 + 首字兜底。 */
            @android.webkit.JavascriptInterface
            public void setAvatar(String dataUrl) {
                try { EverWatchService.setAvatar(dataUrl); } catch (Throwable t) {}
            }

            @android.webkit.JavascriptInterface
            public void setStyle(String st) {
                try { EverWatchService.setStyle(st); } catch (Throwable t) {}
            }

            @android.webkit.JavascriptInterface
            public String hasOverlay() {
                try { return EverWatchService.hasOverlay(MainActivity.this) ? "1" : "0"; }
                catch (Throwable t) { return "0"; }
            }

            @android.webkit.JavascriptInterface
            public void openOverlaySettings() {
                runOnUiThread(new Runnable() { public void run() { openOverlayPage(); } });
            }

            @android.webkit.JavascriptInterface
            public void configure(String json) {
                try {
                    watchCfg = (json == null) ? "" : json;
                    EverWatchService.configure(watchCfg);
                } catch (Throwable t) {}
            }

            @android.webkit.JavascriptInterface
            public void frameDone() {
                try { EverWatchService.frameDone(); } catch (Throwable t) {}
            }

            @android.webkit.JavascriptInterface
            public String isRunning() {
                try { return EverWatchService.isRunning() ? "1" : "0"; }
                catch (Throwable t) { return "0"; }
            }

            /* ★ 5.70 原生选图。"＋"点了就走这条路，不再靠 <input type=file>：
               实测点「＋」打开系统相册的瞬间，WebView 渲染进程会被系统回收，
               回来时页面已经重载（计数清零、change 监听没了），所以前端怎么改
               都接不到文件。这里由 Activity 自己弹相册、自己解码，跟 WebView
               的文件选择器完全不沾边。
               读好的图逐张交给 window._momNativeImg('<dataURL>')。
               返回 "opening" / "error"（页面只用它做兜底提示）。 */
            @android.webkit.JavascriptInterface
            public String pickImages() {
                try {
                    diag("JS 调了 pickImages()");
                    runOnUiThread(new Runnable() { public void run() { openImagePicker(); } });
                    return "opening";
                } catch (Throwable t) {
                    android.util.Log.e("TidalEcho", "pickImages: " + t);
                    return "error";
                }
            }

            /* ★ 5.72 页面往诊断日志里写一行。真机没有 logcat，这是唯一的出口。 */
            @android.webkit.JavascriptInterface
            public void dbgLog(String s) {
                diag("JS  " + (s == null ? "" : s));
            }

            /* 诊断文件在哪（页面上显示给用户看） */
            @android.webkit.JavascriptInterface
            public String dbgPath() {
                try {
                    java.io.File dir = getExternalFilesDir(null);
                    return dir == null ? "" : new java.io.File(dir, DIAG_FILE).getAbsolutePath();
                } catch (Throwable t) { return ""; }
            }

            /* ★ 5.73 把诊断日志落到「下载/Ever-log/ever-diag.log」——
               私有目录电脑端读不到，这个位置能取走。返回结果/路径给页面显示。 */
            @android.webkit.JavascriptInterface
            public String dbgExport() {
                final String r = exportDiag();
                android.util.Log.i("TidalEcho", "dbgExport: " + r);
                return r;
            }
        }, "EverNative");

        /* ★ Android 13+ 要常驻通知得先要权限。不给也能跑（只是通知被隐藏），
           所以这里只是问一下，不阻塞。 */
        askNotification();
        /* ★ 国产系统（MIUI/EMUI/ColorOS…）会主动清后台 —— 不加电池白名单保活基本无效。
           这里只检查、提示，**不擅自弹系统页面**，由页面决定什么时候问用户。 */
        if (!isIgnoringBatteryOptimizations()) {
            android.util.Log.i("TidalEcho", "还没加入电池优化白名单，长时间后台可能被系统清掉");
        }

        web.setWebViewClient(new WebViewClient() {
            /* ★ 用内部 https 域名发素材：file:// origin 下 WebView 会禁掉 IndexedDB，
               聊天图片就存不住了。这里把 https://app.local/** 全部从 APK 的 assets 里读出来。 */
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest req) {
                try {
                    android.net.Uri u = req.getUrl();
                    if (u == null || !"app.local".equals(u.getHost())) return null;
                    String path = u.getPath();
                    if (path == null || path.equals("/")) path = "/index.html";
                    InputStream raw = getAssets().open(path.substring(1));
                    BufferedInputStream in = new BufferedInputStream(raw, 8192);
                    in.mark(16);
                    byte[] head = new byte[12];
                    int n = in.read(head);
                    in.reset();
                    return new WebResourceResponse(mimeOf(path, head, n), null, in);
                } catch (IOException e) {
                    return new WebResourceResponse("text/plain", "utf-8",
                            new ByteArrayInputStream(("404 " + req.getUrl()).getBytes()));
                } catch (Exception e) {
                    return null;
                }
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, String url) {
                if (url != null && (url.startsWith("http://") || url.startsWith("https://"))) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))); return true; }
                    catch (Exception e) { return false; }
                }
                return false;   /* file:// 之类的自己处理 */
            }
            @Override public void onReceivedError(WebView v, int code, String desc, String failingUrl) {
                android.util.Log.e("TidalEcho", "load error " + code + " " + desc + " " + failingUrl);
            }
            @Override public void onPageFinished(WebView v, String url) {
                android.util.Log.i("TidalEcho", "page finished: " + url);
                /* ★ 5.72：页面加载完 = 记一条。要是它出现两次，就说明页面真的被重载过。 */
                diag("page finished: " + url);
                /* ★ 5.72：把**真正装着的版本号**注入页面，诊断面板上显示的就是它 ——
                   一眼分清"装的是新版"还是"页面还是旧的"。 */
                try{
                    android.content.pm.PackageInfo pi =
                        getPackageManager().getPackageInfo(getPackageName(), 0);
                    web.evaluateJavascript("try{window.__everVer="
                        + jsStr(String.valueOf(pi.versionName)) + ";}catch(e){}", null);
                    diag("注入版本号 " + pi.versionName);
                }catch(Throwable t){}
                web.evaluateJavascript(
                  "try{document.documentElement.style.setProperty('-webkit-tap-highlight-color','transparent')}catch(e){}", null);
                /* ★ 5.70：页面刚（重新）载好 —— 把还没送到的原生选图补送一次。
                   这就是「动态配了图、格子不出现」的保险丝：系统相册一开，
                   WebView 很可能被回收重载，图解码出来时页面上已经没有接收方了。 */
                pendingTries = 0;
                deliverNextImg();
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onConsoleMessage(ConsoleMessage m) {
                android.util.Log.i("TidalEcho", m.messageLevel()+" "+m.message()+" @"+m.sourceId()+":"+m.lineNumber());
                /* ★ 5.72：页面的报错也进诊断文件 —— 真机上这是唯一能拿到 JS 异常的办法 */
                try{
                    diag("console[" + m.messageLevel() + "] " + m.message()
                         + " @" + m.sourceId() + ":" + m.lineNumber());
                }catch(Throwable t){}
                return false;   /* 返回 false → WebView 自己也往 logcat 写一份，方便远程排查 */
            }
            /* （原本这里有一个 onPermissionRequest，写的是
                 r.grant(r.getResources()) —— **无条件放行一切**。
               它对麦克风其实没用：Android 6+ 的 RECORD_AUDIO 是运行时权限，
               不先动态申请就一直是拒绝状态，WebView 拿不到音轨。
               已删掉，统一用下面那个会先申请权限的版本。） */
            /* ★ 真实天气：页面调 navigator.geolocation 时走这里。
               Android 6+ 要运行时权限 —— 先把系统的问了，拿到再放行给页面；
               拿不到就明确回调失败（页面会退到 IP 定位，不会卡住）。 */
            @Override public void onGeolocationPermissionsShowPrompt(
                    String origin, android.webkit.GeolocationPermissions.Callback cb) {
                if (hasLocationPermission()) {
                    cb.invoke(origin, true, false);
                    return;
                }
                geoCallback = cb; geoOrigin = origin;
                try {
                    requestPermissions(new String[]{
                        android.Manifest.permission.ACCESS_COARSE_LOCATION,
                        android.Manifest.permission.ACCESS_FINE_LOCATION}, REQ_GEO);
                } catch (Throwable t) {
                    cb.invoke(origin, false, false);
                    geoCallback = null; geoOrigin = null;
                }
            }
            /* ============================================================
               ★ 麦克风权限（通话的语音输入要用）
               ------------------------------------------------------------
               网页里调 getUserMedia 时，WebView 会走到这里。
               两个坑：
                 ① 必须**先动态申请** RECORD_AUDIO（Android 6+ 不动态申请就一直拒），
                    申请完再 invoke —— 直接 invoke(true) 是不生效的。
                 ② 不能只处理 RESOURCE_AUDIO_CAPTURE：音频请求是下面那三个资源
                    的组合，只匹配 AUDIO_CAPTURE 会漏掉，表现为"点了没反应"。
               ============================================================ */
            @Override public void onPermissionRequest(final PermissionRequest request) {
                try {
                    boolean wantsAudio = false;
                    for (String r : request.getResources()) {
                        if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)
                                || "android.webkit.resource.AUDIO_CAPTURE".equals(r)
                                || "android.webkit.resource.VIDEO_CAPTURE".equals(r)) {
                            wantsAudio = true;
                        }
                    }
                    if (!wantsAudio) { request.deny(); return; }
                    if (hasAudioPermission()) {
                        request.grant(request.getResources());
                        return;
                    }
                    micRequest = request;
                    requestPermissions(new String[]{
                        android.Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                } catch (Throwable t) {
                    try { request.deny(); } catch (Throwable t2) {}
                    micRequest = null;
                }
            }

            /* 应用里的"导入备份""选头像"要能弹系统文件选择器 */
            @Override public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb,
                                                       FileChooserParams params) {
                filePathCallback = cb;
                try {
                    /* ★ 5.72：这一行是「动态配图」案子的关键证据 ——
                       WebView 到底有没有来要文件选择器、要多选还是单选。 */
                    diag("原生 onShowFileChooser 被调用 mode=" + params.getMode()
                         + " accept=" + java.util.Arrays.toString(params.getAcceptTypes()));
                    startActivityForResult(params.createIntent(), REQ_FILE);
                    return true;
                } catch (Exception e) {
                    diag("原生 onShowFileChooser 起不来：" + e);
                    filePathCallback = null; return false;
                }
            }
        });

        /* 应用里"导出备份"是 blob 下载：交给自己写进 Download 目录 */
        web.setDownloadListener(new DownloadListener() {
            @Override public void onDownloadStart(String url, String ua, String cd, String mime, long len) {
                try {
                    if (url.startsWith("blob:")) {
                        Toast.makeText(MainActivity.this, "备份已生成：请在应用内用「导入/导出」或浏览器版本导出", Toast.LENGTH_LONG).show();
                        return;
                    }
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                } catch (Exception e) {}
            }
        });

        web.loadUrl("https://app.local/index.html");
    }

    @Override public void onRequestPermissionsResult(int req, String[] perms, int[] res) {
        super.onRequestPermissionsResult(req, perms, res);
        if (req == REQ_GEO) {
            /* 用户答应了就放行给页面；拒绝了也要明确回调，页面才能退到 IP 定位 */
            boolean ok = hasLocationPermission();
            try { if (geoCallback != null) geoCallback.invoke(geoOrigin, ok, false); } catch (Throwable t) {}
            geoCallback = null; geoOrigin = null;
            if (!ok) {
                try { Toast.makeText(this, "没给定位权限，天气改用网络大致位置", Toast.LENGTH_SHORT).show(); } catch (Throwable t) {}
            }
        }
        if (req == REQ_MIC) {
            /* 答应了就放行给页面；拒了也要明确回调，页面才能提示"去设置里开" */
            boolean ok = hasAudioPermission();
            try {
                if (micRequest != null) {
                    if (ok) micRequest.grant(micRequest.getResources());
                    else    micRequest.deny();
                }
            } catch (Throwable t) {}
            micRequest = null;
            if (!ok) {
                try { Toast.makeText(this, "没给麦克风权限，通话里只能打字", Toast.LENGTH_SHORT).show(); } catch (Throwable t) {}
            }
        }
    }

    /* 待回应的麦克风请求：用户在弹出的系统框上点完之后再放行/拒绝 */
    private android.webkit.PermissionRequest micRequest = null;

    private boolean hasAudioPermission() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 23) return true;
            return checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)
                       == android.content.pm.PackageManager.PERMISSION_GRANTED;
        } catch (Throwable t) { return false; }
    }

    private boolean hasLocationPermission() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 23) return true;
            return checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION)
                       == android.content.pm.PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION)
                       == android.content.pm.PackageManager.PERMISSION_GRANTED;
        } catch (Throwable t) { return false; }
    }

    @Override protected void onActivityResult(int req, int res, Intent data) {
        if (req == REQ_PICK_IMG) {
            handlePickedImages(res, data);
            return;
        }
        if (req == REQ_CAP) {
            /* 系统录屏授权回来了：OK 就把那张「凭证 Intent」连同配置一起交给前台服务 */
            if (res == RESULT_OK && data != null) {
                try {
                    EverWatchService.start(this, data, watchCfg);
                } catch (Throwable t) {
                    toastMsg("陪看启动失败：" + t);
                    evalJs("try{window.__everWatchStopped&&window.__everWatchStopped();}catch(e){}");
                }
            } else {
                toastMsg("没给录屏权限，陪看没开起来");
                evalJs("try{window.__everWatchStopped&&window.__everWatchStopped();}catch(e){}");
            }
            return;
        }
        if (req == REQ_DIR) {
            /* 用户在系统「选择文件夹」里挑了一个目录 → 长期保留这份授权 */
            if (res == RESULT_OK && data != null && tefs != null) {
                android.net.Uri tree = data.getData();
                if (tree != null) tefs.onFolderPicked(tree);
            } else if (tefs != null) {
                try { web.evaluateJavascript(
                    "try{if(window.__teFsTell)window.__teFsTell('没有选择文件夹');}catch(e){}", null);
                } catch (Exception e) {}
            }
            return;
        }
        if (req == REQ_FILE) {
            /* ★ 5.72：相册回来这一下必须留证据 —— 是"根本没回来"、
               "回来了但没给图"、还是"给图了但页面已经不认了"。 */
            if (filePathCallback != null) {
                Uri[] got = WebChromeClient.FileChooserParams.parseResult(res, data);
                int n = (got == null) ? 0 : got.length;
                diag("原生 onActivityResult(FILE) res=" + res
                     + " data=" + (data == null ? "null" : "有")
                     + " 交回页面 " + n + " 张");
                for (int i = 0; i < n && i < 9; i++) diag("  uri[" + i + "] " + got[i]);
                filePathCallback.onReceiveValue(got);
                filePathCallback = null;
            } else {
                diag("原生 onActivityResult(FILE) 但 filePathCallback 已是 null"
                     + "（页面在这中间重载过，图没人接）");
            }
            return;
        }
        super.onActivityResult(req, res, data);
    }

    /* ---------- 保活相关的几个小工具 ---------- */

    /* 有没有被排除在电池优化之外（= 厂商不会因为"省电"清掉我们） */
    private boolean isIgnoringBatteryOptimizations() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 23) return true;
            android.os.PowerManager pm =
                (android.os.PowerManager) getSystemService(POWER_SERVICE);
            if (pm == null) return true;
            return pm.isIgnoringBatteryOptimizations(getPackageName());
        } catch (Throwable t) { return true; }
    }

    /* 请求把本应用加进"不受电池优化限制"白名单。
       注：这个系统页面必须由用户点确认，我们不能替他决定 —— 所以只提供入口。 */
    private void requestIgnoreBattery() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 23) return;
            if (isIgnoringBatteryOptimizations()) {
                Toast.makeText(this, "已经在电池白名单里了", Toast.LENGTH_SHORT).show();
                return;
            }
            Intent i = new Intent(
                android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
            i.setData(Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Throwable t) {
            /* 有些机型没有这个页面，退到"电池优化列表"总页面 */
            try {
                startActivity(new Intent(
                    android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            } catch (Throwable t2) {
                Toast.makeText(this, "请在系统设置里把「潮汐回响」设为不受限制", Toast.LENGTH_LONG).show();
            }
        }
    }

    /* Android 13+ 通知权限 */
    private void askNotification() {
        try {
            if (android.os.Build.VERSION.SDK_INT < 33) return;
            if (checkSelfPermission("android.permission.POST_NOTIFICATIONS")
                    == android.content.pm.PackageManager.PERMISSION_GRANTED) return;
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, REQ_NOTI);
        } catch (Throwable t) {}
    }

    /* ---------- 陪看：录屏授权 / 悬浮窗权限 ---------- */

    /* 弹系统「是否允许录制或投放屏幕」。结果走 onActivityResult(REQ_CAP)。 */
    private void requestCapture() {
        try {
            android.media.projection.MediaProjectionManager mpm =
                (android.media.projection.MediaProjectionManager)
                    getSystemService(MEDIA_PROJECTION_SERVICE);
            if (mpm == null) { toastMsg("这台机器不支持录屏"); return; }
            startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAP);
        } catch (Throwable t) {
            toastMsg("打不开录屏授权页");
            evalJs("try{window.__everWatchStopped&&window.__everWatchStopped();}catch(e){}");
        }
    }

    /* 跳系统「显示在其他应用上层」。Android 12+ 允许直接落到本应用的开关页；
       回来后 onResume 里会通知页面刷新按钮状态。 */
    private void openOverlayPage() {
        overlayAsked = true;
        try {
            if (android.os.Build.VERSION.SDK_INT >= 23) {
                Intent i = new Intent(
                    android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:" + getPackageName()));
                startActivity(i);
                return;
            }
        } catch (Throwable t) {}
        try {
            startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION));
        } catch (Throwable t) {
            toastMsg("请在系统设置里找「显示在其他应用上层」给 Ever 打开");
        }
    }

    private void toastMsg(final String s) {
        try {
            runOnUiThread(new Runnable() {
                public void run() {
                    try { Toast.makeText(MainActivity.this, s, Toast.LENGTH_SHORT).show(); } catch (Throwable t) {}
                }
            });
        } catch (Throwable t) {}
    }

    private void evalJs(String js) {
        try { if (web != null) web.evaluateJavascript(js, null); } catch (Throwable t) {}
    }

    @Override protected void onResume() {
        super.onResume();
        /* 从「显示在其他应用上层」设置页回来：让页面把按钮状态重画一次
           （用户可能刚给了权限，也可能又收回去了） */
        if (overlayAsked) {
            overlayAsked = false;
            evalJs("try{window.__everWatchPermBack&&window.__everWatchPermBack();}catch(e){}");
        }
    }

    /* ============================================================================
       ★ 5.70 原生选图
       ----------------------------------------------------------------------------
       病根（真机现象）：点「＋」→ 系统相册弹出 → 选图 → 回来，页面上的
       「相册打开 N 次 · change N 次 · 收到文件 N 个」还是 0/0/0。
       README 里那条推断是"打开相册的瞬间 WebView 被系统回收、页面重载"，
       于是计数清零、change 监听没了、回来时无人接文件 —— 前端改多少轮都不生效。

       对策（不再碰 WebView 的文件选择器）：Activity 自己 startActivityForResult
       去相册，自己用 ContentResolver + BitmapFactory 解码，压好后逐张交给页面。
       三步：
         ① openImagePicker()      弹相册（多选，最多 9 张）
         ② handlePickedImages()   拿 Uri → 后台线程解码（绝不占 UI 线程）
         ③ deliverNextImg()       逐张 evaluateJavascript → window._momNativeImg()
       页面若在过程中被重载，待送队列还在原生这边，onPageFinished 会再送一遍。
       顺带解决：HEIC（BitmapFactory API 28+ 能解）、超大图 OOM、相机照片方向。
       ============================================================================ */

    /* 弹系统相册。用 ACTION_GET_CONTENT 而不是 MediaStore.ACTION_PICK：
       前者所有 ROM / 各家相册（含云相册）都认，而且天然支持多选。 */
    private void openImagePicker() {
        try {
            Intent i = new Intent(Intent.ACTION_GET_CONTENT);
            i.setType("image/*");
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            diag("打开相册：GET_CONTENT image/* 多选（走 chooser）");
            startActivityForResult(Intent.createChooser(i, "选择照片"), REQ_PICK_IMG);
            return;
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "openImagePicker: " + t);
            diag("打开相册(GET_CONTENT)失败：" + t);
        }
        try {
            Intent i2 = new Intent(Intent.ACTION_PICK,
                    android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI);
            i2.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
            diag("打开相册：退到 ACTION_PICK");
            startActivityForResult(i2, REQ_PICK_IMG);
        } catch (Throwable t2) {
            diag("打开相册(ACTION_PICK)也失败：" + t2);
            toastMsg("打不开相册");
            evalJs("try{window._momNativeImgCancel&&window._momNativeImgCancel()}catch(e){}");
        }
    }

    /* 相册回来了：取出 Uri（可能多张），丢给后台线程解码。
       解码几张 4K 照片要 1–2 秒，放在 UI 线程会被系统判成无响应，反而更容易被杀。 */
    private void handlePickedImages(int res, Intent data) {
        if (res != RESULT_OK || data == null) {
            diag("相册回来：res=" + res + " data=" + (data == null ? "null" : "有") + " → 取消/没选");
            evalJs("try{window._momNativeImgCancel&&window._momNativeImgCancel()}catch(e){}");
            return;
        }
        final ArrayList<Uri> uris = new ArrayList<Uri>();
        try {
            ClipData cp = data.getClipData();          /* 多选走 ClipData */
            if (cp != null) {
                for (int i = 0; i < cp.getItemCount() && uris.size() < 9; i++) {
                    ClipData.Item it = cp.getItemAt(i);
                    if (it != null && it.getUri() != null) uris.add(it.getUri());
                }
            }
            if (uris.isEmpty() && data.getData() != null) uris.add(data.getData());   /* 单选 */
            if (uris.isEmpty()) {
                /* 个别相册把结果塞在 extras 里 */
                String p = data.getStringExtra("output");
                if (p != null) uris.add(Uri.parse(p));
            }
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "handlePickedImages read: " + t);
        }
        if (uris.isEmpty()) {
            diag("相册回来 res=OK 但一个 Uri 都没取到（ClipData / getData 都是空）");
            evalJs("try{window._momNativeImgCancel&&window._momNativeImgCancel()}catch(e){}");
            return;
        }
        diag("相册回来 res=OK，拿到 " + uris.size() + " 个 Uri，开始后台解码");
        for (int i = 0; i < uris.size() && i < 9; i++) diag("  选中 " + uris.get(i));
        new Thread(new Runnable() {
            public void run() {
                final ArrayList<String> out = new ArrayList<String>();
                int bad = 0;
                for (int i = 0; i < uris.size(); i++) {
                    String du = imgToDataUrl(uris.get(i));
                    if (du != null) out.add(du); else bad++;
                }
                final int fbad = bad, fok = out.size();
                diag("解码完成：成功 " + fok + " 张，失败 " + fbad + " 张");
                ui.post(new Runnable() {
                    public void run() {
                        pendingImgs.addAll(out);
                        if (fbad > 0) {
                            evalJs("try{window._momNativeImgFail&&window._momNativeImgFail('"
                                   + fbad + " 张读不出来')}catch(e){}");
                        }
                        pendingTries = 0;
                        deliverNextImg();
                    }
                });
            }
        }, "ever-pick-img").start();
    }

    /* 逐张送。页面收下会返回 '1'；返回别的值说明页面还没来得及定义
       _momNativeImg（多半是刚被重载），留着等下一次 onPageFinished 再送。 */
    private void deliverNextImg() {
        if (web == null || pendingImgs.isEmpty()) return;
        if (pendingTries > 6) {            /* 反复送不到就别一直占着队列 */
            android.util.Log.w("TidalEcho", "native img 送不到，放弃 " + pendingImgs.size() + " 张");
            pendingImgs.clear();
            pendingTries = 0;
            return;
        }
        final String du = pendingImgs.get(0);
        try {
            web.evaluateJavascript("try{window._momNativeImg(" + jsStr(du) + ")}catch(e){'0'}",
                new ValueCallback<String>() {
                    @Override public void onReceiveValue(String v) {
                        if (v != null && v.indexOf('1') >= 0) {
                            if (!pendingImgs.isEmpty()) pendingImgs.remove(0);
                            pendingTries = 0;
                            deliverNextImg();               /* 还有就接着送 */
                        } else {
                            pendingTries++;
                            ui.postDelayed(new Runnable() {
                                public void run() { deliverNextImg(); }
                            }, 700);
                        }
                    }
                });
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "deliverNextImg: " + t);
        }
    }

    /* 一张图 → dataURL。两遍解码（先只读尺寸再按 inSampleSize 解），
       避免 4K 原图直接解到 4000×3000 把内存吃穿。 */
    private String imgToDataUrl(Uri uri) {
        InputStream in = null;
        Bitmap bmp = null;
        try {
            /* ① 只读尺寸 */
            BitmapFactory.Options bounds = new BitmapFactory.Options();
            bounds.inJustDecodeBounds = true;
            in = getContentResolver().openInputStream(uri);
            if (in == null) return null;
            BitmapFactory.decodeStream(in, null, bounds);
            closeQuietly(in); in = null;
            int w = bounds.outWidth, h = bounds.outHeight;
            if (w <= 0 || h <= 0) return null;          /* 云相册占位图、损坏文件 */

            /* ② 按 2 的幂降采样，解出来的长边落在 [IMG_MAX, IMG_MAX*2) */
            int sample = 1;
            while (Math.max(w, h) / (sample * 2) >= IMG_MAX) sample *= 2;

            BitmapFactory.Options opt = new BitmapFactory.Options();
            opt.inSampleSize = sample;
            opt.inPreferredConfig = Bitmap.Config.ARGB_8888;
            in = getContentResolver().openInputStream(uri);
            if (in == null) return null;
            bmp = BitmapFactory.decodeStream(in, null, opt);
            closeQuietly(in); in = null;
            if (bmp == null) return null;

            /* ③ 相机竖拍是"横着存 + EXIF 标记"，BitmapFactory 不管这个，得自己转，
                  否则发出去的图全是躺着的 */
            int rot = exifRotation(uri);
            if (rot != 0) {
                Bitmap r = rotateBitmap(bmp, rot);
                if (r != null && r != bmp) { bmp.recycle(); bmp = r; }
            }

            /* ④ 长边准确缩到 IMG_MAX */
            int cw = bmp.getWidth(), ch = bmp.getHeight();
            if (cw <= 0 || ch <= 0) return null;
            float f = Math.min(1f, (float) IMG_MAX / (float) Math.max(cw, ch));
            if (f < 1f) {
                int nw = Math.max(1, Math.round(cw * f));
                int nh = Math.max(1, Math.round(ch * f));
                Bitmap s = Bitmap.createScaledBitmap(bmp, nw, nh, true);
                if (s != null && s != bmp) { bmp.recycle(); bmp = s; }
            }

            /* ⑤ 带透明的 PNG 先垫白底，否则 JPEG 里透明区会变黑 */
            if (bmp.hasAlpha()) {
                Bitmap flat = Bitmap.createBitmap(bmp.getWidth(), bmp.getHeight(),
                                                  Bitmap.Config.ARGB_8888);
                Canvas c = new Canvas(flat);
                c.drawColor(0xFFFFFFFF);
                c.drawBitmap(bmp, 0, 0, null);
                bmp.recycle(); bmp = flat;
            }

            ByteArrayOutputStream bos = new ByteArrayOutputStream(1 << 18);
            bmp.compress(Bitmap.CompressFormat.JPEG, IMG_Q, bos);
            byte[] out = bos.toByteArray();
            if (out == null || out.length < 64) return null;
            return "data:image/jpeg;base64," + Base64.encodeToString(out, Base64.NO_WRAP);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "imgToDataUrl " + uri + " : " + t);
            return null;
        } finally {
            closeQuietly(in);
            try { if (bmp != null) bmp.recycle(); } catch (Throwable t) {}
        }
    }

    /* EXIF 方向 → 要顺时针转多少度 */
    private int exifRotation(Uri uri) {
        InputStream in = null;
        try {
            in = getContentResolver().openInputStream(uri);
            if (in == null) return 0;
            ExifInterface ex = new ExifInterface(in);
            int o = ex.getAttributeInt(ExifInterface.TAG_ORIENTATION,
                                       ExifInterface.ORIENTATION_NORMAL);
            switch (o) {
                case ExifInterface.ORIENTATION_ROTATE_90:  return 90;
                case ExifInterface.ORIENTATION_ROTATE_180: return 180;
                case ExifInterface.ORIENTATION_ROTATE_270: return 270;
                default: return 0;
            }
        } catch (Throwable t) {
            return 0;                        /* HEIC / 没有 EXIF：按原样 */
        } finally {
            closeQuietly(in);
        }
    }

    private static Bitmap rotateBitmap(Bitmap src, int deg) {
        try {
            Matrix m = new Matrix();
            m.postRotate(deg);
            return Bitmap.createBitmap(src, 0, 0, src.getWidth(), src.getHeight(), m, true);
        } catch (Throwable t) {
            return null;
        }
    }

    private static void closeQuietly(InputStream in) {
        try { if (in != null) in.close(); } catch (Throwable t) {}
    }

    /* Java 字符串 → JS 字面量。base64 里不会有引号和反斜杠，
       但 U+2028/2029 会把 JS 源码断行，保险起见一起处理。 */
    private static String jsStr(String s) {
        StringBuilder b = new StringBuilder(s.length() + 16);
        b.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"' || c == '\\') b.append('\\').append(c);
            else if (c == '\n') b.append("\\n");
            else if (c == '\r') b.append("\\r");
            else if (c < 0x20 || c == 0x2028 || c == 0x2029) b.append(' ');
            else b.append(c);
        }
        b.append('"');
        return b.toString();
    }

    /* ============================================================================
       ★ 5.72 真机诊断日志
       ----------------------------------------------------------------------------
       WebView 里出的错在真机上完全看不见（没有 adb 就没有 logcat，
       页面也无处打印）。所以统一写到这里：
         /sdcard/Android/data/com.tidalecho.app/files/ever-diag.log
       电脑端可以直接读这个文件，不用连 adb。
       三路汇进同一个文件：① 原生自己的关键节点（选图器被调没被调、拿回几个 Uri、
       页面有没有重载）② 页面的 console / 未捕获异常 ③ 页面主动 mdbg() 打的点。
       ============================================================================ */
    private static final String DIAG_FILE = "ever-diag.log";

    private static synchronized void diagTo(android.content.Context c, String s) {
        try {
            if (c == null) return;
            java.io.File dir = c.getExternalFilesDir(null);
            if (dir == null) return;
            if (!dir.exists()) dir.mkdirs();
            java.io.File f = new java.io.File(dir, DIAG_FILE);
            if (f.length() > 400 * 1024) {
                java.io.File old = new java.io.File(dir, "ever-diag.old.log");
                try { old.delete(); } catch (Throwable t) {}
                try { f.renameTo(old); } catch (Throwable t) {}
            }
            java.io.FileOutputStream o = new java.io.FileOutputStream(f, true);
            String t = new java.text.SimpleDateFormat("MM-dd HH:mm:ss.SSS",
                            java.util.Locale.US).format(new java.util.Date());
            o.write((t + "  " + s + "\n").getBytes("UTF-8"));
            o.flush();
            o.close();
        } catch (Throwable t) {}
    }

    private void diag(String s) { diagTo(this, s); }

    /* 把诊断日志导一份到「下载/Ever-log/ever-diag.log」。
       为什么不在私有目录里就算了：私有目录（Android/data/com.tidalecho.app）
       在电脑端读不到（Android 11+ 的分区存储），落在 Download 才能取走。
       走 MediaStore 不需要任何权限；同一个文件名先删后写，避免堆一堆。 */
    private String exportDiag() {
        try {
            java.io.File dir = getExternalFilesDir(null);
            if (dir == null) return "ERR 没有外部目录";
            java.io.File f = new java.io.File(dir, DIAG_FILE);
            if (!f.exists()) return "ERR 还没有日志";
            if (android.os.Build.VERSION.SDK_INT < 29) return "ERR 系统太旧（<10）";
            byte[] data = new byte[(int) f.length()];
            java.io.FileInputStream in = new java.io.FileInputStream(f);
            int off = 0;
            while (off < data.length) {
                int n = in.read(data, off, data.length - off);
                if (n <= 0) break;
                off += n;
            }
            in.close();

            String rel = android.os.Environment.DIRECTORY_DOWNLOADS + "/Ever-log";
            /* ★ 5.76：之前 DISPLAY_NAME 写 "ever-diag.log" + MIME text/plain，
               MediaStore 会自作主张存成 "ever-diag.log.txt"，于是下面的删除永远
               匹配不上 —— 每导出一次就多一份 "ever-diag.log (5).txt"。
               现在名字直接用 .txt，删得掉，只保留一份。 */
            final String dn = "ever-diag.txt";
            try{
                getContentResolver().delete(
                    android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    android.provider.MediaStore.MediaColumns.DISPLAY_NAME + "=?",
                    new String[]{ dn });
            }catch(Throwable t){}

            android.content.ContentValues cv = new android.content.ContentValues();
            cv.put(android.provider.MediaStore.MediaColumns.DISPLAY_NAME, dn);
            cv.put(android.provider.MediaStore.MediaColumns.MIME_TYPE, "text/plain");
            cv.put(android.provider.MediaStore.MediaColumns.RELATIVE_PATH, rel);
            Uri u = getContentResolver().insert(
                    android.provider.MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (u == null) return "ERR MediaStore 插入失败";
            java.io.OutputStream os = getContentResolver().openOutputStream(u);
            if (os == null) return "ERR 打不开输出流";
            os.write(data); os.flush(); os.close();
            diag("导出诊断 → Download/Ever-log/ever-diag.log（" + off + "B）");
            return "Download/Ever-log/ever-diag.log";
        } catch (Throwable t) {
            return "ERR " + t.getClass().getSimpleName() + " " + t.getMessage();
        }
    }

    /* 素材打包时统一压过（png 后缀里可能是 webp/jpeg），所以按文件头判断类型 */
    private static String mimeOf(String path, byte[] head, int n) {
        String p = path.toLowerCase();
        if (n >= 12 && head[0] == (byte)0x52 && head[1] == (byte)0x49 && head[8] == (byte)0x57) return "image/webp";
        if (n >= 3 && head[0] == (byte)0xFF && head[1] == (byte)0xD8) return "image/jpeg";
        if (n >= 8 && head[0] == (byte)0x89 && head[1] == 0x50) return "image/png";
        if (n >= 4 && head[0] == 0x47 && head[1] == 0x49) return "image/gif";
        if (p.endsWith(".html") || p.endsWith(".htm")) return "text/html";
        if (p.endsWith(".js")) return "application/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".json")) return "application/json";
        if (p.endsWith(".png") || p.endsWith(".jpg") || p.endsWith(".jpeg") || p.endsWith(".webp")) return "image/png";
        if (p.endsWith(".mp3")) return "audio/mpeg";
        if (p.endsWith(".m4a")) return "audio/mp4";
        if (p.endsWith(".wav")) return "audio/wav";
        if (p.endsWith(".svg")) return "image/svg+xml";
        if (p.endsWith(".ttf")) return "font/ttf";
        if (p.endsWith(".otf")) return "font/otf";
        if (p.endsWith(".woff2")) return "font/woff2";
        return "application/octet-stream";
    }

    @Override public boolean onKeyDown(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_BACK && web != null && web.canGoBack()) {
            web.goBack(); return true;
        }
        return super.onKeyDown(code, e);
    }
    @Override protected void onDestroy() {
        try { EverWatchService.setWebView(null); } catch (Throwable t) {}
        INSTANCE = null;
        if (web != null) { web.destroy(); web = null; }
        super.onDestroy();
    }
}
