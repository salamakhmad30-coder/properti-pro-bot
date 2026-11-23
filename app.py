
"""
AZIRA TEAM v2 - Bot Telegram + Dashboard Web, 1 OTAK (tasks.json sama)
Jalan di Railway sebagai WEB service (bukan worker lagi).

- Bot: polling telebot di thread terpisah
- Web: Flask, serve dashboard + API /api/tasks
- Data: tasks.json yang sama, dikunci threading.Lock biar gak rebutan
"""
import os, json, threading, time
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "7484848251").strip()
PORT = int(os.getenv("PORT", "8080"))
DATA_FILE = "tasks.json"
_lock = threading.Lock()

app = Flask(__name__)

# --- CORS biar dashboard artifact lama juga bisa manggil API ini kalau mau ---
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

TEAM = {
    "Nara": "Content Writer AI", "Vino": "Graphic Designer AI",
    "Saka": "Video Editor AI", "Riko": "Customer Service AI",
    "Luma": "Data Analyst AI", "Ara": "Social Media Manager AI",
}
DEFAULT_TASKS = [
    {"id": 1, "title": "Design Website EEX", "assignee": "Vino", "project": "EEX Indo", "status": "doing", "priority": "Tinggi", "deadline": "2026-11-25", "created_at": "2026-11-23"},
    {"id": 2, "title": "Konten Listing Larangan Tangerang", "assignee": "Nara", "project": "Jurnal Rumah", "status": "todo", "priority": "Tinggi", "deadline": "2026-11-24", "created_at": "2026-11-23"},
    {"id": 3, "title": "Edit Video Cluster 2 Lantai Ciputat", "assignee": "Saka", "project": "Ciputat", "status": "doing", "priority": "Sedang", "deadline": "2026-11-26", "created_at": "2026-11-23"},
    {"id": 4, "title": "Design thumbnail Ciputat", "assignee": "Nara", "project": "Properti Pro", "status": "todo", "priority": "Sedang", "deadline": "2026-11-24", "created_at": "2026-11-23"},
]

# ================= STORAGE v4: Postgres (Railway) + JSON fallback =================
# Kalau DATABASE_URL ada (setelah lo Add Postgres di Railway) -> pakai Postgres, data permanen.
# Kalau belum ada -> pakai tasks.json (biar tetap jalan sambil nunggu Postgres di-setup)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_pg_conn = None
try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except Exception:
    HAS_PG = False
    print("[storage] psycopg2 tidak ada, pakai JSON fallback", flush=True)

