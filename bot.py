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
SUPPORT_USERNAME = "artemizmailov"
# ===================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
REMIND_COOLDOWN = 86400
PLAY_REMIND_COOLDOWN = 7200   # напоминание «поиграть» — раз в 2 часа
REFUND_WINDOW = 604800        # возврат — 7 дней

SHOP = {
    "food10": {"title": "🍖 Корм x10", "stars": 50, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "stars": 250, "desc": "Скин + пассивный доход"},
}

active_games = {}


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
        for col, default in [
            ("last_seen", "0"),
            ("last_remind", "0"),
            ("last_play_remind", "0"),
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
    return int(time.time()) - cat[9 + 1] >= DAILY_COOLDOWN


def render(cat):
    _, name, level, xp, coins, satiety, _, boost_until, vip, last_daily, streak = cat[:11]
    boost = "⚡" if boost_until > int(time.time()) else ""
    crown = "👑" if vip else ""
    bar_filled = min(10, satiety // 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    need = xp_for_next(level)
    fire = f" 🔥x{streak}" if streak > 1 else ""
    if bonus_available(cat):
        bonus_line = "🎁 Бонус дня: <b>доступен!</b>"
    else:
        left = DAILY_COOLDOWN - (int(time.time()) - last_daily)
        h = left // 3600
        m = (left % 3600) // 60
        bonus_line = f"🎁 Бонус дня: через {h}ч {m}м"
    return (
        f"{crown} <b>{name}</b> {boost}{fire}\n"
        f"Уровень: <b>{level}</b>  (XP: {xp}/{need})\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"🍽 Сытость: [{bar}] {satiety}%\n"
        f"{bonus_line}"
    )


# ==================== КЛАВИАТУРЫ ====================
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть",  callback_data="play")],
        [InlineKeyboardButton(text="🎲 Угадай число", callback_data="guess"),
         InlineKeyboardButton(text="🎁 Бонус дня",   callback_data="daily")],
        [InlineKeyboardButton(text="🛒 Магазин",  callback_data="shop"),
         InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
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


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="rename")],
        [InlineKeyboardButton(text="🎨 Скины", callback_data="skins")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="notif_settings")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh")],
    ])


def bottom_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🍖 Покормить"), KeyboardButton(text="🎾 Поиграть")],
            [KeyboardButton(text="🎲 Угадай"),    KeyboardButton(text="🎁 Бонус дня")],
            [KeyboardButton(text="🛒 Магазин"),   KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="❓ Помощь"),    KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


# ==================== ТЕКСТЫ ====================
HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Это игра-тамагочи про котика.</b>\n"
    "Заводишь питомца, кормишь, играешь, качаешь уровень и зарабатываешь монеты.\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (раз в 30 сек)\n"
    "🎾 Поиграть — +XP и монеты\n"
    "🎲 Угадай — мини-игра\n"
    "🎁 Бонус дня — награда раз в 24 часа\n"
    "🛒 Магазин — покупки за ⭐ Stars\n"
    "👤 Профиль — твой котик\n\n"
    "<b>📋 Команды:</b>\n"
    "/start — начать\n"
    "/menu — меню\n"
    "/daily — бонус дня\n"
    "/help — справка\n"
    "/support — поддержка\n"
    "/terms — условия\n"
    "/paysupport — оплата\n"
    "/refund — вернуть звёзды\n"
    "/mute — отключить напоминания\n"
    "/unmute — включить напоминания\n"
    "/hide — скрыть меню\n\n"
    "👑 <b>VIP</b> — +10 монет каждый час"
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра-тамагочи. Все покупки — цифровые товары.\n"
    "2. Монеты и бонусы внутри игры не имеют денежной ценности.\n"
    "3. Возврат средств за Stars возможен через /refund\n"
    "   в течение 7 дней после покупки.\n"
    "4. Игра предоставляется «как есть».\n"
    "5. Мы оставляем право менять условия.\n\n"
    "Используя бота, вы соглашаетесь с этими условиями."
)

SUPPORT_TEXT = (
    "🆘 <b>Поддержка</b>\n\n"
    f"Написать админу: @{SUPPORT_USERNAME}\n\n"
    "По вопросам оплаты — /paysupport\n"
    "⏱ Отвечаем в течение 24 часов."
)

