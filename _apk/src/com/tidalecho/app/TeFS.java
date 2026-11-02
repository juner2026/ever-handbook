package com.tidalecho.app;

import android.app.Activity;
import android.content.ContentResolver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import android.util.Base64;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/* ============================================================================
   TeFS · 潮汐回响的手机文件通道（原生桥）

   为什么需要它：
     页面里原本用 window.showDirectoryPicker()（File System Access API）绑文件夹。
     那个 API 只有桌面版 Chromium 有，**Android WebView 里根本不存在** ——
     所以手机上工作台永远显示「暂无可用通道」，AI 的 <tool_file> 也读不到任何东西。
     页面其实早就留了后门：tfsHost() 会优先找 window.OperitFS.op(op,path,content)。
     这里把那个接口用原生实现出来。

   怎么拿到权限（不申请任何敏感权限）：
     走系统自带的「选择文件夹」对话框（SAF / ACTION_OPEN_DOCUMENT_TREE），
     由**用户自己指定**授权哪个目录，再 takePersistableUriPermission 长期保留。
     所以清单里不需要 MANAGE_EXTERNAL_STORAGE 这类"所有文件"权限，
     系统不会拦，用户也随时能在系统设置里撤销。

   契约（与页面里的 tfsOp 完全一致）：
     op(op, path, content) -> String   op ∈ list | read | write | writeb64 | mkdir | search | status | unbind
     真正的结果异步回给页面里两个回调：
       window.__teFsResult(text)          每次 op 的返回值
       window.__teFsBound(ok, name)       绑定/解绑状态变化
     所有文件操作都在后台线程跑，再回 UI 线程回 JS —— 读写大文件不卡界面。
   ============================================================================ */
public class TeFS {

    private static final String TAG = "TidalEcho";
    private static final String PREF = "tefs";
    private static final int REQ_DIR = 1002;
    private static final String DIR_MIME = "vnd.android.document/directory";

    /* 只存 Uri **字符串**（不是 Uri 对象），所以不会持有 Context，静态是安全的 */
    private static String sTreeUri = null;

    private final Activity act;
    private final WebView web;

    public TeFS(Activity a, WebView w) { this.act = a; this.web = w; }

    /** MainActivity 建好 WebView 后调它：读回上次的授权 */
    public void load() {
        try {
            sTreeUri = act.getSharedPreferences(PREF, Context.MODE_PRIVATE).getString("tree", null);
        } catch (Throwable t) { sTreeUri = null; }
        if (sTreeUri != null) Log.i(TAG, "TeFS 恢复绑定：" + sTreeUri);
    }

    private void savePref(String v) {
        try {
            act.getSharedPreferences(PREF, Context.MODE_PRIVATE).edit().putString("tree", v).apply();
        } catch (Throwable ignore) {}
    }

    /* ---------------- 回 JS ---------------- */
    private void cb(final String js) {
        act.runOnUiThread(new Runnable() {
            @Override public void run() {
                try { web.evaluateJavascript(js, null); } catch (Throwable t) { Log.w(TAG, "cb fail", t); }
            }
        });
    }

