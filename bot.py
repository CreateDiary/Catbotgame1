import asyncio
import aiosqlite
import time
import random
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.client.default import DefaultBotProperties

# ==== НАСТРОЙКИ ====
BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_ID = 5965370780
CONTACT_USERNAME = "Artemchic2009"
# ===================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
REMIND_COOLDOWN = 86400
PLAY_REMIND_COOLDOWN = 7200
REFUND_WINDOW = 604800
SPAM_WINDOW = 10
SPAM_LIMIT = 15
BAN_DURATION = 86400
WARN_COOLDOWN = 300

# Магазин — за звёзды (доход тебе)
SHOP = {
    "food10": {"title": "🍖 Корм x10", "stars": 50, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "stars": 250, "desc": "Скин + пассивный доход"},
}

# Скины — ВСЕ ЗА МОНЕТЫ
SKINS = {
    # Бесплатные
    "default": {"emoji": "🐱", "name": "Обычный кот",  "coins": 0},
    "cat":     {"emoji": "🐈", "name": "Кошка",        "coins": 0},
    "black":   {"emoji": "🐈‍⬛", "name": "Чёрный кот",  "coins": 0},
    # Платные
    "fox":     {"emoji": "🦊", "name": "Рыжий",        "coins": 100},
    "tiger":   {"emoji": "🐯", "name": "Тигр",         "coins": 250},
    "lion":    {"emoji": "🦁", "name": "Лев",          "coins": 400},
    "leopard": {"emoji": "🐆", "name": "Пантера",      "coins": 600},
    "bear":    {"emoji": "🐻", "name": "Медведь-кот",  "coins": 800},
    "panda":   {"emoji": "🐼", "name": "Панда",        "coins": 1000},
    "wolf":    {"emoji": "🐺", "name": "Волк",         "coins": 1300},
    "unicorn": {"emoji": "🦄", "name": "Единорог",     "coins": 1800},
    "dragon":  {"emoji": "🐉", "name": "Дракон",       "coins": 2500},
    "king":    {"emoji": "👑", "name": "Королевский",  "coins": 3000},
    "robot":   {"emoji": "🤖", "name": "Кот-робот",    "coins": 3500},
    "cosmo":   {"emoji": "🚀", "name": "Космо-кот",    "coins": 4000},
    "ghost":   {"emoji": "👻", "name": "Кот-призрак",  "coins": 4500},
    "fire":    {"emoji": "🔥", "name": "Огненный",     "coins": 5000},
}

active_games = {}
warned_users = {}
spam_tracker = {}
banned_users = {}


