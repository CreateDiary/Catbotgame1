import asyncio
import aiosqlite
import time
import random
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_IDS = [5965370780, 6137912809]
CONTACT_USERNAME = "Artemchic2009"

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
REMIND_COOLDOWN = 86400
SPAM_WINDOW = 10
SPAM_LIMIT = 15
BAN_DURATION = 86400
WARN_COOLDOWN = 300
NAME_COOLDOWN = 86400
NAME_MAX_LEN = 20
NAME_MIN_LEN = 2

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
warned_users = {}
spam_tracker = {}
banned_users = {}
awaiting_name = {}


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("CREATE TABLE IF NOT EXISTS cats (user_id INTEGER PRIMARY KEY, name TEXT DEFAULT 'Барсик', level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, coins INTEGER DEFAULT 0, satiety INTEGER DEFAULT 100, last_feed INTEGER DEFAULT 0, boost_until INTEGER DEFAULT 0, vip INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_seen INTEGER DEFAULT 0, last_remind INTEGER DEFAULT 0, banned_until INTEGER DEFAULT 0, current_skin TEXT DEFAULT 'default', last_name_change INTEGER DEFAULT 0, strikes INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS user_skins (user_id INTEGER, skin_key TEXT, purchased_at INTEGER, PRIMARY KEY (user_id, skin_key))")
        await db.execute("CREATE TABLE IF NOT EXISTS complaints (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user_id INTEGER, reported_user_id INTEGER, reason TEXT, created_at INTEGER, processed INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS admin_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, created_at INTEGER)")
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
            await db.execute("INSERT OR IGNORE INTO user_skins(user_id, skin_key, purchased_at) VALUES(?,?,?)", (user_id, skin_key, int(time.time())))
            await db.commit()
        except Exception:
            pass


async def set_current_skin(user_id, skin_key):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET current_skin=? WHERE user_id=?", (skin_key, user_id))
        await db.commit()


async def get_current_skin(user_id):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT current_skin FROM cats WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0]:
            return row[0]
    return "default"


async def log_admin_action(admin_id, action, target_id=None, details=""):
    try:
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT INTO admin_actions(admin_id, action, target_id, details, created_at) VALUES(?,?,?,?,?)", (admin_id, action, target_id, str(details)[:500], int(time.time())))
            await db.commit()
    except Exception:
        pass


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
        await bot.send_message(user_id, "🚫 <b>Ты забанен на 24 часа за спам.</b>")
    except Exception:
        pass
    for admin in ADMIN_IDS:
        try:
            await bot.send_message(admin, f"🚫 Автобан: <code>{user_id}</code>")
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
                    await db.execute("UPDATE cats SET last_seen=? WHERE user_id=?", (int(time.time()), user.id))
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
    return cat[7] > int(time.time())


def is_vip(cat):
    return cat[8] == 1


def bonus_available(cat):
    return int(time.time()) - cat[9] >= DAILY_COOLDOWN


def skin_emoji(skin_key):
    s = SKINS.get(skin_key)
    return s["emoji"] if s else "🐱"


def render(cat, skin_key="default"):
    name = cat[1]
    level = cat[2]
    xp = cat[3]
    coins = cat[4]
    satiety = cat[5]
    boost_until = cat[7]
    vip = cat[8]
    last_daily = cat[9]
    streak = cat[10]
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
    return f"{em} {crown} <b>{name}</b> {boost}{fire}\nУровень: <b>{level}</b>  (XP: {xp}/{need})\n💰 Монеты: <b>{coins}</b>\n🍽 Сытость: [{bar}] {satiety}%\n{bonus_line}"


