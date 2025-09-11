import os, logging, asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN no configurado")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("¡Hola! Bot en Render listo ✅")

async def run_bot():
    # Bucle de reintento para que siempre se levante el polling
    while True:
        try:
            me = await bot.me()
            logging.info(f"Conectado como @{me.username} (id {me.id})")
            await dp.start_polling(bot, skip_updates=True)
        except Exception as e:
            logging.exception("Error en polling; reintento en 5s: %s", e)
            await asyncio.sleep(5)