PAYSUPPORT_TEXT = (
    "💳 <b>Поддержка по оплате</b>\n\n"
    "Если проблема с оплатой:\n"
    "• Списание прошло, но товар не пришёл — напиши нам\n"
    "• Хочешь вернуть Stars — команда /refund (в течение 7 дней)\n"
    "• Двойное списание — вернём лишнее\n\n"
    f"📧 Связь: @{SUPPORT_USERNAME}\n\n"
    "⚠️ <b>Важно:</b> поддержка Telegram не помогает с покупками внутри ботов."
)

SOON_TEXT = (
    "🚧 <b>В разработке</b>\n\n"
    "Эта функция скоро появится. Мы уже работаем над ней!\n\n"
    "<b>Что готовится в ближайших обновлениях:</b>\n\n"
    "✏️ <b>Смена имени</b> котика — бесплатно\n"
    "🎨 <b>Скины</b> — разные коты за монеты и ⭐\n"
    "🏆 <b>Топ игроков</b> — соревнование по уровню\n"
    "🤝 <b>Рефералка</b> — зови друзей, получай бонусы\n"
    "⚔️ <b>Дуэли котиков</b> — бой с другими игроками\n"
    "💎 <b>Больше скинов</b> и редких предметов\n"
    "📅 <b>Ежедневные задания</b> — заходи и получай награды\n"
    "🎉 <b>Ивенты</b> — праздничные бонусы и скины\n\n"
    "🐾 <i>Следи за обновлениями!</i>"
)


# ==================== MIDDLEWARE ====================
class SeenMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            try:
                async with aiosqlite.connect(DB) as db:
                    await db.execute(
                        "UPDATE cats SET last_seen=? WHERE user_id=?",
                        (int(time.time()), user.id)
                    )
                    await db.commit()
            except Exception:
                pass
        return await handler(event, data)


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
    cat = await get_cat(user_id)
    full = render(cat) + f"\n\n{txt}"

    # Умные подсказки
    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен! Жми «🎁 Бонус дня»</b>")
    if cat[5] >= 10:
        hints.append("🎾 Сытый котик хочет поиграть — нажми «🎾 Поиграть»")
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
    cat = await get_cat(user_id)
    full = render(cat) + f"\n\n{txt}"

    hints = []
    if bonus_available(cat):
        hints.append("🎁 <b>Бонус дня доступен! Жми «🎁 Бонус дня»</b>")
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
        f"💰 Ты получил: <b>+{bonus} монет</b>\n"
        f"🔥 Стрик: <b>{streak}</b> " + ("день" if streak == 1 else "дней")
    )
    if streak >= 7:
        txt += "\n🎉 <b>Неделя подряд! +100 монет сверху!</b>"
    elif streak >= 3:
        txt += "\n⚡ Отличная серия!"
    if is_vip(cat):
        txt += "\n👑 VIP-бонус: x2"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"

    txt += (
        "\n\n📢 <b>Это первая версия бонуса.</b>\n"
        "Скоро будет больше наград, редкие скины и особые предметы!\n\n"
        "💡 Заходи каждый день — стрик растёт, бонус увеличивается."
    )

    cat = await get_cat(user_id)
    full = render(cat) + "\n\n" + txt

    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        await target.message.answer(full, reply_markup=bottom_menu())
        await target.answer()


async def _show_shop(target):
    text = "🛒 <b>Магазин за Telegram Stars</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['stars']} ⭐</b>\n  <i>{item['desc']}</i>\n"
    text += "\n💸 Вернуть покупку: /refund (в течение 7 дней)"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=shop_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=shop_kb())
        except Exception:
            await target.message.answer(text, reply_markup=shop_kb())
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


