
"""
Properti Pro Bot - VERSI TELEBOT (No Asyncio, Works di Python 3.14)
Gak ada lagi error 'no current event loop'. Dijamin jalan.
"""
import json, os, telebot
from datetime import datetime, timedelta

# Railway: token WAJIB dari Environment Variable TELEGRAM_BOT_TOKEN
# Jangan taro token di kode! Set di Railway Dashboard -> Variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "9141485270")
DATA_FILE = "tasks.json"

if not TOKEN:
    print("="*60)
    print("TOKEN BELUM DIISI!")
    print("Set TELEGRAM_BOT_TOKEN di Railway Dashboard -> Variables.")
    print("="*60)
    raise SystemExit

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

TEAM = {
    "Nara": "Content Writer AI",
    "Vino": "Graphic Designer AI",
    "Saka": "Video Editor AI",
    "Riko": "Customer Service AI",
    "Luma": "Data Analyst AI",
    "Ara": "Social Media Manager AI",
}

def load_tasks():
    if not os.path.exists(DATA_FILE):
        return [
            {"id": 1, "title": "Design Website EEX", "assignee": "Vino", "project": "EEX Indo", "status": "doing", "priority": "Tinggi", "deadline": "2026-11-25"},
            {"id": 2, "title": "Konten Listing Larangan Tangerang", "assignee": "Nara", "project": "Jurnal Rumah", "status": "todo", "priority": "Tinggi", "deadline": "2026-11-24"},
            {"id": 3, "title": "Edit Video Cluster 2 Lantai Ciputat", "assignee": "Saka", "project": "Ciputat", "status": "doing", "priority": "Sedang", "deadline": "2026-11-26"},
        ]
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_tasks(t):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2, ensure_ascii=False)

def fmt(t):
    e = {"todo": "📌", "doing": "🔄", "done": "✅"}.get(t["status"], "📌")
    return f"{e} #{t['id']} {t['title']}\n   👤 {t['assignee']} • 📁 {t['project']} • ⏰ {t['deadline']}"

@bot.message_handler(commands=["start", "help"])
def start(m):
    bot.reply_to(m,
        f"Halo {m.from_user.first_name}! 👋\n\n"
        f"Gw <b>Properti Pro Bot</b> - Azira Team lo. <b>UDAH JALAN!</b> 🎉\n\n"
        f"Chat ID lo: <code>{m.chat.id}</code>\n\n"
        f"/task - Lihat task hari ini\n"
        f"/tambah [judul] - Tambah task\n"
        f"/done [id] - Selesaikan task\n"
        f"/laporan - Laporan harian\n"
        f"/team - Lihat tim AI\n"
        f"/id - Lihat Chat ID\n\n"
        f"Coba kirim /task sekarang!"
    )

@bot.message_handler(commands=["id"])
def cmd_id(m):
    bot.reply_to(m, f"🆔 Chat ID lo: <code>{m.chat.id}</code>")

@bot.message_handler(commands=["task"])
def cmd_task(m):
    tasks = [t for t in load_tasks() if t["status"] != "done"]
    if not tasks:
        bot.reply_to(m, "🎉 Semua task beres!")
        return
    bot.reply_to(m, f"📋 <b>Task Aktif ({len(tasks)})</b>\n\n" + "\n\n".join(fmt(t) for t in tasks))

@bot.message_handler(commands=["tambah"])
def cmd_tambah(m):
    title = m.text.replace("/tambah", "").strip()
    if not title:
        bot.reply_to(m, "Caranya: <code>/tambah Design thumbnail Ciputat</code>")
        return
    tasks = load_tasks()
    nid = max([t["id"] for t in tasks], default=0) + 1
    nt = {"id": nid, "title": title, "assignee": "Nara", "project": "Properti Pro", "status": "todo", "priority": "Sedang", "deadline": (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d")}
    tasks.append(nt); save_tasks(tasks)
    bot.reply_to(m, f"📌 <b>Task baru dibuat!</b>\n\n{fmt(nt)}")

@bot.message_handler(commands=["done"])
def cmd_done(m):
    parts = m.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        bot.reply_to(m, "Caranya: <code>/done 1</code>")
        return
    tid = int(parts[1])
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == tid:
            t["status"] = "done"; save_tasks(tasks)
            bot.reply_to(m, f"✅ <b>Beres!</b>\n\n{fmt(t)}")
            return
    bot.reply_to(m, f"Task #{tid} gak ketemu. Cek /task dulu.")

@bot.message_handler(commands=["laporan"])
def cmd_laporan(m):
    tasks = load_tasks()
    done = len([t for t in tasks if t["status"]=="done"])
    doing = len([t for t in tasks if t["status"]=="doing"])
    todo = len([t for t in tasks if t["status"]=="todo"])
    txt = f"📊 <b>Laporan Harian - {datetime.now().strftime('%d %B %Y')}</b>\n\nTotal: {len(tasks)} • ✅ {done} • 🔄 {doing} • 📌 {todo}\n\n<b>Per Karyawan AI:</b>\n"
    for name, role in TEAM.items():
        mine = [t for t in tasks if t["assignee"]==name]
        md = len([t for t in mine if t["status"]=="done"])
        txt += f"• {name} ({role}): {md}/{len(mine)} selesai\n"
    bot.reply_to(m, txt)

@bot.message_handler(commands=["team"])
def cmd_team(m):
    tasks = load_tasks()
    txt = "👥 <b>Tim Karyawan AI Lo</b>\n\n"
    for name, role in TEAM.items():
        mine = [t for t in tasks if t["assignee"]==name]
        txt += f"<b>{name}</b> - {role} • Task aktif: {len([t for t in mine if t['status']!='done'])}\n"
    bot.reply_to(m, txt)

@bot.message_handler(func=lambda m: True)
def fallback(m):
    txt = m.text.lower()
    if "task" in txt or "kerjaan" in txt:
        cmd_task(m)
    elif "laporan" in txt or "rekap" in txt:
        cmd_laporan(m)
    elif "halo" in txt or "hai" in txt or "hi" in txt:
        bot.reply_to(m, "Halo! 👋 Ketik /task buat liat kerjaan hari ini.")
    else:
        bot.reply_to(m, "Gw belum paham 😅 Coba /help")

if __name__ == "__main__":
    print("="*60)
    print("🤖 Properti Pro Bot JALAN! (Versi Telebot - Python 3.14 Aman)")
    print("Buka Telegram -> Properti Pro -> kirim /start")
    print("Tekan Ctrl+C buat berhenti")
    print("="*60)
    bot.infinity_polling(skip_pending=True)
