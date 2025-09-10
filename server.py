# server.py
import asyncio
import logging
from fastapi import FastAPI
from bot import run_bot  # Importa la función que arranca tu bot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

app = FastAPI()
bot_task = None  # type: ignore

@app.get("/")
def root():
    return {"ok": True, "service": "reto-relampago-bot"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.on_event("startup")
async def _startup():
    global bot_task
    if bot_task is None or bot_task.done():
        bot_task = asyncio.create_task(run_bot())
        logging.info("Bot lanzado en background desde FastAPI.")

@app.on_event("shutdown")
async def _shutdown():
    global bot_task
    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except Exception:
            pass
        logging.info("Bot detenido en shutdown.")

# Para probar en local: python server.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