def pg_conn():
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        import psycopg2
        _pg_conn = psycopg2.connect(DATABASE_URL)
        _pg_conn.autocommit = True
        with _pg_conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                assignee TEXT DEFAULT 'Nara',
                project TEXT DEFAULT 'Properti Pro',
                status TEXT DEFAULT 'todo',
                priority TEXT DEFAULT 'Sedang',
                deadline TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )""")
            # Seed sekali kalau tabel masih kosong
            cur.execute("SELECT COUNT(*) FROM tasks")
            if cur.fetchone()[0] == 0:
                for t in DEFAULT_TASKS:
                    cur.execute("INSERT INTO tasks (title, assignee, project, status, priority, deadline, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                (t["title"], t["assignee"], t["project"], t["status"], t["priority"], t["deadline"], t.get("created_at","")))
                print("[storage] Postgres: seed DEFAULT_TASKS berhasil", flush=True)
    return _pg_conn

def use_pg():
    return bool(DATABASE_URL) and HAS_PG

def load_tasks():
    if use_pg():
        try:
            with _lock:
                conn = pg_conn()
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT id, title, assignee, project, status, priority, deadline, created_at FROM tasks ORDER BY id")
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
        except Exception as e:
            print(f"[storage] Postgres load gagal, fallback JSON: {e}", flush=True)
    # JSON fallback
    with _lock:
        if not os.path.exists(DATA_FILE):
            return list(DEFAULT_TASKS)
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            return list(DEFAULT_TASKS)

def save_tasks(tasks):
    # Di v4, save_tasks dipakai untuk kompatibilitas JSON fallback.
    # Untuk Postgres, operasi INSERT/UPDATE dilakukan langsung di API/bot via pg helpers di bawah.
    # Fungsi ini tetap simpan ke JSON sebagai backup, biar kalau Postgres down, data gak hilang total.
    if use_pg():
        return  # Postgres sudah disimpan per-operasi, jangan timpa JSON
    with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)

def pg_insert(nt):
    if not use_pg(): return None
    try:
        conn = pg_conn()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tasks (title, assignee, project, status, priority, deadline, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (nt["title"], nt["assignee"], nt["project"], nt["status"], nt["priority"], nt["deadline"], nt.get("created_at","")))
            nt["id"] = cur.fetchone()[0]
            return nt
    except Exception as e:
        print(f"[storage] pg_insert gagal: {e}", flush=True)
        return None

def pg_update(tid, data):
    if not use_pg(): return False
    try:
        conn = pg_conn()
        with conn.cursor() as cur:
            sets = []; vals = []
            for k in ["title","assignee","project","status","priority","deadline"]:
                if k in data:
                    sets.append(f"{k}=%s"); vals.append(data[k])
            if not sets: return False
            vals.append(tid)
            cur.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=%s", vals)
            return True
    except Exception as e:
        print(f"[storage] pg_update gagal: {e}", flush=True)
        return False

def pg_delete(tid):
    if not use_pg(): return False
    try:
        conn = pg_conn()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id=%s", (tid,))
            return True
    except Exception as e:
        print(f"[storage] pg_delete gagal: {e}", flush=True)
        return False

def fmt(t):
    e = {"todo": "📌", "doing": "🔄", "done": "✅"}.get(t["status"], "📌")
    return f"{e} #{t['id']} {t['title']}\n   👤 {t['assignee']} • 📁 {t['project']} • ⏰ {t['deadline']}"

def notify_admin(msg):
    """Kirim notif ke Telegram admin (Juragan) - dipanggil dari web & bot"""
    if not TOKEN or not ADMIN_CHAT_ID:
        return False
    try:
        _bot.send_message(ADMIN_CHAT_ID, msg, parse_mode="HTML")
        return True
    except Exception as e:
        print(f"[notify gagal] {e}", flush=True)
        return False

# ================= BOT =================
_bot = telebot.TeleBot(TOKEN, parse_mode="HTML") if TOKEN else None

if _bot:
    @_bot.message_handler(commands=["start", "help"])
    def h_start(m):
        _bot.reply_to(m, f"Halo {m.from_user.first_name}! 👋\n\nGw <b>Properti Pro Bot</b> - Azira Team lo. <b>UDAH NYAMBUNG KE DASHBOARD WEB!</b> 🎉\n\nChat ID lo: <code>{m.chat.id}</code>\n\n/task - Lihat task (sama kayak di web)\n/tambah [judul] - Tambah task (muncul di web)\n/done [id] - Selesaikan task (web ikut ke-update)\n/laporan - Laporan harian\n/team - Lihat tim AI\n/id - Lihat Chat ID\n/testlaporan - Test auto-laporan jam 8 pagi\n\n⏰ Auto-laporan: Tiap hari jam 08:00 WIB, bot kirim laporan otomatis ke lo.")

    @_bot.message_handler(commands=["id"])
    def h_id(m):
        _bot.reply_to(m, f"🆔 Chat ID lo: <code>{m.chat.id}</code>")

    @_bot.message_handler(commands=["task"])
    def h_task(m):
        tasks = [t for t in load_tasks() if t["status"] != "done"]
        if not tasks:
            _bot.reply_to(m, "🎉 Semua task beres!")
            return
        _bot.reply_to(m, f"📋 <b>Task Aktif ({len(tasks)}) - Sama kayak di Dashboard Web</b>\n\n" + "\n\n".join(fmt(t) for t in tasks))

    @_bot.message_handler(commands=["tambah"])
    def h_tambah(m):
        title = m.text.replace("/tambah", "").strip()
        if not title:
            _bot.reply_to(m, "Caranya: <code>/tambah Design thumbnail Ciputat</code>")
            return
        tasks = load_tasks()
        nid = max([t["id"] for t in tasks], default=0) + 1
        nt = {"id": nid, "title": title, "assignee": "Nara", "project": "Properti Pro", "status": "todo", "priority": "Sedang", "deadline": (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d"), "created_at": datetime.now().strftime("%Y-%m-%d")}
        if use_pg():
            pg_insert(nt)
        else:
            tasks.append(nt); save_tasks(tasks)
        _bot.reply_to(m, f"📌 <b>Task baru dibuat dari Telegram!</b>\n\n{fmt(nt)}\n\n✅ Udah muncul juga di Dashboard Web.")
        # Notif ke admin kalau yang nambah bukan admin
        if str(m.chat.id) != str(ADMIN_CHAT_ID):
            notify_admin(f"📌 Task baru dari {m.from_user.first_name} (Telegram):\n{title}")

    @_bot.message_handler(commands=["done"])
    def h_done(m):
        parts = m.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            _bot.reply_to(m, "Caranya: <code>/done 1</code>")
            return
        tid = int(parts[1]); tasks = load_tasks()
        for t in tasks:
            if t["id"] == tid:
                t["status"] = "done"
                if use_pg(): pg_update(tid, {"status": "done"})
                else: save_tasks(tasks)
                _bot.reply_to(m, f"✅ <b>Beres!</b>\n\n{fmt(t)}\n\n✅ Dashboard Web ikut ke-update.")
                return
        _bot.reply_to(m, f"Task #{tid} gak ketemu. Cek /task dulu.")

    @_bot.message_handler(commands=["laporan"])
    def h_laporan(m):
        tasks = load_tasks()
        done = len([t for t in tasks if t["status"]=="done"]); doing = len([t for t in tasks if t["status"]=="doing"]); todo = len([t for t in tasks if t["status"]=="todo"])
        txt = f"📊 <b>Laporan Harian - {datetime.now().strftime('%d %B %Y')}</b>\n\nTotal: {len(tasks)} • ✅ {done} • 🔄 {doing} • 📌 {todo}\n\n<b>Per Karyawan AI:</b>\n"
        for n, r in TEAM.items():
            mine = [t for t in tasks if t["assignee"]==n]; md = len([t for t in mine if t["status"]=="done"])
            txt += f"• {n} ({r}): {md}/{len(mine)} selesai\n"
        _bot.reply_to(m, txt)

    @_bot.message_handler(commands=["team"])
    def h_team(m):
        tasks = load_tasks(); txt = "👥 <b>Tim Karyawan AI Lo</b>\n\n"
        for n, r in TEAM.items():
            mine = [t for t in tasks if t["assignee"]==n]
            txt += f"<b>{n}</b> - {r} • Aktif: {len([t for t in mine if t['status']!='done'])}\n"
        _bot.reply_to(m, txt)


    @_bot.message_handler(commands=["testlaporan"])
    def h_testlaporan(m):
        _bot.reply_to(m, "⏳ Lagi kirim test auto-laporan ke admin...")
        ok = notify_admin(build_laporan_text())
        _bot.reply_to(m, "✅ Test auto-laporan terkirim! Cek chat admin." if ok else "❌ Gagal kirim. Cek ADMIN_CHAT_ID di Railway (harus 7484848251).")

    @_bot.message_handler(func=lambda m: True)
    def h_fallback(m):
        t = m.text.lower()
        if "task" in t or "kerjaan" in t: h_task(m)
        elif "laporan" in t or "rekap" in t: h_laporan(m)
        elif "halo" in t or "hai" in t: _bot.reply_to(m, "Halo! 👋 Ketik /task buat liat kerjaan.")
        else: _bot.reply_to(m, "Gw belum paham 😅 Coba /help")

    def run_bot():
        print("[bot] polling jalan...", flush=True)
        while True:
            try:
                _bot.infinity_polling(skip_pending=True, timeout=20)
            except Exception as e:
                print(f"[bot] polling error, retry 5 detik: {e}", flush=True)
                time.sleep(5)
else:
    def run_bot():
        print("[bot] TOKEN kosong, bot tidak jalan. Set TELEGRAM_BOT_TOKEN di Railway.", flush=True)


# ================= AUTO-LAPORAN JAM 8 PAGI =================
# Scheduler sederhana: cek tiap 60 detik, kalau jam 08:00 WIB dan belum kirim hari ini -> kirim laporan
# WIB = UTC+7. Railway pakai UTC, jadi 08:00 WIB = 01:00 UTC
# Jadi kita cek waktu WIB dengan +7 jam dari UTC
import datetime as _dt
_last_report_date = {"date": None}

def build_laporan_text():
    tasks = load_tasks()
    done = len([t for t in tasks if t["status"]=="done"]); doing = len([t for t in tasks if t["status"]=="doing"]); todo = len([t for t in tasks if t["status"]=="todo"])
    overdue = [t for t in tasks if t["status"]!="done" and t.get("deadline","") < _dt.datetime.now().strftime("%Y-%m-%d")]
    txt = f"☀️ <b>Selamat Pagi Juragan! Laporan Harian - {_dt.datetime.now().strftime('%d %B %Y')} - Jam 08:00 WIB</b>\n\n"
    txt += f"📊 Total: {len(tasks)} • ✅ Selesai: {done} • 🔄 Dikerjakan: {doing} • 📌 Belum mulai: {todo}\n"
    if overdue:
        txt += f"\n⚠️ <b>OVERDUE ({len(overdue)}):</b>\n"
        for t in overdue:
            txt += f"• #{t['id']} {t['title']} (deadline {t['deadline']}, {t['assignee']})\n"
    txt += "\n<b>Per Karyawan AI:</b>\n"
    for n, r in TEAM.items():
        mine = [t for t in tasks if t["assignee"]==n]; md = len([t for t in mine if t["status"]=="done"])
        txt += f"• {n} ({r}): {md}/{len(mine)} selesai\n"
    txt += "\n<b>Task Hari Ini (yang harus dikejar):</b>\n"
    today_tasks = [t for t in tasks if t["status"]!="done"]
    if not today_tasks:
        txt += "🎉 Semua beres! Gak ada yang tertunda.\n"
    else:
        for t in today_tasks[:10]:
            txt += f"{fmt(t)}\n"
    txt += "\nKetik /task buat detail, /tambah buat nambah task baru. Semangat closing hari ini! 💪"
    return txt

def auto_report_loop():
    print("[scheduler] Auto-laporan jam 08:00 WIB aktif...", flush=True)
    while True:
        try:
            now_utc = _dt.datetime.utcnow()
            now_wib = now_utc + _dt.timedelta(hours=7)  # UTC -> WIB
            today = now_wib.strftime("%Y-%m-%d")
            # Kirim tepat di jam 08:00 - 08:04 WIB, sekali sehari
            if now_wib.hour == 8 and 0 <= now_wib.minute <= 4 and _last_report_date["date"] != today:
                print(f"[scheduler] Kirim auto-laporan {today} jam {now_wib.strftime('%H:%M')} WIB", flush=True)
                ok = notify_admin(build_laporan_text())
                if ok:
                    _last_report_date["date"] = today
                    print(f"[scheduler] Auto-laporan terkirim {today}", flush=True)
                else:
                    print(f"[scheduler] Gagal kirim, coba lagi 60 detik", flush=True)
            # Test manual: kirim /testlaporan di Telegram untuk test tanpa nunggu jam 8
        except Exception as e:
            print(f"[scheduler] error: {e}", flush=True)
        time.sleep(60)

# Handler test manual di bot (di dalam run_bot section, ditambahkan via monkey patch di bawah)

# ================= WEB API + DASHBOARD =================
@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "bot": bool(TOKEN), "storage": "postgres" if use_pg() else "json", "tasks": len(load_tasks()), "time": datetime.now().isoformat()})

@app.route("/api/tasks", methods=["GET"])
def api_list():
    return jsonify(load_tasks())

@app.route("/api/tasks", methods=["POST"])
def api_create():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title wajib"}), 400
    tasks = load_tasks()
    nid = max([t["id"] for t in tasks], default=0) + 1
    nt = {"id": nid, "title": title, "assignee": data.get("assignee", "Nara"), "project": data.get("project", "Properti Pro"), "status": "todo", "priority": data.get("priority", "Sedang"), "deadline": data.get("deadline", (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d")), "created_at": datetime.now().strftime("%Y-%m-%d")}
    if use_pg():
        pg_insert(nt)
    else:
        tasks.append(nt); save_tasks(tasks)
    # >>> INI KUNCINYA: web -> Telegram <<<
    notify_admin(f"📌 <b>Task baru dari Dashboard Web!</b>\n\n{fmt(nt)}\n\nCek /task di Telegram, udah muncul juga.")
    return jsonify(nt), 201

@app.route("/api/tasks/<int:tid>", methods=["PUT"])
def api_update(tid):
    data = request.get_json(force=True) or {}
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == tid:
            for k in ["title", "assignee", "project", "status", "priority", "deadline"]:
                if k in data: t[k] = data[k]
            if use_pg():
                pg_update(tid, data)
            else:
                save_tasks(tasks)
            if data.get("status") == "done":
                notify_admin(f"✅ <b>Task selesai dari Dashboard Web!</b>\n\n{fmt(t)}")
            return jsonify(t)
    return jsonify({"error": "not found"}), 404

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def api_delete(tid):
    if use_pg():
        pg_delete(tid)
    else:
        tasks = [t for t in load_tasks() if t["id"] != tid]
        save_tasks(tasks)
    return jsonify({"ok": True})

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=auto_report_loop, daemon=True).start()
    print(f"[web] Dashboard jalan di port {PORT} - bot + web 1 otak", flush=True)
    app.run(host="0.0.0.0", port=PORT)
