import asyncio
import aiosqlite
import time
import random
import hashlib
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.client.default import DefaultBotProperties

# ==== НАСТРОЙКИ ====
BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_IDS = [5965370780, 6137912809]
CONTACT_USERNAME = "Artemchic2009"
CONTACT_USERNAME_2 = "Andrkaop"
BOT_NAME = "Cat Clicker"
# ===================

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
COMPLAINT_COOLDOWN = 3600
REFUND_WINDOW = 1814400
BROADCAST_COOLDOWN = 3600
COMP_AMOUNT = 10000
CHECK_NAME_INTERVAL = 300  # проверка названия бота каждые 5 мин

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
awaiting_complaint = {}
broadcast_times = {}
last_known_name = {"value": BOT_NAME}
security_alerts = []


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("CREATE TABLE IF NOT EXISTS cats (user_id INTEGER PRIMARY KEY, name TEXT DEFAULT 'Барсик', level INTEGER DEFAULT 1, xp INTEGER DEFAULT 0, coins INTEGER DEFAULT 0, satiety INTEGER DEFAULT 100, last_feed INTEGER DEFAULT 0, boost_until INTEGER DEFAULT 0, vip INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_seen INTEGER DEFAULT 0, last_remind INTEGER DEFAULT 0, banned_until INTEGER DEFAULT 0, current_skin TEXT DEFAULT 'default', last_name_change INTEGER DEFAULT 0, strikes INTEGER DEFAULT 0, last_complaint INTEGER DEFAULT 0, compensation_given INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS user_skins (user_id INTEGER, skin_key TEXT, purchased_at INTEGER, PRIMARY KEY (user_id, skin_key))")
        await db.execute("CREATE TABLE IF NOT EXISTS admin_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, created_at INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_key TEXT, stars INTEGER, charge_id TEXT, created_at INTEGER, refunded INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS complaints (id INTEGER PRIMARY KEY AUTOINCREMENT, from_user_id INTEGER, reported_user TEXT, reason TEXT, created_at INTEGER, processed INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, details TEXT, ip_hash TEXT, created_at INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS security (id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT, severity TEXT, details TEXT, created_at INTEGER)")
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
        # Уведомляем админов
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
        await log_event(admin_id, f"admin_{action}", details)
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
            # Проверка бана
            if is_banned(user.id):
                if isinstance(event, Message):
                    try:
                        await event.answer("🚫 Ты забанен.", reply_markup=ReplyKeyboardRemove())
                    except Exception:
                        pass
                return
            
            # Проверка спама
            if isinstance(event, Message):
                if track_spam(user.id):
                    await auto_ban(user.id, "спам")
                    return
                
                # Логируем сообщения
                text = event.text or ""
                await log_event(user.id, "msg", text[:100])
            
            # Проверка админских команд
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
            
            # last_seen
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
        [InlineKeyboardButton(text="🎁 Компенсация", callback_data="compensation")],
        [InlineKeyboardButton(text="💸 Вернуть звёзды", callback_data="refund_menu")],
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
        [InlineKeyboardButton(text="🎁 Компенсация", callback_data="compensation")],
        [InlineKeyboardButton(text="🚧 Что скоро", callback_data="soon")],
        [InlineKeyboardButton(text="🚨 Пожаловаться", callback_data="complaint")],
        [InlineKeyboardButton(text="💸 Вернуть звёзды", callback_data="refund_menu")],
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


HELP_TEXT = "❓ <b>Что делает этот бот?</b>\n\n🐱 <b>Cat Clicker — игра-тамагочи.</b>\nКорми, играй, качай уровень, покупай скины.\n\n<b>🎮 Кнопки внизу:</b>\n🍖 Покормить • 🎾 Поиграть • 🎲 Угадай\n🎁 Бонус дня • 🛒 Магазин • 🎨 Скины\n👤 Профиль • ✏️ Имя • 🎁 Компенсация\n🚨 Жалоба • ❓ Помощь\n\n<b>📋 Команды:</b>\n/start /menu /daily /soon /help\n/compensation /complaint /refund\n/terms /mute /unmute /hide"

TERMS_TEXT = "📜 <b>Условия</b>\n\n1. Игра-тамагочи.\n2. Монеты — без денежной ценности.\n3. Возврат Stars — /refund, 7 дней.\n4. Спам запрещён — бан.\n5. Право менять условия."