async def _show_profile(target):
    user_id = target.from_user.id if isinstance(target, (Message, CallbackQuery)) else 0
    cat = await get_cat(user_id)
    text = (
        "👤 <b>Профиль котика</b>\n\n"
        + render(cat)
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
        "За <b>Telegram Stars</b> покупай бонусы в магазине.\n\n"
        "📌 Кнопки внизу — главное меню.\n"
        "📌 /help — справка, /menu — меню.\n\n"
        + render(cat)
    )
    if bonus_available(cat):
        text += "\n\n🎁 <b>Бонус дня доступен! Жми «🎁 Бонус дня» внизу.</b>"
    await msg.answer(text, reply_markup=bottom_menu())


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(render(cat), reply_markup=bottom_menu())


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
    await msg.answer(SUPPORT_TEXT, reply_markup=bottom_menu())


@dp.message(Command("paysupport"))
async def cmd_paysupport(msg: Message):
    await msg.answer(PAYSUPPORT_TEXT, reply_markup=bottom_menu())


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


# ==================== ВОЗВРАТ ЗВЁЗД ====================
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
            "💸 <b>У тебя нет покупок для возврата</b>\n\n"
            "• Возможно, ты ещё ничего не покупал\n"
            "• Или уже вернул\n"
            "• Если платил до обновления бота — платёж не сохранился\n\n"
            "По вопросам: /paysupport",
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
            text=f"↩️ Вернуть {item['title']} — {stars}⭐ (осталось {left_hours}ч)",
            callback_data=f"refund:{pid}"
        )])

    if not kb_rows:
        return await msg.answer(
            "💸 <b>Нет покупок для возврата</b>\n\n"
            "Возврат возможен в течение <b>7 дней</b> после покупки.",
            reply_markup=bottom_menu()
        )

    await msg.answer(
        "💸 <b>Возврат покупки</b>\n\n"
        "Выбери покупку для возврата.\n"
        "⭐ Звёзды вернутся сразу.\n"
        "⚠️ Товар отменится (монеты/усилитель/VIP сгорят).\n\n"
        "Возврат доступен в течение <b>7 дней</b> после покупки.",
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
            "FROM payments WHERE id=?",
            (pid,)
        )
        row = await cur.fetchone()

    if not row:
        return await cb.answer("Платёж не найден", show_alert=True)

    owner_id, key, stars, charge_id, created_at, refunded = row

    if owner_id != user_id:
        return await cb.answer("Это не твой платёж", show_alert=True)
    if refunded:
        return await cb.answer("Этот платёж уже возвращён", show_alert=True)
    if now - created_at > REFUND_WINDOW:
        return await cb.answer("Прошло больше 7 дней", show_alert=True)
    if not charge_id:
        return await cb.answer("Нет данных о платеже. Напиши /paysupport", show_alert=True)

    cat = await get_cat(user_id)
    if key == "food10":
        await update_cat(user_id, coins=max(0, cat[4] - 100))
    elif key == "boost":
        await update_cat(user_id, boost_until=0)
    elif key == "vip":
        await update_cat(user_id, vip=0)

    try:
        await bot.refund_star_payment(
            user_id=user_id,
            telegram_payment_charge_id=charge_id
        )
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE payments SET refunded=1 WHERE id=?", (pid,))
            await db.commit()

        await cb.message.edit_text(
            f"✅ <b>Возврат оформлен</b>\n\n"
            f"⭐ <b>{stars} звёзд</b> вернулись на твой баланс.\n"
            f"Товар отменён.\n\n"
            f"Спасибо, что играл! Возвращайся 😊"
        )
        try:
            await bot.send_message(
                ADMIN_ID,
                f"↩️ <b>Возврат!</b>\n👤 <code>{user_id}</code>\n📦 {key} — {stars} ⭐"
            )
        except Exception:
            pass
    except Exception as e:
        err = str(e)
        if "CHARGE_ALREADY_REFUNDED" in err:
            await cb.message.edit_text("ℹ️ Этот платёж уже был возвращён ранее.")
        elif "CHARGE_ID_INVALID" in err or "CHARGE_NOT_FOUND" in err:
            await cb.message.edit_text(
                "❌ <b>Telegram не смог найти этот платёж</b>\n\n"
                "Скорее всего платёж очень старый, или был оформлен до обновления бота.\n\n"
                f"Напиши админу: @{SUPPORT_USERNAME}"
            )
        else:
            await cb.message.edit_text(
                f"❌ <b>Ошибка возврата</b>\n\n<code>{err}</code>\n\n"
                f"Напиши админу: @{SUPPORT_USERNAME}"
            )
    await cb.answer()