# ==================== БАЗА ДАННЫХ ====================
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
                streak INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_key TEXT,
                stars INTEGER,
                charge_id TEXT,
                created_at INTEGER,
                refunded INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                reported_user_id INTEGER,
                reason TEXT,
                created_at INTEGER,
                processed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_skins (
                user_id INTEGER,
                skin_key TEXT,
                purchased_at INTEGER,
                PRIMARY KEY (user_id, skin_key)
            )
        """)
        for col, default in [
            ("last_seen", "0"),
            ("last_remind", "0"),
            ("last_play_remind", "0"),
            ("warnings", "0"),
            ("banned_until", "0"),
            ("current_skin", "'default'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE cats ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass
        try:
            await db.execute("ALTER TABLE payments ADD COLUMN refunded INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()


async def get_cat(user_id):
    async with aiosqlite.connect(DB) as db:
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
                "INSERT INTO user_skins(user_id, skin_key, purchased_at) VALUES(?,?,?)",
                (user_id, skin_key, int(time.time()))
            )
            await db.commit()
        except Exception:
            pass


async def get_current_skin(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT current_skin FROM cats WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            return row[0]
    return "default"


# ==================== АНТИСПАМ ====================
def is_banned(user_id):
    until = banned_users.get(user_id, 0)
    if until > int(time.time()):
        return True
    if until and until <= int(time.time()):
        del banned_users[user_id]
    return False


def track_spam(user_id):
    now = time.time()
    times = spam_tracker.get(user_id, [])
    times = [t for t in times if now - t < SPAM_WINDOW]
    times.append(now)
    spam_tracker[user_id] = times
    return len(times) >= SPAM_LIMIT


async def auto_ban(user_id):
    until = int(time.time()) + BAN_DURATION
    banned_users[user_id] = until
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=? WHERE user_id=?",
                             (until, user_id))
            await db.commit()
    except Exception:
        pass
    try:
        await bot.send_message(user_id,
            f"🚫 <b>Ты забанен на {BAN_DURATION // 3600} часов за спам.</b>")
    except Exception:
        pass
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID,
                f"🚫 Автобан: <code>{user_id}</code>")
        except Exception:
            pass


# ==================== MIDDLEWARE ====================
class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            if is_banned(user.id):
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 Ты забанен.",
                                           reply_markup=ReplyKeyboardRemove())
                    except Exception:
                        pass
                return
            if isinstance(event, Message):
                if track_spam(user.id):
                    await auto_ban(user.id)
                    return
            try:
                async with aiosqlite.connect(DB) as db:
                    await db.execute("UPDATE cats SET last_seen=? WHERE user_id=?",
                                     (int(time.time()), user.id))
                    await db.commit()
            except Exception:
                pass
        return await handler(event, data)


# ==================== ЛОГИКА ====================
def xp_for_next(level):
    return level * 100


async def add_xp(user_id, amount):
    cat = await get_cat(user_id)
    xp = cat[3] + amount
    level = cat[2]
    leveled = False
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
        leveled = True
    await update_cat(user_id, xp=xp, level=level)
    return leveled, level


def is_boost(cat):
    return cat[8] > int(time.time())


def is_vip(cat):
    return cat[9] == 1


def bonus_available(cat):
    return int(time.time()) - cat[10] >= DAILY_COOLDOWN


def skin_emoji(skin_key):
    s = SKINS.get(skin_key)
    return s["emoji"] if s else "🐱"


def render(cat, skin_key="default"):
    _, name, level, xp, coins, satiety, _, boost_until, vip, last_daily, streak = cat[:11]
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
    skin = await get_current_skin(user_id)
    return render(cat, skin)


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть",  callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня",   callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин",  callback_data="shop"),
         InlineKeyboardButton(text="🎨 Скины",   callback_data="skins_menu")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def shop_kb():
    rows = []
    for key, item in SHOP.items():
        rows.append([InlineKeyboardButton(
            text=f"{item['title']} — {item['stars']} ⭐",
            callback_data=f"buy:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skins_kb(user_id, owned, current):
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
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notif_settings")],
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="report")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def bottom_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍖 Покормить"), KeyboardButton(text="🎾 Поиграть")],
            [KeyboardButton(text="🎲 Угадай"),    KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"),   KeyboardButton(text="🎨 Скины")],
            [KeyboardButton(text="👤 Профиль"),   KeyboardButton(text="🚨 Жалоба")],
            [KeyboardButton(text="❓ Помощь"),    KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ==================== ТЕКСТЫ ====================
HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Это игра-тамагочи про котика.</b>\n"
    "Корми, играй, качай уровень, зарабатывай монеты.\n"
    "Меняй скины за монеты!\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (раз в 30 сек)\n"
    "🎾 Поиграть — +XP и монеты\n"
    "🎲 Угадай — мини-игра\n"
    "🎁 Бонус дня — раз в 24 часа\n"
    "🛒 Магазин — покупки за ⭐\n"
    "🎨 Скины — разные коты за монеты\n"
    "👤 Профиль — твой котик\n"
    "🚨 Жалоба — пожаловаться на юзера\n\n"
    "<b>📋 Команды:</b>\n"
    "/start, /menu, /daily, /soon, /help\n"
    "/support — поддержка\n"
    "/paysupport — оплата\n"
    "/terms — условия\n"
    "/refund — вернуть звёзды\n"
    "/mute, /unmute — напоминания\n"
    "/hide — скрыть меню\n\n"
    "📷 <b>Фото, видео, стикеры, текст — удаляются.</b>\n"
    "⚠️ Спам = <b>бан на 24 часа</b>.\n\n"
    "👑 <b>VIP</b> — +10 монет каждый час"
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра-тамагочи. Все покупки — цифровые товары.\n"
    "2. Монеты и бонусы внутри игры не имеют денежной ценности.\n"
    "3. Возврат средств за Stars — /refund, 7 дней.\n"
    "4. Игра предоставляется «как есть».\n"
    "5. Спам, флуд — <b>бан 24 часа</b>.\n"
    "6. Право менять условия.\n\n"
    "Используя бота, вы соглашаетесь с этими условиями."
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    f"Написать админу: @{CONTACT_USERNAME}\n\n"
    "По вопросам оплаты — /paysupport\n"
    "⏱ Отвечаем в течение 24 часов."
)

PAYSUPPORT_TEXT = (
    "💳 <b>Поддержка по оплате</b>\n\n"
    "• Списание прошло, но товар не пришёл — напиши нам\n"
    "• Хочешь вернуть Stars — /refund (7 дней)\n"
    "• Двойное списание — вернём лишнее\n\n"
    f"📧 Связь: @{CONTACT_USERNAME}\n\n"
    "⚠️ <b>Важно:</b> поддержка Telegram не помогает с покупками внутри ботов."
)

SOON_TEXT = (
    "🚧 <b>В разработке</b>\n\n"
    "<b>Что готовится:</b>\n\n"
    "✏️ <b>Смена имени</b> котика\n"
    "🏆 <b>Топ игроков</b>\n"
    "🤝 <b>Рефералка</b> — зови друзей\n"
    "⚔️ <b>Дуэли котиков</b>\n"
    "📅 <b>Ежедневные задания</b>\n"
    "🎉 <b>Ивенты</b> — праздничные бонусы и скины\n\n"
    "🐾 <i>Следи за обновлениями!</i>"
)


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


# ==================== ДЕЙСТВИЯ ====================
async def _do_feed(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat[6] < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - cat[6])
        msg_text = f"Подожди {left} сек 🍽"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=False)

    anim = await _animate(target, [
        "🍖 Кормим котика.",
        "🍖 Кормим котика..",
        "🍖 Кормим котика...",
        "😋 Котик кушает...",
    ])

    coins_gain = random.randint(5, 15)
    if is_boost(cat): coins_gain *= 2
    if is_vip(cat): coins_gain += 5
    await update_cat(user_id, coins=cat[4] + coins_gain,
                     satiety=min(100, cat[5] + 20), last_feed=now)
    leveled, level = await add_xp(user_id, 10)

    txt = f"🍖 +{coins_gain} монет!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    cat = await get_cat(user_id)
    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен!</b>")
    if cat[5] >= 10:
        hints.append("🎾 Сытый котик хочет поиграть")
    if hints:
        full += "\n\n" + "\n".join(hints)

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
    if cat[5] < 10:
        msg_text = "Котик слишком голодный 😿 Сначала покорми!"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    anim = await _animate(target, [
        "🎾 Играем с котиком.",
        "🎾 Играем с котиком..",
        "🎾 Играем с котиком...",
        "😺 Котик веселится!",
    ])

    coins_gain = random.randint(10, 25)
    if is_boost(cat): coins_gain *= 2
    await update_cat(user_id, coins=cat[4] + coins_gain, satiety=max(0, cat[5] - 10))
    leveled, level = await add_xp(user_id, 20)

    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    cat = await get_cat(user_id)
    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен!</b>")
    if cat[5] < 30:
        hints.append("🍖 Котик проголодался — покорми!")
    if hints:
        full += "\n\n" + "\n".join(hints)

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
    last = cat[9]
    streak = cat[10]

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

    base = 50
    bonus = base + (streak - 1) * 15
    if streak >= 7:
        bonus += 100
    if is_vip(cat):
        bonus *= 2

    await update_cat(user_id, coins=cat[4] + bonus, last_daily=now, streak=streak)
    leveled, level = await add_xp(user_id, 20)

    txt = (
        f"🎁 <b>Бонус выдан!</b>\n\n"
        f"💰 +<b>{bonus} монет</b>\n"
        f"🔥 Стрик: <b>{streak}</b> " + ("день" if streak == 1 else "дней")
    )
    if streak >= 7:
        txt += "\n🎉 <b>Неделя подряд! +100 монет!</b>"
    elif streak >= 3:
        txt += "\n⚡ Отличная серия!"
    if is_vip(cat):
        txt += "\n👑 VIP-бонус: x2"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"

    txt += "\n\n📢 <b>Это первая версия бонуса.</b>\n💡 Заходи каждый день — стрик растёт."

    full = await render_user(user_id) + "\n\n" + txt

    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        await target.message.answer(full, reply_markup=bottom_menu())
        await target.answer()


async def _show_shop(target):
    text = "🛒 <b>Магазин за Telegram Stars</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['stars']} ⭐</b>\n  <i>{item['desc']}</i>\n"
    text += "\n🎨 Скины — за монеты: 🎨 Скины в меню\n"
    text += "\n💸 Вернуть покупку: /refund (7 дней)"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=shop_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=shop_kb())
        except Exception:
            await target.message.answer(text, reply_markup=shop_kb())
        await target.answer()


async def _show_skins(user_id, target):
    owned = await get_user_skins(user_id)
    owned = list(set(owned) | {"default", "cat", "black"})
    current = await get_current_skin(user_id)
    cat = await get_cat(user_id)
    text = (
        "🎨 <b>Скины для котика</b>\n\n"
        f"Твой текущий: {skin_emoji(current)} <b>{SKINS.get(current, SKINS['default'])['name']}</b>\n"
        f"💰 У тебя: <b>{cat[4]} монет</b>\n\n"
        "Купленный скин показывается везде в боте.\n"
        "Жми на скин чтобы купить или выбрать."
    )
    kb = skins_kb(user_id, owned, current)
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


async def _show_paysupport(target):
    if isinstance(target, Message):
        await target.answer(PAYSUPPORT_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(PAYSUPPORT_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_profile(target):
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    text = (
        "👤 <b>Профиль котика</b>\n\n"
        + await render_user(user_id)
        + "\n\n<i>Что можно сделать:</i>"
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=profile_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=profile_kb())
        except Exception:
            await target.message.answer(text, reply_markup=profile_kb())
        await target.answer()


async def _show_report(target):
    text = (
        "🚨 <b>Пожаловаться</b>\n\n"
        "Если кто-то спамит, оскорбляет, рекламит — напиши мне:\n\n"
        f"👉 @{CONTACT_USERNAME}\n\n"
        "<b>Укажи:</b>\n"
        "• Кто (юзернейм или ID)\n"
        "• Что сделал\n"
        "• Скрин, если есть\n\n"
        "⚠️ Ложные жалобы = <b>бан</b>."
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=bottom_menu())
    else:
        await target.message.answer(text, reply_markup=bottom_menu())
        await target.answer()


async def _start_guess(user_id, target):
    cat = await get_cat(user_id)
    if cat[4] < 20:
        txt = "🎲 Нужно хотя бы 20 монет чтобы играть"
        if isinstance(target, Message):
            return await target.answer(txt)
        return await target.answer(txt, show_alert=True)

    number = random.randint(1, 10)
    active_games[user_id] = {"number": number, "tries": 3, "bet": 20}
    txt = (
        "🎲 <b>Угадай число от 1 до 10!</b>\n\n"
        "Ставка: <b>20 монет</b>\n"
        "Попыток: <b>3</b>\n"
        "Угадал — <b>+100 монет</b>\n\n"
        "Напиши число в чат 👇"
    )
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    text = (
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "Покупай скины за монеты!\n\n"
        "📌 Кнопки внизу — меню.\n"
        "📌 /help — справка.\n\n"
        + await render_user(msg.from_user.id)
    )
    if bonus_available(cat):
        text += "\n\n🎁 <b>Бонус дня доступен!</b>"
    await msg.answer(text, reply_markup=bottom_menu())


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    await msg.answer(await render_user(msg.from_user.id), reply_markup=bottom_menu())


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await _show_help(msg)


@dp.message(Command("daily"))
async def cmd_daily(msg: Message):
    await _do_daily(msg.from_user.id, msg)


@dp.message(Command("soon"))
async def cmd_soon(msg: Message):
    await _show_soon(msg)


@dp.message(Command("terms"))
async def cmd_terms(msg: Message):
    await msg.answer(TERMS_TEXT, reply_markup=bottom_menu())


@dp.message(Command("support"))
async def cmd_support(msg: Message):
    await _show_support(msg)


@dp.message(Command("paysupport"))
async def cmd_paysupport(msg: Message):
    await _show_paysupport(msg)


@dp.message(Command("hide"))
async def cmd_hide(msg: Message):
    await msg.answer("Меню свёрнуто. Введи /menu чтобы вернуть.",
                     reply_markup=ReplyKeyboardRemove())


@dp.message(Command("mute"))
async def cmd_mute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                         (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔕 <b>Напоминания отключены</b>\n\nВключить: /unmute",
                     reply_markup=bottom_menu())


@dp.message(Command("unmute"))
async def cmd_unmute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=0 WHERE user_id=?",
                         (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔔 <b>Напоминания включены</b>",
                     reply_markup=bottom_menu())


@dp.message(Command("report"))
async def cmd_report(msg: Message):
    await _show_report(msg)


# ==================== АДМИН ====================
@dp.message(Command("ban"))
async def cmd_ban(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Использование: <code>/ban user_id [часы]</code>")
    try:
        target_id = int(parts[1])
        hours = int(parts[2]) if len(parts) > 2 else 24
    except ValueError:
        return await msg.answer("Неверный формат")
    until = int(time.time()) + hours * 3600
    banned_users[target_id] = until
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=? WHERE user_id=?",
                             (until, target_id))
            await db.commit()
    except Exception:
        pass
    await msg.answer(f"🚫 <code>{target_id}</code> забанен на {hours}ч")


@dp.message(Command("unban"))
async def cmd_unban(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Использование: <code>/unban user_id</code>")
    try:
        target_id = int(parts[1])
    except ValueError:
        return await msg.answer("Неверный формат")
    banned_users.pop(target_id, None)
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=0 WHERE user_id=?",
                             (target_id,))
            await db.commit()
    except Exception:
        pass
    await msg.answer(f"✅ <code>{target_id}</code> разбанен")


@dp.message(Command("complaints"))
async def cmd_complaints(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, from_user_id, reported_user_id, reason, created_at "
            "FROM complaints WHERE processed=0 ORDER BY created_at DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    if not rows:
        return await msg.answer("📭 Нет активных жалоб")
    text = "📋 <b>Жалобы</b>\n\n"
    for cid, from_id, to_id, reason, ts in rows:
        ago = (int(time.time()) - ts) // 60
        text += f"#{cid} | <code>{from_id}</code> → <code>{to_id}</code>\n<i>{reason}</i>\n⏱ {ago} мин\n\n"
    await msg.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("SELECT COUNT(*) FROM cats")
            total = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?",
                                   (int(time.time()) - 86400,))
            active_day = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?",
                                   (int(time.time()) - 604800,))
            active_week = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE vip=1")
            vips = (await cur.fetchone())[0]
            cur = await db.execute("SELECT SUM(coins) FROM cats")
            total_coins = (await cur.fetchone())[0] or 0
            cur = await db.execute("SELECT AVG(level) FROM cats")
            avg_level = (await cur.fetchone())[0] or 0
            cur = await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(stars),0) FROM payments WHERE refunded=0"
            )
            row = await cur.fetchone()
            buys, total_stars = row if row else (0, 0)
            cur = await db.execute("SELECT COUNT(*) FROM payments WHERE refunded=1")
            refunds = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM user_skins")
            skins_bought = (await cur.fetchone())[0]

        banned_now = sum(1 for uid, until in banned_users.items() if until > int(time.time()))

        await msg.answer(
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Юзеров: <b>{total}</b>\n"
            f"📅 Активных 24ч: <b>{active_day}</b>\n"
            f"📆 Активных 7д: <b>{active_week}</b>\n"
            f"👑 VIP: <b>{vips}</b>\n"
            f"🚫 Забанено: <b>{banned_now}</b>\n\n"
            f"💰 Монет: <b>{total_coins}</b>\n"
            f"📈 Ср. уровень: <b>{avg_level:.1f}</b>\n"
            f"🎨 Скинов куплено: <b>{skins_bought}</b>\n\n"
            f"🛒 Покупок: <b>{buys}</b>\n"
            f"⭐ Звёзд: <b>{total_stars}</b>\n"
            f"↩️ Возвратов: <b>{refunds}</b>"
        )
    except Exception as e:
        await msg.answer(f"Ошибка: <code>{e}</code>")


# ==================== ВОЗВРАТ ====================
@dp.message(Command("refund"))
async def cmd_refund(msg: Message):
    user_id = msg.from_user.id
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, item_key, stars, charge_id, created_at FROM payments "
            "WHERE user_id=? AND refunded=0 ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        payments = await cur.fetchall()

    if not payments:
        return await msg.answer(
            "💸 <b>Нет покупок для возврата</b>\n\n"
            "• Возможно, ты ещё ничего не покупал\n"
            "• Или уже вернул\n"
            "• Если платил до обновления бота — платёж не сохранился\n\n"
            f"По вопросам: @{CONTACT_USERNAME}",
            reply_markup=bottom_menu()
        )

    kb_rows = []
    for pid, key, stars, charge_id, ts in payments:
        ago = now - ts
        if ago > REFUND_WINDOW:
            continue
        item = SHOP.get(key, {"title": key})
        left_hours = (REFUND_WINDOW - ago) // 3600
        kb_rows.append([InlineKeyboardButton(
            text=f"↩️ {item['title']} — {stars}⭐ ({left_hours}ч)",
            callback_data=f"refund:{pid}"
        )])

    if not kb_rows:
        return await msg.answer(
            "💸 <b>Нет покупок для возврата</b>\n\nВозврат в течение <b>7 дней</b>.",
            reply_markup=bottom_menu()
        )

    await msg.answer(
        "💸 <b>Возврат</b>\n\nВыбери покупку. ⭐ вернутся сразу, товар отменится.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )


@dp.callback_query(F.data.startswith("refund:"))
async def cb_refund(cb: CallbackQuery):
    try:
        pid = int(cb.data.split(":")[1])
    except Exception:
        return await cb.answer("Ошибка", show_alert=True)
    user_id = cb.from_user.id
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT user_id, item_key, stars, charge_id, created_at, refunded "
            "FROM payments WHERE id=?", (pid,)
        )
        row = await cur.fetchone()
    if not row:
        return await cb.answer("Платёж не найден", show_alert=True)
    owner_id, key, stars, charge_id, created_at, refunded = row
    if owner_id != user_id:
        return await cb.answer("Не твой платёж", show_alert=True)
    if refunded:
        return await cb.answer("Уже возвращён", show_alert=True)
    if now - created_at > REFUND_WINDOW:
        return await cb.answer("Прошло больше 7 дней", show_alert=True)
    if not charge_id:
        return await cb.answer("Нет данных. /paysupport", show_alert=True)

    cat = await get_cat(user_id)
    if key == "food10":
        await update_cat(user_id, coins=max(0, cat[4] - 100))
    elif key == "boost":
        await update_cat(user_id, boost_until=0)
    elif key == "vip":
        await update_cat(user_id, vip=0)

    try:
        await bot.refund_star_payment(user_id=user_id,
                                      telegram_payment_charge_id=charge_id)
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE payments SET refunded=1 WHERE id=?", (pid,))
            await db.commit()
        await cb.message.edit_text(
            f"✅ <b>Возврат оформлен</b>\n\n⭐ {stars} звёзд вернулись.\nТовар отменён."
        )
        try:
            await bot.send_message(ADMIN_ID,
                f"↩️ Возврат: <code>{user_id}</code> — {key} {stars}⭐")
        except Exception:
            pass
    except Exception as e:
        err = str(e)
        if "CHARGE_ALREADY_REFUNDED" in err:
            await cb.message.edit_text("ℹ️ Уже возвращён.")
        else:
            await cb.message.edit_text(
                f"❌ <b>Ошибка</b>\n<code>{err}</code>\n\nНапиши: @{CONTACT_USERNAME}"
            )
    await cb.answer()


# ==================== КНОПКИ ВНИЗУ ====================
@dp.message(F.text == "🍖 Покормить")
async def btn_feed(msg: Message):
    await _do_feed(msg.from_user.id, msg)


@dp.message(F.text == "🎾 Поиграть")
async def btn_play(msg: Message):
    await _do_play(msg.from_user.id, msg)


@dp.message(F.text == "🎲 Угадай")
async def btn_guess(msg: Message):
    await _start_guess(msg.from_user.id, msg)


@dp.message(F.text == "🎁 Бонус дня")
async def btn_daily(msg: Message):
    await _do_daily(msg.from_user.id, msg)


@dp.message(F.text == "🛒 Магазин")
async def btn_shop(msg: Message):
    await _show_shop(msg)


@dp.message(F.text == "🎨 Скины")
async def btn_skins(msg: Message):
    await _show_skins(msg.from_user.id, msg)


@dp.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    await _show_profile(msg)


@dp.message(F.text == "🚨 Жалоба")
async def btn_report(msg: Message):
    await _show_report(msg)


@dp.message(F.text == "❓ Помощь")
async def btn_help(msg: Message):
    await _show_help(msg)


@dp.message(F.text == "❌ Скрыть меню")
async def btn_hide(msg: Message):
    await msg.answer("✅ Меню свёрнуто.\n\nВведи /menu или /start — вернуть.",
                     reply_markup=ReplyKeyboardRemove())


# ==================== ЧИСЛА ====================
@dp.message(F.text.regexp(r"^\d+$"))
async def guess_handler(msg: Message):
    user_id = msg.from_user.id
    game = active_games.get(user_id)
    if not game:
        try:
            await msg.delete()
        except Exception:
            pass
        return
    try:
        guess = int(msg.text)
    except ValueError:
        return
    cat = await get_cat(user_id)
    if guess == game["number"]:
        win = game["bet"] * 5
        if is_boost(cat): win *= 2
        await update_cat(user_id, coins=cat[4] + win)
        await add_xp(user_id, 30)
        del active_games[user_id]
        await msg.answer(
            f"🎉 <b>Угадал!</b> Число: <b>{game['number']}</b>\n+{win} монет 💰\n\n"
            + await render_user(user_id),
            reply_markup=bottom_menu()
        )
    else:
        game["tries"] -= 1
        if game["tries"] <= 0:
            await update_cat(user_id, coins=max(0, cat[4] - game["bet"]))
            del active_games[user_id]
            await msg.answer(
                f"😿 <b>Не угадал!</b> Было: <b>{game['number']}</b>\n-{game['bet']} монет\n\n"
                + await render_user(user_id),
                reply_markup=bottom_menu()
            )
        else:
            hint = "🔽 меньше" if guess > game["number"] else "🔼 больше"
            await msg.answer(f"❌ Не то. Подсказка: <b>{hint}</b>\nОсталось: <b>{game['tries']}</b>")


# ==================== ИНЛАЙН ====================
@dp.callback_query(F.data == "refresh")
async def cb_refresh(cb: CallbackQuery):
    try:
        await cb.message.edit_text(await render_user(cb.from_user.id), reply_markup=main_kb())
    except Exception:
        pass
    await cb.answer()


@dp.callback_query(F.data == "feed")
async def cb_feed(cb: CallbackQuery):
    await _do_feed(cb.from_user.id, cb)


@dp.callback_query(F.data == "play")
async def cb_play(cb: CallbackQuery):
    await _do_play(cb.from_user.id, cb)


@dp.callback_query(F.data == "daily")
async def cb_daily(cb: CallbackQuery):
    await _do_daily(cb.from_user.id, cb)


@dp.callback_query(F.data == "guess")
async def cb_guess(cb: CallbackQuery):
    await _start_guess(cb.from_user.id, cb)


@dp.callback_query(F.data == "shop")
async def cb_shop(cb: CallbackQuery):
    await _show_shop(cb)


@dp.callback_query(F.data == "soon")
async def cb_soon(cb: CallbackQuery):
    await _show_soon(cb)


@dp.callback_query(F.data == "skins_menu")
async def cb_skins_menu(cb: CallbackQuery):
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data == "rename")
async def cb_rename(cb: CallbackQuery):
    await cb.message.answer(
        "✏️ <b>Смена имени — в разработке</b>\n\n"
        "Скоро: имя 1 раз в день бесплатно, до 20 символов.",
        reply_markup=profile_kb()
    )
    await cb.answer()


@dp.callback_query(F.data == "notif_settings")
async def cb_notif(cb: CallbackQuery):
    await cb.message.answer(
        "🔔 <b>Уведомления</b>\n\n"
        "🍖 Котик проголодался (24ч)\n"
        "🎾 Котик хочет играть (2ч)\n"
        "🎁 Бонус дня ждёт\n\n"
        "/mute — отключить\n/unmute — включить"
    )
    await cb.answer()


@dp.callback_query(F.data == "report")
async def cb_report(cb: CallbackQuery):
    await _show_report(cb)


@dp.callback_query(F.data == "mute")
async def cb_mute(cb: CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                         (cb.from_user.id,))
        await db.commit()
    try:
        await cb.message.edit_text("🔕 Напоминания отключены.\nВключить: /unmute")
    except Exception:
        pass
    await cb.answer()


# ==================== СКИНЫ (всё за монеты) ====================
@dp.callback_query(F.data.startswith("select_skin:"))
async def cb_select_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    if key not in SKINS:
        return await cb.answer("Скин не найден", show_alert=True)
    owned = await get_user_skins(cb.from_user.id)
    owned = set(owned) | {"default", "cat", "black"}
    if key not in owned:
        return await cb.answer("Сначала купи скин", show_alert=True)
    await update_cat(cb.from_user.id, current_skin=key)
    await cb.answer(f"✅ Скин выбран: {SKINS[key]['name']}")
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data.startswith("buy_skin:"))
async def cb_buy_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    s = SKINS.get(key)
    if not s:
        return await cb.answer("Недоступно", show_alert=True)
    if s["coins"] <= 0:
        # бесплатный скин — просто добавляем
        await add_user_skin(cb.from_user.id, key)
        await update_cat(cb.from_user.id, current_skin=key)
        await cb.answer(f"✅ {s['name']} выбран!")
        return await _show_skins(cb.from_user.id, cb)

    cat = await get_cat(cb.from_user.id)
    if cat[4] < s["coins"]:
        return await cb.answer(
            f"Не хватает монет. Нужно {s['coins']}💰, у тебя {cat[4]}💰",
            show_alert=True
        )
    await update_cat(cb.from_user.id, coins=cat[4] - s["coins"])
    await add_user_skin(cb.from_user.id, key)
    await update_cat(cb.from_user.id, current_skin=key)
    await cb.answer(f"✅ Куплен {s['name']}!")
    try:
        await cb.message.answer(
            f"🎉 <b>Скин куплен!</b>\n\n"
            f"{s['emoji']} <b>{s['name']}</b>\n"
            f"Списано: <b>{s['coins']} монет</b>\n\n"
            f"Он сразу применён!",
            reply_markup=bottom_menu()
        )
    except Exception:
        pass
    await _show_skins(cb.from_user.id, cb)


# ==================== ОПЛАТА ====================
@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def on_paid(msg: Message):
    payload = msg.successful_payment.invoice_payload
    user_id = msg.from_user.id
    stars = msg.successful_payment.total_amount
    charge_id = msg.successful_payment.telegram_payment_charge_id
    cat = await get_cat(user_id)

    key = payload.split(":")[1]
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO payments(user_id, item_key, stars, charge_id, created_at) "
                "VALUES(?,?,?,?,?)",
                (user_id, key, stars, charge_id, int(time.time()))
            )
            await db.commit()
    except Exception:
        pass

    if key == "food10":
        await update_cat(user_id, coins=cat[4] + 100)
        text = "🍖 +100 монет!"
    elif key == "boost":
        until = max(int(time.time()), cat[8]) + 24 * 3600
        await update_cat(user_id, boost_until=until)
        text = "⚡ Ускоритель x2 на 24ч!"
    elif key == "vip":
        await update_cat(user_id, vip=1)
        text = "👑 VIP активирован!"
    else:
        text = "✅ Оплата получена!"

    await msg.answer(f"✅ <b>Оплата прошла!</b>\n{text}\n\n💸 /refund — вернуть (7 дней)",
                     reply_markup=bottom_menu())

    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID,
                f"💰 <b>Покупка!</b>\n"
                f"👤 @{msg.from_user.username} (<code>{user_id}</code>)\n"
                f"📦 {key} — {stars}⭐")
        except Exception:
            pass


# ==================== УДАЛЕНИЕ ЛИШНЕГО ====================
@dp.message(F.photo | F.video | F.video_note | F.voice | F.audio |
            F.document | F.sticker | F.animation | F.location |
            F.contact | F.poll | F.venue | F.dice)
async def delete_media(msg: Message):
    try:
        await msg.delete()
    except Exception:
        pass
    key = msg.from_user.id
    now = int(time.time())
    if now - warned_users.get(key, 0) < WARN_COOLDOWN:
        return
    warned_users[key] = now
    try:
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>\n\nМеню внизу или /help.")
    except Exception:
        pass


@dp.message(F.text & ~F.text.startswith("/") & ~F.text.regexp(r"^\d+$"))
async def delete_random_text(msg: Message):
    try:
        await msg.delete()
    except Exception:
        pass
    key = msg.from_user.id
    now = int(time.time())
    if now - warned_users.get(key, 0) < WARN_COOLDOWN:
        return
    warned_users[key] = now
    try:
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>\n\nМеню внизу или /help.")
    except Exception:
        pass


# ==================== ФОН ====================
async def vip_income_loop():
    while True:
        try:
            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE cats SET coins = coins + 10 WHERE vip=1")
                await db.commit()
        except Exception as e:
            print(f"vip_income_loop: {e}")
        await asyncio.sleep(3600)


async def reminder_loop():
    await asyncio.sleep(60)
    while True:
        try:
            now = int(time.time())
            day_ago = now - 86400
            async with aiosqlite.connect(DB) as db:
                cur = await db.execute(
                    "SELECT user_id, name, last_seen, last_remind, last_daily, "
                    "last_play_remind, satiety, coins FROM cats "
                    "WHERE last_seen < ? AND last_seen > 0",
                    (day_ago,)
                )
                rows = await cur.fetchall()
            for (user_id, name, last_seen, last_remind, last_daily,
                 last_play_remind, satiety, coins) in rows:
                if is_banned(user_id):
                    continue
                send_general = (not last_remind) or (now - last_remind >= REMIND_COOLDOWN)
                send_play = (not last_play_remind) or (now - last_play_remind >= PLAY_REMIND_COOLDOWN)
                days = (now - last_seen) // 86400
                bonus_ready = (now - last_daily) >= DAILY_COOLDOWN
                can_play = satiety >= 10 and coins >= 20
                if send_general and days >= 1:
                    parts = []
                    if days >= 7:
                        parts.append(f"🐱 <b>{name} очень скучает!</b>\nТы не заходил <b>{days} дней</b> 😿")
                    elif days >= 3:
                        parts.append(f"🐱 <b>{name} скучает</b>\nНе заходил <b>{days} дня</b>.")
                    else:
                        parts.append(f"🐱 <b>{name} проголодался!</b>")
                    if bonus_ready:
                        parts.append("\n🎁 <b>Бонус дня ждёт!</b>")
                    if can_play:
                        parts.append("🎾 Котик хочет поиграть!")
                    parts.append("\nПокорми 🍖")
                    text = "\n".join(parts)
                    buttons = []
                    if bonus_ready:
                        buttons.append([InlineKeyboardButton(text="🎁 Бонус", callback_data="daily")])
                    buttons.append([InlineKeyboardButton(text="🍖 Покормить", callback_data="feed")])
                    if can_play:
                        buttons.append([InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")])
                    buttons.append([InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")])
                    try:
                        await bot.send_message(user_id, text,
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                        async with aiosqlite.connect(DB) as db:
                            await db.execute("UPDATE cats SET last_remind=? WHERE user_id=?",
                                             (now, user_id))
                            await db.commit()
                    except Exception as e:
                        print(f"reminder {user_id}: {e}")
                        if "blocked" in str(e).lower():
                            try:
                                async with aiosqlite.connect(DB) as db:
                                    await db.execute(
                                        "UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                                        (user_id,))
                                    await db.commit()
                            except Exception:
                                pass
                elif send_play and can_play and days < 1:
                    try:
                        await bot.send_message(user_id,
                            f"🎾 <b>{name} хочет поиграть!</b>",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
                                [InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")]
                            ]))
                        async with aiosqlite.connect(DB) as db:
                            await db.execute("UPDATE cats SET last_play_remind=? WHERE user_id=?",
                                             (now, user_id))
                            await db.commit()
                    except Exception as e:
                        print(f"play reminder {user_id}: {e}")
        except Exception as e:
            print(f"reminder_loop: {e}")
        await asyncio.sleep(3600)


async def unban_loop():
    while True:
        try:
            now = int(time.time())
            to_unban = [uid for uid, until in banned_users.items() if until <= now]
            for uid in to_unban:
                del banned_users[uid]
                try:
                    async with aiosqlite.connect(DB) as db:
                        await db.execute("UPDATE cats SET banned_until=0 WHERE user_id=?", (uid,))
                        await db.commit()
                except Exception:
                    pass
                try:
                    await bot.send_message(uid, "✅ Ты разбанен!")
                except Exception:
                    pass
        except Exception as e:
            print(f"unban_loop: {e}")
        await asyncio.sleep(300)


async def setup_commands():
    commands = [
        BotCommand(command="start",      description="🐱 Запустить"),
        BotCommand(command="menu",       description="📋 Меню"),
        BotCommand(command="daily",      description="🎁 Бонус дня"),
        BotCommand(command="soon",       description="🚧 Что в разработке"),
        BotCommand(command="help",       description="❓ Помощь"),
        BotCommand(command="support",    description="🆘 Поддержка"),
        BotCommand(command="paysupport", description="💳 Оплата"),
        BotCommand(command="report",     description="🚨 Пожаловаться"),
        BotCommand(command="refund",     description="💸 Вернуть звёзды"),
        BotCommand(command="terms",      description="📜 Условия"),
        BotCommand(command="mute",       description="🔕 Отключить напоминания"),
        BotCommand(command="unmute",     description="🔔 Включить напоминания"),
        BotCommand(command="hide",       description="❌ Скрыть меню"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        print(f"setup_commands: {e}")


async def main():
    await init_db()
    await setup_commands()
    dp.message.middleware(AntiSpamMiddleware())
    dp.callback_query.middleware(AntiSpamMiddleware())
    asyncio.create_task(vip_income_loop())
    asyncio.create_task(reminder_loop())
    asyncio.create_task(unban_loop())
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main()) import asyncio
import aiosqlite
import time
import random
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.client.default import DefaultBotProperties

# ==== НАСТРОЙКИ ====
BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_ID = 5965370780
CONTACT_USERNAME = "Artemchic2009"
# ===================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
REMIND_COOLDOWN = 86400
PLAY_REMIND_COOLDOWN = 7200
REFUND_WINDOW = 604800
SPAM_WINDOW = 10
SPAM_LIMIT = 15
BAN_DURATION = 86400
WARN_COOLDOWN = 300

# Магазин — за звёзды (доход тебе)
SHOP = {
    "food10": {"title": "🍖 Корм x10", "stars": 50, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "stars": 250, "desc": "Скин + пассивный доход"},
}

# Скины — ВСЕ ЗА МОНЕТЫ
SKINS = {
    # Бесплатные
    "default": {"emoji": "🐱", "name": "Обычный кот",  "coins": 0},
    "cat":     {"emoji": "🐈", "name": "Кошка",        "coins": 0},
    "black":   {"emoji": "🐈‍⬛", "name": "Чёрный кот",  "coins": 0},
    # Платные
    "fox":     {"emoji": "🦊", "name": "Рыжий",        "coins": 100},
    "tiger":   {"emoji": "🐯", "name": "Тигр",         "coins": 250},
    "lion":    {"emoji": "🦁", "name": "Лев",          "coins": 400},
    "leopard": {"emoji": "🐆", "name": "Пантера",      "coins": 600},
    "bear":    {"emoji": "🐻", "name": "Медведь-кот",  "coins": 800},
    "panda":   {"emoji": "🐼", "name": "Панда",        "coins": 1000},
    "wolf":    {"emoji": "🐺", "name": "Волк",         "coins": 1300},
    "unicorn": {"emoji": "🦄", "name": "Единорог",     "coins": 1800},
    "dragon":  {"emoji": "🐉", "name": "Дракон",       "coins": 2500},
    "king":    {"emoji": "👑", "name": "Королевский",  "coins": 3000},
    "robot":   {"emoji": "🤖", "name": "Кот-робот",    "coins": 3500},
    "cosmo":   {"emoji": "🚀", "name": "Космо-кот",    "coins": 4000},
    "ghost":   {"emoji": "👻", "name": "Кот-призрак",  "coins": 4500},
    "fire":    {"emoji": "🔥", "name": "Огненный",     "coins": 5000},
}

active_games = {}
warned_users = {}
spam_tracker = {}
banned_users = {}


# ==================== БАЗА ДАННЫХ ====================
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
                streak INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_key TEXT,
                stars INTEGER,
                charge_id TEXT,
                created_at INTEGER,
                refunded INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_user_id INTEGER,
                reported_user_id INTEGER,
                reason TEXT,
                created_at INTEGER,
                processed INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_skins (
                user_id INTEGER,
                skin_key TEXT,
                purchased_at INTEGER,
                PRIMARY KEY (user_id, skin_key)
            )
        """)
        for col, default in [
            ("last_seen", "0"),
            ("last_remind", "0"),
            ("last_play_remind", "0"),
            ("warnings", "0"),
            ("banned_until", "0"),
            ("current_skin", "'default'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE cats ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass
        try:
            await db.execute("ALTER TABLE payments ADD COLUMN refunded INTEGER DEFAULT 0")
        except Exception:
            pass
        await db.commit()


async def get_cat(user_id):
    async with aiosqlite.connect(DB) as db:
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
                "INSERT INTO user_skins(user_id, skin_key, purchased_at) VALUES(?,?,?)",
                (user_id, skin_key, int(time.time()))
            )
            await db.commit()
        except Exception:
            pass


async def get_current_skin(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT current_skin FROM cats WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            return row[0]
    return "default"


# ==================== АНТИСПАМ ====================
def is_banned(user_id):
    until = banned_users.get(user_id, 0)
    if until > int(time.time()):
        return True
    if until and until <= int(time.time()):
        del banned_users[user_id]
    return False


def track_spam(user_id):
    now = time.time()
    times = spam_tracker.get(user_id, [])
    times = [t for t in times if now - t < SPAM_WINDOW]
    times.append(now)
    spam_tracker[user_id] = times
    return len(times) >= SPAM_LIMIT


async def auto_ban(user_id):
    until = int(time.time()) + BAN_DURATION
    banned_users[user_id] = until
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=? WHERE user_id=?",
                             (until, user_id))
            await db.commit()
    except Exception:
        pass
    try:
        await bot.send_message(user_id,
            f"🚫 <b>Ты забанен на {BAN_DURATION // 3600} часов за спам.</b>")
    except Exception:
        pass
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID,
                f"🚫 Автобан: <code>{user_id}</code>")
        except Exception:
            pass


