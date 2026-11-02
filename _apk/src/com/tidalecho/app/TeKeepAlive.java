package com.tidalecho.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

/* ============================================================================
   TidalEcho 后台保活
   ----------------------------------------------------------------------------
   这个应用里有"自主心跳"（AI 自己找话说）、工作流定时唤醒（flow 的 next 到点就跑）、
   每 30 分钟写一次记忆。这些全靠页面里的 JS 定时器。手机一进后台会遇到两道拦：
     ① 进程被系统回收（内存吃紧时）      → 用**前台服务 + 常驻通知**顶住
     ② 屏幕关闭后 CPU 休眠，JS 定时器冻结 → 用**PARTIAL_WAKE_LOCK** 顶住

   所以保活要两件事一起做，只做其中一件都不够。

   实现要点（都是踩过的坑）：
     · Android 8+ 通知必须有 channel，否则 startForeground 直接失败
     · Android 10+ 前台服务要在清单里声明 foregroundServiceType
     · Android 14+ 还要**对应的权限**，否则抛 SecurityException / 启动即被拒。
       用 specialUse（清单里声明一个 property 说明用途）+ 声明
       FOREGROUND_SERVICE_SPECIAL_USE；用 dataSync 在 Android 15 上有 6 小时上限，
       到点会被系统掐掉 —— 所以不用它。
     · Android 15 起 startForeground 抛异常的情形变多，所以逐个类型重试，
       全都失败就退化成"普通服务 + 唤醒锁"，至少不崩。
     · 通知用低优先级（IMPORTANCE_LOW）：不响不震，但常驻不被划掉。

   为什么不能只靠通知：通知只保证**进程**活着；屏幕一关 CPU 就休眠，
   JS 定时器（setInterval/setTimeout）会停摆，AI 该说话的时候不说。
   所以唤醒锁是必需的，且必须带超时 + 定期续期（长时间持锁会被系统警告/回收）。
   ============================================================================ */
public class TeKeepAlive extends Service {

    public static final String ACTION_START = "com.tidalecho.app.KEEPALIVE_START";
    public static final String ACTION_STOP  = "com.tidalecho.app.KEEPALIVE_STOP";

    /* 通知 */
    private static final String CH_ID   = "te_keepalive";
    private static final int    NOTI_ID = 0x7E01;          /* 固定 id：重复启动只更新同一条 */
    private static final int    WAKE_TIMEOUT_MS = 10 * 60 * 1000;
    private static final int    RENEW_MS        = 9 * 60 * 1000;

    private PowerManager.WakeLock wake;
    private Handler handler;
    private Runnable renew;
    private boolean foreground = false;

    /* 页面侧要能问"现在开着吗" */
    public static volatile boolean alive = false;

