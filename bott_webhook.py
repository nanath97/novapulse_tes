# bott_webhook.py
from aiogram import types
from core import dp, bot

ADMIN_ID = 7334072965  # toi

@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    await bot.send_message(
        message.chat.id,
        "🟢 Bot TEST en ligne.\nEnvoie-moi un message pour tester."
    )

@dp.message_handler()
async def echo(message: types.Message):
    await bot.send_message(
        message.chat.id,
        f"Echo TEST : {message.text}"
    )