# ==================== MIDDLEWARE ====================
class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            if is_banned(user.id):
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 Ты забанен.",
                                           reply_markup=ReplyKeyboardRemove())
                    except Exception:
                        pass
                return
            if isinstance(event, Message):
                if track_spam(user.id):
                    await auto_ban(user.id)
                    return
            try:
                async with aiosqlite.connect(DB) as db:
                    await db.execute("UPDATE cats SET last_seen=? WHERE user_id=?",
                                     (int(time.time()), user.id))
                    await db.commit()
            except Exception:
                pass
        return await handler(event, data)


# ==================== ЛОГИКА ====================
def xp_for_next(level):
    return level * 100


async def add_xp(user_id, amount):
    cat = await get_cat(user_id)
    xp = cat[3] + amount
    level = cat[2]
    leveled = False
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
        leveled = True
    await update_cat(user_id, xp=xp, level=level)
    return leveled, level


def is_boost(cat):
    return cat[8] > int(time.time())


def is_vip(cat):
    return cat[9] == 1


def bonus_available(cat):
    return int(time.time()) - cat[10] >= DAILY_COOLDOWN


def skin_emoji(skin_key):
    s = SKINS.get(skin_key)
    return s["emoji"] if s else "🐱"


def render(cat, skin_key="default"):
    _, name, level, xp, coins, satiety, _, boost_until, vip, last_daily, streak = cat[:11]
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
    skin = await get_current_skin(user_id)
    return render(cat, skin)


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть",  callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня",   callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин",  callback_data="shop"),
         InlineKeyboardButton(text="🎨 Скины",   callback_data="skins_menu")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def shop_kb():
    rows = []
    for key, item in SHOP.items():
        rows.append([InlineKeyboardButton(
            text=f"{item['title']} — {item['stars']} ⭐",
            callback_data=f"buy:{key}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skins_kb(user_id, owned, current):
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
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notif_settings")],
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="report")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def bottom_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍖 Покормить"), KeyboardButton(text="🎾 Поиграть")],
            [KeyboardButton(text="🎲 Угадай"),    KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"),   KeyboardButton(text="🎨 Скины")],
            [KeyboardButton(text="👤 Профиль"),   KeyboardButton(text="🚨 Жалоба")],
            [KeyboardButton(text="❓ Помощь"),    KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ==================== ТЕКСТЫ ====================
HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Это игра-тамагочи про котика.</b>\n"
    "Корми, играй, качай уровень, зарабатывай монеты.\n"
    "Меняй скины за монеты!\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (раз в 30 сек)\n"
    "🎾 Поиграть — +XP и монеты\n"
    "🎲 Угадай — мини-игра\n"
    "🎁 Бонус дня — раз в 24 часа\n"
    "🛒 Магазин — покупки за ⭐\n"
    "🎨 Скины — разные коты за монеты\n"
    "👤 Профиль — твой котик\n"
    "🚨 Жалоба — пожаловаться на юзера\n\n"
    "<b>📋 Команды:</b>\n"
    "/start, /menu, /daily, /soon, /help\n"
    "/support — поддержка\n"
    "/paysupport — оплата\n"
    "/terms — условия\n"
    "/refund — вернуть звёзды\n"
    "/mute, /unmute — напоминания\n"
    "/hide — скрыть меню\n\n"
    "📷 <b>Фото, видео, стикеры, текст — удаляются.</b>\n"
    "⚠️ Спам = <b>бан на 24 часа</b>.\n\n"
    "👑 <b>VIP</b> — +10 монет каждый час"
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра-тамагочи. Все покупки — цифровые товары.\n"
    "2. Монеты и бонусы внутри игры не имеют денежной ценности.\n"
    "3. Возврат средств за Stars — /refund, 7 дней.\n"
    "4. Игра предоставляется «как есть».\n"
    "5. Спам, флуд — <b>бан 24 часа</b>.\n"
    "6. Право менять условия.\n\n"
    "Используя бота, вы соглашаетесь с этими условиями."
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    f"Написать админу: @{CONTACT_USERNAME}\n\n"
    "По вопросам оплаты — /paysupport\n"
    "⏱ Отвечаем в течение 24 часов."
)

PAYSUPPORT_TEXT = (
    "💳 <b>Поддержка по оплате</b>\n\n"
    "• Списание прошло, но товар не пришёл — напиши нам\n"
    "• Хочешь вернуть Stars — /refund (7 дней)\n"
    "• Двойное списание — вернём лишнее\n\n"
    f"📧 Связь: @{CONTACT_USERNAME}\n\n"
    "⚠️ <b>Важно:</b> поддержка Telegram не помогает с покупками внутри ботов."
)

SOON_TEXT = (
    "🚧 <b>В разработке</b>\n\n"
    "<b>Что готовится:</b>\n\n"
    "✏️ <b>Смена имени</b> котика\n"
    "🏆 <b>Топ игроков</b>\n"
    "🤝 <b>Рефералка</b> — зови друзей\n"
    "⚔️ <b>Дуэли котиков</b>\n"
    "📅 <b>Ежедневные задания</b>\n"
    "🎉 <b>Ивенты</b> — праздничные бонусы и скины\n\n"
    "🐾 <i>Следи за обновлениями!</i>"
)


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


# ==================== ДЕЙСТВИЯ ====================
async def _do_feed(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat[6] < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - cat[6])
        msg_text = f"Подожди {left} сек 🍽"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=False)

    anim = await _animate(target, [
        "🍖 Кормим котика.",
        "🍖 Кормим котика..",
        "🍖 Кормим котика...",
        "😋 Котик кушает...",
    ])

    coins_gain = random.randint(5, 15)
    if is_boost(cat): coins_gain *= 2
    if is_vip(cat): coins_gain += 5
    await update_cat(user_id, coins=cat[4] + coins_gain,
                     satiety=min(100, cat[5] + 20), last_feed=now)
    leveled, level = await add_xp(user_id, 10)

    txt = f"🍖 +{coins_gain} монет!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    cat = await get_cat(user_id)
    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен!</b>")
    if cat[5] >= 10:
        hints.append("🎾 Сытый котик хочет поиграть")
    if hints:
        full += "\n\n" + "\n".join(hints)

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
    if cat[5] < 10:
        msg_text = "Котик слишком голодный 😿 Сначала покорми!"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    anim = await _animate(target, [
        "🎾 Играем с котиком.",
        "🎾 Играем с котиком..",
        "🎾 Играем с котиком...",
        "😺 Котик веселится!",
    ])

    coins_gain = random.randint(10, 25)
    if is_boost(cat): coins_gain *= 2
    await update_cat(user_id, coins=cat[4] + coins_gain, satiety=max(0, cat[5] - 10))
    leveled, level = await add_xp(user_id, 20)

    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    full = await render_user(user_id) + f"\n\n{txt}"

    cat = await get_cat(user_id)
    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен!</b>")
    if cat[5] < 30:
        hints.append("🍖 Котик проголодался — покорми!")
    if hints:
        full += "\n\n" + "\n".join(hints)

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
    last = cat[9]
    streak = cat[10]

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

    base = 50
    bonus = base + (streak - 1) * 15
    if streak >= 7:
        bonus += 100
    if is_vip(cat):
        bonus *= 2

    await update_cat(user_id, coins=cat[4] + bonus, last_daily=now, streak=streak)
    leveled, level = await add_xp(user_id, 20)

    txt = (
        f"🎁 <b>Бонус выдан!</b>\n\n"
        f"💰 +<b>{bonus} монет</b>\n"
        f"🔥 Стрик: <b>{streak}</b> " + ("день" if streak == 1 else "дней")
    )
    if streak >= 7:
        txt += "\n🎉 <b>Неделя подряд! +100 монет!</b>"
    elif streak >= 3:
        txt += "\n⚡ Отличная серия!"
    if is_vip(cat):
        txt += "\n👑 VIP-бонус: x2"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"

    txt += "\n\n📢 <b>Это первая версия бонуса.</b>\n💡 Заходи каждый день — стрик растёт."

    full = await render_user(user_id) + "\n\n" + txt

    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        await target.message.answer(full, reply_markup=bottom_menu())
        await target.answer()


async def _show_shop(target):
    text = "🛒 <b>Магазин за Telegram Stars</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['stars']} ⭐</b>\n  <i>{item['desc']}</i>\n"
    text += "\n🎨 Скины — за монеты: 🎨 Скины в меню\n"
    text += "\n💸 Вернуть покупку: /refund (7 дней)"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=shop_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=shop_kb())
        except Exception:
            await target.message.answer(text, reply_markup=shop_kb())
        await target.answer()


async def _show_skins(user_id, target):
    owned = await get_user_skins(user_id)
    owned = list(set(owned) | {"default", "cat", "black"})
    current = await get_current_skin(user_id)
    cat = await get_cat(user_id)
    text = (
        "🎨 <b>Скины для котика</b>\n\n"
        f"Твой текущий: {skin_emoji(current)} <b>{SKINS.get(current, SKINS['default'])['name']}</b>\n"
        f"💰 У тебя: <b>{cat[4]} монет</b>\n\n"
        "Купленный скин показывается везде в боте.\n"
        "Жми на скин чтобы купить или выбрать."
    )
    kb = skins_kb(user_id, owned, current)
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


async def _show_paysupport(target):
    if isinstance(target, Message):
        await target.answer(PAYSUPPORT_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(PAYSUPPORT_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_profile(target):
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    text = (
        "👤 <b>Профиль котика</b>\n\n"
        + await render_user(user_id)
        + "\n\n<i>Что можно сделать:</i>"
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=profile_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=profile_kb())
        except Exception:
            await target.message.answer(text, reply_markup=profile_kb())
        await target.answer()


async def _show_report(target):
    text = (
        "🚨 <b>Пожаловаться</b>\n\n"
        "Если кто-то спамит, оскорбляет, рекламит — напиши мне:\n\n"
        f"👉 @{CONTACT_USERNAME}\n\n"
        "<b>Укажи:</b>\n"
        "• Кто (юзернейм или ID)\n"
        "• Что сделал\n"
        "• Скрин, если есть\n\n"
        "⚠️ Ложные жалобы = <b>бан</b>."
    )
    if isinstance(target, Message):
        await target.answer(text, reply_markup=bottom_menu())
    else:
        await target.message.answer(text, reply_markup=bottom_menu())
        await target.answer()


async def _start_guess(user_id, target):
    cat = await get_cat(user_id)
    if cat[4] < 20:
        txt = "🎲 Нужно хотя бы 20 монет чтобы играть"
        if isinstance(target, Message):
            return await target.answer(txt)
        return await target.answer(txt, show_alert=True)

    number = random.randint(1, 10)
    active_games[user_id] = {"number": number, "tries": 3, "bet": 20}
    txt = (
        "🎲 <b>Угадай число от 1 до 10!</b>\n\n"
        "Ставка: <b>20 монет</b>\n"
        "Попыток: <b>3</b>\n"
        "Угадал — <b>+100 монет</b>\n\n"
        "Напиши число в чат 👇"
    )
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


# ==================== КОМАНДЫ ====================
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    text = (
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "Покупай скины за монеты!\n\n"
        "📌 Кнопки внизу — меню.\n"
        "📌 /help — справка.\n\n"
        + await render_user(msg.from_user.id)
    )
    if bonus_available(cat):
        text += "\n\n🎁 <b>Бонус дня доступен!</b>"
    await msg.answer(text, reply_markup=bottom_menu())


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    await msg.answer(await render_user(msg.from_user.id), reply_markup=bottom_menu())


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await _show_help(msg)


@dp.message(Command("daily"))
async def cmd_daily(msg: Message):
    await _do_daily(msg.from_user.id, msg)


@dp.message(Command("soon"))
async def cmd_soon(msg: Message):
    await _show_soon(msg)


@dp.message(Command("terms"))
async def cmd_terms(msg: Message):
    await msg.answer(TERMS_TEXT, reply_markup=bottom_menu())


@dp.message(Command("support"))
async def cmd_support(msg: Message):
    await _show_support(msg)


@dp.message(Command("paysupport"))
async def cmd_paysupport(msg: Message):
    await _show_paysupport(msg)


@dp.message(Command("hide"))
async def cmd_hide(msg: Message):
    await msg.answer("Меню свёрнуто. Введи /menu чтобы вернуть.",
                     reply_markup=ReplyKeyboardRemove())


@dp.message(Command("mute"))
async def cmd_mute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                         (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔕 <b>Напоминания отключены</b>\n\nВключить: /unmute",
                     reply_markup=bottom_menu())


@dp.message(Command("unmute"))
async def cmd_unmute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=0 WHERE user_id=?",
                         (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔔 <b>Напоминания включены</b>",
                     reply_markup=bottom_menu())


@dp.message(Command("report"))
async def cmd_report(msg: Message):
    await _show_report(msg)


# ==================== АДМИН ====================
@dp.message(Command("ban"))
async def cmd_ban(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Использование: <code>/ban user_id [часы]</code>")
    try:
        target_id = int(parts[1])
        hours = int(parts[2]) if len(parts) > 2 else 24
    except ValueError:
        return await msg.answer("Неверный формат")
    until = int(time.time()) + hours * 3600
    banned_users[target_id] = until
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=? WHERE user_id=?",
                             (until, target_id))
            await db.commit()
    except Exception:
        pass
    await msg.answer(f"🚫 <code>{target_id}</code> забанен на {hours}ч")


@dp.message(Command("unban"))
async def cmd_unban(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Использование: <code>/unban user_id</code>")
    try:
        target_id = int(parts[1])
    except ValueError:
        return await msg.answer("Неверный формат")
    banned_users.pop(target_id, None)
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET banned_until=0 WHERE user_id=?",
                             (target_id,))
            await db.commit()
    except Exception:
        pass
    await msg.answer(f"✅ <code>{target_id}</code> разбанен")


@dp.message(Command("complaints"))
async def cmd_complaints(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, from_user_id, reported_user_id, reason, created_at "
            "FROM complaints WHERE processed=0 ORDER BY created_at DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    if not rows:
        return await msg.answer("📭 Нет активных жалоб")
    text = "📋 <b>Жалобы</b>\n\n"
    for cid, from_id, to_id, reason, ts in rows:
        ago = (int(time.time()) - ts) // 60
        text += f"#{cid} | <code>{from_id}</code> → <code>{to_id}</code>\n<i>{reason}</i>\n⏱ {ago} мин\n\n"
    await msg.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID: return
    try:
        async with aiosqlite.connect(DB) as db:
            cur = await db.execute("SELECT COUNT(*) FROM cats")
            total = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?",
                                   (int(time.time()) - 86400,))
            active_day = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?",
                                   (int(time.time()) - 604800,))
            active_week = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM cats WHERE vip=1")
            vips = (await cur.fetchone())[0]
            cur = await db.execute("SELECT SUM(coins) FROM cats")
            total_coins = (await cur.fetchone())[0] or 0
            cur = await db.execute("SELECT AVG(level) FROM cats")
            avg_level = (await cur.fetchone())[0] or 0
            cur = await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(stars),0) FROM payments WHERE refunded=0"
            )
            row = await cur.fetchone()
            buys, total_stars = row if row else (0, 0)
            cur = await db.execute("SELECT COUNT(*) FROM payments WHERE refunded=1")
            refunds = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM user_skins")
            skins_bought = (await cur.fetchone())[0]

        banned_now = sum(1 for uid, until in banned_users.items() if until > int(time.time()))

        await msg.answer(
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Юзеров: <b>{total}</b>\n"
            f"📅 Активных 24ч: <b>{active_day}</b>\n"
            f"📆 Активных 7д: <b>{active_week}</b>\n"
            f"👑 VIP: <b>{vips}</b>\n"
            f"🚫 Забанено: <b>{banned_now}</b>\n\n"
            f"💰 Монет: <b>{total_coins}</b>\n"
            f"📈 Ср. уровень: <b>{avg_level:.1f}</b>\n"
            f"🎨 Скинов куплено: <b>{skins_bought}</b>\n\n"
            f"🛒 Покупок: <b>{buys}</b>\n"
            f"⭐ Звёзд: <b>{total_stars}</b>\n"
            f"↩️ Возвратов: <b>{refunds}</b>"
        )
    except Exception as e:
        await msg.answer(f"Ошибка: <code>{e}</code>")