    public static void start(Context c) {
        try {
            Intent i = new Intent(c, TeKeepAlive.class);
            i.setAction(ACTION_START);
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "keepalive start failed: " + t);
        }
    }

    public static void stop(Context c) {
        try { c.stopService(new Intent(c, TeKeepAlive.class)); }
        catch (Throwable t) { android.util.Log.e("TidalEcho", "keepalive stop failed: " + t); }
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        handler = new Handler(Looper.getMainLooper());
        alive = true;
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        String act = (intent == null) ? null : intent.getAction();
        if (ACTION_STOP.equals(act)) {
            shutdown();
            return START_NOT_STICKY;
        }
        goForeground();
        acquireWake();
        /* START_STICKY：被系统杀了之后尽量拉回来（配合前台服务，实际很少被杀） */
        return START_STICKY;
    }

    /* ---- 前台服务 + 常驻通知 ---- */
    private void goForeground() {
        if (foreground) return;
        try {
            Notification n = buildNotification();
            if (Build.VERSION.SDK_INT >= 29) {
                /* Android 10+：必须指定类型。逐个试，全失败就退化成普通服务（不崩） */
                int[] types = new int[]{
                    /* 14 (0x40000000) = specialUse；13 = shortService；10 = dataSync */
                    Build.VERSION.SDK_INT >= 34 ? 0x40000000 : 0x00000001,
                    0x00000001,
                };
                for (int t : types) {
                    try {
                        startForeground(NOTI_ID, n, t);
                        foreground = true;
                        android.util.Log.i("TidalEcho", "foreground ok, type=" + t);
                        return;
                    } catch (Throwable e) {
                        android.util.Log.w("TidalEcho", "startForeground type " + t + " failed: " + e);
                    }
                }
            }
            startForeground(NOTI_ID, n);
            foreground = true;
        } catch (Throwable e) {
            /* 前台服务起不来也继续跑，至少唤醒锁还在 */
            android.util.Log.e("TidalEcho", "goForeground failed: " + e);
        }
    }

    private Notification buildNotification() {
        if (Build.VERSION.SDK_INT >= 26) {
            try {
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                if (nm != null && nm.getNotificationChannel(CH_ID) == null) {
                    NotificationChannel ch = new NotificationChannel(
                            CH_ID, "后台运行", NotificationManager.IMPORTANCE_LOW);
                    ch.setDescription("让潮汐回响在后台也能继续陪你");
                    ch.setShowBadge(false);
                    ch.enableVibration(false);
                    ch.setSound(null, null);
                    nm.createNotificationChannel(ch);
                }
            } catch (Throwable t) {
                android.util.Log.w("TidalEcho", "channel failed: " + t);
            }
        }

        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int piFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) piFlags |= 0x08000000;   /* FLAG_IMMUTABLE */
        PendingIntent pi = null;
        try { pi = PendingIntent.getActivity(this, 0, open, piFlags); } catch (Throwable t) {}

        Notification.Builder b = (Build.VERSION.SDK_INT >= 26)
                ? new Notification.Builder(this, CH_ID)
                : new Notification.Builder(this);
        b.setContentTitle("潮汐回响在后台陪着你")
              .setContentText("心跳与工作流继续运行中 · 点一下回来")
              .setSmallIcon(android.R.drawable.ic_menu_compass)
              .setOngoing(true)
              .setAutoCancel(false);
        try { b.setPriority(Notification.PRIORITY_LOW); } catch (Throwable t) {}
        if (pi != null) b.setContentIntent(pi);
        return b.build();
    }

    /* ---- 唤醒锁：屏幕关掉后 CPU 还能跑 JS 定时器 ---- */
    private void acquireWake() {
        try {
            if (wake == null) {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (pm == null) return;
                wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TidalEcho::keepalive");
                wake.setReferenceCounted(false);
            }
            if (!wake.isHeld()) wake.acquire(WAKE_TIMEOUT_MS);
        } catch (Throwable t) {
            android.util.Log.e("TidalEcho", "wake acquire failed: " + t);
            return;
        }
        /* 定期续期：长持锁不续期会被系统警告/回收，所以带超时 + 自动续 */
        if (renew == null) {
            renew = new Runnable() {
                @Override public void run() {
                    try { if (wake != null && !wake.isHeld()) wake.acquire(WAKE_TIMEOUT_MS); }
                    catch (Throwable t) {}
                    if (handler != null) handler.postDelayed(this, RENEW_MS);
                }
            };
        }
        if (handler != null) {
            handler.removeCallbacks(renew);
            handler.postDelayed(renew, RENEW_MS);
        }
    }

    private void releaseWake() {
        try {
            if (handler != null && renew != null) handler.removeCallbacks(renew);
            if (wake != null && wake.isHeld()) wake.release();
        } catch (Throwable t) {}
        wake = null;
    }

    private void shutdown() {
        releaseWake();
        try { if (foreground) stopForeground(true); } catch (Throwable t) {}
        foreground = false;
        alive = false;
        try { stopSelf(); } catch (Throwable t) {}
    }

    @Override public void onTaskRemoved(Intent root) {
        /* 从最近任务划掉时不自杀：这正是"保活"要顶住的情形之一 */
        alive = true;
        super.onTaskRemoved(root);
    }

    @Override public void onDestroy() {
        releaseWake();
        alive = false;
        foreground = false;
        super.onDestroy();
    }
}
