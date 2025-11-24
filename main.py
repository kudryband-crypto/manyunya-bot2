import os
import asyncio
import logging
from datetime import datetime, date
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
import sqlite3
from flask import Flask
from threading import Thread
import aioschedule as schedule

# ======================== FLASK ДЛЯ 24/7 ========================
app = Flask('')

@app.route('/')
def home():
    return f"Манюня жив! {datetime.now().strftime('%H:%M:%S')}"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_flask, daemon=True).start()

# ======================== БОТ ========================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002616446934"))
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

CHARACTERS = ["Ален", "Катя", "Кузя"]
conn = sqlite3.connect('manyunya.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS votes
               (user_id INTEGER, character TEXT, vote_type TEXT, vote_date TEXT)''')
conn.commit()

@dp.message(Command("start"))
async def start(message: types.Message):
    kb = [[types.KeyboardButton(text=c)) for c in CHARACTERS]
    await message.answer(
        "Привет! Это <b>Рейтинг Манюнечности</b>!\nВыбери персонажа:",
        reply_markup=types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    )

@dp.message(lambda m: m.text in CHARACTERS)
async def choose(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❤️ Манюня", callback_data=f"vote_{message.text}_manunya"),
        InlineKeyboardButton(text="🖤 Не манюня", callback_data=f"vote_{message.text}_not")
    ]])
    await message.answer(f"Оцени <b>{message.text}</b>:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def vote(callback: types.CallbackQuery):
    _, char, vote_type = callback.data.split("_", 2)
    vote = "❤️" if vote_type == "manunya" else "🖤"
    today = date.today().isoformat()
    cur.execute("INSERT INTO votes VALUES (?, ?, ?, ?)", 
                (callback.from_user.id, char, vote, today))
    conn.commit()
    await callback.answer("Голос засчитан!")
    await callback.message.edit_text(f"Спасибо! Ты выбрал <b>{char}</b> → {vote}")

# ======================== ИТОГИ В 23:40 ========================
async def send_daily_results():
    today = date.today().strftime("%d.%m.%Y")
    results = {char: {"❤️": 0, "🖤": 0} for char in CHARACTERS}
    
    cur.execute("SELECT character, vote_type FROM votes WHERE vote_date = ?", (date.today().isoformat(),))
    for char, vote in cur.fetchall():
        results[char][vote] += 1
    
    text = f"Итоги за {today}\n\n"
    winner = None
    max_votes = -1
    
    for char in CHARACTERS:
        man = results[char]["❤️"]
        not_man = results[char]["🖤"]
        total = man + not_man
        text += f"<b>{char}</b>: ❤️ {man} | 🖤 {not_man} (всего {total})\n"
        if man > max_votes:
            max_votes = man
            winner = char
    
    text += f"\nПобедитель дня — <b>{winner}</b>! "
    
    if max_votes >= 10:
        photo = FSInputFile("super_manyunya.jpg")
        text += "СУПЕР-МАНЮНЯ!"
    elif max_votes >= 5:
        photo = FSInputFile("average_manyunya.jpg")
        text += "Средняя манюня"
    else:
        photo = FSInputFile("not_manyunya.jpg")
        text += "Не манюня..."

    try:
        await bot.send_photo(CHANNEL_ID, photo, caption=text, parse_mode="HTML")
        print("Итоги отправлены в канал!")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

schedule.every().day.at("23:40").do(lambda: asyncio.create_task(send_daily_results()))

async def scheduler():
    while True:
        await schedule.run_pending()
        await asyncio.sleep(30)

# ======================== ЗАПУСК ========================
async def main():
    print("Манюня-бот запускается...")
    await asyncio.gather(
        dp.start_polling(bot),
        scheduler()
    )

if __name__ == "__main__":
    asyncio.run(main())
