import asyncio
import aioschedule
import logging
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types, F, DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

import sqlite3
import pytz
import os

# === НАСТРОЙКИ ===
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002616446934"))  # твой канал @manyunyabot2025

# Персонажи
CHARACTERS = ["Ален", "Катя", "Кузя"]
HEART = "❤️"
BLACK = "🖤"

MOSCOW_TZ = pytz.timezone('Europe/Moscow')
logging.basicConfig(level=logging.INFO)

# Правильная инициализация бота для aiogram ≥3.7
bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# === БАЗА ДАННЫХ ===
conn = sqlite3.connect('manyunya.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS votes
               (user_id INTEGER, character TEXT, vote_type TEXT, vote_date TEXT)''')
cur.execute('''CREATE TABLE IF NOT EXISTS last_vote
               (user_id INTEGER PRIMARY KEY, timestamp REAL)''')
conn.commit()

# === Клавиатуры ===
def start_kb():
    kb = [[types.KeyboardButton(text=name)] for name in CHARACTERS]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def vote_kb(character: str):
    kb = [[
        InlineKeyboardButton(text=f"❤️ Манюня", callback_data=f"vote_{character}_{HEART}"),
        InlineKeyboardButton(text=f"🖤 Не манюня", callback_data=f"vote_{character}_{BLACK}")
    ]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# === Статистика ===
def get_today_stats():
    today = date.today().isoformat()
    cur.execute("SELECT character, vote_type, COUNT(*) FROM votes WHERE vote_date = ? GROUP BY character, vote_type", (today,))
    data = cur.fetchall()
    stats = {char: {"❤️": 0, "🖤": 0} for char in CHARACTERS}
    for char, vtype, cnt in data:
        stats[char][vtype] = cnt
    return stats

def get_month_stats():
    today = date.today()
    year, month = today.year, today.month
    cur.execute("""SELECT character, vote_type, COUNT(*) FROM votes 
                   WHERE substr(vote_date, 1, 7) = ? 
                   GROUP BY character, vote_type""", (f"{year}-{month:02d}",))
    data = cur.fetchall()
    stats = {char: {"❤️": 0, "🖤": 0} for char in CHARACTERS}
    for char, vtype, cnt in data:
        stats[char][vtype] = cnt
    return stats

# === Объявления ===
async def check_daily_winners():
    stats = get_today_stats()
    for char, counts in stats.items():
        if counts[HEART] > 3:
            await bot.send_message(CHANNEL_ID, f"✨ Сегодня <b>{char}</b> — суперманюня! Уже {counts[HEART]} ❤️")
        if counts[BLACK] > 3:
            await bot.send_message(CHANNEL_ID, f"💔 Сегодня <b>{char}</b> — не манюня… {counts[BLACK]} 🖤")

async def check_monthly_winners():
    if date.today().day != 1:
        return
    stats = get_month_stats()
    current_month = datetime.now(MOSCOW_TZ).strftime("%B %Y")
    for char, counts in stats.items():
        if counts[HEART] >= 50:
            await bot.send_message(CHANNEL_ID, f"🏆 В {current_month} главный МАНЮНЯ — <b>{char}</b>! {counts[HEART]} ❤️")
        if counts[BLACK] >= 50:
            await bot.send_message(CHANNEL_ID, f"😭 В {current_month} совсем НЕ МАНЮНЯ — <b>{char}</b>… {counts[BLACK]} 🖤")

# === Планировщик ===
async def scheduler():
    aioschedule.every().day.at("00:05").do(lambda: asyncio.create_task(check_daily_winners()))
    aioschedule.every().day.at("00:01").do(lambda: asyncio.create_task(check_monthly_winners()))
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(60)

# === Хэндлеры ===
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! Это <b>Рейтинг Манюнечности</b>\n"
        "Выбирай персонажа и ставь ❤️ или 🖤\n"
        "Каждый день и каждый месяц определяем главного манюню!",
        reply_markup=start_kb()
    )

@dp.message(F.text.in_(CHARACTERS))
async def choose_character(message: types.Message):
    char = message.text
    await message.answer(f"Оцени <b>{char}</b>:", reply_markup=vote_kb(char))

@dp.callback_query(F.data.startswith("vote_"))
async def process_vote(callback: CallbackQuery):
    _, char, vote = callback.data.split("_", 2)
    user_id = callback.from_user.id
    today = date.today().isoformat()

    # Антиспам 30 сек
    cur.execute("SELECT timestamp FROM last_vote WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    now = datetime.now().timestamp()
    if row and now - row[0] < 30:
        await callback.answer("Подожди 30 секунд перед следующим голосом!", show_alert=True)
        return

    # Сохраняем голос
    cur.execute("INSERT INTO votes VALUES (?, ?, ?, ?)", (user_id, char, vote, today))
    cur.execute("INSERT OR REPLACE INTO last_vote VALUES (?, ?)", (user_id, now))
    conn.commit()

    await callback.answer(f"Твой голос за {char} {vote} засчитан!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Спасибо! Ты проголосовал за <b>{char}</b> → {vote}")

    # Моментальная проверка порога
    stats = get_today_stats()
    if stats[char][HEART] > 3:
        await bot.send_message(CHANNEL_ID, f"✨ Сегодня <b>{char}</b> — официально суперманюня! Уже {stats[char][HEART]} ❤️")
    if stats[char][BLACK] > 3:
        await bot.send_message(CHANNEL_ID, f"💔 Сегодня <b>{char}</b> — не манюня… {stats[char][BLACK]} 🖤")

# === Запуск ===
async def main():
    asyncio.create_task(scheduler())
    await asyncio.sleep(5)
    await check_daily_winners()
    await check_monthly_winners()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
