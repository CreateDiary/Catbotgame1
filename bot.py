import asyncio
import aiosqlite
import time
import random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, BotCommand, BotCommandScopeDefault,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.client.default import DefaultBotProperties

# ==== НАСТРОЙКИ ====
BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
ADMIN_ID = 5965370780
# ===================

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30
DAILY_COOLDOWN = 86400

SHOP = {
    "food10": {"title": "🍖 Корм x10", "stars": 50, "desc": "+100 монет сразу"},
    "boost":  {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":    {"title": "👑 VIP-котик", "stars": 250, "desc": "Скин + пассивный доход"},
}

active_games = {}


# ---------- БД ----------
async def init_db():
    async with aiosqlite.connect(DB) as db:
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


# ---------- Логика ----------
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


# ---------- Клавиатуры ----------
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
            [KeyboardButton(text="🏆 Топ"),       KeyboardButton(text="❓ Помощь")],
            [KeyboardButton(text="❌ Скрыть меню")],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "<b>Команды:</b>\n"
    "/start — начать\n"
    "/menu  — показать меню\n"
    "/help  — эта справка\n"
    "/top   — топ игроков\n"
    "/hide  — скрыть меню\n\n"
    "<b>Кнопки внизу:</b>\n"
    "🍖 Покормить — +монеты (раз в 30 сек)\n"
    "🎾 Поиграть  — +XP и монеты\n"
    "🎲 Угадай    — мини-игра на монеты\n"
    "🎁 Бонус дня — бесплатные монеты раз в 24ч\n"
    "🛒 Магазин   — покупки за ⭐ Stars\n"
    "👤 Профиль   — твой котик\n"
    "🏆 Топ       — рейтинг\n"
    "❌ Скрыть меню — убрать кнопки\n\n"
    "👑 <b>VIP</b> — +10 монет каждый час\n"
    "🔥 <b>Стрик</b> — заходи каждый день, бонус растёт!"
)


# ---------- Действия ----------
async def _do_feed(user_id, target):
    cat = await get_cat(user_id)
    now = int(time.time())
    if now - cat[6] < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - cat[6])
        msg_text = f"Подожди {left} сек 🍽"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=False)

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
    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        try:
            await target.message.edit_text(full, reply_markup=main_kb())
        except Exception:
            await target.message.answer(full)
        await target.answer()


async def _do_play(user_id, target):
    cat = await get_cat(user_id)
    if cat[5] < 10:
        msg_text = "Котик слишком голодный 😿"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    coins_gain = random.randint(10, 25)
    if is_boost(cat): coins_gain *= 2
    await update_cat(user_id, coins=cat[4] + coins_gain, satiety=max(0, cat[5] - 10))
    leveled, level = await add_xp(user_id, 20)

    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    cat = await get_cat(user_id)
    full = render(cat) + f"\n\n{txt}"
    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        try:
            await target.message.edit_text(full, reply_markup=main_kb())
        except Exception:
            await target.message.answer(full)
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
        msg_text = f"⏰ Бонус уже получен. Следующий через {h}ч {m}м"
        if isinstance(target, Message):
            return await target.answer(msg_text)
        return await target.answer(msg_text, show_alert=True)

    if now - last < DAILY_COOLDOWN * 2 and last > 0:
        streak += 1
    else:
        streak = 1

    base = 50
    bonus = base + (streak - 1) * 10
    if is_vip(cat): bonus *= 2

    await update_cat(user_id, coins=cat[4] + bonus, last_daily=now, streak=streak)
    leveled, level = await add_xp(user_id, 15)

    txt = (
        f"🎁 <b>Ежедневный бонус!</b>\n"
        f"+{bonus} монет 💰\n"
        f"🔥 Стрик: <b>{streak}</b> дней"
    )
    if streak >= 3:
        txt += "\n⚡ Отличная серия!"
    if leveled: txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    cat = await get_cat(user_id)
    full = render(cat) + f"\n\n{txt}"
    if isinstance(target, Message):
        await target.answer(full, reply_markup=bottom_menu())
    else:
        await target.message.answer(full, reply_markup=bottom_menu())
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


async def _show_top(target):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT user_id, level, coins, vip FROM cats ORDER BY level DESC, coins DESC LIMIT 10"
        )
        rows = await cur.fetchall()
    if not rows:
        text = "Пока никого нет 🐾"
    else:
        medals = ["🥇", "🥈", "🥉"]
        text = "🏆 <b>Топ-10 котиков</b>\n\n"
        for i, (uid, lvl, coins, vip) in enumerate(rows):
            medal = medals[i] if i < 3 else f"{i+1}."
            crown = "👑" if vip else ""
            text += f"{medal} {crown} Lvl <b>{lvl}</b> — 💰 {coins}\n"
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


# ---------- Команды ----------
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "За <b>Telegram Stars</b> покупай бонусы в магазине.\n\n"
        "📌 Кнопки внизу — главное меню.\n"
        "📌 Нажми <b>❌ Скрыть меню</b> — свернёшь клавиатуру.\n"
        "📌 Или введи /menu — вернуть.\n\n"
        + render(cat),
        reply_markup=bottom_menu()
    )


@dp.message(Command("menu"))
async def cmd_menu(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(render(cat), reply_markup=bottom_menu())


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(HELP_TEXT, reply_markup=bottom_menu())


@dp.message(Command("top"))
async def cmd_top(msg: Message):
    await _show_top(msg)


@dp.message(Command("hide"))
async def cmd_hide(msg: Message):
    await msg.answer("Меню свёрнуто. Введи /menu чтобы вернуть.",
                     reply_markup=ReplyKeyboardRemove())


# ---------- Кнопки внизу ----------
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
    cat = await get_cat(msg.from_user.id)
    await msg.answer(render(cat), reply_markup=bottom_menu())


@dp.message(F.text == "🏆 Топ")
async def btn_top(msg: Message):
    await _show_top(msg)


@dp.message(F.text == "❓ Помощь")
async def btn_help(msg: Message):
    await msg.answer(HELP_TEXT, reply_markup=bottom_menu())


@dp.message(F.text == "❌ Скрыть меню")
async def btn_hide(msg: Message):
    await msg.answer(
        "✅ Меню свёрнуто.\n\nВведи /menu или /start — вернуть.",
        reply_markup=ReplyKeyboardRemove()
    )


# ---------- Угадай число: обработка ввода ----------
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


# ---------- Инлайн-кнопки ----------
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


# ---------- Оплата ----------
@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    await q.answer(ok=True)


@dp.message(F.successful_payment)
async def on_paid(msg: Message):
    payload = msg.successful_payment.invoice_payload
    key = payload.split(":")[1]
    user_id = msg.from_user.id
    cat = await get_cat(user_id)

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
                f"💰 {msg.from_user.full_name} купил <b>{key}</b> за "
                f"{msg.successful_payment.total_amount} ⭐"
            )
        except Exception:
            pass


# ---------- Фоновые задачи ----------
async def vip_income_loop():
    while True:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET coins = coins + 10 WHERE vip=1")
            await db.commit()
        await asyncio.sleep(3600)


async def setup_commands():
    commands = [
        BotCommand(command="start", description="🐱 Запустить"),
        BotCommand(command="menu",  description="📋 Меню"),
        BotCommand(command="top",   description="🏆 Топ игроков"),
        BotCommand(command="hide",  description="❌ Скрыть меню"),
        BotCommand(command="help",  description="❓ Помощь"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main():
    await init_db()
    await setup_commands()
    asyncio.create_task(vip_income_loop())
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
