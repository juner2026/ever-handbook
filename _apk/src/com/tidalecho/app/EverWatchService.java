package com.tidalecho.app;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapShader;
import android.graphics.Canvas;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.graphics.LinearGradient;
import android.graphics.Matrix;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.RadialGradient;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebView;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.lang.ref.WeakReference;
import java.nio.ByteBuffer;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/* ============================================================================
   Ever · 陪你看屏幕（系统级共享屏幕）
   ----------------------------------------------------------------------------
   做两件事：
     ① 抓屏：MediaProjection + ImageReader，每 2 秒抽一帧整屏（所以任何 App 都算），
        缩到长边 ≤ 720、JPEG q0.5、base64 之后塞回 WebView 的 window._everWatchFrame()。
     ② 浮动三件套（三块各自一个 overlay 窗口：合在一个窗口里会把整块透明矩形
        的触摸一起吃掉，下面的列表就滑不动了）：
          画面预览小窗（约 132×74dp） ← 当前抓到的这一帧的缩略图，点一下折叠成小圆点
          回复气泡（纸色）            ← 模型的一句话，2.8 秒淡出，在头像正上方
          AI 头像（圆 48dp）          ← 该 AI 自己的头像（页面推 dataURL），点一下暂停
        三块作为一个整体拖动（>8dp 才算拖），位置存 SharedPreferences；
        长按头像 800ms = 直接停止并收起。

   为什么模型请求不在这里做：这个 App 的接口配置（base/key/model/预设）全在页面
   localStorage 里，原生再读一遍只会读成两套、越用越分叉。所以原生只负责"看见"，
   "说话"交给页面里的 JS（它本来就有 apiEff / apiUrl 那一套）。这里只把
   configure() 推过来的 {base,key,model,style,name} 存着，万一以后要原生回退也不用改协议。

   踩过的坑（都是 Android 14+ 的硬规定，写在这里免得下个人再踩）：
     · Android 14+：必须先 startForeground(…, FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)
       再 getMediaProjection()，顺序反了直接 SecurityException；
       清单里也必须有 FOREGROUND_SERVICE_MEDIA_PROJECTION 权限 + service
       android:foregroundServiceType="mediaProjection"。
     · 悬浮窗要 SYSTEM_ALERT_WINDOW（用户在设置里单独给），TYPE_APPLICATION_OVERLAY
       在 API 26+ 才合法，低版本退回 TYPE_PHONE。
     · 通知必须有 channel（Android 8+），且停止按钮要走 PendingIntent.getService。
     · 抓帧背压：上一帧 JS 还在飞就跳过这一拍（JS 处理完会调 frameDone()）。
       没有背压的话 2 秒一帧会把 WebView 的 JS 队列堆爆（尤其弱网时请求很慢）。
     · ImageReader 的 buffer 有 rowPadding（像素对齐补的字节），直接
       copyPixelsFromBuffer 到 w×h 的 Bitmap 会花屏 —— 必须按 rowStride 算宽度再裁。
     · 透明 overlay 窗口的整个矩形都会吃掉触摸：所以三块分成三个窗口，
       气泡窗口加 FLAG_NOT_TOUCHABLE，才不会挡住下面的列表滚动。
     · 窗口里画阴影要留白：预览窗外面套一圈 4dp 透明 padding，elevation 阴影才画得开。

   停止路径有五条：JS 的 stopWatch() / 通知里的「停止」/ 长按头像 /
   MediaProjection 被系统回收（onStop 回调）/ 服务销毁。都收敛到 shutdown()，
   全部 try/catch。
   ============================================================================ */
public class EverWatchService extends Service {

    public static final String ACTION_START = "com.tidalecho.app.WATCH_START";
    public static final String ACTION_STOP  = "com.tidalecho.app.WATCH_STOP";
    public static final String EXTRA_DATA   = "capture_data";   /* MediaProjection 授权 Intent */
    public static final String EXTRA_CFG    = "cfg_json";       /* {base,key,model,style,name} */

    /* 通知 */
    private static final String CH_ID   = "ever_watch";
    private static final int    NOTI_ID = 0x7E0A;     /* 固定 id：重复启动只更新同一条 */
    private static final int    STOP_REQ = 0x7E0B;

    private static final long TICK_MS      = 2000;    /* 每 2 秒抽一帧 */
    private static final long JS_GIVEUP_MS = 35000;   /* JS 35 秒没 frameDone 就当它卡死，放行下一帧（陪看单请求 30 秒超时） */
    private static final int  MAX_EDGE     = 720;     /* 长边上限：再大一帧 base64 就几 MB 了 */

    /* ---- 悬浮层的尺寸（dp）；位置计算在 metrics()/applyGroupPositions() 里 ---- */
    private static final float AVATAR_DP    = 48f;    /* 头像直径 */
    private static final float PREVIEW_W_DP = 132f;   /* 预览小窗宽 */
    private static final float PREVIEW_H_DP = 74f;    /* 预览小窗高 */
    private static final float PAD_DP       = 4f;     /* 阴影留白：窗口比内容大一圈 */
    private static final float GAP_DP       = 6f;     /* 块与块之间的缝 */
    private static final float SLOT_DP      = 54f;    /* 气泡预留位（约两行）；更长时预览自动上移 */
    private static final float DOT_DP       = 20f;    /* 折叠后的圆点直径 */
    private static final long  BUBBLE_MS    = 2800;   /* 气泡停留时间（任务书：2.8s） */
    private static final long  LONGSTOP_MS  = 800;    /* 长按头像多久算"要停止" */

    /* 页面侧（JS）用得到的静态状态 */
    public static volatile boolean running = false;
    public static volatile boolean paused  = false;
    public static volatile String  style   = "danmu";  /* danmu = 弹幕式；quiet = 安静 */
    public static volatile String  cfgBase = "", cfgKey = "", cfgModel = "";
    /* 页面推上来的当前 AI 头像 + 名字（服务还没起来时先存着，起来直接用） */
    public static volatile Bitmap  avatarBmp = null;
    public static volatile String  aiName    = "AI";

    /* 当前活着的 Service（showReply / frameDone 这些静态方法要用到） */
    private static volatile EverWatchService INSTANCE;
    /* WebView 用弱引用：Activity 被回收时不能把这个 Service 拖死 */
    private static WeakReference<WebView> webRef = new WeakReference<WebView>(null);

    private MediaProjection projection;
    private ImageReader reader;
    private VirtualDisplay vd;
    private ScheduledExecutorService timer;
    private Handler main = new Handler(Looper.getMainLooper());