# ==================== ВОЗВРАТ ====================
@dp.message(Command("refund"))
async def cmd_refund(msg: Message):
    user_id = msg.from_user.id
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT id, item_key, stars, charge_id, created_at FROM payments "
            "WHERE user_id=? AND refunded=0 ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        payments = await cur.fetchall()

    if not payments:
        return await msg.answer(
            "💸 <b>Нет покупок для возврата</b>\n\n"
            "• Возможно, ты ещё ничего не покупал\n"
            "• Или уже вернул\n"
            "• Если платил до обновления бота — платёж не сохранился\n\n"
            f"По вопросам: @{CONTACT_USERNAME}",
            reply_markup=bottom_menu()
        )

    kb_rows = []
    for pid, key, stars, charge_id, ts in payments:
        ago = now - ts
        if ago > REFUND_WINDOW:
            continue
        item = SHOP.get(key, {"title": key})
        left_hours = (REFUND_WINDOW - ago) // 3600
        kb_rows.append([InlineKeyboardButton(
            text=f"↩️ {item['title']} — {stars}⭐ ({left_hours}ч)",
            callback_data=f"refund:{pid}"
        )])

    if not kb_rows:
        return await msg.answer(
            "💸 <b>Нет покупок для возврата</b>\n\nВозврат в течение <b>7 дней</b>.",
            reply_markup=bottom_menu()
        )

    await msg.answer(
        "💸 <b>Возврат</b>\n\nВыбери покупку. ⭐ вернутся сразу, товар отменится.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows)
    )


