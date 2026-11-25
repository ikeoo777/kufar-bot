import html
import json
import os
import threading
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = "7445170187"  # Твой ID (управление ботом)
# ID закрытого VIP-канала (например: "-1001234567890").
# Если не задан в переменных Bothost — посты пойдут тебе в личку.
VIP_CHANNEL_ID = os.getenv("VIP_CHANNEL_ID", ADMIN_ID)

CHECK_INTERVAL = 12  # Пауза между циклами проверки (в секундах)

# ID категорий Куфара:
# 8040 — Мужская одежда
# 8060 — Мужская обувь
TARGET_CATEGORIES = ["8040", "8060"]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "seen_ads.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Словарь "бренд/ключ: максимальная цена в BYN" (0 = без лимита)
DEFAULT_BRANDS = {
    # === КРОССОВКИ И ОБУВЬ ===
    "nike air force": 150, "nike dunk": 160, "nike tn": 180,
    "nike air max": 150, "nike shox": 180, "nike acg": 180,
    "jordan 1": 180, "jordan 4": 220, "adidas campus": 140,
    "adidas samba": 140, "adidas spezial": 140, "adidas gazelle": 130,
    "new balance 550": 150, "new balance 530": 150, "new balance 2002r": 180,
    "new balance 9060": 200, "asics gel": 160, "salomon xt": 220,
    "vans knu skool": 130, "vans sk8": 110, "dc shoes": 120,
    "osiris": 160, "timberland": 180, "dr martens": 180,
    "jeremy scott": 250,

    # === GORPCORE / OUTDOOR ===
    "the north face": 180, "tnf": 180, "arcteryx": 280,
    "salomon": 180, "patagonia": 160, "napapijri": 150,
    "helly hansen": 150, "columbia": 130,

    # === STREETWEAR / CASUAL / SKATE ===
    "carhartt": 140, "stone island": 280, "c.p. company": 250,
    "c.p company": 250, "stussy": 150, "supreme": 180,
    "ralph lauren": 120, "fred perry": 120, "lacoste": 120,
    "dickies": 110, "polar": 130, "evisu": 180,
    "true religion": 160, "superdry": 120, "maison david": 150,

    # === МИДЛ / АРХИВ / ЛЮКС ===
    "diesel": 150, "tommy hilfiger": 120, "calvin klein": 120,
    "off-white": 300, "burberry": 300, "gucci": 350,
    "balenciaga": 400, "rick owens": 400, "maison margiela": 350,
    "archive": 200,

    # === ОБЩИЕ БРЕНДЫ И ФАСОНЫ (В КОНЦЕ, ЧТОБЫ НЕ ПЕРЕБИВАЛИ МОДЕЛИ) ===
    "puma": 100, "adidas": 100, "vans": 100,
    "baggy": 120, "бэгги": 120, "flared": 120, "клеш": 120,
    "джинс": 90, "зип": 100, "худи": 100, "кофт": 80, "толстовк": 90,
}

DEFAULT_BLACKLIST = [
    "реплика", "копия", "под заказ", "люкс копия", "1:1",
    "детские", "детская", "женские", "женская", "доставка из",
]
# =============================================

# Сессия с автоповторами (защита от таймаутов api.kufar.by)
session = requests.Session()
retries = Retry(total=3, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
})

lock = threading.Lock()
seen_ads = {}
BRANDS = {}
BLACKLIST = []


def load_data():
    global seen_ads, BRANDS, BLACKLIST
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
                if isinstance(cfg.get("brands"), dict):
                    BRANDS = cfg["brands"]
                else:
                    BRANDS = dict(DEFAULT_BRANDS)
                BLACKLIST = cfg.get("blacklist", list(DEFAULT_BLACKLIST))
        except Exception:
            BRANDS = dict(DEFAULT_BRANDS)
            BLACKLIST = list(DEFAULT_BLACKLIST)
    else:
        BRANDS = dict(DEFAULT_BRANDS)
        BLACKLIST = list(DEFAULT_BLACKLIST)
        save_config()


def save_db():
    try:
        if len(seen_ads) > 6000:
            keys_to_drop = list(seen_ads.keys())[:-4500]
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
                {"brands": BRANDS, "blacklist": BLACKLIST},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")


