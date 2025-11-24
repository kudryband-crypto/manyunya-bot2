import os
import asyncio
from datetime import date
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
import sqlite3
from flask import Flask
from threading import Thread
import aioschedule as schedule

# ======================== FLASK (чтобы не засыпал) ========================
app = Flask('')

@app.route('/')
def home():
    return "Манюня живёт вечно ❤️"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_flask, daemon=True).start()

# ======================== БОТ ========================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002616446934"))  # твой канал
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CHARACTERS = ["Ален", "Катя", "Кузя"]

# База
conn = sqlite3.connect('manyunya.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS votes
               (user_id INTEGER, character TEXT, vote_type TEXT, vote_date TEXT)''')
conn.commit()

# ======================== КОМАНДЫ ========================
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
        InlineKeyboardButton(text="❤️ Манюня", callback_data=f"vote_{message.text}_❤️"),
        InlineKeyboardButton(text="Не манюня", callback_data=f"vote_{message.text}_")
    ]])
    await message.answer(f"Оцени <b>{message.text}</b>:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("vote_"))
async def vote(callback: types.CallbackQuery):
    _, char, vote = callback.data.split("_", 2)
    today = date.today().isoformat()
    cur.execute("INSERT INTO votes VALUES (?, ?, ?, ?)", 
                (callback.from_user.id, char, vote, today))
    conn.commit()
    await callback.answer("Голос засчитан!")
    await callback.message.edit_text(f"Спасибо! Ты выбрал <b>{char}</b> → {vote}")

# ======================== РУЧНЫЕ ИТОГИ ========================
@dp.message(Command("итоги"))
async def manual_results(message: types.Message):
    await send_daily_results()
    await message.answer("Итоги отправлены в канал!")

# ======================== АВТО-ИТОГИ В 23:50 ========================
async def send_daily_results():
    today = date.today().strftime("%d.%m.%Y")
    results = {char: {"❤️": 0, "": 0} for char in CHARACTERS}
    
    cur.execute("SELECT character, vote_type FROM votes WHERE vote_date = ?", (date.today().isoformat(),))
    for char, vote in cur.fetchall():
        results[char][vote] += 1

    text = f"Итоги за {today}\n\n"
    winner = "Никто"
    max_votes = -1

    for char in CHARACTERS:
        man = results[char]["❤️"]
        not_man = results[char][""]
        total = man + not_man
        text += f"<b>{char}</b>: ❤️ {man} |  {not_man} (всего {total})\n"
        if man > max_votes:
            max_votes = man
            winner = char

    text += f"\nПобедитель дня — <b>{winner}</b>! "

    # Выбор картинки
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
        print(f"ИТОГИ ОТПРАВЛЕНЫ В КАНАЛ — {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"Ошибка отправки фото: {e}")
        await bot.send_message(CHANNEL_ID, text, parse_mode="HTML")

# Планировщик — каждый день в 23:50 по МСК
schedule.every().day.at("23:50").do(lambda: asyncio.create_task(send_daily_results()))

async def scheduler():
    print("Планировщик запущен — ждём 23:50 каждый день")
    while True:
        await schedule.run_pending()
        await asyncio.sleep(30)

# ======================== ЗАПУСК ========================
async def main():
    print("Манюня-бот стартует...")
    await asyncio.gather(
        dp.start_polling(bot),
        scheduler()
    )

if __name__ == "__main__":
    asyncio.run(main())
