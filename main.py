from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router





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


# === TEST STAFF DEBUT
from vip_topics import load_vip_topics_from_disk

@app.on_event("startup")
async def startup_event():
    try:
        bott_webhook.initialize_authorized_users
        await load_vip_topics()      # 👈 s’assure que ceux manquants sont créés

        print(f"[STARTUP] VIP + topics initialisés.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")


# === TEST STAFF FIN

# === 221097 DEBUT
app.include_router(stripe_router)
# === 221097 FIN

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")

# === 221097 FINV1