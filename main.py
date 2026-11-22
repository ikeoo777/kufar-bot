import json
import os
import threading
import time
import requests

# ================= НАСТРОЙКИ =================
import os
BOT_TOKEN = os.getenv("9188876543:AAEOzCWu4CmyzIQpadRIFTuJ2q-Glctq4PQ")
CHAT_ID = "7445170187"

CHECK_INTERVAL = 10  # Проверка каждые 10 секунд

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "seen_ads.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

DEFAULT_KEYWORDS = [
    # === КРОССОВКИ ===
    "кроссовки", "nike air force", "nike dunk", "nike tn", "nike air max",
    "nike shox", "nike acg", "jordan 1", "jordan 4", "adidas campus",
    "adidas samba", "adidas spezial", "adidas gazelle", "new balance 550",
    "new balance 530", "new balance 2002r", "new balance 9060", "asics gel",
    "salomon xt", "vans knu skool", "vans sk8", "dc shoes", "osiris",
    "timberland", "dr martens",
    # === GORPCORE / OUTDOOR ===
    "the north face", "tnf", "arcteryx", "salomon", "patagonia",
    "napapijri", "helly hansen", "columbia",
    # === STREETWEAR / CASUAL / SKATE ===
    "carhartt", "stone island", "c.p. company", "stussy", "supreme",
    "ralph lauren", "fred perry", "lacoste", "dickies", "polar",
    "evisu", "true religion",
    # === МИДЛ / АРХИВ / ЛЮКС ===
    "diesel", "tommy hilfiger", "calvin klein", "balenciaga",
    "rick owens", "maison margiela",
]

DEFAULT_BLACKLIST = [
    "реплика", "копия", "под заказ", "люкс копия",
    "детские", "детская", "женские", "женская", "доставка из",
]
# =============================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

lock = threading.Lock()
seen_ads = {}
KEYWORDS = []
BLACKLIST = []
REGION = None
AREA = None


def load_data():
    global seen_ads, KEYWORDS, BLACKLIST
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                seen_ads = json.load(f)
        except Exception:
            seen_ads = {}

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                KEYWORDS = cfg.get("keywords", list(DEFAULT_KEYWORDS))
                BLACKLIST = cfg.get("blacklist", list(DEFAULT_BLACKLIST))
        except Exception:
            KEYWORDS = list(DEFAULT_KEYWORDS)
            BLACKLIST = list(DEFAULT_BLACKLIST)
    else:
        KEYWORDS = list(DEFAULT_KEYWORDS)
        BLACKLIST = list(DEFAULT_BLACKLIST)
        save_config()


def save_db():
    try:
        # Держим в базе до 5000 последних объявлений, чтобы файл не раздувался
        if len(seen_ads) > 5000:
            keys_to_drop = list(seen_ads.keys())[:-4000]
            for k in keys_to_drop:
                del seen_ads[k]
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_ads, f, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка сохранения базы: {e}")


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"keywords": KEYWORDS, "blacklist": BLACKLIST},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")


def send_telegram(text, image_url=None):
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": text,
                "parse_mode": "HTML",
            }
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def telegram_commands_loop():
    """Фоновый поток для приема команд из Telegram."""
    offset = None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset
            resp = requests.get(url, params=params, timeout=35)
            data = resp.json()
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                if str(msg.get("chat", {}).get("id", "")) != str(CHAT_ID):
                    continue
                text = msg.get("text", "").strip()
                if text:
                    handle_command(text)
        except Exception:
            time.sleep(5)


def handle_command(text):
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    with lock:
        if cmd == "/add" and arg:
            if arg not in KEYWORDS:
                KEYWORDS.append(arg)
                save_config()
                send_telegram(f"✅ Добавил в поиск: <b>{arg}</b>")
            else:
                send_telegram(f"ℹ️ <b>{arg}</b> уже есть в списке.")

        elif cmd == "/del" and arg:
            if arg in KEYWORDS:
                KEYWORDS.remove(arg)
                save_config()
                send_telegram(f"🗑 Удалил из поиска: <b>{arg}</b>")
            else:
                send_telegram(f"❌ Не нашел <b>{arg}</b> в списке.")

        elif cmd == "/ban" and arg:
            if arg not in BLACKLIST:
                BLACKLIST.append(arg)
                save_config()
                send_telegram(f"🚫 Добавил в минус-слова: <b>{arg}</b>")
            else:
                send_telegram(f"ℹ️ <b>{arg}</b> уже в минус-словах.")

        elif cmd == "/unban" and arg:
            if arg in BLACKLIST:
                BLACKLIST.remove(arg)
                save_config()
                send_telegram(f"✅ Убрал из минус-слов: <b>{arg}</b>")
            else:
                send_telegram(f"❌ Не нашел <b>{arg}</b> в минус-словах.")

        elif cmd == "/list":
            kw_str = ", ".join(KEYWORDS) if KEYWORDS else "пусто"
            bl_str = ", ".join(BLACKLIST) if BLACKLIST else "пусто"
            send_telegram(
                f"📋 <b>Поиск ({len(KEYWORDS)}):</b>\n{kw_str}\n\n"
                f"🚫 <b>Минус-слова ({len(BLACKLIST)}):</b>\n{bl_str}"
            )

        elif cmd in ("/help", "/start"):
            send_telegram(
                "🤖 <b>Команды управления:</b>\n"
                "<code>/add бренд</code> — добавить в поиск\n"
                "<code>/del бренд</code> — удалить из поиска\n"
                "<code>/ban слово</code> — добавить минус-слово\n"
                "<code>/unban слово</code> — убрать минус-слово\n"
                "<code>/list</code> — показать все списки"
            )


