# bot.py
import os
import asyncio
import logging
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

# Carga .env si existe (útil en local)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN en variables de entorno")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start_cmd(m: Message):
    await m.answer("¡Hola! Estoy vivo en Render 🚀")

async def run_bot():
    """
    Arranca el polling del bot y reintenta si algo falla.
    Render necesita que el proceso nunca muera; por eso reintentamos.
    """
    while True:
        try:
            logging.info("Iniciando polling del bot...")
            await dp.start_polling(bot, skip_updates=True)
        except Exception as e:
            logging.exception(f"[run_bot] Error: {e}. Reintentando en 5s...")
            await asyncio.sleep(5)