def send_telegram(chat_id, text, image_url=None, button_url=None):
    try:
        reply_markup = None
        if button_url:
            reply_markup = json.dumps({
                "inline_keyboard": [[{"text": "🔗 Открыть на Куфаре", "url": button_url}]]
            })

        if image_url:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
            payload = {
                "chat_id": chat_id,
                "photo": image_url,
                "caption": text,
                "parse_mode": "HTML",
            }
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        resp = session.post(url, data=payload, timeout=12)
        if not resp.ok:
            print(f"Ошибка Telegram API ({resp.status_code}): {resp.text}")
            if image_url:
                send_telegram(chat_id, text, image_url=None, button_url=button_url)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")


def create_one_time_invite():
    """Создает одноразовую ссылку-приглашение в VIP-канал."""
    if str(VIP_CHANNEL_ID) == str(ADMIN_ID):
        return None, "Сначала укажи VIP_CHANNEL_ID в переменных Bothost и добавь бота админом в канал."
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/createChatInviteLink"
        payload = {
            "chat_id": VIP_CHANNEL_ID,
            "member_limit": 1,
            "name": f"VIP_{int(time.time())}",
        }
        resp = session.post(url, data=payload, timeout=10).json()
        if resp.get("ok"):
            return resp["result"]["invite_link"], None
        return None, resp.get("description", "Неизвестная ошибка Telegram API")
    except Exception as e:
        return None, str(e)


def telegram_commands_loop():
    """Фоновый поток для приема команд админа."""
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
                if str(msg.get("chat", {}).get("id", "")) != str(ADMIN_ID):
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
            tokens = arg.rsplit(" ", 1)
            if len(tokens) == 2 and tokens[1].isdigit():
                brand, max_price = tokens[0].strip(), int(tokens[1])
            else:
                brand, max_price = arg, 0
            BRANDS[brand] = max_price
            save_config()
            limit_txt = f"до {max_price} BYN" if max_price > 0 else "без лимита"
            send_telegram(ADMIN_ID, f"✅ Добавил/обновил: <b>{brand}</b> ({limit_txt})")

        elif cmd == "/del" and arg:
            if arg in BRANDS:
                del BRANDS[arg]
                save_config()
                send_telegram(ADMIN_ID, f"🗑 Удалил: <b>{arg}</b>")
            else:
                send_telegram(ADMIN_ID, f"❌ Не нашел <b>{arg}</b> в списке.")

        elif cmd == "/ban" and arg:
            if arg not in BLACKLIST:
                BLACKLIST.append(arg)
                save_config()
                send_telegram(ADMIN_ID, f"🚫 В минус-слова: <b>{arg}</b>")

        elif cmd == "/unban" and arg:
            if arg in BLACKLIST:
                BLACKLIST.remove(arg)
                save_config()
                send_telegram(ADMIN_ID, f"✅ Убрал из бана: <b>{arg}</b>")

        elif cmd == "/invite":
            link, err = create_one_time_invite()
            if link:
                send_telegram(
                    ADMIN_ID,
                    f"🎟 <b>Одноразовая ссылка в VIP-канал:</b>\n<code>{link}</code>\n\n"
                    f"Сработает ровно для 1 человека."
                )
            else:
                send_telegram(ADMIN_ID, f"❌ Ошибка: {err}")

        elif cmd == "/list":
            lines = [f"• {b} (до {p} BYN)" if p > 0 else f"• {b}" for b, p in BRANDS.items()]
            bl_str = ", ".join(BLACKLIST) if BLACKLIST else "пусто"
            send_telegram(
                ADMIN_ID,
                f"📋 <b>Бренды ({len(BRANDS)}):</b>\n" + "\n".join(lines[:40]) +
                f"\n\n🚫 <b>Минус-слова ({len(BLACKLIST)}):</b>\n{bl_str}"
            )

        elif cmd in ("/help", "/start"):
            send_telegram(
                ADMIN_ID,
                "🤖 <b>Админка VIP-бота:</b>\n"
                "<code>/add бренд цена</code> — добавить/изменить лимит (пр: /add carhartt 130)\n"
                "<code>/del бренд</code> — удалить бренд\n"
                "<code>/ban слово</code> — добавить минус-слово\n"
                "<code>/unban слово</code> — убрать минус-слово\n"
                "<code>/invite</code> — создать одноразовую ссылку для клиента\n"
                "<code>/list</code> — текущие фильтры"
            )


