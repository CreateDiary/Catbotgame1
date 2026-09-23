import asyncio
import aiosqlite
import time
import random
import os
import hashlib

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties

# ==================== НАСТРОЙКИ ====================
# ⚠️ Токен читается из переменной окружения BOT_TOKEN.
# В Dockhost: Настройки → Переменные → BOT_TOKEN=твой_токен
BOT_TOKEN = os.getenv("BOT_TOKEN", "8859558366:AAEeHrjzunYXIHCW2b4kjSZXPQmb3-Xm_hM")

ADMIN_IDS = [5965370780, 6137912809]
CONTACT_USERNAME = "Artemchic2009"
CONTACT_USERNAME_2 = "Andrkaop"
BOT_NAME = "Cat Clicker"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан! Добавь переменную окружения.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
SPAM_WINDOW = 10
SPAM_LIMIT = 15
BAN_DURATION = 86400
NAME_COOLDOWN = 86400
NAME_MAX_LEN = 20
NAME_MIN_LEN = 2
COMPLAINT_COOLDOWN = 3600
COMP_AMOUNT = 10000
CHECK_NAME_INTERVAL = 300

SHOP = {
    "food10": {"title": "🍖 Корм x10", "coins": 200, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "coins": 500, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "coins": 2000, "desc": "Пассивный доход +10/час"},
}

SKINS = {
    "default": {"emoji": "🐱", "name": "Обычный кот", "coins": 0},
    "cat":     {"emoji": "🐈", "name": "Кошка", "coins": 0},
    "black":   {"emoji": "🐈‍⬛", "name": "Чёрный кот", "coins": 0},
    "fox":     {"emoji": "🦊", "name": "Рыжий", "coins": 100},
    "tiger":   {"emoji": "🐯", "name": "Тигр", "coins": 250},
    "lion":    {"emoji": "🦁", "name": "Лев", "coins": 400},
    "leopard": {"emoji": "🐆", "name": "Пантера", "coins": 600},
    "bear":    {"emoji": "🐻", "name": "Медведь", "coins": 800},
    "panda":   {"emoji": "🐼", "name": "Панда", "coins": 1000},
    "wolf":    {"emoji": "🐺", "name": "Волк", "coins": 1300},
    "unicorn": {"emoji": "🦄", "name": "Единорог", "coins": 1800},
    "dragon":  {"emoji": "🐉", "name": "Дракон", "coins": 2500},
    "king":    {"emoji": "👑", "name": "Королевский", "coins": 3000},
    "robot":   {"emoji": "🤖", "name": "Кот-робот", "coins": 3500},
    "cosmo":   {"emoji": "🚀", "name": "Космо-кот", "coins": 4000},
    "ghost":   {"emoji": "👻", "name": "Призрак", "coins": 4500},
    "fire":    {"emoji": "🔥", "name": "Огненный", "coins": 5000},
}

active_games = {}
spam_tracker = {}
banned_users = {}
awaiting_name = {}
awaiting_complaint = {}
last_known_name = {"value": BOT_NAME}


