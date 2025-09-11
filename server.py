import asyncio
from fastapi import FastAPI
from bot import run_bot

app = FastAPI()
_bot_task = None

@app.get("/")
async def root():
    return {"ok": True, "service": "reto-relampago", "status": "alive"}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    global _bot_task
    if _bot_task is None or _bot_task.done():
        _bot_task = asyncio.create_task(run_bot())

@app.on_event("shutdown")
async def on_shutdown():
    global _bot_task
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except Exception:
            pass