def fetch_latest_ads():
    url = "https://api.kufar.by/search-api/v2/search/rendered-paginated"
    all_ads = []

    for cat_id in TARGET_CATEGORIES:
        params = {
            "lang": "ru",
            "size": 40,
            "sort": "lst.d",
            "cat": cat_id,
        }
        try:
            resp = session.get(url, params=params, timeout=12)
            resp.raise_for_status()
            ads = resp.json().get("ads", [])
            all_ads.extend(ads)
        except Exception as e:
            print(f"Ошибка запроса категории {cat_id}: {e}")
        time.sleep(0.5)

    print(f"[DEBUG] Получено от Kufar: {len(all_ads)} объявлений")
    return all_ads


def match_ad(ad, price):
    """Проверяет заголовок + характеристики (бренд), бан-лист и лимит цены."""
    title = ad.get("subject", "")
    params_text = " ".join(
        str(p.get("vl", "")) for p in ad.get("ad_parameters", []) if p.get("vl")
    )
    searchable = f"{title} {params_text}".lower()

    with lock:
        for bad in BLACKLIST:
            if bad in searchable:
                return None
        for brand, max_price in BRANDS.items():
            if brand in searchable:
                if max_price > 0 and price > max_price:
                    continue
                return brand
    return None


def parse_details(ad):
    """Вытаскивает город, размер и состояние."""
    city = None
    size_val = None
    cond_val = None

    for p in ad.get("ad_parameters", []):
        p_key = p.get("p", "")
        label = str(p.get("pl", "")).lower()
        val = p.get("vl")
        if not val:
            continue
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        if p_key == "area" and not city:
            city = str(val)
        elif "размер" in label and not size_val:
            size_val = str(val)
        elif "состояние" in label and not cond_val:
            cond_val = str(val)

    parts = []
    if city:
        parts.append(f"📍 Город: <b>{html.escape(city)}</b>")
    if size_val:
        parts.append(f"📏 Размер: <b>{html.escape(size_val)}</b>")
    if cond_val:
        parts.append(f"🏷 Состояние: <b>{html.escape(cond_val)}</b>")
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
    load_data()
    threading.Thread(target=telegram_commands_loop, daemon=True).start()

    if not seen_ads:
        for ad in fetch_latest_ads():
            ad_id = str(ad.get("ad_id", ""))
            if ad_id:
                seen_ads[ad_id] = parse_price(ad)
        save_db()

    mode = "VIP-канал" if str(VIP_CHANNEL_ID) != str(ADMIN_ID) else "Тест (в личку)"
    print(f"V2 бот запущен! Режим: {mode}. В базе: {len(seen_ads)}")
    send_telegram(
        ADMIN_ID,
        f"⚡ <b>VIP-бот V2 запущен (Мужской шмот • Вся РБ)!</b>\n"
        f"Режим: <b>{mode}</b>\n"
        f"В базе: {len(seen_ads)} объявлений.\n"
        f"Жми /help для управления."
    )

    while True:
        ads = fetch_latest_ads()
        db_changed = False

        for ad in ads:
            ad_id = str(ad.get("ad_id", ""))
            if not ad_id:
                continue

            title = ad.get("subject", "")
            safe_title = html.escape(title)
            price = parse_price(ad)
            matched_brand = match_ad(ad, price)
            if not matched_brand:
                continue

            link = ad.get("ad_link", "")
            img = get_image_url(ad)
            details = parse_details(ad)
            details_block = f"{details}\n" if details else ""
            price_str = f"{price:.2f} BYN" if price > 0 else "Договорная"

            if ad_id not in seen_ads:
                seen_ads[ad_id] = price
                db_changed = True
                msg = (
                    f"🔥 <b>НАХОДКА • {html.escape(matched_brand.upper())}</b>\n\n"
                    f"📦 {safe_title}\n"
                    f"{details_block}"
                    f"💰 <b>{price_str}</b>"
                )
                send_telegram(VIP_CHANNEL_ID, msg, img, button_url=link)
                print(f"[NEW] {title} — {price_str}")

            else:
                old_price = seen_ads[ad_id]
                if 0 < price < old_price:
                    diff = old_price - price
                    seen_ads[ad_id] = price
                    db_changed = True
                    msg = (
                        f"📉 <b>СКИДКА • {html.escape(matched_brand.upper())}</b>\n\n"
                        f"📦 {safe_title}\n"
                        f"{details_block}"
                        f"💸 Было: <s>{old_price:.2f} BYN</s>\n"
                        f"💰 Стало: <b>{price_str}</b> (-{diff:.2f} BYN)"
                    )
                    send_telegram(VIP_CHANNEL_ID, msg, img, button_url=link)
                    print(f"[DROP] {title}: {old_price} -> {price}")

        if db_changed:
            save_db()

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
