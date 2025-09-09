# server.py
import asyncio
from fastapi import FastAPI
import uvicorn

# Importa el runner del bot
from bot import run_bot

app = FastAPI()
bot_task: asyncio.Task | None = None

@app.get("/")
def root():
    return {"ok": True, "service": "reto-relampago", "status": "alive"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.on_event("startup")
async def _startup():
    global bot_task
    if bot_task is None or bot_task.done():
        # Lanza el polling del bot en segundo plano
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
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
