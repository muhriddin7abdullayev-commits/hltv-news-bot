#!/usr/bin/env python3
"""
CS2/Counter-Strike -> Telegram avtomatik yangiliklar boti.

Ishlash printsipi:
1. Google News'ning CS2/Counter-Strike bo'yicha qidiruv RSS lentasidan
   so'nggi yangiliklarni oladi (turli manbalardan: HLTV, Dust2, Dexerto va h.k.).
   To'g'ridan-to'g'ri HLTV.org'dan olish o'rniga shu yo'l tanlangan, chunki
   HLTV Cloudflare orqali bot so'rovlarini (shu jumladan GitHub Actions'ning
   datacenter IP'larini) qattiq bloklaydi — Google News esa bunday cheklov
   qo'ymaydi va barqaror ishlaydi.
2. Avval yuborilgan yangiliklarni seen.json faylida saqlab boradi, shunday
   qilib bir xil yangilik ikki marta post qilinmaydi.
3. Yangi topilgan har bir yangilikni belgilangan Telegram kanaliga yuboradi.

Ishga tushirish:
    python3 post_news.py

Muhit o'zgaruvchilari (environment variables) orqali sozlanadi:
    TELEGRAM_BOT_TOKEN  - @BotFather bergan bot tokeni
    TELEGRAM_CHAT_ID    - kanal ID'si yoki @kanal_username
    RSS_URL             - (ixtiyoriy) standart: https://www.hltv.org/rss/news
    MAX_POSTS_PER_RUN   - (ixtiyoriy) bitta ishga tushirishda nechta yangilik
                           yuborilsin, standart: 5 (spam bo'lib ketmasligi uchun)
"""

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

