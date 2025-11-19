from fastapi import FastAPI, Request
from aiogram import types
from dotenv import load_dotenv
import os

from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router
from vip_topics import load_vip_topics_from_airtable

load_dotenv()

app = FastAPI()


@app.post(f"/bot/{os.getenv('BOT_TOKEN')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@app.on_event("startup")
async def startup_event():
    try:
        # Recharge les VIP dans authorized_users
        bott_webhook.initialize_authorized_users()

        # Recharge les topics depuis Airtable
        await load_vip_topics_from_airtable()

        print("[STARTUP] VIP + topics initialisés.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")


# Stripe webhook
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