    /** 安全转义成 JS 字符串字面量 */
    private static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder(s.length() + 16);
        b.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"':  b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n");  break;
                case '\r': b.append("\\r");  break;
                case '\t': b.append("\\t");  break;
                case '\b': b.append("\\b");  break;
                case '\f': b.append("\\f");  break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        b.append('"');
        return b.toString();
    }

    /* ---------------- 状态 ---------------- */
    @JavascriptInterface
    public boolean ready() { return sTreeUri != null; }

    @JavascriptInterface
    public String treeName() {
        if (sTreeUri == null) return "";
        try { return DocumentsContract.getTreeDocumentId(Uri.parse(sTreeUri)); }
        catch (Throwable t) { return sTreeUri; }
    }

    @JavascriptInterface
    public String status() {
        boolean ok = sTreeUri != null;
        String nm = ok ? treeName() : "";
        cb("try{if(window.__teFsStatus)window.__teFsStatus(" + ok + "," + q(nm) + ");}catch(e){}");
        return ok ? nm : "";
    }

    /** 打开系统「选择文件夹」 */
    @JavascriptInterface
    public void bindFolder() {
        act.runOnUiThread(new Runnable() {
            @Override public void run() {
                try {
                    Intent it = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
                    it.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
                              | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
                              | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION
                              | Intent.FLAG_GRANT_PREFIX_URI_PERMISSION);
                    act.startActivityForResult(it, REQ_DIR);
                } catch (Throwable t) {
                    tell("打不开系统文件夹选择器：" + t.getMessage());
                }
            }
        });
    }

    @JavascriptInterface
    public void unbind() {
        try {
            if (sTreeUri != null) {
                act.getContentResolver().releasePersistableUriPermission(Uri.parse(sTreeUri),
                        Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            }
        } catch (Throwable ignore) {}
        sTreeUri = null; savePref(null);
        cb("try{if(window.__teFsBound)window.__teFsBound(false,'');}catch(e){}");
    }

    /** MainActivity 在 onActivityResult 里回调 */
    public void onFolderPicked(final Uri tree) {
        if (tree == null) return;
        sTreeUri = tree.toString();
        try {
            act.getContentResolver().takePersistableUriPermission(tree,
                    Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        } catch (Throwable t) { Log.w(TAG, "take persist fail", t); }
        savePref(sTreeUri);
        Log.i(TAG, "TeFS 绑定：" + sTreeUri);
        cb("try{if(window.__teFsBound)window.__teFsBound(true," + q(treeName()) + ");}catch(e){}");
    }

    /* ---------------- 主入口：与页面 tfsOp(op,path,content) 同签名 ---------------- */
    @JavascriptInterface
    public String op(final String op0, final String path0, final String content0) {
        final String op = op0 == null ? "list" : op0.trim().toLowerCase();
        final String path = path0 == null ? "" : path0;
        final String content = content0 == null ? "" : content0;
        new Thread(new Runnable() {
            @Override public void run() {
                String r;
                try { r = run0(op, path, content); }
                catch (Throwable t) { r = "出错了：" + t.getClass().getSimpleName() + " " + t.getMessage(); }
                cb("try{if(window.__teFsResult)window.__teFsResult(" + q(r) + ");}catch(e){}");
            }
        }, "TeFS").start();
        return "";   /* 真正结果走 __teFsResult 异步回来 */
    }

    private String run0(String op, String path, String content) throws Exception {
        if ("status".equals(op)) return sTreeUri == null ? "还没绑定文件夹" : ("已绑定：" + treeName());
        if ("unbind".equals(op)) { unbind(); return "已解除绑定"; }
        if (sTreeUri == null) {
            return "还没绑定文件夹 —— 去「工作台 → 文件」点「绑定文件夹」，"
                 + "在弹出的系统窗口里选一个目录（比如 Download 或 Documents）。";
        }
        Uri tree = Uri.parse(sTreeUri);
        String rootId = DocumentsContract.getTreeDocumentId(tree);

        if ("list".equals(op))    return list(tree, rootId, path);
        if ("read".equals(op))    return read(tree, rootId, path);
        if ("write".equals(op))   return write(tree, rootId, path, content, false);
        if ("writeb64".equals(op))return write(tree, rootId, path, content, true);
        if ("mkdir".equals(op))   return mkdir(tree, rootId, path);
        if ("search".equals(op)) {
            List<String> hits = new ArrayList<String>();
            search(tree, joinId(rootId, path), normRel(path), content.trim(), hits, 0);
            Collections.sort(hits);
            return "找到 " + hits.size() + " 项含「" + content + "」：\n"
                 + (hits.isEmpty() ? "（没有）" : join(hits, "\n"));
        }
        return "不认识的操作：" + op + "（可用 list / read / write / mkdir / search）";
    }

    /* ---------------- 路径处理 ---------------- */
    private static String normRel(String path) {
        String p = path == null ? "" : path.replace('\\', '/').trim();
        while (p.startsWith("/")) p = p.substring(1);
        while (p.endsWith("/")) p = p.substring(0, p.length() - 1);
        return p;
    }

    /** 把相对路径拼成 documentId（根 id 自身可能含冒号，如 primary:Download） */
    private static String joinId(String rootId, String path) {
        String p = normRel(path);
        return p.isEmpty() ? rootId : (rootId + "/" + p);
    }

    private Uri uriOf(Uri tree, String docId) {
        return DocumentsContract.buildDocumentUriUsingTree(tree, docId);
    }

    /* ---------------- list ---------------- */
    private String list(Uri tree, String rootId, String path) throws Exception {
        String id = joinId(rootId, path);
        StringBuilder b = new StringBuilder();
        int n = 0;
        Cursor c = null;
        try {
            Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id);
            c = act.getContentResolver().query(children, new String[]{
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                    DocumentsContract.Document.COLUMN_MIME_TYPE,
                    DocumentsContract.Document.COLUMN_SIZE
            }, null, null, null);
            List<String> dirs = new ArrayList<String>();
            List<String> files = new ArrayList<String>();
            while (c != null && c.moveToNext()) {
                String nm = c.getString(0), mt = c.getString(1);
                long sz = c.isNull(2) ? -1 : c.getLong(2);
                if (DIR_MIME.equals(mt)) dirs.add("[" + nm + "]/");
                else files.add(nm + (sz >= 0 ? ("  (" + human(sz) + ")") : ""));
                n++;
            }
            Collections.sort(dirs);
            Collections.sort(files);
            dirs.addAll(files);
            b.append("「").append(normRel(path).isEmpty() ? "/" : normRel(path)).append("」共 ").append(n).append(" 项：\n");
            b.append(dirs.isEmpty() ? "（空）" : join(dirs, "\n"));
        } catch (SecurityException se) {
            return "没有权限读这个目录（可能你在系统设置里撤销了授权）—— 回工作台重新绑一次。";
        } finally {
            if (c != null) try { c.close(); } catch (Throwable ignore) {}
        }
        return b.toString();
    }

    /* ---------------- read ---------------- */
    private String read(Uri tree, String rootId, String path) throws Exception {
        InputStream in = null;
        try {
            in = act.getContentResolver().openInputStream(uriOf(tree, joinId(rootId, path)));
            if (in == null) return "读不到这个文件（可能不存在）：" + path;
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            int r, total = 0, cap = 512 * 1024;
            boolean cut = false;
            while ((r = in.read(buf)) > 0) {
                if (total + r > cap) { bo.write(buf, 0, cap - total); cut = true; break; }
                bo.write(buf, 0, r); total += r;
            }
            byte[] data = bo.toByteArray();
            String txt = new String(data, "UTF-8");
            int bad = 0;
            for (int i = 0; i < txt.length(); i++) if (txt.charAt(i) == '\uFFFD') bad++;
            if (txt.length() > 0 && bad * 20 > txt.length()) {
                return "（这是二进制文件）" + normRel(path) + " 大小 " + human(data.length) + "，不能按文本读。";
            }
            String head = txt.length() > 6000 ? txt.substring(0, 6000) : txt;
            return head
                 + (txt.length() > 6000 ? ("\n…（太长，截断了；全文 " + txt.length() + " 字）") : "")
                 + (cut ? "\n…（文件超过 512KB，只读了前 512KB）" : "");
        } finally {
            if (in != null) try { in.close(); } catch (Throwable ignore) {}
        }
    }

    /* ---------------- write ---------------- */
    private String write(Uri tree, String rootId, String path, String content, boolean b64) throws Exception {
        String p = normRel(path);
        int i = p.lastIndexOf('/');
        String dirRel = i > 0 ? p.substring(0, i) : "";
        String name = i >= 0 ? p.substring(i + 1) : p;
        if (name.isEmpty()) return "得给个文件名";

        String parentId = ensureDir(tree, rootId, dirRel);
        byte[] data = b64 ? Base64.decode(content, Base64.DEFAULT) : content.getBytes("UTF-8");
        ContentResolver cr = act.getContentResolver();
        Uri target = findChild(tree, parentId, name);
        boolean created = false;
        if (target == null) {
            target = DocumentsContract.createDocument(cr, uriOf(tree, parentId), "application/octet-stream", name);
            created = true;
            if (target == null) return "建不了这个文件：" + p;
        }
        OutputStream os = null;
        try {
            os = cr.openOutputStream(target, "wt");    /* wt = 截断重写 */
            if (os == null) return "写不进去（这个目录可能只读）：" + p;
            os.write(data);
            os.flush();
        } finally {
            if (os != null) try { os.close(); } catch (Throwable ignore) {}
        }
        return (created ? "建好了：" : "写好了：") + p + "（" + human(data.length) + "）";
    }

    /** 逐级确保目录存在，返回最终 parent 的 documentId（对齐桌面版 create:true） */
    private String ensureDir(Uri tree, String rootId, String rel) {
        String r = normRel(rel);
        if (r.isEmpty()) return rootId;
        String cur = rootId;
        for (String seg : r.split("/")) {
            if (seg.isEmpty() || ".".equals(seg)) continue;
            Uri found = findChild(tree, cur, seg);
            if (found != null) { cur = DocumentsContract.getDocumentId(found); continue; }
            try {
                Uri made = DocumentsContract.createDocument(act.getContentResolver(),
                        uriOf(tree, cur), DIR_MIME, seg);
                if (made == null) return cur;
                cur = DocumentsContract.getDocumentId(made);
            } catch (Throwable t) { return cur; }
        }
        return cur;
    }

    /* ---------------- mkdir ---------------- */
    private String mkdir(Uri tree, String rootId, String path) throws Exception {
        String p = normRel(path);
        if (p.isEmpty()) return "得给个目录名";
        int i = p.lastIndexOf('/');
        String dirRel = i > 0 ? p.substring(0, i) : "";
        String name = i >= 0 ? p.substring(i + 1) : p;
        String parentId = ensureDir(tree, rootId, dirRel);
        if (findChild(tree, parentId, name) != null) return "这个目录已经有了：" + p;
        Uri made = DocumentsContract.createDocument(act.getContentResolver(),
                uriOf(tree, parentId), DIR_MIME, name);
        return made == null ? ("建不了目录：" + p) : ("建好了目录：" + p);
    }

    /* ---------------- search ---------------- */
    private void search(Uri tree, String dirId, String rel, String kw, List<String> hits, int depth) {
        if (depth > 3 || hits.size() >= 60 || kw == null || kw.isEmpty()) return;
        Cursor c = null;
        try {
            Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, dirId);
            c = act.getContentResolver().query(children, new String[]{
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME,
                    DocumentsContract.Document.COLUMN_MIME_TYPE
            }, null, null, null);
            List<String[]> kids = new ArrayList<String[]>();
            while (c != null && c.moveToNext())
                kids.add(new String[]{c.getString(0), c.getString(1), c.getString(2)});
            for (String[] k : kids) {
                if (hits.size() >= 60) return;
                String nm = k[1], mt = k[2];
                String shown = (rel == null || rel.isEmpty()) ? nm : (rel + "/" + nm);
                boolean isDir = DIR_MIME.equals(mt);
                if (nm != null && nm.contains(kw)) hits.add(isDir ? ("[" + shown + "]/") : shown);
                if (isDir) search(tree, k[0], shown, kw, hits, depth + 1);
            }
        } catch (Throwable ignore) {
        } finally {
            if (c != null) try { c.close(); } catch (Throwable ignore) {}
        }
    }

    /* ---------------- 小工具 ---------------- */
    private Uri findChild(Uri tree, String parentId, String name) {
        Cursor c = null;
        try {
            Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, parentId);
            c = act.getContentResolver().query(children, new String[]{
                    DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                    DocumentsContract.Document.COLUMN_DISPLAY_NAME
            }, null, null, null);
            while (c != null && c.moveToNext()) {
                if (name.equals(c.getString(1)))
                    return DocumentsContract.buildDocumentUriUsingTree(tree, c.getString(0));
            }
        } catch (Throwable ignore) {
        } finally {
            if (c != null) try { c.close(); } catch (Throwable ignore) {}
        }
        return null;
    }

    private void tell(final String s) {
        cb("try{if(window.__teFsTell)window.__teFsTell(" + q(s) + ");}catch(e){}");
    }

    private static String join(List<String> l, String sep) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < l.size(); i++) { if (i > 0) b.append(sep); b.append(l.get(i)); }
        return b.toString();
    }

    private static String human(long n) {
        if (n < 1024) return n + " B";
        if (n < 1024 * 1024) return String.format("%.1f KB", n / 1024.0);
        return String.format("%.1f MB", n / (1024.0 * 1024.0));
    }

    @JavascriptInterface
    public String info() {
        return "TeFS/1 · SAF 目录授权 · op=list|read|write|writeb64|mkdir|search|status|unbind";
    }

    public static final int REQ_DIR_CODE = REQ_DIR;
}
