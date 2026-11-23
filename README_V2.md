# Azira v2 - Bot + Dashboard 1 Otak

## Cara Update Railway dari v1 ke v2
1. Di GitHub repo properti-pro-bot, upload / timpa file-file di folder ini (app.py, dashboard.html, requirements.txt, Procfile, railway.json)
   - HAPUS / JANGAN PAKAI lagi: bot.py lama (biar gak dobel). File yang jalan sekarang app.py.
2. Di Railway: Settings -> Networking -> Generate Domain (biar dapet link web https://xxx.up.railway.app)
   - Link ini = Dashboard Web lo yang baru, yang nyambung ke bot.
3. Variables tetap sama: TELEGRAM_BOT_TOKEN + ADMIN_CHAT_ID=7484848251
4. Railway akan redeploy otomatis. Cek Logs: harus ada "[web] Dashboard jalan" + "[bot] polling jalan..."
5. Buka link domain Railway -> Dashboard Web muncul.
6. Test 2 arah:
   - Web -> Telegram: tambah task di web, cek Telegram ada notif
   - Telegram -> Web: /tambah Test dari Telegram, Refresh web, muncul

## Penting
- Service di Railway harus jadi WEB (bukan worker lagi), karena Procfile sekarang "web: python app.py"
- Kalau di Railway masih ada service worker lama yang jalan, hapus / stop biar gak dobel bales.
- tasks.json di Railway itu ephemeral: kalau redeploy, data bisa ke-reset ke awal. Untuk produksi, nanti pindah ke database (Railway Postgres). Tapi buat sekarang, ini udah 2 arah beneran.