    private WindowManager wm;
    /* ---- 三块悬浮层 ---- */
    private View avatarView;                 /* 头像（自绘：阴影/圆图/白描边/兜底首字） */
    private FrameLayout previewHost;         /* 预览窗口的根（含 4dp 阴影留白） */
    private FrameLayout previewRoot;         /* 预览内容（圆角、描边、裁剪） */
    private ImageView previewImg;            /* 这一帧的缩略图 */
    private View previewScrim;               /* 暂停时盖灰 */
    private TextView previewLive;            /* 右下角「正在看」 */
    private TextView previewPaused;          /* 中间「已暂停」 */
    private TextView bubble;                 /* 回复气泡 */
    private WindowManager.LayoutParams avatarLp, previewLp, bubbleLp;
    private boolean avatarAttached = false;
    private boolean previewAttached = false;
    private boolean bubbleAttached = false;
    private volatile boolean collapsed = false;
    private volatile boolean anchorReady = false;
    private int previewShift = 0;            /* 三行气泡时预览临时上移的像素 */
    private Bitmap previewBmp = null;        /* 当前预览缩略图（换下来的延迟回收） */
    private Runnable bubbleHide;
    private boolean overlayWarned = false;   /* 「悬浮层没画出来」只提醒一次 */

    /* 尺寸（px），metrics() 里按屏幕密度算 */
    private int avatarPx = 132, previewW = 363, previewH = 203, pad = 11;
    private int gap = 16, slot = 148, dotPx = 55;
    private int ax = 0, ay = 0;              /* 组锚点 = 头像窗口左上角 */
    private int screenW = 1080, screenH = 1920;
    private int prefsX = -1, prefsY = -1;

    private volatile boolean jsBusy = false;
    private volatile long jsBusySince = 0;

    /* ------------------------------------------------------------------ 静态入口 */

    /** MainActivity 建好 WebView 之后调一次；页面销毁时传 null。 */
    public static void setWebView(WebView w) {
        webRef = new WeakReference<WebView>(w);
    }
    private static WebView web() {
        try { return webRef.get(); } catch (Throwable t) { return null; }
    }

