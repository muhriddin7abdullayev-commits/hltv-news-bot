# HLTV → Telegram yangiliklar boti

Bu bot HLTV.org'ning rasmiy RSS lentasidan (`/rss/news`) yangiliklarni o'qib,
ularni sizning Telegram kanalingizga avtomatik post qiladi. To'g'ridan-to'g'ri
sahifani "scraping" qilish o'rniga RSS ishlatilgan, chunki:
- HLTV kabi saytlar Cloudflare himoyasi tufayli oddiy scraping'ni bloklab qo'yishi mumkin
- RSS rasmiy, barqaror va sayt dizayni o'zgarganda ham ishlayveradi

## 1-qadam: Telegram bot yaratish

1. Telegram'da **@BotFather** ga yozing
2. `/newbot` buyrug'ini yuboring, nom va username tanlang
3. Sizga beriladigan **tokenni** saqlab qo'ying (masalan: `123456:ABC-DEF...`)

## 2-qadam: Botni kanalga admin qilish

1. O'z Telegram kanalingizga o'ting → **Administrators** → botni admin qilib qo'shing
   (kamida "Post messages" huquqi bilan)
2. Kanal **chat_id**'sini bilish uchun:
   - Agar kanal public bo'lsa: shunchaki `@kanal_username` dan foydalansa bo'ladi
   - Agar private bo'lsa: kanalga bitta xabar yuboring, so'ng brauzerda quyidagi
     havolani oching (TOKEN o'rniga o'zingiznikini qo'ying):
     `https://api.telegram.org/botTOKEN/getUpdates`
     Natijada `"chat":{"id": -1001234567890, ...}` kabi raqamni topasiz — shu
     `chat_id` bo'ladi

## 3-qadam: Joylashtirish (hosting)

Sizga eng qulay va **bepul** variant — **GitHub Actions**. Doim ishlab turadigan
serverga (VPS) ehtiyoj qolmaydi, chunki GitHub o'zi belgilangan vaqt oralig'ida
(bu yerda har 15 daqiqada) kodni ishga tushirib beradi.

1. Ushbu papkani (`hltv_telegram_bot`) GitHub'da yangi **public yoki private repo**
   qilib yuklang
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**
   orqali quyidagi ikkita sirni qo'shing:
   - `TELEGRAM_BOT_TOKEN` — BotFather bergan token
   - `TELEGRAM_CHAT_ID` — kanal ID'si yoki `@username`
3. Shu bilan tamom — `.github/workflows/post_news.yml` avtomatik ishga tushadi
   va har 15 daqiqada yangi yangiliklarni tekshirib, topsa, kanalga post qiladi
4. Qo'lda sinab ko'rish uchun: repo'ning **Actions** bo'limiga kirib,
   "HLTV yangiliklarini Telegramga post qilish" → **Run workflow** tugmasini bosing

### Muqobil variant: o'z VPS'ingizda

Agar GitHub Actions o'rniga o'zingizning serveringizda (masalan, arzon $3-5/oy VPS)
ishlatmoqchi bo'lsangiz:

```bash
pip install -r requirements.txt  # bu loyihada tashqi kutubxona shart emas,
                                   # skript faqat Python standart kutubxonasidan foydalanadi
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="@kanal_username"
python3 post_news.py
```

Doimiy ishlashi uchun `cron` orqali har 15 daqiqada ishga tushirib turing:

```
*/15 * * * * cd /path/to/hltv_telegram_bot && /usr/bin/python3 post_news.py >> bot.log 2>&1
```

## Sozlamalar

`post_news.py` quyidagi muhit o'zgaruvchilarini qabul qiladi:

| O'zgaruvchi | Majburiymi | Izoh |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Ha | BotFather bergan token |
| `TELEGRAM_CHAT_ID` | Ha | Kanal ID yoki `@username` |
| `RSS_URL` | Yo'q | Standart: `https://www.hltv.org/rss/news` |
| `MAX_POSTS_PER_RUN` | Yo'q | Bitta ishga tushirishda nechta yangilik yuborilsin (standart: 5, spam bo'lmasligi uchun) |

## Fayllar

- `post_news.py` — asosiy skript
- `seen.json` — allaqachon post qilingan havolalar ro'yxati (takror post bo'lmasligi uchun)
- `.github/workflows/post_news.yml` — GitHub Actions orqali avtomatik ishga tushirish