@dp.callback_query(F.data.startswith("refund:"))
async def cb_refund(cb: CallbackQuery):
    try:
        pid = int(cb.data.split(":")[1])
    except Exception:
        return await cb.answer("Ошибка", show_alert=True)
    user_id = cb.from_user.id
    now = int(time.time())
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT user_id, item_key, stars, charge_id, created_at, refunded "
            "FROM payments WHERE id=?", (pid,)
        )
        row = await cur.fetchone()
    if not row:
        return await cb.answer("Платёж не найден", show_alert=True)
    owner_id, key, stars, charge_id, created_at, refunded = row
    if owner_id != user_id:
        return await cb.answer("Не твой платёж", show_alert=True)
    if refunded:
        return await cb.answer("Уже возвращён", show_alert=True)
    if now - created_at > REFUND_WINDOW:
        return await cb.answer("Прошло больше 7 дней", show_alert=True)
    if not charge_id:
        return await cb.answer("Нет данных. /paysupport", show_alert=True)

    cat = await get_cat(user_id)
    if key == "food10":
        await update_cat(user_id, coins=max(0, cat[4] - 100))
    elif key == "boost":
        await update_cat(user_id, boost_until=0)
    elif key == "vip":
        await update_cat(user_id, vip=0)

    try:
        await bot.refund_star_payment(user_id=user_id,
                                      telegram_payment_charge_id=charge_id)
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE payments SET refunded=1 WHERE id=?", (pid,))
            await db.commit()
        await cb.message.edit_text(
            f"✅ <b>Возврат оформлен</b>\n\n⭐ {stars} звёзд вернулись.\nТовар отменён."
        )
        try:
            await bot.send_message(ADMIN_ID,
                f"↩️ Возврат: <code>{user_id}</code> — {key} {stars}⭐")
        except Exception:
            pass
    except Exception as e:
        err = str(e)
        if "CHARGE_ALREADY_REFUNDED" in err:
            await cb.message.edit_text("ℹ️ Уже возвращён.")
        else:
            await cb.message.edit_text(
                f"❌ <b>Ошибка</b>\n<code>{err}</code>\n\nНапиши: @{CONTACT_USERNAME}"
            )
    await cb.answer()


