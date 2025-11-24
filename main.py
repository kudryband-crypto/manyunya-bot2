import asyncio
import aioschedule
import logging
from datetime import datetime, date
from flask import Flask
from threading import Thread

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

import sqlite3
import os

# ==================== ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Manyunya Bot is alive and running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Запускаем веб-сервер
keep_alive()

# ==================== НАСТРОЙКИ ====================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN не найден! Добавь в переменные окружения")

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002616446934"))

CHARACTERS = ["Ален", "Катя", "Кузя"]
HEART = "❤️"
BLACK = "🖤"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== БАЗА ДАННЫХ ====================
conn = sqlite3.connect('manyunya.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS votes
               (user_id INTEGER, character TEXT, vote_type TEXT, vote_date TEXT)''')
cur.execute('''CREATE TABLE IF NOT EXISTS last_vote
               (user_id INTEGER PRIMARY KEY, timestamp REAL)''')
conn.commit()

# ==================== КЛАВИАТУРЫ ====================
def start_kb():
    kb = [[types.KeyboardButton(text=name)] for name in CHARACTERS]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def vote_kb(character: str):
    kb = [[
        InlineKeyboardButton(text="❤️ Манюня", callback_data=f"vote_{character}_❤️"),
        InlineKeyboardButton(text="🖤 Не манюня", callback_data=f"vote_{character}_🖤")
    ]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ==================== СТАТИСТИКА ====================
def get_today_stats():
    today = date.today().isoformat()
    cur.execute("SELECT character, vote_type, COUNT(*) FROM votes WHERE vote_date = ? GROUP BY character, vote_type", (today,))
    data = cur.fetchall()
    stats = {char: {"❤️": 0, "🖤": 0} for char in CHARACTERS}
    for char, vtype, cnt in data:
        stats[char][vtype] = cnt
    return stats

# ==================== ОТПРАВКА ИТОГОВ С КАРТИНКОЙ ====================
async def send_daily_result(char: str, hearts: int, blacks: int):
    total = hearts + blacks

    if hearts > 3:
        photo = FSInputFile("super_manyunya.jpg")
        caption = f"✨ Сегодня <b>{char}</b> — СУПЕРМАНЮНЯ!\n" \
                  f"Получил {hearts} {HEART} из {total}"
    elif blacks > 3:
        photo = FSInputFile("not_manyunya.jpg")
        caption = f"💔 Сегодня <b>{char}</b> — не манюня…\n" \
                  f"Получил {blacks} {BLACK} из {total}"
    else:
        photo = FSInputFile("average_manyunya.jpg")
        caption = f"Сегодня <b>{char}</b> был средней манюнечности 😐\n" \
                  f"{hearts} {HEART} и {blacks} {BLACK} (из {total})"

    try:
        await bot.send_photo(CHANNEL_ID, photo, caption=caption)
    except Exception as e:
        logging.error(f"Ошибка отправки фото: {e}")
        await bot.send_message(CHANNEL_ID, caption)  # на всякий случай без фото

# ==================== ЕЖЕДНЕВНЫЕ ИТОГИ ====================
async def check_daily_winners():
    stats = get_today_stats()
    for char in CHARACTERS:
        hearts = stats[char][HEART]
        blacks = stats[char][BLACK]
        if hearts + blacks > 0:  # только если были голоса
            await send_daily_result(char, hearts, blacks)

# ==================== ПЛАНИРОВЩИК (23:00 МСК = 20:00 UTC) ====================
async def scheduler():
    aioschedule.every().day.at("20:00").do(lambda: asyncio.create_task(check_daily_winners()))
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(60)

# ==================== ХЭНДЛЕРЫ ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Это <b>Рейтинг Манюнечности</b>\n"
        "Голосуй каждый день — в 23:00 подведём итоги с картинками!",
        reply_markup=start_kb()
    )

@dp.message(F.text.in_(CHARACTERS))
async def choose_character(message: types.Message):
    await message.answer(f"Оцени <b>{message.text}</b>:", reply_markup=vote_kb(message.text))

@dp.callback_query(F.data.startswith("vote_"))
async def process_vote(callback: types.CallbackQuery):
    _, char, vote = callback.data.split("_", 2)
    user_id = callback.from_user.id
    today = date.today().isoformat()

    # Антиспам 30 секунд
    cur.execute("SELECT timestamp FROM last_vote WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    now = datetime.now().timestamp()
    if row and now - row[0] < 30:
        await callback.answer("Подожди 30 секунд!", show_alert=True)
        return

    cur.execute("INSERT INTO votes VALUES (?, ?, ?, ?)", (user_id, char, vote, today))
    cur.execute("INSERT OR REPLACE INTO last_vote VALUES (?, ?)", (user_id, now))
    conn.commit()

    await callback.answer("Голос засчитан!")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"Спасибо! Ты проголосовал за <b>{char}</b> → {vote}")

# ==================== ЗАПУСК ====================
async def main():
    asyncio.create_task(scheduler())
    await check_daily_winners()  # на случай перезапуска
    await dp.start_polling(bot)

if __name__ == "__main__":
    print("🚀 Бот запускается...")
    print("✅ Веб-сервер активен на порту 8080")
    print("🤖 Telegram бот подключается...")
    asyncio.run(main())