RSS_URL = os.environ.get(
    "RSS_URL",
    "https://news.google.com/rss/search?q=CS2+OR+%22Counter-Strike%22+"
    "(tournament+OR+match+OR+final+OR+playoffs+OR+beat+OR+defeat)"
    "&hl=en-US&gl=US&ceid=US:en",
)
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "5"))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen.json")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# HLTV Cloudflare orqasida turadi va oddiy User-Agent'ni ko'pincha bot deb
# bloklaydi (403). Haqiqiy brauzerga o'xshash to'liq header to'plami
# yuborish blok bo'lish ehtimolini kamaytiradi.
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.hltv.org/",
    "Connection": "keep-alive",
}


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen_links):
    # Fayl cheksiz o'smasligi uchun oxirgi 500 tasini saqlaymiz
    trimmed = list(seen_links)[-500:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def fetch_rss(url):
    """RSS'ni oladi. Avval to'g'ridan-to'g'ri, muvaffaqiyatsiz bo'lsa
    (masalan 403 Forbidden — Cloudflare GitHub'ning datacenter IP'sini
    bloklagan bo'lsa), ochiq proksi orqali qayta urinadi."""
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 429, 503):
            raise
        print(
            f"To'g'ridan-to'g'ri so'rov {exc.code} bilan qaytdi, "
            "proksi orqali qayta urinilmoqda...",
            file=sys.stderr,
        )
        proxy_url = "https://api.allorigins.win/raw?url=" + urllib.parse.quote(
            url, safe=""
        )
        proxy_req = urllib.request.Request(
            proxy_url, headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(proxy_req, timeout=30) as resp:
            return resp.read()


def strip_html(text):
    """RSS description ichidagi HTML teglarini olib tashlaydi."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def parse_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = strip_html(item.findtext("description") or "")
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append(
                {
                    "title": html.unescape(title),
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                }
            )
    return items


def translate_text(text, target_lang):
    """Matnni tarjima qiladi (Google'ning ochiq, API-kalitsiz tarjima
    endpoint'i orqali). Xato bo'lsa, asl matnni qaytaradi — bot to'xtab
    qolmasin uchun."""
    if not text:
        return ""
    try:
        params = urllib.parse.urlencode(
            {
                "client": "gtx",
                "sl": "auto",
                "tl": target_lang,
                "dt": "t",
                "q": text,
            }
        )
        url = f"https://translate.googleapis.com/translate_a/single?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Javob formati: [[["tarjima1","asl1",...], ["tarjima2","asl2",...], ...], ...]
        return "".join(segment[0] for segment in data[0] if segment[0])
    except Exception as exc:
        print(f"Tarjima xatosi ({target_lang}): {exc}", file=sys.stderr)
        return text


EXCLUDE_KEYWORDS = (
    "how to",
    "guide",
    "best settings",
    "best crosshair",
    "launch options",
    "tier list",
    "wallpaper",
    "release date",
    " tips",
    "callouts",
)

INCLUDE_KEYWORDS = (
    "beat",
    "defeat",
    "win",
    "wins",
    "won",
    "final",
    "playoff",
    "qualifier",
    "bracket",
    "champion",
    "tournament",
    "major",
    " vs ",
    "vs.",
    "match",
    "round",
    "advance",
    "eliminate",
    "upset",
    "result",
)


def is_match_result_news(title):
    """Faqat turnir/match natijalariga oid yangiliklarni qoldiradi;
    'qanday qilish', 'eng yaxshi sozlamalar' kabi qo'llanma
    maqolalarni chiqarib tashlaydi."""
    lowered = title.lower()
    if any(bad in lowered for bad in EXCLUDE_KEYWORDS):
        return False
    return any(good in lowered for good in INCLUDE_KEYWORDS)


def send_telegram_message(text):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram xatosi: {result}")
    return result


def format_message(item):
    title_uz = html.escape(translate_text(item["title"], "uz"))
    title_ru = html.escape(translate_text(item["title"], "ru"))
    desc_uz = html.escape(translate_text(item["description"], "uz"))
    desc_ru = html.escape(translate_text(item["description"], "ru"))
    link = html.escape(item["link"], quote=True)

    lines = [f"🇺🇿 <b>{title_uz}</b>"]
    if desc_uz:
        lines.append(desc_uz)

    lines.append("┈┈┈┈┈┈┈┈┈┈")

    lines.append(f"🇷🇺 <b>{title_ru}</b>")
    if desc_ru:
        lines.append(desc_ru)

    lines.append(f'\n🔗 <a href="{link}">To\'liq / Подробнее</a>')
    return "\n".join(lines)


def main():
    if not BOT_TOKEN or not CHAT_ID:
        print(
            "XATOLIK: TELEGRAM_BOT_TOKEN va TELEGRAM_CHAT_ID "
            "muhit o'zgaruvchilarini o'rnating.",
            file=sys.stderr,
        )
        sys.exit(1)

    seen = load_seen()

    try:
        xml_bytes = fetch_rss(RSS_URL)
    except Exception as exc:
        print(f"RSS'ni olishda xatolik: {exc}", file=sys.stderr)
        sys.exit(1)

    items = parse_items(xml_bytes)
    if not items:
        print("Hech qanday yangilik topilmadi (RSS bo'sh yoki formati o'zgargan).")
        return

    # RSS odatda yangidan eskiga tartiblangan bo'ladi; eng eski yangidan
    # boshlab yuboramiz, shunda kanalda xronologik tartib saqlanadi.
    unseen_items = [it for it in items if it["link"] not in seen]
    new_items = []
    for it in unseen_items:
        if is_match_result_news(it["title"]):
            new_items.append(it)
        else:
            # Mavzuga mos kelmaydi (guide/tips va h.k.) — post qilinmaydi,
            # lekin har safar qayta tekshirilmasligi uchun "seen" belgilanadi
            seen.add(it["link"])
    new_items.reverse()

    if not new_items:
        save_seen(seen)
        print("Yangi mos yangilik yo'q (filtr yoki yangilik yo'qligi sababli).")
        return

    posted = 0
    for item in new_items:
        if posted >= MAX_POSTS_PER_RUN:
            print(
                f"MAX_POSTS_PER_RUN ({MAX_POSTS_PER_RUN}) chegarasiga yetdi, "
                "qolganlari keyingi ishga tushirishda yuboriladi."
            )
            break
        try:
            send_telegram_message(format_message(item))
            print(f"Yuborildi: {item['title']}")
            seen.add(item["link"])
            posted += 1
            time.sleep(2)  # Telegram rate-limit'iga hurmat
        except Exception as exc:
            print(f"Yuborishda xatolik ({item['title']}): {exc}", file=sys.stderr)
            # Xato bo'lsa ham davom etamiz, lekin bu itemni 'seen' qilmaymiz
            # keyingi safar qayta urinib ko'radi

    save_seen(seen)
    print(f"Jami {posted} ta yangi yangilik post qilindi.")


if __name__ == "__main__":
    main()