# ==================== КНОПКИ ВНИЗУ ====================
@dp.message(F.text == "🍖 Покормить")
async def btn_feed(msg: Message):
    await _do_feed(msg.from_user.id, msg)


@dp.message(F.text == "🎾 Поиграть")
async def btn_play(msg: Message):
    await _do_play(msg.from_user.id, msg)


@dp.message(F.text == "🎲 Угадай")
async def btn_guess(msg: Message):
    await _start_guess(msg.from_user.id, msg)


@dp.message(F.text == "🎁 Бонус дня")
async def btn_daily(msg: Message):
    await _do_daily(msg.from_user.id, msg)


@dp.message(F.text == "🛒 Магазин")
async def btn_shop(msg: Message):
    await _show_shop(msg)


@dp.message(F.text == "🎨 Скины")
async def btn_skins(msg: Message):
    await _show_skins(msg.from_user.id, msg)


@dp.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    await _show_profile(msg)


@dp.message(F.text == "🚨 Жалоба")
async def btn_report(msg: Message):
    await _show_report(msg)


@dp.message(F.text == "❓ Помощь")
async def btn_help(msg: Message):
    await _show_help(msg)


@dp.message(F.text == "❌ Скрыть меню")
async def btn_hide(msg: Message):
    await msg.answer("✅ Меню свёрнуто.\n\nВведи /menu или /start — вернуть.",
                     reply_markup=ReplyKeyboardRemove())


