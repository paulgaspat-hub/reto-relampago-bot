import asyncio
from fastapi import FastAPI
import uvicorn

from bot import run_bot  # importa el runner del bot (definido en bot.py)

app = FastAPI()
bot_task: asyncio.Task | None = None


@app.get("/")
async def root():
    return {"ok": True, "service": "reto-relampago", "status": "alive"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.on_event("startup")
async def _startup():
    global bot_task
    # Lanza el bot en segundo plano al iniciar el server
    if bot_task is None or bot_task.done():
        bot_task = asyncio.create_task(run_bot())


@app.on_event("shutdown")
async def _shutdown():
    global bot_task
    if bot_task and not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except Exception:
            pass


if __name__ == "__main__":
    # Solo para pruebas locales. En Render no se usa esta rama.
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