async def render_user(user_id):
    cat = await get_cat(user_id)
    skin = await get_current_skin(user_id)
    return render(cat, skin)


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"), InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"), InlineKeyboardButton(text="🎁 Бонус дня", callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="shop"), InlineKeyboardButton(text="🎨 Скины", callback_data="skins_menu")],
        [InlineKeyboardButton(text="✏️ Имя", callback_data="rename"), InlineKeyboardButton(text="🚧 Скоро", callback_data="soon")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def shop_kb():
    rows = []
    for key, item in SHOP.items():
        rows.append([InlineKeyboardButton(text=f"{item['title']} — {item['coins']} 💰", callback_data=f"buy:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skins_kb(owned, current):
    rows = []
    for key, s in SKINS.items():
        if key in owned:
            mark = "✅" if key == current else "👈"
            rows.append([InlineKeyboardButton(text=f"{s['emoji']} {s['name']} {mark}", callback_data=f"select_skin:{key}")])
        else:
            rows.append([InlineKeyboardButton(text=f"{s['emoji']} {s['name']} — {s['coins']} 💰", callback_data=f"buy_skin:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="refresh")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="rename")],
        [InlineKeyboardButton(text="🎨 Скины", callback_data="skins_menu")],
        [InlineKeyboardButton(text="🚧 Что скоро", callback_data="soon")],
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
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="✏️ Имя")],
            [KeyboardButton(text="🚧 Скоро"), KeyboardButton(text="🚨 Жалоба")],
            [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


HELP_TEXT = "❓ <b>Что делает этот бот?</b>\n\n🐱 <b>Игра-тамагочи про котика.</b>\nКорми, играй, качай уровень, покупай скины за монеты, меняй имя.\n\n<b>🎮 Кнопки внизу:</b>\n🍖 Покормить — +монеты\n🎾 Поиграть — +XP и монеты\n🎲 Угадай — мини-игра\n🎁 Бонус дня — раз в 24ч\n🛒 Магазин — за монеты\n🎨 Скины — за монеты\n👤 Профиль — твой котик\n✏️ Имя — сменить имя (1 раз/день)\n🚧 Скоро — будущие фичи\n🚨 Жалоба — на юзера\n\n<b>📋 Команды:</b>\n/start, /menu, /daily, /soon, /help\n/support, /report, /terms, /mute, /unmute, /hide\n\n📷 Фото, видео, стикеры, текст удаляются.\n⚠️ Спам = <b>бан 24 часа</b>."

TERMS_TEXT = "📜 <b>Условия использования</b>\n\n1. Это игра-тамагочи.\n2. Монеты не имеют денежной ценности.\n3. Игра «как есть».\n4. Спам запрещён — <b>бан 24 часа</b>.\n5. Право менять условия."

SUPPORT_TEXT = f"🆘 <b>Поддержка</b>\n\nНаписать админу: @{CONTACT_USERNAME}\n\n⏱ Отвечаем в течение 24 часов."

SOON_TEXT = "🚧 <b>Что готовится в боте</b>\n\n🏆 <b>Топ игроков</b> — рейтинг\n🤝 <b>Рефералка</b> — зови друзей\n🎁 <b>Ежедневные задания</b>\n🎉 <b>Ивенты</b> — праздники\n⚔️ <b>Дуэли котиков</b>\n🍀 <b>Лотерея</b>\n🎰 <b>Рулетка</b>\n🎣 <b>Рыбалка</b>\n🌱 <b>Огород</b>\n🎨 <b>Больше скинов</b>\n🎩 <b>Аксессуары</b>\n🏠 <b>Домики</b>\n🌟 <b>Эффекты</b>\n👨‍👩‍👧 <b>Семьи котиков</b>\n💌 <b>Подарки</b>\n🏅 <b>Достижения</b>\n\n🐾 <i>Следи за обновлениями!</i>"

RENAME_TEXT = "✏️ <b>Смена имени котика</b>\n\nОтправь новое имя одним сообщением.\n\n📏 2-20 символов, можно эмодзи.\n⏰ 1 раз в 24 часа.\n\n❌ Отмена — /cancel"


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
    anim = await _animate(target, ["🍖 Кормим котика.", "🍖 Кормим котика..", "🍖 Кормим котика...", "😋 Котик кушает..."])
    coins_gain = random.randint(5, 15)
    if is_boost(cat): coins_gain *= 2
    if is_vip(cat): coins_gain += 5
    await update_cat(user_id, coins=cat[4] + coins_gain, satiety=min(100, cat[5] + 20), last_feed=now)
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
    anim = await _animate(target, ["🎾 Играем с котиком.", "🎾 Играем с котиком..", "🎾 Играем с котиком...", "😺 Котик веселится!"])
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
    bonus = 50 + (streak - 1) * 15
    if streak >= 7:
        bonus += 100
    if is_vip(cat):
        bonus *= 2
    await update_cat(user_id, coins=cat[4] + bonus, last_daily=now, streak=streak)
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


async def _show_shop(target):
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    cat = await get_cat(user_id)
    text = f"🛒 <b>Магазин за монеты</b>\n\n💰 У тебя: <b>{cat[4]} монет</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['coins']} 💰</b>\n  <i>{item['desc']}</i>\n"
    text += "\n🎨 Скины — отдельный раздел."
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
    current_name = SKINS.get(current, SKINS['default'])['name']
    text = f"🎨 <b>Скины для котика</b>\n\nТекущий: {skin_emoji(current)} <b>{current_name}</b>\n💰 У тебя: <b>{cat[4]} монет</b>\n\n✅ — куплен, 👈 — текущий."
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
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    text = "👤 <b>Профиль котика</b>\n\n" + await render_user(user_id)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=profile_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=profile_kb())
        except Exception:
            await target.message.answer(text, reply_markup=profile_kb())
        await target.answer()


async def _show_report(target):
    text = f"🚨 <b>Пожаловаться</b>\n\nЕсли кто-то спамит, оскорбляет:\n\n👉 @{CONTACT_USERNAME}\n\n⚠️ Ложные жалобы = <b>бан</b>."
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
    txt = "🎲 <b>Угадай число от 1 до 10!</b>\n\nСтавка: <b>20 монет</b>\nПопыток: <b>3</b>\nУгадал — <b>+100 монет</b>\n\nНапиши число в чат 👇"
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    text = "🐱 <b>Привет! Это твой котик.</b>\n\nКорми, играй, качай уровень.\nСкины — за монеты, имя — меняй!\n\n📌 Кнопки внизу — меню.\n\n" + await render_user(msg.from_user.id)
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


@dp.message(Command("hide"))
async def cmd_hide(msg: Message):
    await msg.answer("Меню свёрнуто. /menu — вернуть.", reply_markup=ReplyKeyboardRemove())


@dp.message(Command("mute"))
async def cmd_mute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?", (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔕 <b>Напоминания отключены</b>\n\nВключить: /unmute", reply_markup=bottom_menu())


@dp.message(Command("unmute"))
async def cmd_unmute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=0 WHERE user_id=?", (msg.from_user.id,))
        await db.commit()
    await msg.answer("🔔 <b>Напоминания включены</b>", reply_markup=bottom_menu())


@dp.message(Command("report"))
async def cmd_report(msg: Message):
    await _show_report(msg)


@dp.message(Command("cancel"))
async def cmd_cancel(msg: Message):
    if msg.from_user.id in awaiting_name:
        del awaiting_name[msg.from_user.id]
    await msg.answer("Отменено.", reply_markup=bottom_menu())


@dp.message(Command("admins"))
async def cmd_admins(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    text = "👑 <b>Список админов</b>\n\n"
    for i, admin_id in enumerate(ADMIN_IDS, 1):
        mark = " (ты)" if admin_id == msg.from_user.id else ""
        text += f"{i}. <code>{admin_id}</code>{mark}\n"
    text += f"\nВсего: <b>{len(ADMIN_IDS)}</b>"
    await msg.answer(text)


@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT COUNT(*) FROM cats")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?", (int(time.time()) - 86400,))
        active_day = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM cats WHERE last_seen > ?", (int(time.time()) - 604800,))
        active_week = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM cats WHERE vip=1")
        vips = (await cur.fetchone())[0]
        cur = await db.execute("SELECT SUM(coins) FROM cats")
        total_coins = (await cur.fetchone())[0] or 0
        cur = await db.execute("SELECT COUNT(*) FROM user_skins")
        skins_bought = (await cur.fetchone())[0]
    await msg.answer(f"📊 <b>Статистика</b>\n\n👥 Юзеров: <b>{total}</b>\n📅 Активных 24ч: <b>{active_day}</b>\n📆 Активных 7д: <b>{active_week}</b>\n👑 VIP: <b>{vips}</b>\n\n💰 Монет: <b>{total_coins}</b>\n🎨 Скинов куплено: <b>{skins_bought}</b>")


@dp.message(Command("ban"))
async def cmd_ban(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
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
    await log_admin_action(msg.from_user.id, "ban", target_id, f"{hours}ч")
    await msg.answer(f"🚫 <code>{target_id}</code> забанен на {hours}ч")


@dp.message(Command("unban"))
async def cmd_unban(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    parts = msg.text.split()
    if len(parts) < 2:
        return await msg.answer("Использование: <code>/unban user_id</code>")
    try:
        target_id = int(parts[1])
    except ValueError:
        return await msg.answer("Неверный формат")
    banned_users.pop(target_id, None)
    await log_admin_action(msg.from_user.id, "unban", target_id)
    await msg.answer(f"✅ <code>{target_id}</code> разбанен")


@dp.message(Command("admin_log"))
async def cmd_admin_log(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT admin_id, action, target_id, details, created_at FROM admin_actions ORDER BY created_at DESC LIMIT 15")
        rows = await cur.fetchall()
    if not rows:
        return await msg.answer("📭 Логов админов пока нет")
    text = "👑 <b>Действия админов</b>\n\n"
    for aid, action, target, details, ts in rows:
        ago = (int(time.time()) - ts) // 60
        text += f"<code>{aid}</code> | {action}"
        if target:
            text += f" → <code>{target}</code>"
        text += f" | {ago}м\n"
    await msg.answer(text)


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


@dp.message(F.text == "✏️ Имя")
async def btn_name(msg: Message):
    cat = await get_cat(msg.from_user.id)
    last_change = cat[15] if len(cat) > 15 else 0
    now = int(time.time())
    if last_change and now - last_change < NAME_COOLDOWN:
        left = NAME_COOLDOWN - (now - last_change)
        h = left // 3600
        m = (left % 3600) // 60
        return await msg.answer(f"⏰ Имя можно менять раз в 24ч. Осталось: <b>{h}ч {m}м</b>", reply_markup=bottom_menu())
    awaiting_name[msg.from_user.id] = True
    await msg.answer(RENAME_TEXT, reply_markup=ReplyKeyboardRemove())


@dp.message(F.text == "🚧 Скоро")
async def btn_soon(msg: Message):
    await _show_soon(msg)


@dp.message(F.text == "🚨 Жалоба")
async def btn_report(msg: Message):
    await _show_report(msg)


@dp.message(F.text == "❓ Помощь")
async def btn_help(msg: Message):
    await _show_help(msg)


@dp.message(F.text == "❌ Скрыть меню")
async def btn_hide(msg: Message):
    await msg.answer("✅ Меню свёрнуто.", reply_markup=ReplyKeyboardRemove())


@dp.message(F.text & ~F.text.startswith("/") & ~F.text.regexp(r"^\d+$"))
async def handle_name_or_delete(msg: Message):
    user_id = msg.from_user.id
    if user_id in awaiting_name:
        new_name = msg.text.strip()
        if len(new_name) < NAME_MIN_LEN:
            return await msg.answer(f"❌ Имя слишком короткое. Минимум {NAME_MIN_LEN} символа.")
        if len(new_name) > NAME_MAX_LEN:
            return await msg.answer(f"❌ Имя слишком длинное. Максимум {NAME_MAX_LEN} символов.")
        await update_cat(user_id, name=new_name, last_name_change=int(time.time()))
        del awaiting_name[user_id]
        return await msg.answer(f"✅ Имя изменено на <b>{new_name}</b>!", reply_markup=bottom_menu())
    try:
        await msg.delete()
    except Exception:
        pass
    now = int(time.time())
    if now - warned_users.get(user_id, 0) < WARN_COOLDOWN:
        return
    warned_users[user_id] = now
    try:
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>")
    except Exception:
        pass


@dp.message(F.text.regexp(r"^\d+$"))
async def guess_handler(msg: Message):
    user_id = msg.from_user.id
    if user_id in awaiting_name:
        return await handle_name_or_delete(msg)
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
        await msg.answer(f"🎉 <b>Угадал!</b> Число: <b>{game['number']}</b>\n+{win} монет 💰\n\n" + await render_user(user_id), reply_markup=bottom_menu())
    else:
        game["tries"] -= 1
        if game["tries"] <= 0:
            await update_cat(user_id, coins=max(0, cat[4] - game["bet"]))
            del active_games[user_id]
            await msg.answer(f"😿 <b>Не угадал!</b> Было: <b>{game['number']}</b>\n-{game['bet']} монет\n\n" + await render_user(user_id), reply_markup=bottom_menu())
        else:
            hint = "🔽 меньше" if guess > game["number"] else "🔼 больше"
            await msg.answer(f"❌ Не то. Подсказка: <b>{hint}</b>\nОсталось: <b>{game['tries']}</b>")


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
    cat = await get_cat(cb.from_user.id)
    last_change = cat[15] if len(cat) > 15 else 0
    now = int(time.time())
    if last_change and now - last_change < NAME_COOLDOWN:
        left = NAME_COOLDOWN - (now - last_change)
        h = left // 3600
        m = (left % 3600) // 60
        return await cb.answer(f"Через {h}ч {m}м", show_alert=True)
    awaiting_name[cb.from_user.id] = True
    await cb.message.answer(RENAME_TEXT, reply_markup=ReplyKeyboardRemove())
    await cb.answer()


@dp.callback_query(F.data == "notif_settings")
async def cb_notif(cb: CallbackQuery):
    await cb.message.answer("🔔 <b>Уведомления</b>\n\n/mute — отключить\n/unmute — включить")
    await cb.answer()


@dp.callback_query(F.data == "report")
async def cb_report(cb: CallbackQuery):
    await _show_report(cb)


@dp.callback_query(F.data == "mute")
async def cb_mute(cb: CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=9999999999 WHERE user_id=?", (cb.from_user.id,))
        await db.commit()
    try:
        await cb.message.edit_text("🔕 Напоминания отключены.")
    except Exception:
        pass
    await cb.answer()


@dp.callback_query(F.data.startswith("select_skin:"))
async def cb_select_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    if key not in SKINS:
        return await cb.answer("Скин не найден", show_alert=True)
    owned = await get_user_skins(cb.from_user.id)
    owned = set(owned) | {"default", "cat", "black"}
    if key not in owned:
        return await cb.answer("Сначала купи скин", show_alert=True)
    await set_current_skin(cb.from_user.id, key)
    await cb.answer(f"✅ Применён: {SKINS[key]['name']}")
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data.startswith("buy_skin:"))
async def cb_buy_skin(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    s = SKINS.get(key)
    if not s:
        return await cb.answer("Недоступно", show_alert=True)
    if s["coins"] <= 0:
        await add_user_skin(cb.from_user.id, key)
        await set_current_skin(cb.from_user.id, key)
        await cb.answer(f"✅ {s['name']} выбран!")
        return await _show_skins(cb.from_user.id, cb)
    cat = await get_cat(cb.from_user.id)
    if cat[4] < s["coins"]:
        return await cb.answer(f"Нужно {s['coins']}💰, у тебя {cat[4]}💰", show_alert=True)
    await update_cat(cb.from_user.id, coins=cat[4] - s["coins"])
    await add_user_skin(cb.from_user.id, key)
    await set_current_skin(cb.from_user.id, key)
    await cb.answer(f"✅ Куплен {s['name']}!")
    try:
        await cb.message.answer(f"🎉 <b>Скин куплен!</b>\n\n{s['emoji']} <b>{s['name']}</b>\nСписано: <b>{s['coins']} монет</b>\n\nОн сразу применён!", reply_markup=bottom_menu())
    except Exception:
        pass
    await _show_skins(cb.from_user.id, cb)


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    item = SHOP.get(key)
    if not item:
        return await cb.answer("Товар не найден", show_alert=True)
    user_id = cb.from_user.id
    cat = await get_cat(user_id)
    if cat[4] < item["coins"]:
        return await cb.answer(f"Нужно {item['coins']}💰, у тебя {cat[4]}💰", show_alert=True)
    if key == "food10":
        await update_cat(user_id, coins=cat[4] - item["coins"] + 100)
        text = "🍖 +100 монет!"
    elif key == "boost":
        until = max(int(time.time()), cat[7]) + 24 * 3600
        await update_cat(user_id, coins=cat[4] - item["coins"], boost_until=until)
        text = "⚡ Ускоритель x2 на 24ч!"
    elif key == "vip":
        await update_cat(user_id, coins=cat[4] - item["coins"], vip=1)
        text = "👑 VIP активирован!"
    else:
        await update_cat(user_id, coins=cat[4] - item["coins"])
        text = "✅ Куплено!"
    await cb.message.answer(f"✅ <b>Куплено!</b>\n{text}", reply_markup=bottom_menu())
    await cb.answer()


@dp.message(F.photo | F.video | F.video_note | F.voice | F.audio | F.document | F.sticker | F.animation | F.location | F.contact | F.poll | F.venue | F.dice)
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
        await msg.answer("🐱 <b>Я понимаю только команды и кнопки.</b>")
    except Exception:
        pass


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
                cur = await db.execute("SELECT user_id, name, last_seen, last_remind, last_daily FROM cats WHERE last_seen < ? AND last_seen > 0", (day_ago,))
                rows = await cur.fetchall()
            for (user_id, name, last_seen, last_remind, last_daily) in rows:
                if is_banned(user_id):
                    continue
                if last_remind and now - last_remind < REMIND_COOLDOWN:
                    continue
                days = (now - last_seen) // 86400
                bonus_ready = (now - last_daily) >= DAILY_COOLDOWN
                text = f"🐱 <b>{name} проголодался!</b>"
                if days >= 7:
                    text = f"🐱 <b>{name} очень скучает!</b>\nНе заходил <b>{days} дней</b> 😿"
                elif days >= 3:
                    text = f"🐱 <b>{name} скучает</b>"
                if bonus_ready:
                    text += "\n\n🎁 <b>Бонус дня ждёт!</b>"
                buttons = []
                if bonus_ready:
                    buttons.append([InlineKeyboardButton(text="🎁 Бонус", callback_data="daily")])
                buttons.append([InlineKeyboardButton(text="🍖 Покормить", callback_data="feed")])
                buttons.append([InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")])
                try:
                    await bot.send_message(user_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                    async with aiosqlite.connect(DB) as db:
                        await db.execute("UPDATE cats SET last_remind=? WHERE user_id=?", (now, user_id))
                        await db.commit()
                except Exception:
                    pass
        except Exception as e:
            print(f"reminder_loop: {e}")
        await asyncio.sleep(3600)


async def setup_commands():
    commands = [
        BotCommand(command="start", description="🐱 Запустить"),
        BotCommand(command="menu", description="📋 Меню"),
        BotCommand(command="daily", description="🎁 Бонус дня"),
        BotCommand(command="soon", description="🚧 Что скоро"),
        BotCommand(command="help", description="❓ Помощь"),
        BotCommand(command="support", description="🆘 Поддержка"),
        BotCommand(command="report", description="🚨 Пожаловаться"),
        BotCommand(command="terms", description="📜 Условия"),
        BotCommand(command="mute", description="🔕 Отключить напоминания"),
        BotCommand(command="unmute", description="🔔 Включить напоминания"),
        BotCommand(command="cancel", description="❌ Отменить"),
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
    print("Бот запущен...")
    await dp.start_polling(bot)

asyncio.run(main())