# ==================== БД ====================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cats (
                user_id INTEGER PRIMARY KEY,
                name TEXT DEFAULT 'Барсик',
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                coins INTEGER DEFAULT 0,
                satiety INTEGER DEFAULT 100,
                last_feed INTEGER DEFAULT 0,
                boost_until INTEGER DEFAULT 0,
                vip INTEGER DEFAULT 0,
                last_daily INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_seen INTEGER DEFAULT 0,
                banned_until INTEGER DEFAULT 0,
                current_skin TEXT DEFAULT 'default',
                last_name_change INTEGER DEFAULT 0,
                strikes INTEGER DEFAULT 0,
                last_complaint INTEGER DEFAULT 0,
                compensation_given INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_skins (
                user_id INTEGER, skin_key TEXT, purchased_at INTEGER,
                PRIMARY KEY (user_id, skin_key)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER, action TEXT, target_id INTEGER,
                details TEXT, created_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER, reported_user TEXT, reason TEXT,
                created_at INTEGER, processed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, action TEXT, details TEXT,
                ip_hash TEXT, created_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT, severity TEXT, details TEXT, created_at INTEGER
            )
        """)
        await db.commit()


async def log_event(user_id, action, details="", ip_hash=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO logs(user_id, action, details, ip_hash, created_at) VALUES(?,?,?,?,?)",
                (user_id, action, str(details)[:500], ip_hash, int(time.time()))
            )
            await db.commit()
    except Exception:
        pass


async def log_security(event, severity, details=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO security(event, severity, details, created_at) VALUES(?,?,?,?)",
                (event, severity, str(details)[:500], int(time.time()))
            )
            await db.commit()
        if severity in ("high", "critical"):
            for admin in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin,
                        f"🚨 <b>SECURITY ALERT</b>\n\n"
                        f"⚡️ Событие: <b>{event}</b>\n"
                        f"🎯 Уровень: <b>{severity}</b>\n\n"
                        f"📝 {details}\n\n"
                        f"⏱ {time.strftime('%H:%M:%S')}"
                    )
                except Exception:
                    pass
    except Exception:
        pass


async def get_cat(user_id):
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM cats WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO cats(user_id) VALUES(?)", (user_id,))
            await db.commit()
            cur = await db.execute("SELECT * FROM cats WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
        return row


async def update_cat(user_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DB) as db:
        await db.execute(f"UPDATE cats SET {keys} WHERE user_id=?", vals)
        await db.commit()


async def get_user_skins(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT skin_key FROM user_skins WHERE user_id=?", (user_id,))
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def add_user_skin(user_id, skin_key):
    async with aiosqlite.connect(DB) as db:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO user_skins(user_id, skin_key, purchased_at) VALUES(?,?,?)",
                (user_id, skin_key, int(time.time()))
            )
            await db.commit()
        except Exception:
            pass


async def set_current_skin(user_id, skin_key):
    await update_cat(user_id, current_skin=skin_key)


async def log_admin_action(admin_id, action, target_id=None, details=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO admin_actions(admin_id, action, target_id, details, created_at) VALUES(?,?,?,?,?)",
                (admin_id, action, target_id, str(details)[:500], int(time.time()))
            )
            await db.commit()
        await log_event(admin_id, f"admin_{action}", details)
    except Exception:
        pass


# ==================== БАН / СПАМ ====================
def is_banned(user_id):
    until = banned_users.get(user_id, 0)
    if until > int(time.time()):
        return True
    if until and until <= int(time.time()):
        banned_users.pop(user_id, None)
    return False


def track_spam(user_id):
    now = time.time()
    times = [t for t in spam_tracker.get(user_id, []) if now - t < SPAM_WINDOW]
    times.append(now)
    spam_tracker[user_id] = times
    return len(times) >= SPAM_LIMIT


async def auto_ban(user_id, reason="спам"):
    until = int(time.time()) + BAN_DURATION
    banned_users[user_id] = until
    await log_security("auto_ban", "high", f"Юзер {user_id} забанен. Причина: {reason}")
    try:
        await bot.send_message(user_id, f"🚫 <b>Ты забанен на 24 часа.</b>\nПричина: {reason}")
    except Exception:
        pass
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, f"🚫 Автобан: <code>{user_id}</code>\nПричина: {reason}")
        except Exception:
            pass


class SecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            if is_banned(user.id):
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 Ты забанен.", reply_markup=ReplyKeyboardRemove())
                    except Exception:
                        pass
                return

            if isinstance(event, Message):
                if track_spam(user.id):
                    await auto_ban(user.id, "спам")
                    return
                text = event.text or ""
                await log_event(user.id, "msg", text[:100])

            if isinstance(event, Message):
                text = event.text or ""
                if text.startswith("/"):
                    cmd = text.split()[0].lower()
                    admin_cmds = ["/ban", "/unban", "/give_all", "/comp_give", "/broadcast",
                                  "/stats", "/logs", "/security", "/admins", "/admin_log",
                                  "/complaints", "/set_bot_name", "/reset"]
                    if cmd in admin_cmds and user.id not in ADMIN_IDS:
                        await log_security("unauthorized_cmd", "high",
                            f"Юзер {user.id} пытался использовать {cmd}")
                        return

            try:
                await update_cat(user.id, last_seen=int(time.time()))
            except Exception:
                pass
        return await handler(event, data)


# ==================== ИГРОВАЯ ЛОГИКА ====================
def xp_for_next(level):
    return level * 100


async def add_xp(user_id, amount):
    cat = await get_cat(user_id)
    xp = cat["xp"] + amount
    level = cat["level"]
    leveled = False
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
        leveled = True
    await update_cat(user_id, xp=xp, level=level)
    return leveled, level


def is_boost(cat):
    return cat["boost_until"] > int(time.time())


def is_vip(cat):
    return cat["vip"] == 1


def bonus_available(cat):
    return int(time.time()) - cat["last_daily"] >= DAILY_COOLDOWN


def skin_emoji(skin_key):
    s = SKINS.get(skin_key)
    return s["emoji"] if s else "🐱"


def render(cat, skin_key="default"):
    name = cat["name"]
    level = cat["level"]
    xp = cat["xp"]
    coins = cat["coins"]
    satiety = cat["satiety"]
    boost_until = cat["boost_until"]
    vip = cat["vip"]
    last_daily = cat["last_daily"]
    streak = cat["streak"]
    boost = "⚡" if boost_until > int(time.time()) else ""
    crown = "👑" if vip else ""
    bar_filled = min(10, satiety // 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    need = xp_for_next(level)
    fire = f" 🔥x{streak}" if streak > 1 else ""
    em = skin_emoji(skin_key)
    if bonus_available(cat):
        bonus_line = "🎁 Бонус дня: <b>доступен!</b>"
    else:
        left = DAILY_COOLDOWN - (int(time.time()) - last_daily)
        h = left // 3600
        m = (left % 3600) // 60
        bonus_line = f"🎁 Бонус дня: через {h}ч {m}м"
    return (
        f"{em} {crown} <b>{name}</b> {boost}{fire}\n"
        f"Уровень: <b>{level}</b>  (XP: {xp}/{need})\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"🍽 Сытость: [{bar}] {satiety}%\n"
        f"{bonus_line}"
    )


async def render_user(user_id):
    cat = await get_cat(user_id)
    return render(cat, cat["current_skin"])


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня", callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
         InlineKeyboardButton(text="🎨 Скины", callback_data="skins_menu")],
        [InlineKeyboardButton(text="✏️ Имя", callback_data="rename"),
         InlineKeyboardButton(text="🚧 Скоро", callback_data="soon")],
        [InlineKeyboardButton(text="🎁 Компенсация", callback_data="compensation")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def shop_kb():
    rows = []
    for key, item in SHOP.items():
        rows.append([InlineKeyboardButton(
            text=f"{item['title']} — {item['coins']} 💰",
            callback_data=f"buy:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skins_kb(owned, current):
    rows = []
    for key, s in SKINS.items():
        if key in owned:
            mark = "✅" if key == current else "👈"
            rows.append([InlineKeyboardButton(
                text=f"{s['emoji']} {s['name']} {mark}",
                callback_data=f"select_skin:{key}"
            )])
        else:
            rows.append([InlineKeyboardButton(
                text=f"{s['emoji']} {s['name']} — {s['coins']} 💰",
                callback_data=f"buy_skin:{key}"
            )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="rename")],
        [InlineKeyboardButton(text="🎨 Скины", callback_data="skins_menu")],
        [InlineKeyboardButton(text="🎁 Компенсация", callback_data="compensation")],
        [InlineKeyboardButton(text="🚧 Что скоро", callback_data="soon")],
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="complaint")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def complaint_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="complaint_send")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="complaint_cancel")],
    ])


def complaint_admin_kb(cid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Обработать", callback_data=f"cmp_done:{cid}")],
        [InlineKeyboardButton(text="🚫 Забанить", callback_data=f"cmp_ban:{cid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cmp_reject:{cid}")],
    ])


def bottom_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍖 Покормить"), KeyboardButton(text="🎾 Поиграть")],
            [KeyboardButton(text="🎲 Угадай"), KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎨 Скины")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="✏️ Имя")],
            [KeyboardButton(text="🎁 Компенсация"), KeyboardButton(text="🚧 Скоро")],
            [KeyboardButton(text="🚨 Жалоба"), KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ==================== ТЕКСТЫ ====================
HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Cat Clicker — игра-тамагочи.</b>\n"
    "Корми, играй, качай уровень, покупай скины.\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить • 🎾 Поиграть • 🎲 Угадай\n"
    "🎁 Бонус дня • 🛒 Магазин • 🎨 Скины\n"
    "👤 Профиль • ✏️ Имя • 🎁 Компенсация\n"
    "🚨 Жалоба • ❓ Помощь\n\n"
    "<b>📋 Команды:</b>\n"
    "/start /menu /daily /soon /help\n"
    "/compensation /complaint /refund\n"
    "/terms /hide"
)

TERMS_TEXT = (
    "📜 <b>Условия</b>\n\n"
    "1. Игра-тамагочи.\n"
    "2. Монеты — без денежной ценности.\n"
    "3. Возврат Stars — /refund, 7 дней.\n"
    "4. Спам запрещён — бан.\n"
    "5. Право менять условия."
)

SUPPORT_TEXT = (
    f"🆘 <b>Поддержка</b>\n\n"
    f"@{CONTACT_USERNAME}\n"
    f"@{CONTACT_USERNAME_2}\n\n"
    f"⏱ Отвечаем 24 часа."
)

SOON_TEXT = (
    "🚧 <b>Скоро</b>\n\n"
    "🏆 Топ игроков\n"
    "🤝 Рефералка\n"
    "⚔️ Дуэли котиков\n"
    "🎉 Ивенты\n"
    "🎨 Больше скинов\n\n"
    "🐾 Следи за обновлениями!"
)

RENAME_TEXT = (
    "✏️ <b>Смена имени</b>\n\n"
    "Отправь новое имя.\n\n"
    "2-20 символов. 1 раз в 24 часа.\n\n"
    "❌ Отмена — /cancel"
)

COMPLAINT_STEP1 = "🚨 <b>Жалоба 1/2</b>\n\nНа кого жалуешься? Напиши @username или ID.\n\n❌ /cancel"
COMPLAINT_STEP2 = "🚨 <b>Жалоба 2/2</b>\n\nОпиши проблему.\n\n❌ /cancel"


# ==================== АНИМАЦИЯ ====================
async def _animate(target, frames, delay=0.4):
    msg = None
    if isinstance(target, CallbackQuery):
        msg = target.message
    elif isinstance(target, Message):
        msg = await target.answer(frames[0])
    if msg is None:
        return None
    for frame in frames[1:]:
        try:
            await msg.edit_text(frame)
        except Exception:
            pass
        await asyncio.sleep(delay)
    return msg


# ==================== ИГРОВЫЕ ДЕЙСТВИЯ ====================
async def _do_feed(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat["last_feed"] < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - cat["last_feed"])
        msg_text = f"Подожди {left} сек 🍽"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=False)

    anim = await _animate(target, [
        "🍖 Кормим котика.", "🍖 Кормим котика..",
        "🍖 Кормим котика...", "😋 Котик кушает..."
    ])
    coins_gain = random.randint(5, 15)
    if is_boost(cat): coins_gain *= 2
    if is_vip(cat): coins_gain += 5

    await update_cat(
        user_id,
        coins=cat["coins"] + coins_gain,
        satiety=min(100, cat["satiety"] + 20),
        last_feed=now
    )
    leveled, level = await add_xp(user_id, 10)
    await log_event(user_id, "feed", f"+{coins_gain}")

    txt = f"🍖 +{coins_gain} монет!"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    if anim:
        try:
            await anim.edit_text(full, reply_markup=main_kb())
        except Exception:
            await anim.edit_text(full)
    elif isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    if isinstance(target, CallbackQuery):
        await target.answer()


async def _do_play(user_id, target):
    cat = await get_cat(user_id)
    if cat["satiety"] < 10:
        msg_text = "Котик слишком голодный 😿 Сначала покорми!"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    anim = await _animate(target, [
        "🎾 Играем с котиком.", "🎾 Играем с котиком..",
        "🎾 Играем с котиком...", "😺 Котик веселится!"
    ])
    coins_gain = random.randint(10, 25)
    if is_boost(cat): coins_gain *= 2

    await update_cat(
        user_id,
        coins=cat["coins"] + coins_gain,
        satiety=max(0, cat["satiety"] - 10)
    )
    leveled, level = await add_xp(user_id, 20)
    await log_event(user_id, "play", f"+{coins_gain}")

    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    if anim:
        try:
            await anim.edit_text(full, reply_markup=main_kb())
        except Exception:
            await anim.edit_text(full)
    elif isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    if isinstance(target, CallbackQuery):
        await target.answer()


async def _do_daily(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    last = cat["last_daily"]
    streak = cat["streak"]

    if now - last < DAILY_COOLDOWN:
        left = DAILY_COOLDOWN - (now - last)
        h = left // 3600
        m = (left % 3600) // 60
        msg_text = f"⏰ Бонус уже получен. Следующий через <b>{h}ч {m}м</b>"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    if 0 < last and now - last < DAILY_COOLDOWN * 2:
        streak += 1
    else:
        streak = 1

    bonus = 50 + (streak - 1) * 15
    if streak >= 7: bonus += 100
    if is_vip(cat): bonus *= 2

    await update_cat(user_id, coins=cat["coins"] + bonus, last_daily=now, streak=streak)
    leveled, level = await add_xp(user_id, 20)
    await log_event(user_id, "daily", f"+{bonus}")

    txt = f"🎁 <b>Бонус выдан!</b>\n\n💰 +<b>{bonus} монет</b>\n🔥 Стрик: <b>{streak}</b>"
    if streak >= 7: txt += "\n🎉 <b>Неделя подряд! +100 монет!</b>"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"

    full = await render_user(user_id) + "\n\n" + txt
    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        await target.message.answer(full, reply_markup=bottom_menu())
        await target.answer()


async def _do_compensation(user_id, chat_id):
    cat = await get_cat(user_id)
    if cat["compensation_given"] == 1:
        return await bot.send_message(
            chat_id,
            "✅ <b>Ты уже получил компенсацию!</b>\n\nСпасибо, что с нами 🐾",
            reply_markup=bottom_menu()
        )
    await update_cat(
        user_id,
        coins=cat["coins"] + COMP_AMOUNT,
        vip=1,
        compensation_given=1
    )
    await log_event(user_id, "compensation", f"+{COMP_AMOUNT} +VIP")
    await bot.send_message(
        chat_id,
        f"🎁 <b>Компенсация получена!</b>\n\n"
        f"💰 +<b>{COMP_AMOUNT} монет</b>\n"
        f"👑 <b>VIP-статус</b>!\n\n"
        f"Спасибо, что с нами! 🐾",
        reply_markup=bottom_menu()
    )


async def _show_shop(target):
    user_id = target.from_user.id
    cat = await get_cat(user_id)
    text = f"🛒 <b>Магазин за монеты</b>\n\n💰 У тебя: <b>{cat['coins']} монет</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['coins']} 💰</b>\n  <i>{item['desc']}</i>\n"

    if isinstance(target, Message):
        await target.answer(text, reply_markup=shop_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=shop_kb())
        except Exception:
            await target.message.answer(text, reply_markup=shop_kb())
        await target.answer()


async def _show_skins(user_id, target):
    owned = set(await get_user_skins(user_id)) | {"default", "cat", "black"}
    cat = await get_cat(user_id)
    current = cat["current_skin"]
    current_name = SKINS.get(current, SKINS["default"])["name"]
    text = (
        f"🎨 <b>Скины</b>\n\n"
        f"Текущий: {skin_emoji(current)} <b>{current_name}</b>\n"
        f"💰 У тебя: <b>{cat['coins']} монет</b>\n\n"
        f"✅ куплен, 👈 текущий."
    )
    kb = skins_kb(owned, current)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        try:
            await target.message.edit_text(text, reply_markup=kb)
        except Exception:
            await target.message.answer(text, reply_markup=kb)
        await target.answer()


async def _show_help(target):
    if isinstance(target, Message):
        await target.answer(HELP_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(HELP_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_soon(target):
    if isinstance(target, Message):
        await target.answer(SOON_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(SOON_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_support(target):
    if isinstance(target, Message):
        await target.answer(SUPPORT_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(SUPPORT_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_profile(target):
    user_id = target.from_user.id
    text = "👤 <b>Профиль</b>\n\n" + await render_user(user_id)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=profile_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=profile_kb())
        except Exception:
            await target.message.answer(text, reply_markup=profile_kb())
        await target.answer()


async def _start_guess(user_id, target):
    cat = await get_cat(user_id)
    if cat["coins"] < 20:
        txt = "🎲 Нужно 20 монет чтобы играть"
        if isinstance(target, Message):
            return await target.answer(txt)
        return await target.answer(txt, show_alert=True)

    number = random.randint(1, 10)
    active_games[user_id] = {"number": number, "tries": 3, "bet": 20}
    txt = (
        "🎲 <b>Угадай число 1-10!</b>\n\n"
        "Ставка: <b>20 монет</b>\n"
        "Попыток: <b>3</b>\n"
        "Угадал — <b>+100 монет</b>\n\n"
        "Напиши число 👇"
    )
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


async def _start_complaint(user_id, chat_id):
    """Начать жалобу. Кулдаун — 1 час."""
    cat = await get_cat(user_id)
    now = int(time.time())
    last = cat["last_complaint"]

    # Проверка кулдауна
    if last and now - last < COMPLAINT_COOLDOWN:
        left = COMPLAINT_COOLDOWN - (now - last)
        m = left // 60
        return await bot.send_message(
            chat_id,
            f"⏰ Жалобу можно отправить раз в час.\n\nОсталось: <b>{m} мин</b>"
        )

    # Запускаем диалог
    awaiting_complaint[user_id] = {"step": 1, "target": None, "reason": None}
    await bot.send_message(chat_id, COMPLAINT_STEP1)


# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    cat = await get_cat(message.from_user.id)
    await log_event(message.from_user.id, "start", "Первый запуск")

    kb = main_kb()
    if cat["compensation_given"] == 0:
        kb.inline_keyboard.insert(
            0,
            [InlineKeyboardButton(text="🎁 Забрать компенсацию", callback_data="compensation")]
        )

    await message.answer(
        f"🐱 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Добро пожаловать в <b>Cat Clicker</b> — игру про твоего котика!\n\n"
        f"Корми, играй, прокачивай уровень и зарабатывай монетки 💰\n\n"
        f"Выбери действие:",
        reply_markup=kb
    )
    await message.answer("Или используй меню внизу 👇", reply_markup=bottom_menu())


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(await render_user(message.from_user.id), reply_markup=main_kb())


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await _show_help(message)


@dp.message(Command("daily"))
async def cmd_daily(message: Message):
    await _do_daily(message.from_user.id, message)


@dp.message(Command("soon"))
async def cmd_soon(message: Message):
    await _show_soon(message)


@dp.message(Command("support"))
async def cmd_support(message: Message):
    await _show_support(message)


@dp.message(Command("terms"))
async def cmd_terms(message: Message):
    await message.answer(TERMS_TEXT)


@dp.message(Command("compensation"))
async def cmd_compensation(message: Message):
    await _do_compensation(message.from_user.id, message.chat.id)


@dp.message(Command("complaint"))
async def cmd_complaint(message: Message):
    await _start_complaint(message.from_user.id, message.chat.id)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    uid = message.from_user.id
    awaiting_name.pop(uid, None)
    awaiting_complaint.pop(uid, None)
    active_games.pop(uid, None)
    await message.answer("❌ Отменено.", reply_markup=bottom_menu())


@dp.message(Command("hide"))
async def cmd_hide(message: Message):
    await message.answer("Меню скрыто. /menu — вернуть.", reply_markup=ReplyKeyboardRemove())


# ==================== АДМИН-КОМАНДЫ ====================
@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /ban <user_id> [причина]")
    try:
        target_id = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "Решение админа"
        await auto_ban(target_id, reason)
        await log_admin_action(message.from_user.id, "ban", target_id, reason)
        await message.answer(f"🚫 Юзер <code>{target_id}</code> забанен.")
    except ValueError:
        await message.answer("❌ user_id должен быть числом")


@dp.message(Command("unban"))
async def cmd_unban(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /unban <user_id>")
    try:
        target_id = int(args[1])
        banned_users.pop(target_id, None)
        await update_cat(target_id, banned_until=0)
        await log_admin_action(message.from_user.id, "unban", target_id)
        await message.answer(f"✅ Юзер <code>{target_id}</code> разбанен.")
    except ValueError:
        await message.answer("❌ user_id должен быть числом")


@dp.message(Command("give_all"))
async def cmd_give_all(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /give_all <сумма>")
    try:
        amount = int(args[1])
    except ValueError:
        return await message.answer("❌ Сумма должна быть числом")
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET coins = coins + ?", (amount,))
        await db.commit()
    await log_admin_action(message.from_user.id, "give_all", None, f"+{amount}")
    await message.answer(f"💰 Всем начислено по <b>{amount}</b> монет.")


@dp.message(Command("comp_give"))
async def cmd_comp_give(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /comp_give <user_id>")
    try:
        target_id = int(args[1])
    except ValueError:
        return await message.answer("❌ user_id должен быть числом")
    await update_cat(target_id, coins=COMP_AMOUNT, vip=1, compensation_given=1)
    await log_admin_action(message.from_user.id, "comp_give", target_id)
    await message.answer(f"🎁 Юзеру <code>{target_id}</code> выдана компенсация.")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM cats")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?",
                               (int(time.time()) - 86400,))
        active_24h = (await cur.fetchone())[0]
        cur = await db.execute("SELECT SUM(coins) FROM cats")
        coins_sum = (await cur.fetchone())[0] or 0
        cur = await db.execute("SELECT COUNT(*) FROM complaints WHERE processed=0")
        complaints = (await cur.fetchone())[0]
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего юзеров: <b>{total}</b>\n"
        f"🔥 Активных (24ч): <b>{active_24h}</b>\n"
        f"💰 Монет в игре: <b>{coins_sum}</b>\n"
        f"🚨 Открытых жалоб: <b>{complaints}</b>"
    )


@dp.message(Command("logs"))
async def cmd_logs(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT user_id, action, details, created_at FROM logs ORDER BY id DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    if not rows:
        return await message.answer("Логов пока нет.")
    text = "📜 <b>Последние 20 действий</b>\n\n"
    for r in rows:
        t = time.strftime("%H:%M:%S", time.localtime(r[3]))
        text += f"[{t}] <code>{r[0]}</code> → {r[1]}: {r[2]}\n"
    await message.answer(text)


@dp.message(Command("security"))
async def cmd_security(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT event, severity, details, created_at FROM security ORDER BY id DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    if not rows:
        return await message.answer("Событий безопасности нет.")
    text = "🛡 <b>Последние 20 событий</b>\n\n"
    for r in rows:
        t = time.strftime("%H:%M:%S", time.localtime(r[3]))
        text += f"[{t}] <b>{r[1]}</b> {r[0]}: {r[2]}\n"
    await message.answer(text)


@dp.message(Command("complaints"))
async def cmd_complaints(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, from_user_id, reported_user, reason, created_at "
            "FROM complaints WHERE processed=0 ORDER BY id DESC LIMIT 10"
        )
        rows = await cur.fetchall()
    if not rows:
        return await message.answer("Открытых жалоб нет.")
    for r in rows:
        await message.answer(
            f"🚨 <b>Жалоба #{r[0]}</b>\n\n"
            f"От: <code>{r[1]}</code>\n"
            f"На: {r[2]}\n"
            f"Причина: {r[3]}",
            reply_markup=complaint_admin_kb(r[0])
        )


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("Использование: /broadcast <текст>")
    text = args[1]
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT user_id FROM cats")
        users = [r[0] for r in await cur.fetchall()]
    sent = 0
    for uid in users:
        try:
            await bot.send_message(uid, f"📢 <b>Объявление</b>\n\n{text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await log_admin_action(message.from_user.id, "broadcast", None, f"sent={sent}")
    await message.answer(f"✅ Отправлено: <b>{sent}</b> из {len(users)}")


@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("Использование: /reset <user_id>")
    try:
        target_id = int(args[1])
    except ValueError:
        return await message.answer("❌ user_id должен быть числом")
    await update_cat(target_id, coins=0, level=1, xp=0, vip=0, satiety=100, strikes=0)
    await log_admin_action(message.from_user.id, "reset", target_id)
    await message.answer(f"♻️ Юзер <code>{target_id}</code> сброшен.")


# ==================== CALLBACK-ОБРАБОТЧИКИ ====================
@dp.callback_query(F.data == "refresh")
async def cb_refresh(call: CallbackQuery):
    await call.message.edit_text(await render_user(call.from_user.id), reply_markup=main_kb())
    await call.answer()


@dp.callback_query(F.data == "feed")
async def cb_feed(call: CallbackQuery):
    await _do_feed(call.from_user.id, call)


@dp.callback_query(F.data == "play")
async def cb_play(call: CallbackQuery):
    await _do_play(call.from_user.id, call)


@dp.callback_query(F.data == "daily")
async def cb_daily(call: CallbackQuery):
    await _do_daily(call.from_user.id, call)


@dp.callback_query(F.data == "shop")
async def cb_shop(call: CallbackQuery):
    await _show_shop(call)


@dp.callback_query(F.data == "skins_menu")
async def cb_skins(call: CallbackQuery):
    await _show_skins(call.from_user.id, call)


@dp.callback_query(F.data == "guess")
async def cb_guess(call: CallbackQuery):
    await _start_guess(call.from_user.id, call)


@dp.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery):
    await _show_profile(call)


@dp.callback_query(F.data == "soon")
async def cb_soon(call: CallbackQuery):
    await _show_soon(call)


@dp.callback_query(F.data == "compensation")
async def cb_compensation(call: CallbackQuery):
    await _do_compensation(call.from_user.id, call.message.chat.id)
    await call.answer()


@dp.callback_query(F.data == "rename")
async def cb_rename(call: CallbackQuery):
    awaiting_name[call.from_user.id] = True
    await call.message.answer(RENAME_TEXT)
    await call.answer()


@dp.callback_query(F.data == "complaint")
async def cb_complaint(call: CallbackQuery):
    await _start_complaint(call.from_user.id, call.message.chat.id)
    await call.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    item = SHOP.get(key)
    if not item:
        return await call.answer("Товар не найден", show_alert=True)
    cat = await get_cat(call.from_user.id)
    if cat["coins"] < item["coins"]:
        return await call.answer("Недостаточно монет 💰", show_alert=True)

    now = int(time.time())
    fields = {"coins": cat["coins"] - item["coins"]}
    if key == "food10":
        fields["coins"] = cat["coins"] - item["coins"] + 100
    elif key == "boost":
        fields["boost_until"] = max(cat["boost_until"], now) + 86400
    elif key == "vip":
        fields["vip"] = 1

    await update_cat(call.from_user.id, **fields)
    await log_event(call.from_user.id, "buy", key)
    await call.answer(f"✅ Куплено: {item['title']}", show_alert=True)
    await call.message.edit_text(await render_user(call.from_user.id), reply_markup=main_kb())


@dp.callback_query(F.data.startswith("buy_skin:"))
async def cb_buy_skin(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    s = SKINS.get(key)
    if not s:
        return await call.answer("Скин не найден", show_alert=True)
    cat = await get_cat(call.from_user.id)
    if cat["coins"] < s["coins"]:
        return await call.answer("Недостаточно монет 💰", show_alert=True)

    await update_cat(
        call.from_user.id,
        coins=cat["coins"] - s["coins"],
        current_skin=key
    )
    await add_user_skin(call.from_user.id, key)
    await log_event(call.from_user.id, "buy_skin", key)
    await call.answer(f"✅ Скин куплен: {s['name']}", show_alert=True)
    await _show_skins(call.from_user.id, call)


@dp.callback_query(F.data.startswith("select_skin:"))
async def cb_select_skin(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    owned = set(await get_user_skins(call.from_user.id)) | {"default", "cat", "black"}
    if key not in owned:
        return await call.answer("Скин не куплен", show_alert=True)
    await set_current_skin(call.from_user.id, key)
    await log_event(call.from_user.id, "select_skin", key)
    await call.answer("✅ Скин установлен", show_alert=True)
    await _show_skins(call.from_user.id, call)


@dp.callback_query(F.data == "complaint_send")
async def cb_complaint_send(call: CallbackQuery):
    data = awaiting_complaint.get(call.from_user.id)
    if not data or not data.get("reason"):
        return await call.answer("Жалоба не найдена", show_alert=True)

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO complaints(from_user_id, reported_user, reason, created_at) "
            "VALUES(?,?,?,?)",
            (call.from_user.id, data["target"], data["reason"], int(time.time()))
        )
        cid = cur.lastrowid
        await db.execute(
            "UPDATE cats SET last_complaint=? WHERE user_id=?",
            (int(time.time()), call.from_user.id)
        )
        await db.commit()

    awaiting_complaint.pop(call.from_user.id, None)
    await call.message.edit_text("✅ Жалоба отправлена админам.")
    await call.answer()

    for admin in ADMIN_IDS:
        try:
            await bot.send_message(
                admin,
                f"🚨 <b>Жалоба #{cid}</b>\n\n"
                f"От: <code>{call.from_user.id}</code>\n"
                f"На: {data['target']}\n"
                f"Причина: {data['reason']}",
                reply_markup=complaint_admin_kb(cid)
            )
        except Exception:
            pass


@dp.callback_query(F.data == "complaint_cancel")
async def cb_complaint_cancel(call: CallbackQuery):
    awaiting_complaint.pop(call.from_user.id, None)
    await call.message.edit_text("❌ Жалоба отменена.")
    await call.answer()


@dp.callback_query(F.data.startswith("cmp_"))
async def cb_cmp_admin(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return await call.answer("Нет доступа", show_alert=True)

    action, cid = call.data.split(":", 1)
    cid = int(cid)
    await log_admin_action(call.from_user.id, action, cid)

    if action == "cmp_done":
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE complaints SET processed=1 WHERE id=?", (cid,))
            await db.commit()
        await call.message.edit_text(f"✅ Жалоба #{cid} обработана.")
    elif action == "cmp_reject":
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE complaints SET processed=1 WHERE id=?", (cid,))
            await db.commit()
        await call.message.edit_text(f"❌ Жалоба #{cid} отклонена.")
    elif action == "cmp_ban":
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("SELECT reported_user FROM complaints WHERE id=?", (cid,))
            row = await cur.fetchone()
            await db.execute("UPDATE complaints SET processed=1 WHERE id=?", (cid,))
            await db.commit()
        if row:
            try:
                target_id = int(row[0])
                await auto_ban(target_id, reason="Жалоба подтверждена")
                await call.message.edit_text(f"🚫 Юзер {target_id} забанен.")
            except Exception:
                await call.message.edit_text("⚠️ Не удалось забанить (нужен ID).")
        else:
            await call.message.edit_text("Жалоба не найдена.")
    await call.answer()


# ==================== ТЕКСТОВЫЕ СООБЩЕНИЯ ====================
@dp.message(F.text == "🍖 Покормить")
async def msg_feed(message: Message):
    await _do_feed(message.from_user.id, message)


@dp.message(F.text == "🎾 Поиграть")
async def msg_play(message: Message):
    await _do_play(message.from_user.id, message)


@dp.message(F.text == "🎲 Угадай")
async def msg_guess(message: Message):
    await _start_guess(message.from_user.id, message)


@dp.message(F.text == "🎁 Бонус дня")
async def msg_daily(message: Message):
    await _do_daily(message.from_user.id, message)


@dp.message(F.text == "🛒 Магазин")
async def msg_shop(message: Message):
    await _show_shop(message)


@dp.message(F.text == "🎨 Скины")
async def msg_skins(message: Message):
    await _show_skins(message.from_user.id, message)


@dp.message(F.text == "👤 Профиль")
async def msg_profile(message: Message):
    await _show_profile(message)


@dp.message(F.text == "✏️ Имя")
async def msg_rename(message: Message):
    awaiting_name[message.from_user.id] = True
    await message.answer(RENAME_TEXT)


@dp.message(F.text == "🎁 Компенсация")
async def msg_compensation(message: Message):
    await _do_compensation(message.from_user.id, message.chat.id)


@dp.message(F.text == "🚧 Скоро")
async def msg_soon(message: Message):
    await _show_soon(message)


@dp.message(F.text == "🚨 Жалоба")
async def msg_complaint(message: Message):
    await _start_complaint(message.from_user.id, message.chat.id)


@dp.message(F.text == "❓ Помощь")
async def msg_help(message: Message):
    await _show_help(message)


@dp.message(F.text == "❌ Скрыть меню")
async def msg_hide(message: Message):
    await message.answer("Меню скрыто. /menu — вернуть.", reply_markup=ReplyKeyboardRemove())


# ==================== СВОБОДНЫЙ ТЕКСТ ====================
@dp.message(F.text)
async def handle_text(message: Message):
    uid = message.from_user.id
    text = (message.text or "").strip()

    # Жалоба
    if uid in awaiting_complaint:
        data = awaiting_complaint[uid]
        if data["step"] == 1:
            data["target"] = text
            data["step"] = 2
            await message.answer(COMPLAINT_STEP2)
            return
        elif data["step"] == 2:
            data["reason"] = text
            awaiting_complaint[uid] = data
            await message.answer(
                f"🚨 <b>Проверь жалобу:</b>\n\n"
                f"На: {data['target']}\n"
                f"Причина: {data['reason']}",
                reply_markup=complaint_confirm_kb()
            )
            return

    # Смена имени
    if uid in awaiting_name:
        if len(text) < NAME_MIN_LEN or len(text) > NAME_MAX_LEN:
            return await message.answer(
                f"❌ Имя должно быть от {NAME_MIN_LEN} до {NAME_MAX_LEN} символов."
            )
        cat = await get_cat(uid)
        now = int(time.time())
        if now - cat["last_name_change"] < NAME_COOLDOWN:
            left = NAME_COOLDOWN - (now - cat["last_name_change"])
            h = left // 3600
            return await message.answer(f"⏰ Имя можно менять раз в 24ч. Осталось: {h}ч")
        await update_cat(uid, name=text, last_name_change=now)
        awaiting_name.pop(uid, None)
        await log_event(uid, "rename", text)
        await message.answer(f"✅ Имя изменено на <b>{text}</b>!", reply_markup=bottom_menu())
        return

    # Мини-игра "Угадай число"
    if uid in active_games:
        game = active_games[uid]
        if text.isdigit():
            guess = int(text)
            game["tries"] -= 1
            if guess == game["number"]:
                cat = await get_cat(uid)
                await update_cat(uid, coins=cat["coins"] + 100)
                active_games.pop(uid, None)
                await message.answer("🎉 <b>Угадал!</b> +100 монет!")
                return
            elif game["tries"] <= 0:
                cat = await get_cat(uid)
                await update_cat(uid, coins=max(0, cat["coins"] - game["bet"]))
                active_games.pop(uid, None)
                await message.answer(f"😿 Не угадал. Было <b>{game['number']}</b>. -20 монет.")
                return
            else:
                hint = "больше" if guess < game["number"] else "меньше"
                await message.answer(
                    f"❌ Не то. Загаданное число <b>{hint}</b>. Осталось попыток: {game['tries']}"
                )
                return

    await message.answer("Используй кнопки меню 👇", reply_markup=bottom_menu())


# ==================== ЗАЩИТА ИМЕНИ БОТА ====================
async def check_bot_name():
    """Периодически проверяет, не сменили ли имя бота."""
    while True:
        try:
            me = await bot.get_me()
            if me.first_name != BOT_NAME:
                await log_security(
                    "bot_name_changed", "high",
                    f"Было: {BOT_NAME}, стало: {me.first_name}"
                )
                try:
                    await bot.set_my_name(BOT_NAME)
                    await log_security("bot_name_restored", "medium", BOT_NAME)
                except Exception as e:
                    await log_security("bot_name_restore_fail", "high", str(e))
        except Exception as e:
            print(f"check_bot_name error: {e}")
        await asyncio.sleep(CHECK_NAME_INTERVAL)


# ==================== ЗАПУСК ====================
async def on_startup():
    await init_db()
    try:
        await bot.set_my_commands([
            BotCommand(command="start",        description="🐱 Начать"),
            BotCommand(command="menu",         description="📋 Меню"),
            BotCommand(command="daily",        description="🎁 Бонус дня"),
            BotCommand(command="soon",         description="🚧 Что скоро"),
            BotCommand(command="help",         description="❓ Помощь"),
            BotCommand(command="compensation", description="🎁 Компенсация"),
            BotCommand(command="complaint",    description="🚨 Жалоба"),
            BotCommand(command="terms",        description="📜 Условия"),
            BotCommand(command="support",      description="🆘 Поддержка"),
            BotCommand(command="cancel",       description="❌ Отмена"),
        ], scope=BotCommandScopeDefault())
    except Exception as e:
        print(f"set_my_commands error: {e}")

    asyncio.create_task(check_bot_name())
    print("🐱 Cat Clicker запущен!")


async def main():
    dp.message.middleware(SecurityMiddleware())
    dp.callback_query.middleware(SecurityMiddleware())
    await on_startup()
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