# ==================== STATS ====================
@dp.message(Command("stats"))
async def cmd_stats(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return
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

        await msg.answer(
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего юзеров: <b>{total}</b>\n"
            f"📅 Активных за 24ч: <b>{active_day}</b>\n"
            f"📆 Активных за 7д: <b>{active_week}</b>\n"
            f"👑 VIP-юзеров: <b>{vips}</b>\n\n"
            f"💰 Монет у всех: <b>{total_coins}</b>\n"
            f"📈 Средний уровень: <b>{avg_level:.1f}</b>\n\n"
            f"🛒 Покупок: <b>{buys}</b>\n"
            f"⭐ Звёзд получено: <b>{total_stars}</b>\n"
            f"↩️ Возвратов: <b>{refunds}</b>"
        )
    except Exception as e:
        await msg.answer(f"Ошибка: <code>{e}</code>")


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


@dp.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    await _show_profile(msg)


@dp.message(F.text == "❓ Помощь")
async def btn_help(msg: Message):
    await _show_help(msg)


@dp.message(F.text == "❌ Скрыть меню")
async def btn_hide(msg: Message):
    await msg.answer(
        "✅ Меню свёрнуто.\n\nВведи /menu или /start — вернуть.",
        reply_markup=ReplyKeyboardRemove()
    )


# ==================== УГАДАЙ ЧИСЛО ====================
@dp.message(F.text.regexp(r"^\d+$"))
async def guess_handler(msg: Message):
    user_id = msg.from_user.id
    game = active_games.get(user_id)
    if not game:
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
        cat = await get_cat(user_id)
        await msg.answer(
            f"🎉 <b>Угадал!</b> Это было число <b>{game['number']}</b>\n"
            f"+{win} монет 💰\n\n" + render(cat),
            reply_markup=bottom_menu()
        )
    else:
        game["tries"] -= 1
        if game["tries"] <= 0:
            await update_cat(user_id, coins=max(0, cat[4] - game["bet"]))
            del active_games[user_id]
            cat = await get_cat(user_id)
            await msg.answer(
                f"😿 <b>Не угадал!</b> Было число <b>{game['number']}</b>\n"
                f"-{game['bet']} монет\n\n" + render(cat),
                reply_markup=bottom_menu()
            )
        else:
            hint = "🔽 меньше" if guess > game["number"] else "🔼 больше"
            await msg.answer(
                f"❌ Не то. Подсказка: <b>{hint}</b>\n"
                f"Осталось попыток: <b>{game['tries']}</b>"
            )


# ==================== ИНЛАЙН-КНОПКИ ====================
@dp.callback_query(F.data == "refresh")
async def cb_refresh(cb: CallbackQuery):
    cat = await get_cat(cb.from_user.id)
    try:
        await cb.message.edit_text(render(cat), reply_markup=main_kb())
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


@dp.callback_query(F.data == "rename")
async def cb_rename(cb: CallbackQuery):
    await cb.message.answer(
        "✏️ <b>Смена имени — в разработке</b>\n\n"
        "Скоро ты сможешь переименовать своего котика!\n\n"
        "<b>Что будет:</b>\n"
        "• Бесплатная смена имени — 1 раз в день\n"
        "• Имя от 2 до 20 символов\n"
        "• Эмодзи в имени — можно\n"
        "• История имён сохранится\n\n"
        "<b>Когда:</b> в ближайшем обновлении 🚀\n\n"
        "А пока — играй, качай котика, копи монеты!",
        reply_markup=profile_kb()
    )
    await cb.answer()


@dp.callback_query(F.data == "skins")
async def cb_skins(cb: CallbackQuery):
    await cb.message.answer(
        "🎨 <b>Скины — в разработке</b>\n\n"
        "Скоро появятся разные котики, которых можно будет покупать!\n\n"
        "<b>Что будет:</b>\n"
        "🐱 Обычный — бесплатно\n"
        "🐈 Полосатый — за монеты\n"
        "🐈‍⬛ Чёрный — за монеты\n"
        "🦁 Лев-кот — за ⭐ Stars\n"
        "🐯 Тигр — за ⭐ Stars\n"
        "🐉 Дракон-кот — за ⭐ Stars (легендарный!)\n\n"
        "Скины будут отображаться в профиле и сообщениях.\n\n"
        "<b>Когда:</b> в ближайшем обновлении 🚀",
        reply_markup=profile_kb()
    )
    await cb.answer()


@dp.callback_query(F.data == "notif_settings")
async def cb_notif(cb: CallbackQuery):
    await cb.message.answer(
        "🔔 <b>Уведомления</b>\n\n"
        "Сейчас бот может присылать:\n"
        "🍖 «Котик проголодался» — если не заходил 24ч\n"
        "🎾 «Котик хочет играть» — если давно не играл\n"
        "🎁 «Бонус дня ждёт» — раз в сутки\n\n"
        "<b>Управление:</b>\n"
        "/mute — отключить все напоминания\n"
        "/unmute — включить обратно\n\n"
        "📌 Скоро: настройка «тихих часов» и выбора типа уведомлений."
    )
    await cb.answer()


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


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    item = SHOP.get(key)
    if not item:
        return await cb.answer("Товар не найден", show_alert=True)
    await cb.message.answer_invoice(
        title=item["title"],
        description=item["desc"],
        payload=f"shop:{key}",
        currency="XTR",
        prices=[LabeledPrice(label=item["title"], amount=item["stars"])],
        provider_token="",
    )
    await cb.answer()


# ==================== ОПЛАТА ====================
@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def on_paid(msg: Message):
    payload = msg.successful_payment.invoice_payload
    key = payload.split(":")[1]
    user_id = msg.from_user.id
    cat = await get_cat(user_id)

    stars = msg.successful_payment.total_amount
    charge_id = msg.successful_payment.telegram_payment_charge_id

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
        text = "🍖 +100 монет зачислено!"
    elif key == "boost":
        until = max(int(time.time()), cat[8]) + 24 * 3600
        await update_cat(user_id, boost_until=until)
        text = "⚡ Ускоритель x2 активирован на 24 часа!"
    elif key == "vip":
        await update_cat(user_id, vip=1)
        text = "👑 Ты стал VIP-котиком! Пассивный доход активирован."
    else:
        text = "✅ Оплата получена!"

    await msg.answer(
        f"✅ <b>Оплата прошла!</b>\n{text}\n\n"
        f"💸 Вернуть можно в течение 7 дней: /refund",
        reply_markup=bottom_menu()
    )

    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"💰 <b>Новая покупка!</b>\n\n"
                f"👤 {msg.from_user.full_name} (@{msg.from_user.username})\n"
                f"🆔 <code>{user_id}</code>\n"
                f"📦 Товар: <b>{key}</b>\n"
                f"⭐ Сумма: <b>{stars} Stars</b>\n"
                f"🧾 Charge: <code>{charge_id}</code>"
            )
        except Exception:
            pass


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================
async def vip_income_loop():
    while True:
        try:
            async with aiosqlite.connect(DB) as db:
                await db.execute("UPDATE cats SET coins = coins + 10 WHERE vip=1")
                await db.commit()
        except Exception as e:
            print(f"vip_income_loop ошибка: {e}")
        await asyncio.sleep(3600)


