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
SUPPORT_USERNAME = "artemizmailov"   # ← замени на свой юзернейм (без @)
# ===================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400
REMIND_COOLDOWN = 86400

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
                created_at INTEGER
            )
        """)
        # миграции колонок
        for col, default in [("last_seen", "0"), ("last_remind", "0")]:
            try:
                await db.execute(f"ALTER TABLE cats ADD COLUMN {col} INTEGER DEFAULT {default}")
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


def render(cat):
    _, name, level, xp, coins, satiety, _, boost_until, vip, last_daily, streak = cat[:11]
    boost = "⚡" if boost_until > int(time.time()) else ""
    crown = "👑" if vip else ""
    bar_filled = min(10, satiety // 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    need = xp_for_next(level)
    fire = f" 🔥x{streak}" if streak > 1 else ""
    return (
        f"{crown} <b>{name}</b> {boost}{fire}\n"
        f"Уровень: <b>{level}</b>  (XP: {xp}/{need})\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"🍽 Сытость: [{bar}] {satiety}%"
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
BONUS_SOON_TEXT = (
    "🎁 <b>Бонус дня — в разработке</b>\n\n"
    "Эта функция скоро будет доступна.\n"
    "Мы уже работаем над ней — совсем скоро ты сможешь получать\n"
    "ежедневные награды за вход в бота!\n\n"
    "🐾 <i>Спасибо, что играешь с нами.</i>"
)

HELP_TEXT = (
    "❓ <b>Что делает этот бот?</b>\n\n"
    "🐱 <b>Это игра-тамагочи про котика.</b>\n"
    "Заводишь питомца, кормишь, играешь, качаешь уровень и зарабатываешь монеты.\n\n"
    "<b>🎮 Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (раз в 30 сек)\n"
    "🎾 Поиграть — +XP и монеты\n"
    "🎲 Угадай — мини-игра на монеты\n"
    "🎁 Бонус дня — скоро\n"
    "🛒 Магазин — покупки за ⭐ Stars\n"
    "👤 Профиль — твой котик\n\n"
    "<b>📋 Команды:</b>\n"
    "/start — начать\n"
    "/menu — показать меню\n"
    "/help — эта справка\n"
    "/support — поддержка\n"
    "/terms — условия\n"
    "/mute — отключить напоминания\n"
    "/unmute — включить напоминания\n"
    "/hide — скрыть меню\n\n"
    "👑 <b>VIP</b> — +10 монет каждый час"
)

TERMS_TEXT = (
    "📜 <b>Условия использования</b>\n\n"
    "1. Это игра-тамагочи. Все покупки — цифровые товары.\n"
    "2. Монеты и бонусы внутри игры не имеют денежной ценности\n"
    "   и не подлежат обмену на реальные деньги.\n"
    "3. Возврат средств за Stars возможен через /paysupport\n"
    "   в течение 24 часов после покупки.\n"
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
    "• Хочешь вернуть Stars — можно в течение 24ч\n"
    "• Двойное списание — вернём лишнее\n\n"
    f"📧 Связь: @{SUPPORT_USERNAME}\n\n"
    "⚠️ <b>Важно:</b> поддержка Telegram не помогает с покупками внутри ботов."
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


# ==================== ДЕЙСТВИЯ ====================
async def _animate(target, frames, delay=0.4):
    """Плавная анимация через редактирование сообщения."""
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

    # АНИМАЦИЯ
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
        msg_text = "Котик слишком голодный 😿"
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

    if anim:
        try:
            await anim.edit_text(full, reply_markup=main_kb())
        except Exception:
            await anim.edit_text(full)
    elif isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    if isinstance(target, CallbackQuery):
        await target.answer()


async def _show_shop(target):
    text = "🛒 <b>Магазин за Telegram Stars</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['stars']} ⭐</b>\n  <i>{item['desc']}</i>\n"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=shop_kb())
    else:
        try:
            await target.message.edit_text(text, reply_markup=shop_kb())
        except Exception:
            await target.message.answer(text, reply_markup=shop_kb())
        await target.answer()


async def _show_soon(target):
    if isinstance(target, Message):
        await target.answer(BONUS_SOON_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(BONUS_SOON_TEXT, reply_markup=bottom_menu())
        await target.answer()


async def _show_help(target):
    if isinstance(target, Message):
        await target.answer(HELP_TEXT, reply_markup=bottom_menu())
    else:
        await target.message.answer(HELP_TEXT, reply_markup=bottom_menu())
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
    await msg.answer(
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "За <b>Telegram Stars</b> покупай бонусы в магазине.\n\n"
        "📌 Кнопки внизу — главное меню.\n"
        "📌 /help — справка, /menu — меню.\n\n"
        + render(cat),
        reply_markup=bottom_menu()
    )


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(render(cat), reply_markup=bottom_menu())


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await _show_help(msg)


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
    await msg.answer(
        "🔕 <b>Напоминания отключены</b>\n\n"
        "Бот больше не будет тебе писать.\n"
        "Включить обратно: /unmute",
        reply_markup=bottom_menu()
    )


@dp.message(Command("unmute"))
async def cmd_unmute(msg: Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("UPDATE cats SET last_remind=0 WHERE user_id=?",
                         (msg.from_user.id,))
        await db.commit()
    await msg.answer(
        "🔔 <b>Напоминания включены</b>\n\n"
        "Бот будет напоминать, если ты давно не заходил.",
        reply_markup=bottom_menu()
    )


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

            cur = await db.execute("SELECT COUNT(*), COALESCE(SUM(stars),0) FROM payments")
            row = await cur.fetchone()
            buys, total_stars = row if row else (0, 0)

        await msg.answer(
            f"📊 <b>Статистика бота</b>\n\n"
            f"👥 Всего юзеров: <b>{total}</b>\n"
            f"📅 Активных за 24ч: <b>{active_day}</b>\n"
            f"📆 Активных за 7д: <b>{active_week}</b>\n"
            f"👑 VIP-юзеров: <b>{vips}</b>\n\n"
            f"💰 Монет у всех: <b>{total_coins}</b>\n"
            f"📈 Средний уровень: <b>{avg_level:.1f}</b>\n\n"
            f"🛒 Покупок: <b>{buys}</b>\n"
            f"⭐ Звёзд получено: <b>{total_stars}</b>"
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
    await _show_soon(msg)


@dp.message(F.text == "🛒 Магазин")
async def btn_shop(msg: Message):
    await _show_shop(msg)


@dp.message(F.text == "👤 Профиль")
async def btn_profile(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(render(cat), reply_markup=bottom_menu())


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
    await _show_soon(cb)


@dp.callback_query(F.data == "guess")
async def cb_guess(cb: CallbackQuery):
    await _start_guess(cb.from_user.id, cb)


@dp.callback_query(F.data == "shop")
async def cb_shop(cb: CallbackQuery):
    await _show_shop(cb)


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

    # сохраняем платёж
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

    await msg.answer(f"✅ <b>Оплата прошла!</b>\n{text}", reply_markup=bottom_menu())

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
    await asyncio.sleep(60)  # подождём, пока бот стартует
    while True:
        try:
            now = int(time.time())
            day_ago = now - 86400

            async with aiosqlite.connect(DB) as db:
                cur = await db.execute(
                    "SELECT user_id, name, last_seen, last_remind FROM cats "
                    "WHERE last_seen < ? AND last_seen > 0",
                    (day_ago,)
                )
                rows = await cur.fetchall()

            for user_id, name, last_seen, last_remind in rows:
                if last_remind and now - last_remind < REMIND_COOLDOWN:
                    continue

                days = (now - last_seen) // 86400

                if days >= 7:
                    text = (
                        f"🐱 <b>Твой котик {name} очень скучает!</b>\n\n"
                        f"Ты не заходил уже <b>{days} дней</b>. "
                        f"Он голодный и грустный 😿\n\n"
                        f"Зайди, покорми его! 🍖"
                    )
                elif days >= 3:
                    text = (
                        f"🐱 <b>{name} скучает по тебе</b>\n\n"
                        f"Ты не заходил <b>{days} дня</b>. Котик хочет есть 🍖"
                    )
                elif days >= 1:
                    text = f"🐱 <b>{name} проголодался!</b>\n\nПокорми его — он ждёт 🍖"
                else:
                    continue

                try:
                    await bot.send_message(
                        user_id, text,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed")],
                            [InlineKeyboardButton(text="🔕 Не напоминать", callback_data="mute")]
                        ])
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
        except Exception as e:
            print(f"reminder_loop ошибка: {e}")

        await asyncio.sleep(3600)


async def setup_commands():
    commands = [
        BotCommand(command="start",      description="🐱 Запустить"),
        BotCommand(command="menu",       description="📋 Меню"),
        BotCommand(command="help",       description="❓ Помощь"),
        BotCommand(command="support",    description="🆘 Поддержка"),
        BotCommand(command="paysupport", description="💳 Оплата"),
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