    /** 启动抓屏。data = createScreenCaptureIntent() 的授权结果。 */
    public static void start(Context c, Intent data, String cfgJson) {
        try {
            Intent i = new Intent(c, EverWatchService.class);
            i.setAction(ACTION_START);
            i.putExtra(EXTRA_DATA, data);
            i.putExtra(EXTRA_CFG, cfgJson == null ? "" : cfgJson);
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "watch start failed: " + t);
        }
    }

    /** 停止：JS 的 stopWatch() / 通知按钮 / 长按头像都走这里。 */
    public static void stop(Context c) {
        try { c.stopService(new Intent(c, EverWatchService.class)); } catch (Throwable t) {}
        EverWatchService s = INSTANCE;
        if (s != null) {
            final EverWatchService fs = s;
            s.main.post(new Runnable() { public void run() { try { fs.shutdown(); } catch (Throwable t) {} } });
        }
        running = false; paused = false;
    }

    /** JS 处理完一帧（成功或失败都要调，否则背压会把抓帧卡死）。 */
    public static void frameDone() {
        EverWatchService s = INSTANCE;
        if (s != null) { s.jsBusy = false; s.jsBusySince = 0; }
    }

    /** 把一句回复显示到悬浮气泡上（头像正上方，自动 2.8s 淡出）。 */
    public static void showReply(String text) {
        final EverWatchService s = INSTANCE;
        if (s == null || text == null) return;
        final String t = text;
        s.main.post(new Runnable() { public void run() { try { s.showBubble(t); } catch (Throwable e) {} } });
    }

    /**
     * 页面推过来的**当前 AI 头像**（data URL，如 data:image/jpeg;base64,…）。
     * 传空串 = 没有头像，原生用粉渐变圆 + 名字首字兜底。
     * 存成静态：服务可能还没起来，等悬浮层创建时再直接拿来用。
     */
    public static void setAvatar(String dataUrl) {
        try {
            if (dataUrl == null) return;
            String s = dataUrl.trim();
            int comma = s.indexOf(',');
            if (s.length() < 32 || comma < 0) {
                avatarBmp = null;
            } else {
                if (s.startsWith("data:")) s = s.substring(comma + 1);
                byte[] raw = Base64.decode(s, Base64.DEFAULT);
                if (raw == null || raw.length < 64) return;
                Bitmap b = android.graphics.BitmapFactory.decodeByteArray(raw, 0, raw.length);
                if (b == null) return;
                /* 兜底：页面要是推来一张特别大的图，先缩到 256 以内再存（悬浮层只画 48dp） */
                int mw = b.getWidth(), mh = b.getHeight();
                int mm = Math.max(mw, mh);
                if (mm > 256) {
                    float k = 256f / (float) mm;
                    Bitmap nb = Bitmap.createScaledBitmap(b,
                            Math.max(1, Math.round(mw * k)), Math.max(1, Math.round(mh * k)), true);
                    if (nb != null && nb != b) {
                        try { b.recycle(); } catch (Throwable t) {}
                        b = nb;
                    }
                }
                avatarBmp = b;
            }
            final EverWatchService inst = INSTANCE;
            if (inst != null) {
                inst.main.post(new Runnable() {
                    @Override public void run() { try { inst.refreshAvatar(); } catch (Throwable t) {} }
                });
            }
        } catch (Throwable t) {
            android.util.Log.w("TidalEcho", "setAvatar failed: " + t);
        }
    }

    /** "danmu" / "quiet"：只影响提示词（提示词在 JS 里），这里存一份状态。 */
    public static void setStyle(String st) {
        if ("quiet".equals(st) || "danmu".equals(st)) style = st;
    }
    public static String getStyle() { return style; }

    /** 页面把 {base,key,model,style,name} 推过来（这版模型请求在 JS，留着是为了以后原生回退）。 */
    public static void configure(String json) {
        try {
            if (json == null || json.length() == 0) return;
            org.json.JSONObject o = new org.json.JSONObject(json);
            cfgBase  = o.optString("base",  cfgBase);
            cfgKey   = o.optString("key",   cfgKey);
            cfgModel = o.optString("model", cfgModel);
            String st = o.optString("style", style);
            if ("quiet".equals(st) || "danmu".equals(st)) style = st;
            /* 名字只用于头像拿不到时的首字兜底 */
            String nm = o.optString("name", "").trim();
            if (nm.length() > 0) aiName = nm;
        } catch (Throwable t) {
            android.util.Log.w("TidalEcho", "watch configure bad json: " + t);
        }
    }

    /** 悬浮窗权限（页面按钮靠它决定先跳设置还是直接开）。 */
    public static boolean hasOverlay(Context c) {
        try {
            if (Build.VERSION.SDK_INT < 23) return true;
            return android.provider.Settings.canDrawOverlays(c);
        } catch (Throwable t) { return false; }
    }

    public static boolean isRunning() { return running; }

    /** 通知栏「停止」按钮直接打到 Service 上（不依赖 Activity 还活着）。 */
    public static PendingIntent stopPendingIntent(Context c) {
        Intent i = new Intent(c, EverWatchService.class);
        i.setAction(ACTION_STOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        try {
            if (Build.VERSION.SDK_INT >= 26) return PendingIntent.getForegroundService(c, STOP_REQ, i, flags);
            return PendingIntent.getService(c, STOP_REQ, i, flags);
        } catch (Throwable t) { return null; }
    }

    /* ------------------------------------------------------------------ 生命周期 */

    @Override public android.os.IBinder onBind(Intent i) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        INSTANCE = this;
        try { wm = (WindowManager) getSystemService(WINDOW_SERVICE); } catch (Throwable t) {}
        try {
            SharedPreferences sp = getSharedPreferences("ever_watch", MODE_PRIVATE);
            prefsX = sp.getInt("ball_x", -1);
            prefsY = sp.getInt("ball_y", -1);
            collapsed = sp.getBoolean("preview_collapsed", false);
        } catch (Throwable t) {}
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String act = (intent == null) ? null : intent.getAction();
        if (ACTION_STOP.equals(act)) {
            try { shutdown(); } catch (Throwable t) {}
            return START_NOT_STICKY;
        }
        if (intent != null) {
            configure(intent.getStringExtra(EXTRA_CFG));
            Intent data = null;
            try { data = (Intent) intent.getParcelableExtra(EXTRA_DATA); } catch (Throwable t) {}
            if (running) {
                /* 已经在跑：只更新文案，不重复建虚拟屏（重复建会黑屏/双悬浮层） */
                refreshNotification();
                return START_NOT_STICKY;
            }
            if (data != null) beginCapture(data);
        }
        return START_NOT_STICKY;
    }

    @Override public void onDestroy() {
        try { shutdown(); } catch (Throwable t) {}
        INSTANCE = null;
        super.onDestroy();
    }

    /** 转屏：屏幕尺寸变了，把三块按新尺寸重新夹回屏内（否则会有一半落到屏幕外）。 */
    @Override public void onConfigurationChanged(android.content.res.Configuration cfg) {
        super.onConfigurationChanged(cfg);
        try {
            WindowManager wmi = (WindowManager) getSystemService(WINDOW_SERVICE);
            DisplayMetrics dm = new DisplayMetrics();
            wmi.getDefaultDisplay().getRealMetrics(dm);
            if (dm.widthPixels > 0 && dm.heightPixels > 0) {
                screenW = dm.widthPixels;
                screenH = dm.heightPixels;
            }
            main.post(new Runnable() {
                @Override public void run() {
                    try {
                        metrics();
                        ax = clamp(ax, minAx(), maxAx());
                        ay = clamp(ay, minAy(), maxAy());
                        applyGroupPositions();
                    } catch (Throwable t) {}
                }
            });
        } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 抓屏 */

    private void beginCapture(Intent data) {
        /* ① 先当前台服务（Android 14+ 顺序不能反，反了就 SecurityException） */
        goForeground();
        /* ② 再要 MediaProjection */
        try {
            MediaProjectionManager mpm =
                (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
            projection = mpm.getMediaProjection(Activity.RESULT_OK, data);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "getMediaProjection failed: " + t);
            projection = null;
        }
        if (projection == null) {
            toast("没拿到录屏授权，陪看没开起来");
            try { shutdown(); } catch (Throwable t) {}
            return;
        }
        try {
            projection.registerCallback(new MediaProjection.Callback() {
                @Override public void onStop() {
                    /* 系统回收了录屏（用户从通知/状态栏点了停止）→ 老老实实收摊 */
                    main.post(new Runnable() { public void run() { try { shutdown(); } catch (Throwable t) {} } });
                }
            }, main);
        } catch (Throwable t) {}

        /* ③ 屏幕尺寸 + ImageReader + VirtualDisplay */
        int dpi = 320;
        try {
            WindowManager wmi = (WindowManager) getSystemService(WINDOW_SERVICE);
            DisplayMetrics dm = new DisplayMetrics();
            wmi.getDefaultDisplay().getRealMetrics(dm);
            if (dm.widthPixels > 0 && dm.heightPixels > 0) {
                screenW = dm.widthPixels;
                screenH = dm.heightPixels;
                dpi = dm.densityDpi > 0 ? dm.densityDpi : 320;
            }
        } catch (Throwable t) {}
        try {
            reader = ImageReader.newInstance(screenW, screenH, PixelFormat.RGBA_8888, 2);
            vd = projection.createVirtualDisplay("ever_watch",
                    screenW, screenH, dpi,
                    DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                    reader.getSurface(), null, main);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "createVirtualDisplay failed: " + t);
            toast("这版系统不让我抓屏");
            try { shutdown(); } catch (Throwable t2) {}
            return;
        }

        main.post(new Runnable() { public void run() { try { attachGroup(); } catch (Throwable t) {} } });

        running = true;
        paused = false;
        jsBusy = false;
        startTicker();
        refreshNotification();
        evalJs("try{if(window.__everWatchStarted)window.__everWatchStarted();}catch(e){}");
    }

    private void startTicker() {
        stopTicker();
        try {
            timer = Executors.newSingleThreadScheduledExecutor();
            timer.scheduleWithFixedDelay(new Runnable() {
                @Override public void run() { try { tick(); } catch (Throwable t) {} }
            }, 900, TICK_MS, TimeUnit.MILLISECONDS);
        } catch (Throwable t) {}
    }

    private void stopTicker() {
        try { if (timer != null) timer.shutdownNow(); } catch (Throwable t) {}
        timer = null;
    }

    /** 一拍：抽帧 → 缩 → 压 JPEG → base64 → 丢给 JS；顺手把缩略图塞进预览小窗。 */
    private void tick() {
        if (!running || paused) return;
        if (reader == null) return;
        /* 背压：上一帧 JS 还在飞就跳过这一拍 */
        if (jsBusy && (SystemClock.uptimeMillis() - jsBusySince) < JS_GIVEUP_MS) return;
        jsBusy = false;

        Image img = null;
        Bitmap raw = null, src = null, out = null;
        try {
            img = reader.acquireLatestImage();
        } catch (Throwable t) { img = null; }
        if (img == null) return;
        try {
            Image.Plane[] planes = img.getPlanes();
            if (planes == null || planes.length == 0) return;
            ByteBuffer buf = planes[0].getBuffer();
            int pixelStride = planes[0].getPixelStride();
            int rowStride   = planes[0].getRowStride();
            int w = img.getWidth(), h = img.getHeight();
            if (w <= 0 || h <= 0) return;
            int rowPad = rowStride - pixelStride * w;
            int paddedW = w + (pixelStride > 0 ? rowPad / pixelStride : 0);
            buf.rewind();
            raw = Bitmap.createBitmap(paddedW, h, Bitmap.Config.ARGB_8888);
            raw.copyPixelsFromBuffer(buf);
            if (rowPad == 0 && paddedW == w) {
                src = raw;
            } else {
                src = Bitmap.createBitmap(raw, 0, 0, w, h);
            }
            int maxSide = Math.max(w, h);
            if (maxSide > MAX_EDGE) {
                float k = (float) MAX_EDGE / (float) maxSide;
                int nw = Math.max(1, Math.round(w * k));
                int nh = Math.max(1, Math.round(h * k));
                out = Bitmap.createScaledBitmap(src, nw, nh, true);
            } else {
                out = src;
            }
            /* ★ 预览小窗：直接拿这张已经缩过的帧再缩一次，不给抓帧链路加负担 */
            updatePreview(out);
            ByteArrayOutputStream bo = new ByteArrayOutputStream(64 * 1024);
            out.compress(Bitmap.CompressFormat.JPEG, 50, bo);
            byte[] jpg = bo.toByteArray();
            try { bo.close(); } catch (Throwable t) {}
            if (jpg == null || jpg.length < 64) return;
            String b64 = Base64.encodeToString(jpg, Base64.NO_WRAP);
            deliver(b64);
        } catch (Throwable t) {
            android.util.Log.w("TidalEcho", "tick encode failed: " + t);
        } finally {
            try { if (img != null) img.close(); } catch (Throwable t) {}
            /* 三种情况：out 只可能是 缩放图 / src；src 只可能是 raw / 裁掉补边的图。 */
            try { if (out != null && out != src) out.recycle(); } catch (Throwable t) {}
            try { if (src != null && src != out) src.recycle(); } catch (Throwable t) {}
            try { if (raw != null) raw.recycle(); } catch (Throwable t) {}
        }
    }

    /** 把一帧 base64 丢进 WebView 的 JS。base64 只有 A-Za-z0-9+/=，拼进单引号里是安全的。 */
    private void deliver(final String b64) {
        final WebView w = web();
        if (w == null) return;                      /* 页面没了就丢帧，别攒 */
        jsBusy = true;
        jsBusySince = SystemClock.uptimeMillis();
        try {
            w.post(new Runnable() {
                @Override public void run() {
                    try {
                        w.evaluateJavascript(
                            "try{window._everWatchFrame&&window._everWatchFrame('" + b64 + "');}catch(e){}",
                            null);
                    } catch (Throwable t) {
                        jsBusy = false;
                    }
                }
            });
        } catch (Throwable t) {
            jsBusy = false;
        }
    }

    /* ------------------------------------------------------------------ 前台通知 */

    private Notification buildNotification() {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager nm =
                (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            try {
                if (nm != null && nm.getNotificationChannel(CH_ID) == null) {
                    NotificationChannel ch = new NotificationChannel(
                        CH_ID, "陪你看屏幕", NotificationManager.IMPORTANCE_LOW);
                    ch.setDescription("共享屏幕时显示的预览小窗、AI 头像和一句话气泡");
                    ch.setShowBadge(false);
                    nm.createNotificationChannel(ch);
                }
            } catch (Throwable t) {}
            b = new Notification.Builder(this, CH_ID);
        } else {
            b = new Notification.Builder(this);
        }
        b.setSmallIcon(android.R.drawable.ic_menu_camera)
         .setContentTitle("Ever 正在陪你看屏幕")
         .setContentText(paused
             ? "已暂停 · 点头像继续"
             : "点头像暂停／继续 · 点小窗折叠 · 长按头像停止")
         .setOngoing(true)
         .setOnlyAlertOnce(true)
         .setShowWhen(false);
        PendingIntent pi = stopPendingIntent(this);
        if (pi != null) {
            try { b.addAction(android.R.drawable.ic_menu_close_clear_cancel, "停止", pi); } catch (Throwable t) {}
        }
        return b.build();
    }

    private void goForeground() {
        Notification n = buildNotification();
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTI_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
            } else {
                startForeground(NOTI_ID, n);
            }
        } catch (Throwable t) {
            android.util.Log.w("TidalEcho", "startForeground(type) failed: " + t);
            try { startForeground(NOTI_ID, n); } catch (Throwable t2) {}
        }
    }

    private void refreshNotification() {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null && running) nm.notify(NOTI_ID, buildNotification());
        } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 悬浮层小工具 */

    private int dp(float v) {
        try { return Math.round(v * getResources().getDisplayMetrics().density); }
        catch (Throwable t) { return Math.round(v * 2.75f); }
    }

    private static int clamp(int v, int lo, int hi) {
        if (hi < lo) return lo;
        return v < lo ? lo : (v > hi ? hi : v);
    }

    private static boolean overlayTypeOk() { return Build.VERSION.SDK_INT >= 26; }

    private WindowManager.LayoutParams baseLp(int w, int h) {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams();
        lp.type = overlayTypeOk()
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        lp.format = PixelFormat.TRANSLUCENT;
        lp.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                 | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN;
        lp.gravity = Gravity.TOP | Gravity.START;
        lp.width = w;
        lp.height = h;
        return lp;
    }

    private void metrics() {
        avatarPx = dp(AVATAR_DP);
        previewW = dp(PREVIEW_W_DP);
        previewH = dp(PREVIEW_H_DP);
        pad      = dp(PAD_DP);
        gap      = dp(GAP_DP);
        slot     = dp(SLOT_DP);
        dotPx    = dp(DOT_DP);
        if (avatarPx < 24) avatarPx = 24;
        if (previewW < 80) previewW = 80;
        if (previewH < 40) previewH = 40;
        if (pad < 1) pad = 1;
    }

    /* ---- 组内几何（全部用窗口/内容坐标推，别散着改）---- */
    private int groupTopRel() { return 2 * gap + slot + previewH; }  /* 头像窗口顶 → 预览窗口顶 */
    private int circleTop()   { return ay + pad; }                    /* 头像圆的上沿 */
    private int avCx()        { return ax + pad + avatarPx / 2; }     /* 头像圆心 x */
    private int minAx()       { return Math.max(0, previewW / 2 - avatarPx / 2); }
    private int maxAx()       {
        return Math.max(minAx(), screenW - avatarPx / 2 - previewW / 2 - 2 * pad);
    }
    private int minAy()       { return groupTopRel(); }
    private int maxAy()       { return Math.max(minAy(), screenH - avatarPx - 2 * pad); }

    /* ------------------------------------------------------------------ 悬浮层创建 */

    private void attachGroup() {
        if (wm == null) return;
        metrics();
        if (!anchorReady) {
            ax = clamp(prefsX >= 0 ? prefsX : maxAx(), minAx(), maxAx());
            ay = clamp(prefsY >= 0 ? prefsY : dp(320), minAy(), maxAy());
            anchorReady = true;
        } else {
            ax = clamp(ax, minAx(), maxAx());
            ay = clamp(ay, minAy(), maxAy());
        }
        /* 已经挂好了就别每次回话都重画一遍（showBubble 会频繁调进来） */
        if (avatarAttached && previewAttached) return;
        if (avatarView == null) createAvatar();
        if (previewHost == null) createPreview();
        applyCollapsedVisual(false);
        applyGroupPositions();
        applyPausedVisual();
        if (avatarView != null && !avatarAttached) {
            avatarLp = (avatarLp == null) ? baseLp(avatarPx + 2 * pad, avatarPx + 2 * pad) : avatarLp;
            try { wm.addView(avatarView, avatarLp); avatarAttached = true; }
            catch (Throwable t) {
                avatarAttached = false;
                android.util.Log.e("TidalEcho", "add avatar failed: " + t);
                warnOverlayOnce();
            }
        }
        if (previewHost != null && !previewAttached) {
            previewLp = (previewLp == null) ? baseLp(previewW + 2 * pad, previewH + 2 * pad) : previewLp;
            try { wm.addView(previewHost, previewLp); previewAttached = true; }
            catch (Throwable t) {
                previewAttached = false;
                android.util.Log.e("TidalEcho", "add preview failed: " + t);
                warnOverlayOnce();
            }
        }
        applyGroupPositions();
    }

    /** 加不上悬浮窗只提醒一次（每 2 秒回一次话就别每回都弹 Toast） */
    private void warnOverlayOnce() {
        if (overlayWarned) return;
        overlayWarned = true;
        toast("悬浮层没能显示（检查『显示在其他应用上层』权限）");
    }

    private void createAvatar() {
        try {
            avatarView = new AvatarView(this);
            avatarLp = baseLp(avatarPx + 2 * pad, avatarPx + 2 * pad);
            avatarView.setContentDescription("Ever 陪你看屏幕：点一下暂停或继续，长按停止，拖动可以换位置");
            avatarView.setOnTouchListener(new GroupTouch(true));
        } catch (Throwable t) {
            avatarView = null;
            android.util.Log.e("TidalEcho", "createAvatar failed: " + t);
        }
    }

    private void createPreview() {
        try {
            previewHost = new FrameLayout(this);
            previewHost.setClipChildren(false);
            previewHost.setClipToPadding(false);

            previewRoot = new FrameLayout(this);
            previewRoot.setBackground(previewBg());
            try { previewRoot.setClipToOutline(true); } catch (Throwable t) {}
            try { if (Build.VERSION.SDK_INT >= 21) previewRoot.setElevation(dp(3)); } catch (Throwable t) {}

            previewImg = new ImageView(this);
            previewImg.setScaleType(ImageView.ScaleType.FIT_CENTER);
            previewRoot.addView(previewImg, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

            previewScrim = new View(this);
            previewScrim.setBackgroundColor(0x66000000);
            previewScrim.setVisibility(View.GONE);
            previewRoot.addView(previewScrim, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

            previewPaused = new TextView(this);
            previewPaused.setText("已暂停");
            previewPaused.setTextColor(0xFFFFFFFF);
            previewPaused.setTextSize(10f);
            previewPaused.setTypeface(Typeface.DEFAULT_BOLD);
            previewPaused.setGravity(Gravity.CENTER);
            previewPaused.setPadding(dp(7), dp(2), dp(7), dp(2));
            previewPaused.setBackground(pill(0x8C000000, 6));
            previewPaused.setVisibility(View.GONE);
            previewRoot.addView(previewPaused, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.CENTER));

            previewLive = new TextView(this);
            previewLive.setText("正在看");
            previewLive.setTextColor(0xF2FFFFFF);
            previewLive.setTextSize(8f);
            previewLive.setPadding(dp(4), dp(1), dp(4), dp(1));
            previewLive.setBackground(pill(0x8C000000, 4));
            FrameLayout.LayoutParams llp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                    Gravity.BOTTOM | Gravity.END);
            llp.setMargins(0, 0, dp(4), dp(4));
            previewRoot.addView(previewLive, llp);

            previewHost.addView(previewRoot, new FrameLayout.LayoutParams(
                    previewW, previewH, Gravity.CENTER));
            previewLp = baseLp(previewW + 2 * pad, previewH + 2 * pad);
            previewHost.setOnTouchListener(new GroupTouch(false));
        } catch (Throwable t) {
            previewHost = null;
            previewRoot = null;
            previewImg = null;
            android.util.Log.e("TidalEcho", "createPreview failed: " + t);
        }
    }

    private GradientDrawable previewBg() {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        g.setCornerRadius(dp(8));
        g.setColor(0xE62A2320);                 /* 暖深底：缩略图留边时也不刺眼 */
        g.setStroke(dp(1), 0x99FFFFFF);         /* 1dp 半透明白描边 */
        return g;
    }

    private GradientDrawable dotBg() {
        GradientDrawable g = new GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                new int[]{0xFFF9A8C9, 0xFFE0638F});
        g.setShape(GradientDrawable.OVAL);
        g.setStroke(dp(1.2f), 0xD9FFFFFF);
        return g;
    }

    private GradientDrawable pill(int color, float radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.RECTANGLE);
        g.setCornerRadius(dp(radiusDp));
        g.setColor(color);
        return g;
    }

    /* ------------------------------------------------------------------ 位置 */

    private void applyGroupPositions() {
        if (avatarLp != null) { avatarLp.x = ax; avatarLp.y = ay; }
        positionPreview();
        if (bubbleAttached) placeBubbleNow();
        if (avatarAttached && avatarView != null && avatarLp != null) {
            try { wm.updateViewLayout(avatarView, avatarLp); } catch (Throwable t) {}
        }
    }

    private void positionPreview() {
        if (previewLp == null || previewRoot == null) return;
        int pw = collapsed ? dotPx : previewW;
        int ph = collapsed ? dotPx : previewH;
        previewLp.width = pw + 2 * pad;
        previewLp.height = ph + 2 * pad;
        int cx = avCx();
        previewLp.x = clamp(cx - (pw + 2 * pad) / 2, 0, Math.max(0, screenW - (pw + 2 * pad)));
        int top;
        if (collapsed) {
            /* 折叠后的小圆点落在原本预览小窗的中心，展开时位置不跳 */
            int contentCenterY = (ay - groupTopRel() - previewShift) + pad + previewH / 2;
            top = contentCenterY - (ph + 2 * pad) / 2;
        } else {
            top = ay - groupTopRel() - previewShift;
        }
        previewLp.y = clamp(top, 0, Math.max(0, screenH - (ph + 2 * pad)));
        try {
            FrameLayout.LayoutParams rlp = (FrameLayout.LayoutParams) previewRoot.getLayoutParams();
            if (rlp != null && (rlp.width != pw || rlp.height != ph)) {
                rlp.width = pw;
                rlp.height = ph;
                previewRoot.setLayoutParams(rlp);
            }
        } catch (Throwable t) {}
        if (previewAttached && previewHost != null) {
            try { wm.updateViewLayout(previewHost, previewLp); } catch (Throwable t) {}
        }
    }

    private void placeBubbleNow() {
        if (!bubbleAttached || bubble == null || bubbleLp == null) return;
        int bw = bubble.getWidth(), bh = bubble.getHeight();
        if (bw <= 0 || bh <= 0) return;
        bubbleLp.x = clamp(avCx() - bw / 2, dp(4), Math.max(dp(4), screenW - bw - dp(4)));
        int by = circleTop() - gap - bh;
        if (by < dp(4)) by = dp(4);
        bubbleLp.y = by;
        try { wm.updateViewLayout(bubble, bubbleLp); } catch (Throwable t) {}
        /* 三行气泡比预留位高：只把预览往上让一点，别压字 */
        int shift = Math.max(0, bh - slot);
        if (shift != previewShift) {
            previewShift = shift;
            positionPreview();
        }
    }

    private void requestPlaceBubble() { requestPlaceBubble(0); }

    private void requestPlaceBubble(final int attempt) {
        if (!bubbleAttached || bubble == null) return;
        if (bubble.getWidth() <= 0 || bubble.getHeight() <= 0) {
            if (attempt < 5) {
                main.postDelayed(new Runnable() {
                    @Override public void run() { try { requestPlaceBubble(attempt + 1); } catch (Throwable t) {} }
                }, 32);
            }
            return;
        }
        placeBubbleNow();
    }

    /* ------------------------------------------------------------------ 预览小窗内容 */

    /** 每抓一帧调一次（抓帧线程）：缩成预览尺寸再丢主线程，旧图延迟回收。 */
    private void updatePreview(Bitmap frame) {
        if (frame == null || paused || collapsed) return;
        if (!previewAttached || previewImg == null) return;
        try {
            int cw = previewW, ch = previewH;
            if (cw <= 0 || ch <= 0) return;
            float k = Math.min((float) cw / frame.getWidth(), (float) ch / frame.getHeight());
            int tw = Math.max(1, Math.round(frame.getWidth() * k));
            int th = Math.max(1, Math.round(frame.getHeight() * k));
            final Bitmap thumb = Bitmap.createScaledBitmap(frame, tw, th, true);
            main.post(new Runnable() {
                @Override public void run() {
                    try {
                        if (!previewAttached || previewImg == null) { thumb.recycle(); return; }
                        final Bitmap old = previewBmp;
                        previewBmp = thumb;
                        previewImg.setImageBitmap(thumb);
                        if (old != null && old != thumb) {
                            main.postDelayed(new Runnable() {
                                @Override public void run() { try { old.recycle(); } catch (Throwable t) {} }
                            }, 2000);
                        }
                    } catch (Throwable t) {}
                }
            });
        } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 头像 / 暂停 / 折叠 */

    private void refreshAvatar() {
        try { if (avatarView != null) avatarView.invalidate(); } catch (Throwable t) {}
    }

    private void togglePaused() {
        paused = !paused;
        if (!paused) jsBusy = false;
        /* ★ 告诉页面：暂停时把在飞的请求中断、清掉忙标记和退避 ——
           不然「暂停一会儿再继续」会卡在上一帧的 30 秒超时/退避里，看着就是半天不回 */
        try {
            evalJs(paused
                ? "try{window.__everWatchPaused&&window.__everWatchPaused();}catch(e){}"
                : "try{window.__everWatchResumed&&window.__everWatchResumed();}catch(e){}");
        } catch (Throwable t) {}
        applyPausedVisual();
        refreshNotification();
        toast(paused ? "陪看已暂停" : "继续陪你看");
    }

    private void applyPausedVisual() {
        try {
            if (previewImg != null) previewImg.setColorFilter(paused ? greyFilter() : null);
            if (previewScrim != null) previewScrim.setVisibility(paused ? View.VISIBLE : View.GONE);
            if (previewPaused != null) previewPaused.setVisibility(paused ? View.VISIBLE : View.GONE);
            if (previewLive != null) previewLive.setVisibility((paused || collapsed) ? View.GONE : View.VISIBLE);
            if (avatarView != null) avatarView.setAlpha(paused ? 0.55f : 1f);
        } catch (Throwable t) {}
    }

    private ColorMatrixColorFilter greyFilter() {
        ColorMatrix cm = new ColorMatrix();
        cm.setSaturation(0f);
        ColorMatrix dim = new ColorMatrix();
        dim.setScale(0.72f, 0.72f, 0.72f, 1f);
        cm.postConcat(dim);
        return new ColorMatrixColorFilter(cm);
    }

    private void toggleCollapsed() {
        collapsed = !collapsed;
        try {
            SharedPreferences sp = getSharedPreferences("ever_watch", MODE_PRIVATE);
            sp.edit().putBoolean("preview_collapsed", collapsed).apply();
        } catch (Throwable t) {}
        applyCollapsedVisual(true);
        toast(collapsed ? "小窗折叠了 · 点小圆点展开" : "小窗展开了");
    }

    private void applyCollapsedVisual(boolean move) {
        try {
            if (previewRoot != null) {
                previewRoot.setBackground(collapsed ? dotBg() : previewBg());
                try { previewRoot.setClipToOutline(!collapsed); } catch (Throwable t) {}
            }
            if (previewImg != null) previewImg.setVisibility(collapsed ? View.GONE : View.VISIBLE);
            if (previewScrim != null) previewScrim.setVisibility((collapsed || !paused) ? View.GONE : View.VISIBLE);
            if (previewPaused != null) previewPaused.setVisibility((collapsed || !paused) ? View.GONE : View.VISIBLE);
            if (previewLive != null) previewLive.setVisibility((collapsed || paused) ? View.GONE : View.VISIBLE);
        } catch (Throwable t) {}
        if (move) applyGroupPositions();
    }

    /* ------------------------------------------------------------------ 拖动 / 点击 / 长按 */

    private class GroupTouch implements View.OnTouchListener {
        private final boolean isAvatar;
        private float downX, downY;
        private int startAx, startAy;
        private boolean dragging;
        private boolean longFired;
        private Runnable longR;

        GroupTouch(boolean avatar) { isAvatar = avatar; }

        private void cancelLong() {
            if (longR != null) {
                try { main.removeCallbacks(longR); } catch (Throwable t) {}
                longR = null;
            }
        }

        @Override public boolean onTouch(View v, MotionEvent e) {
            try {
                switch (e.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        downX = e.getRawX();
                        downY = e.getRawY();
                        startAx = ax;
                        startAy = ay;
                        dragging = false;
                        longFired = false;
                        if (isAvatar) {
                            cancelLong();
                            longR = new Runnable() {
                                @Override public void run() {
                                    longFired = true;
                                    try { toast("已停止陪看"); } catch (Throwable t) {}
                                    try { shutdown(); } catch (Throwable t) {}
                                }
                            };
                            main.postDelayed(longR, LONGSTOP_MS);
                        }
                        return true;

                    case MotionEvent.ACTION_MOVE: {
                        float dx = e.getRawX() - downX, dy = e.getRawY() - downY;
                        float thr = dp(8);
                        if (!dragging && (Math.abs(dx) > thr || Math.abs(dy) > thr)) {
                            dragging = true;
                            cancelLong();
                        }
                        if (dragging) {
                            ax = clamp(startAx + (int) dx, minAx(), maxAx());
                            ay = clamp(startAy + (int) dy, minAy(), maxAy());
                            applyGroupPositions();
                        }
                        return true;
                    }

                    case MotionEvent.ACTION_UP:
                    case MotionEvent.ACTION_CANCEL:
                        cancelLong();
                        if (!dragging && !longFired && e.getActionMasked() == MotionEvent.ACTION_UP) {
                            if (isAvatar) togglePaused();
                            else toggleCollapsed();
                        }
                        if (dragging && e.getActionMasked() == MotionEvent.ACTION_UP) saveAnchor();
                        dragging = false;
                        return true;
                }
            } catch (Throwable t) {}
            return false;
        }
    }

    private void saveAnchor() {
        try {
            SharedPreferences sp = getSharedPreferences("ever_watch", MODE_PRIVATE);
            sp.edit().putInt("ball_x", ax).putInt("ball_y", ay).apply();
        } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 回复气泡 */

    private void ensureBubbleView() {
        if (bubble != null) return;
        TextView tv = new TextView(this);
        tv.setTextColor(0xFF4A3B36);
        tv.setTextSize(13f);
        tv.setLineSpacing(dp(1), 1f);
        tv.setPadding(dp(12), dp(8), dp(12), dp(8));
        tv.setMaxWidth(Math.max(dp(120), Math.round(screenW * 0.68f)));
        tv.setMaxLines(3);
        tv.setSingleLine(false);
        tv.setEllipsize(android.text.TextUtils.TruncateAt.END);
        GradientDrawable bg = new GradientDrawable();
        bg.setShape(GradientDrawable.RECTANGLE);
        bg.setCornerRadius(dp(12));
        bg.setColor(0xF7FFFBF4);           /* 纸色，略透 */
        bg.setStroke(dp(1), 0x80E8C9B8);
        tv.setBackground(bg);
        tv.setAlpha(1f);
        bubble = tv;
    }

    private void showBubble(String text) {
        try {
            if (wm == null) return;
            attachGroup();
            ensureBubbleView();
            if (bubble == null) return;
            if (bubbleHide != null) {
                try { main.removeCallbacks(bubbleHide); } catch (Throwable t) {}
                bubbleHide = null;
            }
            try { bubble.animate().cancel(); } catch (Throwable t) {}
            bubble.setText(text == null ? "" : text);
            bubble.setAlpha(1f);
            if (!bubbleAttached) {
                bubbleLp = baseLp(WindowManager.LayoutParams.WRAP_CONTENT,
                                 WindowManager.LayoutParams.WRAP_CONTENT);
                bubbleLp.flags |= WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE;
                try {
                    wm.addView(bubble, bubbleLp);
                    bubbleAttached = true;
                } catch (Throwable t) {
                    bubbleAttached = false;
                    return;
                }
            }
            requestPlaceBubble();
            /* 文字变了会重新量高：落定后再对一次位，免得新气泡压住预览窗 */
            main.postDelayed(new Runnable() {
                @Override public void run() { try { requestPlaceBubble(); } catch (Throwable t) {} }
            }, 48);
            /* 2.8 秒后淡出并摘掉（复用同一个视图，不会叠） */
            bubbleHide = new Runnable() {
                @Override public void run() {
                    try {
                        if (bubble == null) return;
                        final TextView b = bubble;
                        b.animate().cancel();
                        b.animate().alpha(0f).setDuration(220)
                         .withEndAction(new Runnable() {
                             @Override public void run() {
                                 try {
                                     if (b != null && b == bubble && bubbleAttached) {
                                         wm.removeView(b);
                                         bubbleAttached = false;
                                     }
                                 } catch (Throwable t) {}
                                 previewShift = 0;
                                 try { positionPreview(); } catch (Throwable t) {}
                             }
                         }).start();
                    } catch (Throwable t) {}
                }
            };
            main.postDelayed(bubbleHide, BUBBLE_MS);
        } catch (Throwable t) {
            android.util.Log.w("TidalEcho", "showBubble failed: " + t);
        }
    }

    /* ------------------------------------------------------------------ 移除 */

    private void removeOverlays() {
        try { if (bubbleHide != null) main.removeCallbacks(bubbleHide); } catch (Throwable t) {}
        bubbleHide = null;
        try { if (bubble != null) bubble.animate().cancel(); } catch (Throwable t) {}
        try {
            if (bubble != null && bubbleAttached) wm.removeView(bubble);
        } catch (Throwable t) {}
        try {
            if (previewHost != null && previewAttached) wm.removeView(previewHost);
        } catch (Throwable t) {}
        try {
            if (avatarView != null && avatarAttached) wm.removeView(avatarView);
        } catch (Throwable t) {}
        try { if (previewImg != null) previewImg.setImageBitmap(null); } catch (Throwable t) {}
        bubbleAttached = false;
        previewAttached = false;
        avatarAttached = false;
        bubble = null;
        previewHost = null;
        previewRoot = null;
        previewImg = null;
        previewScrim = null;
        previewLive = null;
        previewPaused = null;
        avatarView = null;
        avatarLp = null;
        previewLp = null;
        bubbleLp = null;
        previewBmp = null;
        previewShift = 0;
        anchorReady = false;
    }

    /* ------------------------------------------------------------------ 停止 */

    private void shutdown() {
        /* 幂等：可能被 JS / 通知 / 长按 / onDestroy / projection.onStop 同时叫到 */
        running = false;
        paused = false;
        jsBusy = false;
        stopTicker();
        try { if (vd != null) vd.release(); } catch (Throwable t) {}
        vd = null;
        try { if (reader != null) reader.close(); } catch (Throwable t) {}
        reader = null;
        try { if (projection != null) projection.stop(); } catch (Throwable t) {}
        projection = null;
        try { removeOverlays(); } catch (Throwable t) {}
        try { stopForeground(true); } catch (Throwable t) {}
        try { NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE); if (nm != null) nm.cancel(NOTI_ID); } catch (Throwable t) {}
        evalJs("try{if(window.__everWatchStopped)window.__everWatchStopped();}catch(e){}");
        try { stopSelf(); } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 小工具 */

    private void toast(final String s) {
        main.post(new Runnable() {
            @Override public void run() {
                try { android.widget.Toast.makeText(EverWatchService.this, s, android.widget.Toast.LENGTH_SHORT).show(); }
                catch (Throwable t) {}
            }
        });
    }

    private void evalJs(String js) {
        WebView w = web();
        if (w == null) return;
        try { w.evaluateJavascript(js, null); } catch (Throwable t) {}
    }

    /* ------------------------------------------------------------------ 头像视图 */

    /**
     * AI 头像：圆形、白描边、轻阴影。图片是页面推过来的 dataURL（静态 avatarBmp），
     * 拿不到就用粉渐变圆 + 名字首字兜底。
     * 全部自绘，不依赖 setClipToOutline 的椭圆 outline（低版本对 OVAL 支持不齐）。
     */
    private class AvatarView extends View {
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint ring = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint txt  = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Matrix mtx = new Matrix();
        private Bitmap bound;
        private BitmapShader shader;
        private Shader shadowShader;
        private int shadowKey = -1;

        AvatarView(Context c) {
            super(c);
            ring.setStyle(Paint.Style.STROKE);
            ring.setColor(0xF2FFFFFF);
            ring.setStrokeWidth(dp(1.6f));
            txt.setColor(0xFFFFFFFF);
            txt.setTextSize(dp(19));
            txt.setTypeface(Typeface.DEFAULT_BOLD);
            txt.setTextAlign(Paint.Align.CENTER);
        }

        @Override protected void onDraw(Canvas cv) {
            try {
                int w = getWidth(), h = getHeight();
                if (w <= 0 || h <= 0) return;
                float cx = w / 2f, cy = h / 2f;
                float r = Math.min(w, h) / 2f - dp(PAD_DP) - dp(0.4f);
                if (r <= 1f) return;
                drawShadow(cv, cx, cy, r, w, h);
                if (avatarBmp != null && !avatarBmp.isRecycled()) {
                    if (bound != avatarBmp) {
                        bound = avatarBmp;
                        shader = null;
                    }
                    if (shader == null) {
                        shader = new BitmapShader(bound, Shader.TileMode.CLAMP, Shader.TileMode.CLAMP);
                        float d = 2 * r;
                        float sc = Math.max(d / bound.getWidth(), d / bound.getHeight());
                        mtx.reset();
                        mtx.setScale(sc, sc);
                        mtx.postTranslate(cx - bound.getWidth() * sc / 2f, cy - bound.getHeight() * sc / 2f);
                        shader.setLocalMatrix(mtx);
                    }
                    fill.setShader(shader);
                    fill.setAlpha(255);
                    cv.drawCircle(cx, cy, r, fill);
                    fill.setShader(null);
                } else {
                    fallback(cv, cx, cy, r);
                }
                cv.drawCircle(cx, cy, r, ring);
            } catch (Throwable t) {}
        }

        private void drawShadow(Canvas cv, float cx, float cy, float r, int w, int h) {
            try {
                int key = w * 10000 + h;
                float off = dp(1.6f);
                float sr = r + dp(3.2f);
                if (shadowShader == null || key != shadowKey) {
                    shadowShader = new RadialGradient(cx, cy + off, sr,
                            new int[]{0x4D000000, 0x1F000000, 0x00000000},
                            new float[]{0f, 0.86f, 1f}, Shader.TileMode.CLAMP);
                    shadowKey = key;
                }
                fill.setShader(shadowShader);
                fill.setAlpha(255);
                cv.drawCircle(cx, cy + off, sr, fill);
                fill.setShader(null);
            } catch (Throwable t) {}
        }

        private void fallback(Canvas cv, float cx, float cy, float r) {
            try {
                Shader g = new LinearGradient(cx - r, cy - r, cx + r, cy + r,
                        new int[]{0xFFF9A8C9, 0xFFE0638F}, null, Shader.TileMode.CLAMP);
                fill.setShader(g);
                fill.setAlpha(255);
                cv.drawCircle(cx, cy, r, fill);
                fill.setShader(null);
                String nm = aiName;
                String ini = (nm == null || nm.length() == 0) ? "E" : nm.substring(0, 1);
                cv.drawText(ini, cx, cy - (txt.ascent() + txt.descent()) / 2f, txt);
            } catch (Throwable t) {}
        }
    }
}