# ==================== ЧИСЛА ====================
@dp.message(F.text.regexp(r"^\d+$"))
async def guess_handler(msg: Message):
    user_id = msg.from_user.id
    game = active_games.get(user_id)
    if not game:
        try:
            await msg.delete()
        except Exception:
            pass
        return
    try:
        guess = int(msg.text)
    except ValueError:
        return
    cat = await get_cat(user_id)
    if guess == game["number"]:
        win = game["bet"] * 5
        if is_boost(cat): win *= 2
        await update_cat(user_id, coins=cat[4] + win)
        await add_xp(user_id, 30)
        del active_games[user_id]
        await msg.answer(
            f"🎉 <b>Угадал!</b> Число: <b>{game['number']}</b>\n+{win} монет 💰\n\n"
            + await render_user(user_id),
            reply_markup=bottom_menu()
        )
    else:
        game["tries"] -= 1
        if game["tries"] <= 0:
            await update_cat(user_id, coins=max(0, cat[4] - game["bet"]))
            del active_games[user_id]
            await msg.answer(
                f"😿 <b>Не угадал!</b> Было: <b>{game['number']}</b>\n-{game['bet']} монет\n\n"
                + await render_user(user_id),
                reply_markup=bottom_menu()
            )
        else:
            hint = "🔽 меньше" if guess > game["number"] else "🔼 больше"
            await msg.answer(f"❌ Не то. Подсказка: <b>{hint}</b>\nОсталось: <b>{game['tries']}</b>")


# ==================== ИНЛАЙН ====================
@dp.callback_query(F.data == "refresh")
async def cb_refresh(cb: CallbackQuery):
    try:
        await cb.message.edit_text(await render_user(cb.from_user.id), reply_markup=main_kb())
    except Exception:
        pass
    await cb.answer()


@dp.callback_query(F.data == "feed")
async def cb_feed(cb: CallbackQuery):
    await _do_feed(cb.from_user.id, cb)


@dp.callback_query(F.data == "play")
async def cb_play(cb: CallbackQuery):
    await _do_play(cb.from_user.id, cb)


@dp.callback_query(F.data == "daily")
async def cb_daily(cb: CallbackQuery):
    await _do_daily(cb.from_user.id, cb)


@dp.callback_query(F.data == "guess")
async def cb_guess(cb: CallbackQuery):
    await _start_guess(cb.from_user.id, cb)


@dp.callback_query(F.data == "shop")
async def cb_shop(cb: CallbackQuery):
    await _show_shop(cb)


@dp.callback_query(F.data == "soon")
async def cb_soon(cb: CallbackQuery):
    await _show_soon(cb)


@dp.callback_query(F.data == "skins_menu")
async def cb_skins_menu(cb: CallbackQuery):
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data == "rename")
async def cb_rename(cb: CallbackQuery):
    await cb.message.answer(
        "✏️ <b>Смена имени — в разработке</b>\n\n"
        "Скоро: имя 1 раз в день бесплатно, до 20 символов.",
        reply_markup=profile_kb()
    )
    await cb.answer()


@dp.callback_query(F.data == "notif_settings")
async def cb_notif(cb: CallbackQuery):
    await cb.message.answer(
        "🔔 <b>Уведомления</b>\n\n"
        "🍖 Котик проголодался (24ч)\n"
        "🎾 Котик хочет играть (2ч)\n"
        "🎁 Бонус дня ждёт\n\n"
        "/mute — отключить\n/unmute — включить"
    )
    await cb.answer()


@dp.callback_query(F.data == "report")
async def cb_report(cb: CallbackQuery):
    await _show_report(cb)


