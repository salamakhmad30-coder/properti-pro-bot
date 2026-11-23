
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

def load_tasks():
    with _lock:
        if not os.path.exists(DATA_FILE):
            return list(DEFAULT_TASKS)
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            return list(DEFAULT_TASKS)

def save_tasks(tasks):
    with _lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)

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
        _bot.reply_to(m, f"Halo {m.from_user.first_name}! 👋\n\nGw <b>Properti Pro Bot</b> - Azira Team lo. <b>UDAH NYAMBUNG KE DASHBOARD WEB!</b> 🎉\n\nChat ID lo: <code>{m.chat.id}</code>\n\n/task - Lihat task (sama kayak di web)\n/tambah [judul] - Tambah task (muncul di web)\n/done [id] - Selesaikan task (web ikut ke-update)\n/laporan - Laporan harian\n/team - Lihat tim AI\n/id - Lihat Chat ID")

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
                t["status"] = "done"; save_tasks(tasks)
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

# ================= WEB API + DASHBOARD =================
@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "bot": bool(TOKEN), "tasks": len(load_tasks()), "time": datetime.now().isoformat()})

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
            save_tasks(tasks)
            if data.get("status") == "done":
                notify_admin(f"✅ <b>Task selesai dari Dashboard Web!</b>\n\n{fmt(t)}")
            return jsonify(t)
    return jsonify({"error": "not found"}), 404

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def api_delete(tid):
    tasks = [t for t in load_tasks() if t["id"] != tid]
    save_tasks(tasks)
    return jsonify({"ok": True})

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    print(f"[web] Dashboard jalan di port {PORT} - bot + web 1 otak", flush=True)
    app.run(host="0.0.0.0", port=PORT)