async def reminder_loop():
    await asyncio.sleep(60)
    while True:
        try:
            now = int(time.time())
            day_ago = now - 86400
            two_hours_ago = now - PLAY_REMIND_COOLDOWN

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

                # Общее напоминание — не чаще 1 в день
                send_general = (not last_remind) or (now - last_remind >= REMIND_COOLDOWN)
                # Отдельное напоминание «поиграть» — не чаще 1 в 2 часа
                send_play = (not last_play_remind) or (now - last_play_remind >= PLAY_REMIND_COOLDOWN)

                days = (now - last_seen) // 86400
                bonus_ready = (now - last_daily) >= DAILY_COOLDOWN
                can_play = satiety >= 10 and coins >= 20

                if send_general and days >= 1:
                    # ОСНОВНОЕ напоминание
                    parts = []
                    if days >= 7:
                        parts.append(
                            f"🐱 <b>Твой котик {name} очень скучает!</b>\n"
                            f"Ты не заходил уже <b>{days} дней</b> 😿"
                        )
                    elif days >= 3:
                        parts.append(
                            f"🐱 <b>{name} скучает по тебе</b>\n"
                            f"Ты не заходил <b>{days} дня</b>."
                        )
                    else:
                        parts.append(f"🐱 <b>{name} проголодался!</b>")

                    if bonus_ready:
                        parts.append("\n🎁 <b>Бонус дня ждёт тебя!</b> Забери бесплатные монеты.")
                    if can_play:
                        parts.append("🎾 Котик хочет поиграть — зайди!")

                    parts.append("\nПокорми котика — он ждёт 🍖")
                    text = "\n".join(parts)

                    buttons = []
                    if bonus_ready:
                        buttons.append([InlineKeyboardButton(
                            text="🎁 Забрать бонус", callback_data="daily"
                        )])
                    buttons.append([InlineKeyboardButton(
                        text="🍖 Покормить", callback_data="feed"
                    )])
                    if can_play:
                        buttons.append([InlineKeyboardButton(
                            text="🎾 Поиграть", callback_data="play"
                        )])
                    buttons.append([InlineKeyboardButton(
                        text="🔕 Не напоминать", callback_data="mute"
                    )])

                    try:
                        await bot.send_message(
                            user_id, text,
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                        )
                        async with aiosqlite.connect(DB) as db:
                            await db.execute(
                                "UPDATE cats SET last_remind=? WHERE user_id=?",
                                (now, user_id)
                            )
                            await db.commit()
                    except Exception as e:
                        print(f"Напоминание {user_id} не прошло: {e}")
                        if "blocked" in str(e).lower():
                            try:
                                async with aiosqlite.connect(DB) as db:
                                    await db.execute(
                                        "UPDATE cats SET last_remind=9999999999 WHERE user_id=?",
                                        (user_id,)
                                    )
                                    await db.commit()
                            except Exception:
                                pass
                elif send_play and can_play and days < 1:
                    # ДОПОЛНИТЕЛЬНОЕ напоминание про игру (только если юзер активен)
                    try:
                        await bot.send_message(
                            user_id,
                            f"🎾 <b>{name} хочет поиграть!</b>\n\n"
                            f"Ты давно не играл. Заходи — получишь монеты и XP!",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🎾 Поиграть", callback_data="play")],
                                [InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")]
                            ])
                        )
                        async with aiosqlite.connect(DB) as db:
                            await db.execute(
                                "UPDATE cats SET last_play_remind=? WHERE user_id=?",
                                (now, user_id)
                            )
                            await db.commit()
                    except Exception as e:
                        print(f"Игровое напоминание {user_id} не прошло: {e}")
        except Exception as e:
            print(f"reminder_loop ошибка: {e}")

        await asyncio.sleep(3600)


async def setup_commands():
    commands = [
        BotCommand(command="start",      description="🐱 Запустить"),
        BotCommand(command="menu",       description="📋 Меню"),
        BotCommand(command="daily",      description="🎁 Бонус дня"),
        BotCommand(command="soon",       description="🚧 Что в разработке"),
        BotCommand(command="help",       description="❓ Помощь"),
        BotCommand(command="support",    description="🆘 Поддержка"),
        BotCommand(command="paysupport", description="💳 Оплата"),
        BotCommand(command="refund",     description="💸 Вернуть звёзды"),
        BotCommand(command="terms",      description="📜 Условия"),
        BotCommand(command="mute",       description="🔕 Отключить напоминания"),
        BotCommand(command="unmute",     description="🔔 Включить напоминания"),
        BotCommand(command="hide",       description="❌ Скрыть меню"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        print(f"setup_commands ошибка: {e}")


# ==================== ЗАПУСК ====================
async def main():
    await init_db()
    await setup_commands()
    dp.message.middleware(SeenMiddleware())
    dp.callback_query.middleware(SeenMiddleware())
    asyncio.create_task(vip_income_loop())
    asyncio.create_task(reminder_loop())
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