def detect_bobruisk_ids():
    url = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    params = {"query": "бобруйск", "lang": "ru", "size": 30}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        for ad in resp.json().get("ads", []):
            rgn, ar = None, None
            is_bobruisk = False
            for p in ad.get("ad_parameters", []):
                if p.get("p") == "region":
                    rgn = p.get("v")
                elif p.get("p") == "area":
                    ar = p.get("v")
                    if "бобруйск" in str(p.get("vl", "")).lower():
                        is_bobruisk = True
            if is_bobruisk and rgn and ar:
                return rgn, ar
    except Exception as e:
        print(f"Ошибка определения города: {e}")
    return None, None


def fetch_latest_ads():
    url = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    params = {"lang": "ru", "size": 40, "sort": "lst.d"}
    if REGION:
        params["rgn"] = REGION
    if AREA:
        params["ar"] = AREA

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("ads", [])
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return []


def check_title(title):
    """Возвращает найденный бренд или None (если не совпало или попало в бан)."""
    title_lower = title.lower()
    with lock:
        for bad in BLACKLIST:
            if bad in title_lower:
                return None
        for kw in KEYWORDS:
            if kw in title_lower:
                return kw
    return None


def parse_details(ad):
    """Вытаскивает размер и состояние из параметров объявления."""
    size_val = None
    cond_val = None
    for p in ad.get("ad_parameters", []):
        label = str(p.get("pl", "")).lower()
        val = p.get("vl")
        if not val:
            continue
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        if "размер" in label and not size_val:
            size_val = str(val)
        elif "состояние" in label and not cond_val:
            cond_val = str(val)

    parts = []
    if size_val:
        parts.append(f"📏 Размер: <b>{size_val}</b>")
    if cond_val:
        parts.append(f"🏷 Состояние: <b>{cond_val}</b>")
    return "\n".join(parts)


def parse_price(ad):
    raw_price = ad.get("price_byn")
    if not raw_price or raw_price == "0":
        return 0.0
    return int(raw_price) / 100


def get_image_url(ad):
    images = ad.get("images", [])
    if not images:
        return None
    img_path = images[0].get("path")
    if img_path:
        return f"https://rms.kufar.by/v1/gallery/{img_path}"
    return None


def main():
    global REGION, AREA
    load_data()

    # Запускаем поток для команд Telegram
    threading.Thread(target=telegram_commands_loop, daemon=True).start()

    print("Определяю ID Бобруйска...")
    REGION, AREA = detect_bobruisk_ids()
    if REGION and AREA:
        print(f"Нашел Бобруйск! (rgn={REGION}, ar={AREA})")
    else:
        print("Не удалось определить ID Бобруйска, мониторю всю Беларусь.")

    # Если база пустая (первый запуск) — запоминаем текущую ленту без спама
    if not seen_ads:
        for ad in fetch_latest_ads():
            ad_id = str(ad.get("ad_id", ""))
            if ad_id:
                seen_ads[ad_id] = parse_price(ad)
        save_db()

    print(f"Турбо-бот запущен! В базе {len(seen_ads)} объявлений.")
    send_telegram(
        f"⚡ <b>Турбо-бот запущен (Бобруйск)!</b>\n"
        f"В базе: {len(seen_ads)} объявлений.\n"
        f"Напиши /help чтобы увидеть команды управления."
    )

    while True:
        ads = fetch_latest_ads()
        db_changed = False

        for ad in ads:
            ad_id = str(ad.get("ad_id", ""))
            if not ad_id:
                continue

            title = ad.get("subject", "")
            matched_kw = check_title(title)
            if not matched_kw:
                continue

            price = parse_price(ad)
            link = ad.get("ad_link", "")
            img = get_image_url(ad)
            details = parse_details(ad)
            details_block = f"{details}\n" if details else ""
            price_str = f"{price:.2f} BYN" if price > 0 else "Договорная"

            # 1. Новое объявление
            if ad_id not in seen_ads:
                seen_ads[ad_id] = price
                db_changed = True
                msg = (
                    f"⚡ <b>Новое ({matched_kw})</b>\n\n"
                    f"📦 {title}\n"
                    f"{details_block}"
                    f"💰 <b>{price_str}</b>\n"
                    f"🔗 <a href='{link}'>Открыть на Куфаре</a>"
                )
                send_telegram(msg, img)
                print(f"[NEW] {title} — {price_str}")

            # 2. Снижение цены
            else:
                old_price = seen_ads[ad_id]
                if 0 < price < old_price:
                    diff = old_price - price
                    seen_ads[ad_id] = price
                    db_changed = True
                    msg = (
                        f"📉 <b>Снижение цены ({matched_kw})</b>\n\n"
                        f"📦 {title}\n"
                        f"{details_block}"
                        f"💸 Было: <s>{old_price:.2f} BYN</s>\n"
                        f"💰 Стало: <b>{price:.2f} BYN</b> (-{diff:.2f} BYN)\n"
                        f"🔗 <a href='{link}'>Открыть на Куфаре</a>"
                    )
                    send_telegram(msg, img)
                    print(f"[DROP] {title}: {old_price} -> {price}")

        if db_changed:
            save_db()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
