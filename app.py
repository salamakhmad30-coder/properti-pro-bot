
"""
AZIRA TEAM v3 - Bot Telegram + Dashboard Web + RUANG MEETING AI
Jalan di Railway (web service) / Vercel (serverless Flask, bot polling nonaktif di sini).

- Bot: polling telebot di thread terpisah (hanya di persistent process / Railway)
- Web: Flask, serve dashboard + API /api/tasks, /api/meeting, /api/image
- Storage: Supabase (REST) > Postgres (DATABASE_URL) > tasks.json (fallback)
"""
import os, json, threading, time, re
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

# --- CORS ---
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

# ================= STORAGE v5: Supabase REST > Postgres > JSON fallback =================
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SB_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SB_KEY = os.getenv("SUPABASE_KEY", "").strip()
_pg_conn = None
try:
    import psycopg2
    import psycopg2.extras
    HAS_PG = True
except Exception:
    HAS_PG = False
    print("[storage] psycopg2 tidak ada, Postgres direct dimatikan", flush=True)

try:
    import requests
    HAS_REQ = True
except Exception:
    HAS_REQ = False
    print("[storage] requests tidak ada, Supabase REST dimatikan", flush=True)

# ---------- Supabase REST helpers ----------
def use_sb():
    return bool(SB_URL) and bool(SB_KEY) and HAS_REQ

