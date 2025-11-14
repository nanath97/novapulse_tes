# core.py
import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware  # tu peux l'ajouter après

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN manquant dans l'environnement")

bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)
dp = Dispatcher(bot)

authorized_users = set()

# Pour commencer, tu peux commenter cette ligne,
# et l'activer plus tard une fois que le bot de base marche
# from middlewares.payment_filter import PaymentFilterMiddleware
# dp.middleware.setup(PaymentFilterMiddleware(authorized_users))