@dp.callback_query(F.data == "mute")
async def cb_mute(cb: CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                         (cb.from_user.id,))
        await db.commit()
    try:
        await cb.message.edit_text("🔕 Напоминания отключены.\nВключить: /unmute")
    except Exception:
        pass
    await cb.answer()


# ==================== СКИНЫ (всё за монеты) ====================
@dp.callback_query(F.data.startswith("select_skin:"))
async def cb_select_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    if key not in SKINS:
        return await cb.answer("Скин не найден", show_alert=True)
    owned = await get_user_skins(cb.from_user.id)
    owned = set(owned) | {"default", "cat", "black"}
    if key not in owned:
        return await cb.answer("Сначала купи скин", show_alert=True)
    await update_cat(cb.from_user.id, current_skin=key)
    await cb.answer(f"✅ Скин выбран: {SKINS[key]['name']}")
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data.startswith("buy_skin:"))
async def cb_buy_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    s = SKINS.get(key)
    if not s:
        return await cb.answer("Недоступно", show_alert=True)
    if s["coins"] <= 0:
        # бесплатный скин — просто добавляем
        await add_user_skin(cb.from_user.id, key)
        await update_cat(cb.from_user.id, current_skin=key)
        await cb.answer(f"✅ {s['name']} выбран!")
        return await _show_skins(cb.from_user.id, cb)

    cat = await get_cat(cb.from_user.id)
    if cat[4] < s["coins"]:
        return await cb.answer(
            f"Не хватает монет. Нужно {s['coins']}💰, у тебя {cat[4]}💰",
            show_alert=True
        )
    await update_cat(cb.from_user.id, coins=cat[4] - s["coins"])
    await add_user_skin(cb.from_user.id, key)
    await update_cat(cb.from_user.id, current_skin=key)
    await cb.answer(f"✅ Куплен {s['name']}!")
    try:
        await cb.message.answer(
            f"🎉 <b>Скин куплен!</b>\n\n"
            f"{s['emoji']} <b>{s['name']}</b>\n"
            f"Списано: <b>{s['coins']} монет</b>\n\n"
            f"Он сразу применён!",
            reply_markup=bottom_menu()
        )
    except Exception:
        pass
    await _show_skins(cb.from_user.id, cb)


# ==================== ОПЛАТА ====================
@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def on_paid(msg: Message):
    payload = msg.successful_payment.invoice_payload
    user_id = msg.from_user.id
    stars = msg.successful_payment.total_amount
    charge_id = msg.successful_payment.telegram_payment_charge_id
    cat = await get_cat(user_id)

    key = payload.split(":")[1]
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT INTO payments(user_id, item_key, stars, charge_id, created_at) "
                "VALUES(?,?,?,?,?)",
                (user_id, key, stars, charge_id, int(time.time()))
            )
            await db.commit()
    except Exception:
        pass

    if key == "food10":
        await update_cat(user_id, coins=cat[4] + 100)
        text = "🍖 +100 монет!"
    elif key == "boost":
        until = max(int(time.time()), cat[8]) + 24 * 3600
        await update_cat(user_id, boost_until=until)
        text = "⚡ Ускоритель x2 на 24ч!"
    elif key == "vip":
        await update_cat(user_id, vip=1)
        text = "👑 VIP активирован!"
    else:
        text = "✅ Оплата получена!"

    await msg.answer(f"✅ <b>Оплата прошла!</b>\n{text}\n\n💸 /refund — вернуть (7 дней)",
                     reply_markup=bottom_menu())

    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID,
                f"💰 <b>Покупка!</b>\n"
                f"👤 @{msg.from_user.username} (<code>{user_id}</code>)\n"
                f"📦 {key} — {stars}⭐")
        except Exception:
            pass


# ==================== УДАЛЕНИЕ ЛИШНЕГО ====================
@dp.message(F.photo | F.video | F.video_note | F.voice | F.audio |
            F.document | F.sticker | F.animation | F.location |
            F.contact | F.poll | F.venue | F.dice)
async def delete_media(msg: Message):
    try:
        await msg.delete()
    except Exception:
        pass
    key = msg.from_user.id
    now = int(time.time())
    if now - warned_users.get(key, 0) < WARN_COOLDOWN:
        return
    warned_users[key] = now
    try:
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>\n\nМеню внизу или /help.")
    except Exception:
        pass


@dp.message(F.text & ~F.text.startswith("/") & ~F.text.regexp(r"^\d+$"))
async def delete_random_text(msg: Message):
    try:
        await msg.delete()
    except Exception:
        pass
    key = msg.from_user.id
    now = int(time.time())
    if now - warned_users.get(key, 0) < WARN_COOLDOWN:
        return
    warned_users[key] = now
    try:
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>\n\nМеню внизу или /help.")
    except Exception:
        pass


# ==================== ФОН ====================
async def vip_income_loop():
    while True:
        try:
            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE cats SET coins = coins + 10 WHERE vip=1")
                await db.commit()
        except Exception as e:
            print(f"vip_income_loop: {e}")
        await asyncio.sleep(3600)


async def reminder_loop():
    await asyncio.sleep(60)
    while True:
        try:
            now = int(time.time())
            day_ago = now - 86400
            async with aiosqlite.connect(DB) as db:
                cur = await db.execute(
                    "SELECT user_id, name, last_seen, last_remind, last_daily, "
                    "last_play_remind, satiety, coins FROM cats "
                    "WHERE last_seen < ? AND last_seen > 0",
                    (day_ago,)
                )
                rows = await cur.fetchall()
            for (user_id, name, last_seen, last_remind, last_daily,
                 last_play_remind, satiety, coins) in rows:
                if is_banned(user_id):
                    continue
                send_general = (not last_remind) or (now - last_remind >= REMIND_COOLDOWN)
                send_play = (not last_play_remind) or (now - last_play_remind >= PLAY_REMIND_COOLDOWN)
                days = (now - last_seen) // 86400
                bonus_ready = (now - last_daily) >= DAILY_COOLDOWN
                can_play = satiety >= 10 and coins >= 20
                if send_general and days >= 1:
                    parts = []
                    if days >= 7:
                        parts.append(f"🐱 <b>{name} очень скучает!</b>\nТы не заходил <b>{days} дней</b> 😿")
                    elif days >= 3:
                        parts.append(f"🐱 <b>{name} скучает</b>\nНе заходил <b>{days} дня</b>.")
                    else:
                        parts.append(f"🐱 <b>{name} проголодался!</b>")
                    if bonus_ready:
                        parts.append("\n🎁 <b>Бонус дня ждёт!</b>")
                    if can_play:
                        parts.append("🎾 Котик хочет поиграть!")
                    parts.append("\nПокорми 🍖")
                    text = "\n".join(parts)
                    buttons = []
                    if bonus_ready:
                        buttons.append([InlineKeyboardButton(text="🎁 Бонус", callback_data="daily")])
                    buttons.append([InlineKeyboardButton(text="🍖 Покормить", callback_data="feed")])
                    if can_play:
                        buttons.append([InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")])
                    buttons.append([InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")])
                    try:
                        await bot.send_message(user_id, text,
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                        async with aiosqlite.connect(DB) as db:
                            await db.execute("UPDATE cats SET last_remind=? WHERE user_id=?",
                                             (now, user_id))
                            await db.commit()
                    except Exception as e:
                        print(f"reminder {user_id}: {e}")
                        if "blocked" in str(e).lower():
                            try:
                                async with aiosqlite.connect(DB) as db:
                                    await db.execute(
                                        "UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                                        (user_id,))
                                    await db.commit()
                            except Exception:
                                pass
                elif send_play and can_play and days < 1:
                    try:
                        await bot.send_message(user_id,
                            f"🎾 <b>{name} хочет поиграть!</b>",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
                                [InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")]
                            ]))
                        async with aiosqlite.connect(DB) as db:
                            await db.execute("UPDATE cats SET last_play_remind=? WHERE user_id=?",
                                             (now, user_id))
                            await db.commit()
                    except Exception as e:
                        print(f"play reminder {user_id}: {e}")
        except Exception as e:
            print(f"reminder_loop: {e}")
        await asyncio.sleep(3600)


async def unban_loop():
    while True:
        try:
            now = int(time.time())
            to_unban = [uid for uid, until in banned_users.items() if until <= now]
            for uid in to_unban:
                del banned_users[uid]
                try:
                    async with aiosqlite.connect(DB) as db:
                        await db.execute("UPDATE cats SET banned_until=0 WHERE user_id=?", (uid,))
                        await db.commit()
                except Exception:
                    pass
                try:
                    await bot.send_message(uid, "✅ Ты разбанен!")
                except Exception:
                    pass
        except Exception as e:
            print(f"unban_loop: {e}")
        await asyncio.sleep(300)


async def setup_commands():
    commands = [
        BotCommand(command="start",      description="🐱 Запустить"),
        BotCommand(command="menu",       description="📋 Меню"),
        BotCommand(command="daily",      description="🎁 Бонус дня"),
        BotCommand(command="soon",       description="🚧 Что в разработке"),
        BotCommand(command="help",       description="❓ Помощь"),
        BotCommand(command="support",    description="🆘 Поддержка"),
        BotCommand(command="paysupport", description="💳 Оплата"),
        BotCommand(command="report",     description="🚨 Пожаловаться"),
        BotCommand(command="refund",     description="💸 Вернуть звёзды"),
        BotCommand(command="terms",      description="📜 Условия"),
        BotCommand(command="mute",       description="🔕 Отключить напоминания"),
        BotCommand(command="unmute",     description="🔔 Включить напоминания"),
        BotCommand(command="hide",       description="❌ Скрыть меню"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        print(f"setup_commands: {e}")


async def main():
    await init_db()
    await setup_commands()
    dp.message.middleware(AntiSpamMiddleware())
    dp.callback_query.middleware(AntiSpamMiddleware())
    asyncio.create_task(vip_income_loop())
    asyncio.create_task(reminder_loop())
    asyncio.create_task(unban_loop())
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
