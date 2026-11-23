# Deploy ke Railway - Properti Pro Bot (Azira Team)

## 1. Upload ke GitHub (5 menit)
1. Buka github.com -> New repository -> nama: properti-pro-bot -> Public -> Create
2. Klik "uploading an existing file" -> drag SEMUA file dari folder ini (bot.py, requirements.txt, Procfile, railway.json, tasks.json)
   - JANGAN upload token.txt / .env
3. Klik Commit

## 2. Deploy di Railway
1. Buka railway.app -> Login with GitHub
2. New Project -> Deploy from GitHub repo -> pilih properti-pro-bot
3. Railway akan otomatis detect Python + install requirements.txt
4. Tunggu sampai status Building -> Active

## 3. Isi Token (PENTING - jangan di kode!)
1. Di Railway, klik project lo -> Variables -> New Variable
2. Name: TELEGRAM_BOT_TOKEN
   Value: [paste token BARU dari @BotFather, yang sudah di-revoke dari yang bocor]
3. Name: ADMIN_CHAT_ID
   Value: 9141485270
4. Klik Deploy / Redeploy

## 4. Test
- Buka Telegram -> Properti Pro -> kirim /start
- Harus langsung dibales, walau laptop lo MATI
- Cek Logs di Railway kalau error: Deployments -> View Logs

## Kenapa harus revoke dulu?
Token lama lo pernah ke-screenshot dan kebaca di chat ini. Kalau tidak di-revoke, orang lain bisa ambil alih bot lo.
@BotFather -> /mybots -> Properti Pro -> API Token -> Revoke current token -> copy yang baru.

## Matikan bot di laptop
Setelah Railway jalan, tutup CMD di laptop lo. Kalau CMD laptop masih jalan + Railway juga jalan, bot akan dobel bales (2x reply). Matikan salah satu.