def _sb_headers(prefer=None):
    h = {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h

def sb_select(table, params=""):
    r = requests.get(f"{SB_URL}/rest/v1/{table}?{params}", headers=_sb_headers(), timeout=20)
    r.raise_for_status()
    return r.json()

def sb_insert(table, rows):
    r = requests.post(f"{SB_URL}/rest/v1/{table}", headers=_sb_headers("return=representation"), json=rows, timeout=20)
    r.raise_for_status()
    return r.json()

def sb_update(table, match, data):
    r = requests.patch(f"{SB_URL}/rest/v1/{table}?{match}", headers=_sb_headers("return=representation"), json=data, timeout=20)
    r.raise_for_status()
    return r.json()

def sb_delete(table, match):
    r = requests.delete(f"{SB_URL}/rest/v1/{table}?{match}", headers=_sb_headers(), timeout=20)
    r.raise_for_status()
    return True

# ---------- Postgres direct (Railway) helpers ----------
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
            cur.execute("SELECT COUNT(*) FROM tasks")
            if cur.fetchone()[0] == 0:
                for t in DEFAULT_TASKS:
                    cur.execute("INSERT INTO tasks (title, assignee, project, status, priority, deadline, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                (t["title"], t["assignee"], t["project"], t["status"], t["priority"], t["deadline"], t.get("created_at","")))
                print("[storage] Postgres: seed DEFAULT_TASKS berhasil", flush=True)
    return _pg_conn

def use_pg():
    return bool(DATABASE_URL) and HAS_PG

# ---------- Tasks: 3-layer storage ----------
def load_tasks():
    if use_sb():
        try:
            return sb_select("tasks", "select=*&order=id")
        except Exception as e:
            print(f"[storage] Supabase load gagal, coba fallback lain: {e}", flush=True)
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
        except Exception:
            return list(DEFAULT_TASKS)

def save_tasks(tasks):
    """Hanya untuk JSON fallback. Supabase/Postgres disimpan per-operasi."""
    if use_sb() or use_pg():
        return
    try:
        with _lock:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[storage] save_tasks gagal (read-only FS?): {e}", flush=True)

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

def task_insert(nt):
    if use_sb():
        try:
            rows = sb_insert("tasks", nt)
            return rows[0] if isinstance(rows, list) and rows else nt
        except Exception as e:
            print(f"[storage] sb_insert gagal: {e}", flush=True)
            return None
    if use_pg():
        return pg_insert(nt)
    tasks = load_tasks()
    nt["id"] = max([t["id"] for t in tasks], default=0) + 1
    tasks.append(nt); save_tasks(tasks)
    return nt

def task_update(tid, data):
    if use_sb():
        try:
            sb_update("tasks", f"id=eq.{tid}", {k: v for k, v in data.items() if k in ["title","assignee","project","status","priority","deadline"]})
            return True
        except Exception as e:
            print(f"[storage] sb_update gagal: {e}", flush=True)
            return False
    if use_pg():
        return pg_update(tid, data)
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == tid:
            t.update({k: v for k, v in data.items() if k in ["title","assignee","project","status","priority","deadline"]})
            save_tasks(tasks)
            return True
    return False

def task_delete(tid):
    if use_sb():
        try:
            sb_delete("tasks", f"id=eq.{tid}")
            return True
        except Exception as e:
            print(f"[storage] sb_delete gagal: {e}", flush=True)
            return False
    if use_pg():
        return pg_delete(tid)
    tasks = [t for t in load_tasks() if t["id"] != tid]
    save_tasks(tasks)
    return True

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
        _bot.reply_to(m, f"Halo {m.from_user.first_name}! 👋\n\nGw <b>Properti Pro Bot</b> - Azira Team lo. <b>UDAH NYAMBUNG KE DASHBOARD WEB!</b> 🎉\n\nChat ID lo: <code>{m.chat.id}</code>\n\n/task - Lihat task (sama kayak di web)\n/tambah [judul] - Tambah task (muncul di web)\n/done [id] - Selesaikan task (web ikut ke-update)\n/laporan - Laporan harian\n/team - Lihat tim AI\n/id - Lihat Chat ID\n/testlaporan - Test auto-laporan jam 8 pagi\n/rapat [topik] - Kasih perintah rapat ke Karyawan AI (contoh: /rapat strategi konten Ciputat)\n\n⏰ Auto-laporan: Tiap hari jam 08:00 WIB, bot kirim laporan otomatis ke lo.")

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
        nt = {"title": title, "assignee": "Nara", "project": "Properti Pro", "status": "todo", "priority": "Sedang", "deadline": (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d"), "created_at": datetime.now().strftime("%Y-%m-%d")}
        nt = task_insert(nt)
        if not nt:
            _bot.reply_to(m, "❌ Gagal simpan task. Cek koneksi storage.")
            return
        _bot.reply_to(m, f"📌 <b>Task baru dibuat dari Telegram!</b>\n\n{fmt(nt)}\n\n✅ Udah muncul juga di Dashboard Web.")
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
                task_update(tid, {"status": "done"})
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

    @_bot.message_handler(commands=["rapat"])
    def h_rapat(m):
        topic = m.text.replace("/rapat", "").strip()
        if not topic:
            _bot.reply_to(m, "Caranya: <code>/rapat strategi konten Ciputat cluster 2</code>")
            return
        _bot.reply_to(m, f"🗣️ Rapat dimulai: <b>{topic}</b>\nPara Karyawan AI lagi diskusi... tunggu ~30 detik ⏳")
        try:
            result = run_meeting(topic, rounds=1)
            txt = f"🗣️ <b>Hasil Rapat: {topic}</b>\n\n"
            for msg in result["messages"]:
                txt += f"<b>{msg['agent']}</b>: {msg['content'][:400]}\n\n"
            txt += f"📝 <b>Kesimpulan:</b>\n{result['summary'][:1200]}"
            if len(txt) > 4000:
                txt = txt[:3990] + "..."
            _bot.reply_to(m, txt)
        except Exception as e:
            _bot.reply_to(m, f"❌ Rapat gagal: {e}")

    @_bot.message_handler(commands=["testlaporan"])
    def h_testlaporan(m):
        _bot.reply_to(m, "⏳ Lagi kirim test auto-laporan ke admin...")
        ok = notify_admin(build_laporan_text())
        _bot.reply_to(m, "✅ Test auto-laporan terkirim! Cek chat admin." if ok else "❌ Gagal kirim. Cek ADMIN_CHAT_ID di Railway (harus 7484848251).")

    @_bot.message_handler(func=lambda m: True)
    def h_fallback(m):
        t = (m.text or "").lower()
        if "task" in t or "kerjaan" in t: h_task(m)
        elif "laporan" in t or "rekap" in t: h_laporan(m)
        elif "rapat" in t or "meeting" in t: h_rapat(m)
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
        print("[bot] TOKEN kosong, bot tidak jalan. Set TELEGRAM_BOT_TOKEN.", flush=True)


# ================= AUTO-LAPORAN JAM 8 PAGI =================
import datetime as _dt
_last_report_date = {"date": None}

def build_laporan_text():
    tasks = load_tasks()
    done = len([t for t in tasks if t["status"]=="done"]); doing = len([t for t in tasks if t["status"]=="doing"]); todo = len([t for t in tasks if t["status"]=="todo"])
    overdue = [t for t in tasks if t["status"]!="done" and t.get("deadline","") and t["deadline"] < _dt.datetime.now().strftime("%Y-%m-%d")]
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
        except Exception as e:
            print(f"[scheduler] error: {e}", flush=True)
        time.sleep(60)

# ================= RUANG MEETING AI =================
# Para Karyawan AI (LLM agents) diskusi satu sama lain soal satu topik,
# lalu dimoderasi jadi kesimpulan + action items.
KIE_API_KEY = os.getenv("KIE_API_KEY", "").strip()
KIE_TEXT_API_KEY = os.getenv("KIE_TEXT_API_KEY", "").strip() or KIE_API_KEY
KIE_TEXT_MODEL = os.getenv("KIE_TEXT_MODEL", "gpt-6.1-sol").strip() or "gpt-6.1-sol"
KIE_IMAGE_MODEL = os.getenv("KIE_IMAGE_MODEL", "gpt-image-2-5-flare-text-to-image").strip() or "gpt-image-2-5-flare-text-to-image"
KIE_RESPONSES_API_KEY = os.getenv("KIE_RESPONSES_API_KEY", "").strip()
KIE_RESPONSES_MODEL = os.getenv("KIE_RESPONSES_MODEL", "deepseek-v4-1-flash").strip() or "deepseek-v4-1-flash"
KIE_RESPONSES_ENDPOINT = os.getenv("KIE_RESPONSES_ENDPOINT", "https://api.kie.ai/openai/v1/responses").strip() or "https://api.kie.ai/openai/v1/responses"
KIE_REASONING_EFFORT = os.getenv("KIE_REASONING_EFFORT", "low").strip() or "low"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENROUTER_TEXT_MODEL = os.getenv("OPENROUTER_TEXT_MODEL", "google/gemini-2.5-flash").strip() or "google/gemini-2.5-flash"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1"

def llm_available():
    return bool(KIE_RESPONSES_API_KEY or os.getenv("KIE_RESPONSES_API_KEY", "").strip() or KIE_TEXT_API_KEY or os.getenv("KIE_TEXT_API_KEY", "").strip() or KIE_API_KEY or os.getenv("KIE_API_KEY", "").strip() or OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "").strip() or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip())

PERSONAS = [
    ("Luma", "Data Analyst", "📊",
     "Kamu Luma, Data Analyst AI di Azira Team (perusahaan properti & digital marketing: EEX Indo, Properti Pro, Jurnal Rumah, SKOR Bold, Ciputat). Gaya bicara: logis, tajam, suka angka & insight pasar. Kamu selalu mulai dari data/pertanyaan riset. Jangan sok tau di luar bidang data, tapi boleh brief soal prioritas berbasis dampak."),
    ("Nara", "Content Writer", "✍️",
     "Kamu Nara, Content Writer AI di Azira Team (perusahaan properti & digital marketing). Gaya bicara: natural, storytelling, paham copywriting properti & SEO. Kamu yang pegang narasi: judul, caption, artikel, tone of voice. Kasih contoh kalimat konkret kalau relevan."),
    ("Vino", "Graphic Designer", "🎨",
     "Kamu Vino, Graphic Designer AI di Azira Team (perusahaan properti & digital marketing). Gaya bicara: visual-minded, kreatif, opinionated soal layout, warna, hierarchy, brand. Kamu mikir soal aset visual: thumbnail, feed, banner, signage. Kasih arahan desain yang spesifik (warna, komposisi, elemen)."),
    ("Ara", "Social Media Manager", "📣",
     "Kamu Ara, Social Media Manager AI di Azira Team. Gaya bicara: ngerti trend, engagement, hook, jadwal posting, format konten (Reels/Carousel/TikTok). Kamu pikirkan distribution & virality, bukan cuma konten. Kasih ide format + caption hook + jam posting."),
    ("Riko", "Customer Service", "💬",
     "Kamu Riko, Customer Service AI di Azira Team (properti: lead & closing). Gaya bicara: empatik, solutif, paham keberatan umum pembeli (harga, KPR, lokasi, takut tipu). Kamu pikirkan: FAQ, script follow-up, cara handle objection, nurture lead. Kasih contoh script singkat."),
    ("Saka", "Video Editor", "🎬",
     "Kamu Saka, Video Editor AI di Azira Team. Gaya bicara: teknis-kreatif soal video: pacing, hook 3 detik pertama, B-roll, caption, musik, format 9:16/16:9. Kamu pikirkan: storyboard, shot list, editing direction untuk konten properti. Kasih arahan shot/edit yang konkret."),
]
AGENT_NAMES = [p[0] for p in PERSONAS]

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def meeting_storage_available():
    return use_sb() or use_pg()

def meeting_insert(topic, rounds):
    created = _now()
    if use_sb():
        rows = sb_insert("meetings", {"topic": topic, "rounds": rounds, "created_at": created})
        return rows[0]["id"] if rows else None
    if use_pg():
        conn = pg_conn()
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS meetings (id SERIAL PRIMARY KEY, topic TEXT NOT NULL, rounds INT DEFAULT 1, summary TEXT DEFAULT '', created_at TEXT DEFAULT '')")
            cur.execute("CREATE TABLE IF NOT EXISTS meeting_messages (id SERIAL PRIMARY KEY, meeting_id INT, agent TEXT, content TEXT, round INT DEFAULT 1, created_at TEXT DEFAULT '')")
            cur.execute("CREATE TABLE IF NOT EXISTS meeting_tasks (id SERIAL PRIMARY KEY, meeting_id INT, title TEXT, assignee TEXT DEFAULT 'Nara', project TEXT DEFAULT 'Properti Pro', created_at TEXT DEFAULT '')")
            cur.execute("INSERT INTO meetings (topic, rounds, created_at) VALUES (%s,%s,%s) RETURNING id", (topic, rounds, created))
            return cur.fetchone()[0]
    return int(time.time())  # memory mode (tidak persisten)

def meeting_add_message(meeting_id, agent, content, rnd):
    created = _now()
    msg = {"meeting_id": meeting_id, "agent": agent, "content": content, "round": rnd, "created_at": created}
    try:
        if use_sb():
            sb_insert("meeting_messages", msg)
        elif use_pg():
            conn = pg_conn()
            with conn.cursor() as cur:
                cur.execute("INSERT INTO meeting_messages (meeting_id, agent, content, round, created_at) VALUES (%s,%s,%s,%s,%s)",
                            (meeting_id, agent, content, rnd, created))
    except Exception as e:
        print(f"[meeting] gagal simpan message: {e}", flush=True)
    return msg

def meeting_finish(meeting_id, summary, action_items):
    try:
        if use_sb():
            sb_update("meetings", f"id=eq.{meeting_id}", {"summary": summary})
            if action_items:
                sb_insert("meeting_tasks", [{"meeting_id": meeting_id, "title": i["title"], "assignee": i.get("assignee","Nara"), "project": i.get("project","Properti Pro"), "created_at": _now()} for i in action_items])
        elif use_pg():
            conn = pg_conn()
            with conn.cursor() as cur:
                cur.execute("UPDATE meetings SET summary=%s WHERE id=%s", (summary, meeting_id))
                for i in action_items:
                    cur.execute("INSERT INTO meeting_tasks (meeting_id, title, assignee, project, created_at) VALUES (%s,%s,%s,%s,%s)",
                                (meeting_id, i["title"], i.get("assignee","Nara"), i.get("project","Properti Pro"), _now()))
    except Exception as e:
        print(f"[meeting] gagal simpan summary: {e}", flush=True)

def meeting_get_all(limit=20):
    try:
        if use_sb():
            return sb_select("meetings", f"select=id,topic,rounds,summary,created_at&order=id.desc&limit={limit}")
        if use_pg():
            conn = pg_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, topic, rounds, summary, created_at FROM meetings ORDER BY id DESC LIMIT %s", (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[meeting] list gagal: {e}", flush=True)
    return []

def meeting_get_detail(meeting_id):
    try:
        if use_sb():
            m = sb_select("meetings", f"select=*&id=eq.{meeting_id}")
            if not m: return None
            msgs = sb_select("meeting_messages", f"select=*&meeting_id=eq.{meeting_id}&order=id")
            items = sb_select("meeting_tasks", f"select=*&meeting_id=eq.{meeting_id}&order=id")
            return {"meeting": m[0], "messages": msgs, "action_items": items}
        if use_pg():
            conn = pg_conn()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, topic, rounds, summary, created_at FROM meetings WHERE id=%s", (meeting_id,))
                row = cur.fetchone()
                if not row: return None
                cur.execute("SELECT agent, content, round, created_at FROM meeting_messages WHERE meeting_id=%s ORDER BY id", (meeting_id,))
                msgs = [dict(r) for r in cur.fetchall()]
                cur.execute("SELECT title, assignee, project FROM meeting_tasks WHERE meeting_id=%s ORDER BY id", (meeting_id,))
                items = [dict(r) for r in cur.fetchall()]
                return {"meeting": dict(row), "messages": msgs, "action_items": items}
    except Exception as e:
        print(f"[meeting] detail gagal: {e}", flush=True)
    return None

def gemini_call(prompt, temperature=0.85, max_tokens=900):
    # Prefer KIE Responses API (DeepSeek V4.1 Flash) kalau key-nya ada
    responses_key = KIE_RESPONSES_API_KEY or os.getenv("KIE_RESPONSES_API_KEY", "").strip()
    if responses_key:
        effort = os.getenv("KIE_REASONING_EFFORT", KIE_REASONING_EFFORT).strip() or "low"
        r = requests.post(
            KIE_RESPONSES_ENDPOINT,
            headers={"Authorization": f"Bearer {responses_key}", "Content-Type": "application/json"},
            json={"model": KIE_RESPONSES_MODEL,
                  "stream": False,
                  "reasoning": {"effort": effort},
                  "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]},
            timeout=120,
        )
        data = r.json() if r.text else {}
        if r.status_code != 200 or (isinstance(data, dict) and data.get("code") not in (None, 200)):
            msg = data.get("msg") if isinstance(data, dict) else str(data)[:300]
            raise RuntimeError(f"KIE DeepSeek error {r.status_code}: {msg}")
        try:
            texts = []
            for item in data.get("output", []):
                if not isinstance(item, dict) or item.get("type") != "message":
                    continue
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                        texts.append(part["text"])
            content = "\n".join(texts).strip()
            if content:
                return content
            raise ValueError("no output_text message in response")
        except Exception:
            raise RuntimeError("KIE DeepSeek: respons kosong / tidak terduga")
    # Fallback: KIE AI (OpenAI-compatible /v1/chat/completions) kalau key teksnya ada
    kie_key = KIE_TEXT_API_KEY or os.getenv("KIE_TEXT_API_KEY", "").strip() or KIE_API_KEY or os.getenv("KIE_API_KEY", "").strip()
    if kie_key:
        r = requests.post(
            "https://api.kie.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"},
            json={"model": KIE_TEXT_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=60,
        )
        data = r.json() if r.text else {}
        if r.status_code != 200 or (isinstance(data, dict) and data.get("code") not in (None, 200)):
            msg = data.get("msg") if isinstance(data, dict) else str(data)[:300]
            raise RuntimeError(f"KIE AI error {r.status_code}: {msg}. (Key kamu mungkin hanya diizinkan untuk model gambar - buat key baru di kie.ai dengan model teks diizinkan, atau set KIE_TEXT_API_KEY yang benar.)")
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            raise RuntimeError("KIE AI: respons kosong / tidak terduga")
    # Fallback: OpenRouter
    or_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://properti-pro-bot.vercel.app", "X-Title": "Azira Team Bot"},
            json={"model": OPENROUTER_TEXT_MODEL,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=60,
        )
        if r.status_code != 200:
            raise RuntimeError(f"OpenRouter API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            raise RuntimeError("OpenRouter API: respons kosong / tidak terduga")
    # Fallback: Gemini langsung
    key = GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Belum ada API key LLM. Set OPENROUTER_API_KEY (atau GEMINI_API_KEY) di Vercel → Settings → Environment Variables.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    r = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini API error {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
    except Exception:
        raise RuntimeError("Gemini API: respons kosong / tidak terduga")

def run_meeting(topic, rounds=1):
    meeting_id = meeting_insert(topic, rounds)
    messages = []
    history = ""
    for rnd in range(1, rounds + 1):
        for name, role, emoji, persona in PERSONAS:
            if rnd == 1:
                ask = "Sampaikan pendapat/ide kamu (maksimal 3-4 kalimat, langsung ke inti, boleh panggil nama rekan)."
            else:
                ask = "Dengarkan pendapat rekan-rekanmu di atas. Tanggapi, setuju/tidak, tambahkan hal penting dari sudut pandang kamu (maksimal 3-4 kalimat). Jangan mengulang pendapat sendiri."
            prompt = f"""{persona}

Kamu sedang rapat tim Azira Team. Topik rapat: "{topic}"

Percakapan rapat sejauh ini:
{history if history else "(belum ada, kamu yang buka)"}

{ask}
Bahasa Indonesia santai tapi profesional. JANGAN tulis prefix nama kamu atau basa-basi pembuka."""
            try:
                reply = gemini_call(prompt)
            except Exception as e:
                reply = f"(gagal menjawab: {e})"
            msg = meeting_add_message(meeting_id, name, reply, rnd)
            msg["role"] = role
            msg["emoji"] = emoji
            messages.append(msg)
            history += f"{name} ({role}): {reply}\n"
    # Moderator: kesimpulan + action items (JSON ketat)
    mod_prompt = f"""Kamu Azira, Moderator rapat Azira Team. Berikut transkrip rapat tentang "{topic}":

{history}

Buat KESIMPULAN rapat dan ACTION PLAN. Balas HANYA dengan JSON valid (tanpa markdown, tanpa ```), format:
{{"summary": "kesimpulan singkat 3-5 kalimat, padat, bahasa Indonesia", "action_items": [{{"title": "aksi konkret", "assignee": "Nara|Vino|Saka|Riko|Luma|Ara", "project": "Properti Pro|EEX Indo|SKOR Bold|Jurnal Rumah|Ciputat"}}]}}
Maksimal 6 action items. Assignee harus sesuai keahlian masing-masing."""
    summary, action_items = "", []
    try:
        raw = gemini_call(mod_prompt, temperature=0.4, max_tokens=1200)
        raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        summary = str(parsed.get("summary", "")).strip()
        for item in parsed.get("action_items", [])[:6]:
            t = str(item.get("title", "")).strip()
            if not t:
                continue
            assignee = str(item.get("assignee", "Nara")).strip()
            if assignee not in AGENT_NAMES:
                assignee = "Nara"
            project = str(item.get("project", "Properti Pro")).strip()
            action_items.append({"title": t, "assignee": assignee, "project": project})
    except Exception as e:
        print(f"[meeting] moderator gagal / JSON tidak valid: {e}", flush=True)
        summary = raw if 'raw' in dir() else f"Ringkasan rapat tersimpan. (Moderator gagal: {e})"
    meeting_finish(meeting_id, summary, action_items)
    return {"meeting_id": meeting_id, "topic": topic, "rounds": rounds,
            "messages": messages, "summary": summary, "action_items": action_items,
            "persisted": meeting_storage_available()}

# ================= WEB API + DASHBOARD =================
@app.route("/")
def index():
    return send_from_directory(".", "dashboard.html")

@app.route("/api/health")
def health():
    storage = "supabase" if use_sb() else ("postgres" if use_pg() else "json")
    responses_key = KIE_RESPONSES_API_KEY or os.getenv("KIE_RESPONSES_API_KEY","").strip()
    llm = "kie-deepseek" if responses_key else ("kie" if (KIE_TEXT_API_KEY or os.getenv("KIE_TEXT_API_KEY","").strip() or KIE_API_KEY or os.getenv("KIE_API_KEY","").strip()) else ("openrouter" if (OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY","").strip()) else ("gemini" if (GEMINI_API_KEY or os.getenv("GEMINI_API_KEY","").strip()) else None)))
    return jsonify({"ok": True, "bot": bool(TOKEN), "storage": storage, "llm": llm, "kie": bool(KIE_API_KEY or os.getenv("KIE_API_KEY","").strip()), "deepseek": bool(responses_key), "openrouter": bool(OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY","").strip()), "gemini": bool(os.getenv("GEMINI_API_KEY","").strip()), "tasks": len(load_tasks()), "time": datetime.now().isoformat()})

@app.route("/api/tasks", methods=["GET"])
def api_list():
    return jsonify(load_tasks())

@app.route("/api/tasks", methods=["POST"])
def api_create():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title wajib"}), 400
    nt = {"title": title, "assignee": data.get("assignee", "Nara"), "project": data.get("project", "Properti Pro"),
          "status": "todo", "priority": data.get("priority", "Sedang"),
          "deadline": data.get("deadline", (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d")),
          "created_at": datetime.now().strftime("%Y-%m-%d")}
    nt = task_insert(nt)
    if not nt:
        return jsonify({"error": "gagal simpan ke storage"}), 500
    notify_admin(f"📌 <b>Task baru dari Dashboard Web!</b>\n\n{fmt(nt)}\n\nCek /task di Telegram, udah muncul juga.")
    return jsonify(nt), 201

@app.route("/api/tasks/<int:tid>", methods=["PUT"])
def api_update(tid):
    data = request.get_json(force=True) or {}
    ok = task_update(tid, data)
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == tid:
            if data.get("status") == "done":
                notify_admin(f"✅ <b>Task selesai dari Dashboard Web!</b>\n\n{fmt(t)}")
            return jsonify(t)
    return (jsonify({"error": "not found"}), 404) if not ok else jsonify(data)

@app.route("/api/tasks/<int:tid>", methods=["DELETE"])
def api_delete(tid):
    task_delete(tid)
    return jsonify({"ok": True})

@app.route("/api/meeting", methods=["POST"])
def api_meeting():
    data = request.get_json(force=True) or {}
    topic = (data.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "topic wajib diisi"}), 400
    if len(topic) > 500:
        return jsonify({"error": "topic kepanjangan (maks 500 karakter)"}), 400
    try:
        rounds = int(data.get("rounds", 1))
    except Exception:
        rounds = 1
    rounds = max(1, min(3, rounds))
    if not llm_available():
        return jsonify({"error": "API key LLM belum di-set di Vercel → Settings → Environment Variables (KIE_RESPONSES_API_KEY / KIE_TEXT_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY). Rapat belum bisa jalan."}), 503
    try:
        result = run_meeting(topic, rounds)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Rapat gagal: {e}"}), 500

@app.route("/api/meetings", methods=["GET"])
def api_meetings():
    return jsonify(meeting_get_all(20))

@app.route("/api/meetings/<int:meeting_id>", methods=["GET"])
def api_meeting_detail(meeting_id):
    detail = meeting_get_detail(meeting_id)
    if not detail:
        return jsonify({"error": "meeting tidak ditemukan / storage tidak persisten"}), 404
    return jsonify(detail)

@app.route("/api/image", methods=["POST"])
def api_image():
    data = request.get_json(force=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt wajib diisi"}), 400
    if len(prompt) > 1000:
        return jsonify({"error": "prompt kepanjangan (maks 1000 karakter)"}), 400
    # Prefer KIE AI GPT Image (async: createTask -> poll recordInfo)
    kie_key = KIE_API_KEY or os.getenv("KIE_API_KEY", "").strip()
    if kie_key:
        try:
            r = requests.post(
                "https://api.kie.ai/api/v1/jobs/createTask",
                headers={"Authorization": f"Bearer {kie_key}", "Content-Type": "application/json"},
                json={"model": KIE_IMAGE_MODEL,
                      "input": {"prompt": prompt, "aspect_ratio": "1:1", "resolution": "1K", "background": "auto"}},
                timeout=60,
            )
            cj = r.json() if r.text else {}
            if r.status_code != 200 or cj.get("code") not in (None, 200):
                return jsonify({"error": f"KIE AI createTask error {r.status_code}: {cj.get('msg', r.text[:200])}"}), 502
            task_id = (cj.get("data") or {}).get("taskId")
            if not task_id:
                return jsonify({"error": "KIE AI tidak mengembalikan taskId", "debug": str(cj)[:300]}), 502
            import time as _t
            for _ in range(55):  # maks ~160 detik
                _t.sleep(3)
                q = requests.get(f"https://api.kie.ai/api/v1/jobs/recordInfo?taskId={task_id}",
                                 headers={"Authorization": f"Bearer {kie_key}"}, timeout=30)
                qj = q.json() if q.text else {}
                qdata = qj.get("data") or {}
                state = (qdata.get("state") or "").lower()
                if state == "success":
                    try:
                        urls = json.loads(qdata.get("resultJson") or "{}").get("resultUrls") or []
                    except Exception:
                        urls = []
                    if urls:
                        return jsonify({"image": urls[0], "task_id": task_id})
                    return jsonify({"error": "Gambar selesai tapi URL kosong", "debug": str(qdata)[:300]}), 502
                if state in ("fail", "failed", "error"):
                    return jsonify({"error": f"KIE AI gagal generate: {qdata.get('failMsg') or qdata.get('failCode') or 'unknown error'}"}), 502
            return jsonify({"error": "Timeout menunggu gambar dari KIE AI (task masih diproses, coba lagi nanti)", "task_id": task_id}), 504
        except Exception as e:
            return jsonify({"error": f"Gagal generate gambar: {e}"}), 500
    # Fallback: OpenRouter image model (OpenAI-compatible chat completions, modalities image+text)
    or_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "").strip()
    if or_key:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {or_key}", "Content-Type": "application/json",
                         "HTTP-Referer": "https://properti-pro-bot.vercel.app", "X-Title": "Azira Team Bot"},
                json={"model": os.getenv("OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"),
                      "messages": [{"role": "user", "content": prompt}],
                      "modalities": ["image", "text"]},
                timeout=180,
            )
            if r.status_code != 200:
                return jsonify({"error": f"OpenRouter Images error {r.status_code}: {r.text[:300]}"}), 502
            data = r.json()
            imgs = []
            try:
                imgs = data["choices"][0]["message"].get("images") or []
            except Exception:
                imgs = []
            for im in imgs:
                url = (im.get("image_url") or {}).get("url") if isinstance(im, dict) else None
                url = url or (im.get("imageUrl") or {}).get("url") if isinstance(im, dict) else url
                if url:
                    return jsonify({"image": url})
            return jsonify({"error": "Respons gambar kosong dari OpenRouter", "debug": str(data)[:300]}), 502
        except Exception as e:
            return jsonify({"error": f"Gagal generate gambar: {e}"}), 500
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return jsonify({"error": "Belum ada API key gambar. Set OPENROUTER_API_KEY (atau OPENAI_API_KEY) di Vercel → Settings → Environment Variables."}), 503
    try:
        r = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "n": 1},
            timeout=120,
        )
        if r.status_code != 200:
            return jsonify({"error": f"OpenAI Images API error {r.status_code}: {r.text[:300]}"}), 502
        img = (r.json().get("data") or [{}])[0]
        if img.get("b64_json"):
            return jsonify({"image": "data:image/png;base64," + img["b64_json"]})
        if img.get("url"):
            return jsonify({"image": img["url"]})
        return jsonify({"error": "Respons gambar kosong dari OpenAI"}), 502
    except Exception as e:
        return jsonify({"error": f"Gagal generate gambar: {e}"}), 500

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=auto_report_loop, daemon=True).start()
    print(f"[web] Dashboard jalan di port {PORT} - bot + web 1 otak", flush=True)
    app.run(host="0.0.0.0", port=PORT)
