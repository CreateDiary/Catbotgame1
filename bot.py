import asyncio
import aiosqlite
import os
import time
import random
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery
)
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8917267408:AAF_9tu6V-OEelOLVzSlke570QotQviJdcY"
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB = "cat.db"
FEED_COOLDOWN = 30  # секунд

# ---------- Магазин ----------
SHOP = {
    "food10":  {"title": "🍖 Корм x10",        "stars": 50,  "desc": "+100 монет сразу"},
    "boost":   {"title": "⚡ Ускоритель x2 (24ч)", "stars": 100, "desc": "Двойные монеты сутки"},
    "vip":     {"title": "👑 VIP-котик",        "stars": 250, "desc": "Скин + пассивный доход"},
}


# ---------- БД ----------
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cats (
                user_id     INTEGER PRIMARY KEY,
                name        TEXT DEFAULT 'Барсик',
                level       INTEGER DEFAULT 1,
                xp          INTEGER DEFAULT 0,
                coins       INTEGER DEFAULT 0,
                satiety     INTEGER DEFAULT 100,
                last_feed   INTEGER DEFAULT 0,
                boost_until INTEGER DEFAULT 0,
                vip         INTEGER DEFAULT 0
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
    _, name, level, xp, coins, satiety, _, boost_until, vip = cat
    boost = "⚡" if boost_until > int(time.time()) else ""
    crown = "👑" if vip else ""
    bar_filled = min(10, satiety // 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)
    need = xp_for_next(level)
    return (
        f"{crown} <b>{name}</b> {boost}\n"
        f"Уровень: <b>{level}</b>  (XP: {xp}/{need})\n"
        f"💰 Монеты: <b>{coins}</b>\n"
        f"🍽 Сытость: [{bar}] {satiety}%"
    )


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍖 Покормить", callback_data="feed"),
         InlineKeyboardButton(text="🎾 Поиграть",  callback_data="play")],
        [InlineKeyboardButton(text="🛒 Магазин",  callback_data="shop"),
         InlineKeyboardButton(text="🔄 Обновить",  callback_data="refresh")],
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


# ---------- Хендлеры ----------
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    cat = await get_cat(msg.from_user.id)
    await msg.answer(
        "🐱 <b>Привет! Это твой котик.</b>\n\n"
        "Корми, играй, качай уровень.\n"
        "За <b>Telegram Stars</b> покупай бонусы в магазине.\n\n"
        + render(cat),
        reply_markup=main_kb()
    )


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
    cat = await get_cat(cb.from_user.id)
    now = int(time.time())
    last = cat[6]
    if now - last < FEED_COOLDOWN:
        left = FEED_COOLDOWN - (now - last)
        return await cb.answer(f"Подожди {left} сек 🍽", show_alert=False)

    coins_gain = random.randint(5, 15)
    if is_boost(cat):
        coins_gain *= 2
    if is_vip(cat):
        coins_gain += 5

    satiety = min(100, cat[5] + 20)
    coins = cat[4] + coins_gain
    await update_cat(cb.from_user.id, coins=coins, satiety=satiety, last_feed=now)
    leveled, level = await add_xp(cb.from_user.id, 10)

    txt = f"🍖 +{coins_gain} монет!"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    cat = await get_cat(cb.from_user.id)
    await cb.message.edit_text(render(cat) + f"\n\n{txt}", reply_markup=main_kb())
    await cb.answer()


@dp.callback_query(F.data == "play")
async def cb_play(cb: CallbackQuery):
    cat = await get_cat(cb.from_user.id)
    if cat[5] < 10:
        return await cb.answer("Котик слишком голодный 😿", show_alert=True)

    coins_gain = random.randint(10, 25)
    if is_boost(cat):
        coins_gain *= 2
    satiety = max(0, cat[5] - 10)
    coins = cat[4] + coins_gain
    await update_cat(cb.from_user.id, coins=coins, satiety=satiety)
    leveled, level = await add_xp(cb.from_user.id, 20)

    txt = f"🎾 +{coins_gain} монет, +20 XP!"
    if leveled:
        txt += f"\n🎉 Новый уровень: <b>{level}</b>!"
    cat = await get_cat(cb.from_user.id)
    await cb.message.edit_text(render(cat) + f"\n\n{txt}", reply_markup=main_kb())
    await cb.answer()


# ---------- Магазин и Stars ----------
@dp.callback_query(F.data == "shop")
async def cb_shop(cb: CallbackQuery):
    text = "🛒 <b>Магазин за Telegram Stars</b>\n\n"
    for item in SHOP.values():
        text += f"• {item['title']} — <b>{item['stars']} ⭐</b>\n  <i>{item['desc']}</i>\n"
    await cb.message.edit_text(text, reply_markup=shop_kb())
    await cb.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    key = cb.data.split(":")[1]
    item = SHOP.get(key)
    if not item:
        return await cb.answer("Товар не найден", show_alert=True)

    # Отправляем invoice со Stars (currency="XTR")
    await cb.message.answer_invoice(
        title=item["title"],
        description=item["desc"],
        payload=f"shop:{key}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=item["title"], amount=item["stars"])],
        provider_token="",  # для Stars пустой!
    )
    await cb.answer()


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    # Обязательно подтвердить в течение 10 секунд
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

    await msg.answer(f"✅ <b>Оплата прошла!</b>\n{text}")

    # уведомление админу
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"💰 {msg.from_user.full_name} (@{msg.from_user.username}) "
                f"купил <b>{key}</b> за "
                f"{msg.successful_payment.total_amount} ⭐"
            )
        except Exception:
            pass


# ---------- Пассивный доход для VIP ----------
async def vip_income_loop():
    while True:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE cats SET coins = coins + 10 WHERE vip=1")
            await db.commit()
        await asyncio.sleep(3600)  # каждый час


# ---------- Запуск ----------
async def main():
    await init_db()
    asyncio.create_task(vip_income_loop())
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
