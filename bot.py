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

BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_ID = 5965370780
CONTACT_USERNAME = "Artemchic2009"

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

SHOP = {
    "food10": {"title": "🍖 Корм x10", "stars": 50, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "stars": 250, "desc": "Скин + пассивный доход"},
}

SKINS = {
    "default": {"emoji": "🐱", "name": "Обычный кот", "coins": 0},
    "cat":     {"emoji": "🐈", "name": "Кошка", "coins": 0},
    "black":   {"emoji": "🐈‍⬛", "name": "Чёрный кот", "coins": 0},
    "fox":     {"emoji": "🦊", "name": "Рыжий", "coins": 100},
    "tiger":   {"emoji": "🐯", "name": "Тигр", "coins": 250},
    "lion":    {"emoji": "🦁", "name": "Лев", "coins": 400},
    "leopard": {"emoji": "🐆", "name": "Пантера", "coins": 600},
    "bear":    {"emoji": "🐻", "name": "Медведь-кот", "coins": 800},
    "panda":   {"emoji": "🐼", "name": "Панда", "coins": 1000},
    "wolf":    {"emoji": "🐺", "name": "Волк", "coins": 1300},
    "unicorn": {"emoji": "🦄", "name": "Единорог", "coins": 1800},
    "dragon":  {"emoji": "🐉", "name": "Дракон", "coins": 2500},
    "king":    {"emoji": "👑", "name": "Королевский", "coins": 3000},
    "robot":   {"emoji": "🤖", "name": "Кот-робот", "coins": 3500},
    "cosmo":   {"emoji": "🚀", "name": "Космо-кот", "coins": 4000},
    "ghost":   {"emoji": "👻", "name": "Кот-призрак", "coins": 4500},
    "fire":    {"emoji": "🔥", "name": "Огненный", "coins": 5000},
}

active_games = {}
warned_users = {}
spam_tracker = {}
banned_users = {}


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
        ]:
            try:
                await db.execute(f"ALTER TABLE cats ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass
        try:
            await db.execute("ALTER TABLE cats ADD COLUMN current_skin TEXT DEFAULT 'default'")
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
            await db.execute("UPDATE cats SET banned_until=? WHERE user_id=?", (until, user_id))
            await db.commit()
    except Exception:
        pass
    try:
        await bot.send_message(user_id, f"🚫 <b>Ты забанен на {BAN_DURATION // 3600} часов за спам.</b>")
    except Exception:
        pass
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, f"🚫 Автобан: <code>{user_id}</code>")
        except Exception:
            pass


class AntiSpamMiddleware(BaseMiddleware):
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


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня", callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"),
         InlineKeyboardButton(text="🎨 Скины", callback_data="skins_menu")],
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
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notif_settings")],
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="report")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def bottom_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍖 Покормить"), KeyboardButton(text="🎾 Поиграть")],
            [KeyboardButton(text="🎲 Угадай"), KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎨 Скины")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🚨 Жалоба")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Игра-тамагочи про котика.</b>\n"
    "Корми, играй, качай уровень, покупай скины.\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (30 сек)\n"
    "🎾 Поиграть — +XP и монеты\n"
    "🎲 Угадай — мини-игра\n"
    "🎁 Бонус дня — раз в 24ч\n"
    "🛒 Магазин — за ⭐ Stars\n"
    "🎨 Скины — за монеты\n"
    "👤 Профиль — твой котик\n"
    "🚨 Жалоба — на юзера\n\n"
    "<b>📋 Команды:</b>\n"
    "/start, /menu, /daily, /soon, /help\n"
    "/support, /paysupport, /refund, /terms\n"
    "/report, /mute, /unmute, /hide\n\n"
    "📷 <b>Фото, видео, стикеры, текст удаляются.</b>\n"
    "⚠️ Спам = <b>бан на 24 часа</b>."
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра-тамагочи. Все покупки — цифровые товары.\n"
    "2. Монеты не имеют денежной ценности.\n"
    "3. Возврат Stars — /refund, 7 дней.\n"
    "4. Игра предоставляется «как есть».\n"
    "5. Спам запрещён — <b>бан 24 часа</b>.\n"
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
    "• Вернуть Stars — /refund (7 дней)\n"
    "• Двойное списание — вернём лишнее\n\n"
    f"📧 Связь: @{CONTACT_USERNAME}\n\n"
    "⚠️ Поддержка Telegram не помогает с покупками внутри ботов."
)

SOON_TEXT = (
    "🚧 <b>В разработке</b>\n\n"
    "✏️ <b>Смена имени</b> котика\n"
    "🏆 <b>Топ игроков</b>\n"
    "🤝 <b>Рефералка</b> — зови друзей\n"
    "⚔️ <b>Дуэли котиков</b>\n"
    "📅 <b>Ежедневные задания</b>\n"
    "🎉 <b>Ивенты</b> — праздничные бонусы\n\n"
    "🐾 <i>Следи за обновлениями!</i>"
)


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
    text += "\n🎨 Скины — за монеты: кнопка «🎨 Скины»\n"
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
        f"Текущий: {skin_emoji(current)} <b>{SKINS.get(current, SKINS['default'])['name']}</b>\n"
        f"💰 У тебя: <b>{cat[4]} монет</b>\n\n"
        "Купленный скин показывается везде в боте."
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
        "Если кто-то спамит, оскорбляет, рекламит:\n\n"
        f"👉 @{CONTACT_USERNAME}\n\n"
        "Укажи:\n"
        "• Кто (юзернейм или ID)\n"
        "• Что сделал\n"
        "• Скрин\n\n"
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


@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    text = (
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "Скины — за монеты!\n\n"
        "📌 Кнопки внизу — меню. /help — справка.\n\n"
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
    await msg.answer("Меню свёрнуто. /menu — вернуть.", reply_markup=ReplyKeyboardRemove())


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
    await msg.answer("🔔 <b>Напоминания включены</b>", reply_markup=bottom_menu())


@dp.message(Command("report"))
async def cmd_report(msg: Message):
    await _show_report(msg)


@dp.message(Command("ban"))
async def cmd_ban(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
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
            await
