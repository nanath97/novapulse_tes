# main.py
import os
from fastapi import FastAPI, Request
from aiogram import types

from core import bot, dp, BOT_TOKEN
from stripe_webhook import router as stripe_router  # tu peux le brancher plus tard

app = FastAPI()

# si tu veux, tu peux commenter cette ligne au tout début
# app.include_router(stripe_router)

@app.get("/")
async def root():
    return {"status": "ok", "message": "NovaPulse TEST bot running"}

@app.post(f"/bot{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}
