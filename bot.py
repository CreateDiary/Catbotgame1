import asyncio
import aiosqlite
import time
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8859558366:AAHJgh_IldjCabGpFsqsAMkWPYoapc2jrQY"
ADMIN_IDS = [5965370780, 6137912809]
CONTACT_USERNAME = "Artemchic2009"
CONTACT_USERNAME_2 = "Andrkaop"

BOT_NAME_LOCK = "Cat Clicker"
CHECK_INTERVAL = 60
MAX_ACTIONS_PER_MIN = 30
BAN_DURATION = 86400
STRIKE_LIMIT = 3

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
SPAM_WINDOW = 10
SPAM_LIMIT = 15
NAME_COOLDOWN = 86400
NAME_MAX_LEN = 20
NAME_MIN_LEN = 2
COMPLAINT_COOLDOWN = 3600

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

# Память
active_games = {}
spam_tracker = {}
banned_users = {}
awaiting_name = {}
awaiting_complaint = {}
action_tracker = {}


# ==================== БД ====================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
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
                user_id INTEGER, action TEXT, details TEXT, created_at INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT, user_id INTEGER, details TEXT,
                severity TEXT, created_at INTEGER
            )
        """)
        await db.commit()


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


# ==================== ЛОГИ ====================
async def log_action(user_id, action, details=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO logs(user_id, action, details, created_at) VALUES(?,?,?,?)",
                (user_id, action, str(details)[:500], int(time.time()))
            )
            await db.commit()
    except Exception as e:
        print(f"log_action error: {e}")


async def log_security(event_type, user_id, details, severity="low"):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO security_events(event_type, user_id, details, severity, created_at) "
                "VALUES(?,?,?,?,?)",
                (event_type, user_id, str(details)[:500], severity, int(time.time()))
            )
            await db.commit()
        if severity == "high":
            for admin in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin,
                        f"🚨 <b>SECURITY ALERT</b>\n\n"
                        f"Тип: {event_type}\n"
                        f"Юзер: <code>{user_id}</code>\n"
                        f"Детали: {details}"
                    )
                except Exception:
                    pass
    except Exception as e:
        print(f"log_security error: {e}")


async def log_admin(admin_id, action, target_id=None, details=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO admin_actions(admin_id, action, target_id, details, created_at) "
                "VALUES(?,?,?,?,?)",
                (admin_id, action, target_id, str(details)[:500], int(time.time()))
            )
            await db.commit()
    except Exception as e:
        print(f"log_admin error: {e}")


# ==================== БАН / СПАМ / АНТИФРОД ====================
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


def track_actions(user_id):
    now = time.time()
    times = [t for t in action_tracker.get(user_id, []) if now - t < 60]
    times.append(now)
    action_tracker[user_id] = times
    return len(times) >= MAX_ACTIONS_PER_MIN


async def add_strike(user_id, reason):
    cat = await get_cat(user_id)
    strikes = cat["strikes"] + 1
    await update_cat(user_id, strikes=strikes)
    await log_security("strike", user_id, reason, "medium")
    if strikes >= STRIKE_LIMIT:
        await auto_ban(user_id, reason=f"3 страйка: {reason}")
        return True
    return False


async def auto_ban(user_id, reason="Подозрительная активность"):
    until = int(time.time()) + BAN_DURATION
    banned_users[user_id] = until
    await update_cat(user_id, banned_until=until)
    await log_security("auto_ban", user_id, reason, "high")
    try:
        await bot.send_message(
            user_id,
            f"🚫 <b>Ты забанен на 24 часа.</b>\n\nПричина: {reason}"
        )
    except Exception:
        pass


# ==================== MIDDLEWARE ====================
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

            if isinstance(event, Message) and track_spam(user.id):
                await auto_ban(user.id, reason="Спам")
                return

            if track_actions(user.id):
                await log_security("rate_limit", user.id, "Слишком быстро", "medium")
                if await add_strike(user.id, "Слишком быстро"):
                    return

            await update_cat(user.id, last_seen=int(time.time()))

        return await handler(event, data)


# ==================== ЛОГИКА ИГРЫ ====================
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


async def get_user_skins(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT skin_key FROM user_skins WHERE user_id=?", (user_id,))
        rows = await cur.fetchall()
    return [r[0] for r in rows]


async def add_user_skin(user_id, skin_key):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO user_skins(user_id, skin_key, purchased_at) VALUES(?,?,?)",
            (user_id, skin_key, int(time.time()))
        )
        await db.commit()


async def set_current_skin(user_id, skin_key):
    await update_cat(user_id, current_skin=skin_key)


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть",  callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня",   callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин",  callback_data="shop"),
         InlineKeyboardButton(text="🎨 Скины",   callback_data="skins_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
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
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="complaint")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")],
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
            [KeyboardButton(text="🎲 Угадай"),    KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"),   KeyboardButton(text="🎨 Скины")],
            [KeyboardButton(text="👤 Профиль"),   KeyboardButton(text="✏️ Имя")],
            [KeyboardButton(text="🚨 Жалоба"),    KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ==================== ТЕКСТЫ ====================
HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Cat Clicker — игра-тамагочи про котика.</b>\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты\n"
    "🎾 Поиграть — +XP\n"
    "🎲 Угадай — мини-игра\n"
    "🎁 Бонус дня — раз в 24ч\n"
    "🛒 Магазин — за монеты\n"
    "🎨 Скины — за монеты\n"
    "👤 Профиль\n"
    "✏️ Имя — сменить имя\n"
    "🚨 Жалоба\n\n"
    "<b>📋 Команды:</b>\n"
    "/start, /menu, /daily, /help\n"
    "/terms, /support, /cancel"
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра.\n"
    "2. Монеты не имеют ценности.\n"
    "3. Спам запрещён — бан 24ч.\n"
    "4. Право менять условия."
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    "Написать:\n"
    f"• @{CONTACT_USERNAME}\n"
    f"• @{CONTACT_USERNAME_2}\n\n"
    "⏱ Отвечаем 24ч."
)

RENAME_TEXT = (
    "✏️ <b>Смена имени котика</b>\n\n"
    "Отправь новое имя.\n"
    f"📏 {NAME_MIN_LEN}-{NAME_MAX_LEN} символов.\n"
    "⏰ 1 раз в 24 часа.\n\n"
    "❌ Отмена — /cancel"
)

COMPLAINT_STEP1 = "🚨 <b>Жалоба</b>\n\nШаг 1/2: На кого жалуешься?\n\nНапиши @username или ID.\n\n❌ /cancel"
COMPLAINT_STEP2 = "🚨 <b>Жалоба</b>\n\nШаг 2/2: Опиши проблему.\n\n❌ /cancel"


# ==================== ДЕЙСТВИЯ ====================
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


async def _do_feed(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat["last_feed"] < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - cat["last_feed"])
        msg_text = f"Подожди {left} сек 🍽"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

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
        msg_text = "Котик слишком голодный 😿"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    anim = await _animate(target, [
        "🎾 Играем.", "🎾 Играем..", "🎾 Играем...", "😺 Котик веселится!"
    ])
    coins_gain = random.randint(10, 25)
    if is_boost(cat): coins_gain *= 2

    await update_cat(
        user_id,
        coins=cat["coins"] + coins_gain,
        satiety=max(0, cat["satiety"] - 10)
    )
    leveled, level = await add_xp(user_id, 20)
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
        msg_text = f"⏰ Бонус уже получен. Через <b>{h}ч {m}м</b>"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    if 0 < last and now - last < DAILY_COOLDOWN * 2:
        streak += 1
    else:
        streak = 1

    bonus = 50 + (streak - 1) * 15
    if streak >= 7:
        bonus += 100
    if is_vip(cat):
        bonus *= 2

    await update_cat(user_id, coins=cat["coins"] + bonus, last_daily=now, streak=streak)
    leveled, level = await add_xp(user_id, 20)

    txt = f"🎁 <b>Бонус выдан!</b>\n\n💰 +<b>{bonus} монет</b>\n🔥 Стрик: <b>{streak}</b>"
    if streak >= 7:
        txt += "\n🎉 <b>Неделя подряд! +100 монет!</b>"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"

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
            "✅ <b>Ты уже получил компенсацию!</b>\n\nСпасибо, что остался с нами 🐾",
            reply_markup=bottom_menu()
        )

    await update_cat(user_id, coins=cat["coins"] + 2000, vip=1, compensation_given=1)
    await bot.send_message(
        chat_id,
        "🎁 <b>Компенсация получена!</b>\n\n"
        "💰 +<b>2000 монет</b>\n"
        "👑 <b>VIP-статус</b> — бесплатно!\n\n"
        "VIP даёт:\n"
        "• +10 монет каждый час\n"
        "• x2 к бонусу дня\n"
        "• 👑 значок рядом с именем",
        reply_markup=bottom_menu()
    )


async def _show_shop(target):
    user_id = target.from_user.id
    cat = await get_cat(user_id)
    text = f"🛒 <b>Магазин</b>\n\n💰 У тебя: <b>{cat['coins']} монет</b>\n\n"
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
        f"✅ — куплен, 👈 — текущий."
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
        txt = "🎲 Нужно 20 монет"
        if isinstance(target, Message):
            return await target.answer(txt)
        return await target.answer(txt, show_alert=True)

    number = random.randint(1, 10)
    active_games[user_id] = {"number": number, "tries": 3, "bet": 20}
    txt = (
        "🎲 <b>Угадай число 1-10!</b>\n\n"
        "Ставка: <b>20 монет</b>\n"
        "Попыток: <b>3</b>\n"
        "Угадал — <b>+100</b>\n\n"
        "Напиши число 👇"
    )
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


async def _start_complaint(user_id, chat_id):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat["last_complaint"] < COMPLAINT_COOLDOWN:
        left = COMPLAINT_COOLDOWN - (now - cat["last_complaint"])
        m = left // 60
        return await bot.send_message(
            chat_id,
            f"⏰ Жалобу можно отправить раз в час.\n\nОсталось: <b>{m} мин</b>"
        )

    awaiting_complaint[user_id] = {"step": 1, "target": None, "reason": None}
    await bot.send_message(chat_id, COMPLAINT_STEP1)


# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    cat = await get_cat(message.from_user.id)
    await log_action(message.from_user.id, "start", "Первый запуск")

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


@dp.message(Command("terms"))
async def cmd_terms(message: Message):
    await message.answer(TERMS_TEXT)


@dp.message(Command("support"))
async def cmd_support(message: Message):
    await message.answer(SUPPORT_TEXT)


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message):
    uid = message.from_user.id
    awaiting_name.pop(uid, None)
    awaiting_complaint.pop(uid, None)
    active_games.pop(uid, None)
    await message.answer("❌ Отменено.", reply_markup=bottom_menu())


# ==================== КОЛБЭКИ ====================
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
    await log_action(call.from_user.id, "buy", key)
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

    await update_cat(call.from_user.id, coins=cat["coins"] - s["coins"], current_skin=key)
    await add_user_skin(call.from_user.id, key)
    await log_action(call.from_user.id, "buy_skin", key)
    await call.answer(f"✅ Скин куплен: {s['name']}", show_alert=True)
    await _show_skins(call.from_user.id, call)


@dp.callback_query(F.data.startswith("select_skin:"))
async def cb_select_skin(call: CallbackQuery):
    key = call.data.split(":", 1)[1]
    owned = set(await get_user_skins(call.from_user.id)) | {"default", "cat", "black"}
    if key not in owned:
        return await call.answer("Скин не куплен", show_alert=True)

    await set_current_skin(call.from_user.id, key)
    await log_action(call.from_user.id, "select_skin", key)
    await call.answer("✅ Скин установлен", show_alert=True)
    await _show_skins(call.from_user.id, call)


@dp.callback_query(F.data == "complaint_send")
async def cb_complaint_send(call: CallbackQuery):
    data = awaiting_complaint.get(call.from_user.id)
    if not data or not data.get("reason"):
        return await call.answer("Жалоба не найдена", show_alert=True)

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "INSERT INTO complaints(from_user_id, reported_user, reason, created_at) VALUES(?,?,?,?)",
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
    await log_admin(call.from_user.id, action, cid)

    if action == "cmp_done":
        await call.message.edit_text(f"✅ Жалоба #{cid} обработана.")
    elif action == "cmp_reject":
        await call.message.edit_text(f"❌ Жалоба #{cid} отклонена.")
    elif action == "cmp_ban":
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("SELECT reported_user FROM complaints WHERE id=?", (cid,))
            row = await cur.fetchone()
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
        await log_action(uid, "rename", text)
        await message.answer(f"✅ Имя изменено на <b>{text}</b>!", reply_markup=bottom_menu())
        return

    # Мини-игра
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
                await message.answer(f"😿 Не угадал. Было число <b>{game['number']}</b>. -20 монет.")
                return
            else:
                hint = "больше" if guess < game["number"] else "меньше"
                await message.answer(
                    f"❌ Не то. Загаданное число <b>{hint}</b>. Осталось попыток: {game['tries']}"
                )
                return

    await message.answer("Используй кнопки меню 👇", reply_markup=bottom_menu())


# ==================== ЗАЩИТА БОТА ====================
async def check_bot_security():
    while True:
        try:
            me = await bot.get_me()
            if BOT_NAME_LOCK and me.first_name != BOT_NAME_LOCK:
                await log_security(
                    "bot_name_changed", 0,
                    f"Было: {BOT_NAME_LOCK}, стало: {me.first_name}",
                    "high"
                )
                try:
                    await bot.set_my_name(BOT_NAME_LOCK)
                    await log_security("bot_name_restored", 0, BOT_NAME_LOCK, "medium")
                except Exception as e:
                    await log_security("bot_name_restore_fail", 0, str(e), "high")
        except Exception as e:
            print(f"check_bot_security error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


# ==================== ЗАПУСК ====================
async def on_startup():
    await init_db()
    await bot.set_my_commands([
        BotCommand(command="start",   description="🐱 Начать"),
        BotCommand(command="menu",    description="📋 Меню"),
        BotCommand(command="daily",   description="🎁 Бонус дня"),
        BotCommand(command="help",    description="❓ Помощь"),
        BotCommand(command="terms",   description="📜 Условия"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="cancel",  description="❌ Отмена"),
    ], scope=BotCommandScopeDefault())
    asyncio.create_task(check_bot_security())
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