SUPPORT_TEXT = f"🆘 <b>Поддержка</b>\n\n@{CONTACT_USERNAME}\n@{CONTACT_USERNAME_2}\n\n⏱ Отвечаем 24 часа."

SOON_TEXT = "🚧 <b>Скоро</b>\n\n🏆 Топ игроков\n🤝 Рефералка\n⚔️ Дуэли котиков\n🎉 Ивенты\n🎨 Больше скинов\n\n🐾 Следи за обновлениями!"

RENAME_TEXT = "✏️ <b>Смена имени</b>\n\nОтправь новое имя.\n\n2-20 символов. 1 раз в 24 часа.\n\n❌ Отмена — /cancel"
COMPLAINT_STEP1 = "🚨 <b>Жалоба 1/2</b>\n\nНа кого жалуешься? Напиши @username или ID.\n\n❌ /cancel"
COMPLAINT_STEP2 = "🚨 <b>Жалоба 2/2</b>\n\nОпиши проблему.\n\n❌ /cancel"


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
    anim = await _animate(target, ["🍖 Кормим котика.", "🍖 Кормим котика..", "🍖 Кормим котика...", "😋 Котик кушает..."])
    coins_gain = random.randint(5, 15)
    if is_boost(cat): coins_gain *= 2
    if is_vip(cat): coins_gain += 5
    await update_cat(user_id, coins=cat[4] + coins_gain, satiety=min(100, cat[5] + 20), last_feed=now)
    leveled, level = await add_xp(user_id, 10)
    await log_event(user_id, "feed", f"+{coins_gain}")
    txt = f"🍖 +{coins_gain} монет!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
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
    await log_event(user_id, "play", f"+{coins_gain}")
    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
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
    if streak >= 7: bonus += 100
    if is_vip(cat): bonus *= 2
    await update_cat(user_id, coins=cat[4] + bonus, last_daily=now, streak=streak)
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
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT compensation_given FROM cats WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row and row[0] == 1:
            await bot.send_message(chat_id, "✅ <b>Ты уже получил компенсацию!</b>\n\nСпасибо, что с нами 🐾", reply_markup=bottom_menu())
            return
        await db.execute("UPDATE cats SET coins = coins + ?, vip = 1, compensation_given = 1 WHERE user_id=?", (COMP_AMOUNT, user_id))
        await db.commit()
    await log_event(user_id, "compensation", f"+{COMP_AMOUNT} +VIP")
    await bot.send_message(chat_id,
        f"🎁 <b>Компенсация получена!</b>\n\n💰 +<b>{COMP_AMOUNT} монет</b>\n👑 <b>VIP-статус</b>!\n\nСпасибо, что с нами! 🐾",
        reply_markup=bottom_menu())


async def _show_shop(target):
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    cat = await get_cat(user_id)
    text = f"🛒 <b>Магазин за монеты</b>\n\n💰 У тебя: <b>{cat[4]} монет</b>\n\n"
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
    owned = await get_user_skins(user_id)
    owned = list(set(owned) | {"default", "cat", "black"})
    current = await get_current_skin(user_id)
    cat = await get_cat(user_id)
    current_name = SKINS.get(current, SKINS['default'])['name']
    text = f"🎨 <b>Скины</b>\n\nТекущий: {skin_emoji(current)} <b>{current_name}</b>\n💰 У тебя: <b>{cat[4]} монет</b>\n\n✅ куплен, 👈 текущий."
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
    if cat[4] < 20:
        txt = "🎲 Нужно 20 монет чтобы играть"
        if isinstance(target, Message):
            return await target.answer(txt)
        return await target.answer(txt, show_alert=True)
    number = random.randint(1, 10)
    active_games[user_id] = {"number": number, "tries": 3, "bet": 20}
    txt = "🎲 <b>Угадай число 1-10!</b>\n\nСтавка: <b>20 монет</b>\nПопыток: <b>3</b>\nУгадал — <b>+100 монет</b>\n\nНапиши число 👇"
    if isinstance(target, Message):
        await target.answer(txt)
    else:
        await target.message.answer(txt)
        await target.answer()


async def _start_complaint(user_id, chat_id):
    cat = await get_cat(user_id)
    last = cat[17] if len(cat) > 17 else 0
    now = int(time.time())
    if last and now - last < COMPLAINT_COOLDOWN:
        left = COMPLAINT_COOLDOWN - (
