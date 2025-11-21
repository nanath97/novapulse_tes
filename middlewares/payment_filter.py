from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list  # Import de la ban_list

import asyncio
import time
import os

# IDs
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DIRECTEUR_ID = int(os.getenv("DIRECTEUR_ID", "0"))
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# --- Récupération sûre des admins autorisés (peut être défini ailleurs) ---
# On essaie dans l'ordre : variable globale AUTHORIZED_ADMIN_IDS, puis ADMIN_IDS env (CSV)
AUTHORIZED_ADMIN_IDS = set()
try:
    raw = globals().get("AUTHORIZED_ADMIN_IDS")
    if raw:
        if isinstance(raw, (set, list, tuple)):
            AUTHORIZED_ADMIN_IDS = set(int(x) for x in raw)
        else:
            AUTHORIZED_ADMIN_IDS = {int(raw)}
    else:
        # fallback : lire ADMIN_IDS depuis .env (CSV)
        admin_ids_csv = os.getenv("ADMIN_IDS", "")
        for part in admin_ids_csv.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                AUTHORIZED_ADMIN_IDS.add(int(part))
            except Exception:
                pass
except Exception:
    AUTHORIZED_ADMIN_IDS = {ADMIN_ID}

# Utilisateurs jamais limités (définition avant update)
EXCLUDED_IDS = {
    ADMIN_ID,
    DIRECTEUR_ID,
    7334072965,   # Ton ID perso (Nathan)
}

# Fusionner avec les admins autorisés si besoin
try:
    EXCLUDED_IDS.update(AUTHORIZED_ADMIN_IDS)
except Exception:
    # sécurité si AUTHORIZED_ADMIN_IDS n'est pas itérable
    try:
        EXCLUDED_IDS.add(int(AUTHORIZED_ADMIN_IDS))
    except Exception:
        pass

# Boutons autorisés
BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour... tout en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# Lien VIP
VIP_URL = "https://buy.stripe.com/5kQ9AS60J2ET9wxfi57AI0W"

# Anti-doublon
_processed_keys = {}
_PROCESSED_TTL = 60

def _prune_processed(now: float):
    for k, ts in list(_processed_keys.items()):
        if now - ts > _PROCESSED_TTL:
            del _processed_keys[k]


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        chat = message.chat

        # Admins / staff jamais bloqués
        if user_id in EXCLUDED_IDS:
            return

        # Le blocage s'applique uniquement en privé
        if chat.type != "private":
            return

        now = time.time()
        _prune_processed(now)
        key = (chat.id, message.message_id)
        if key in _processed_keys:
            return
        _processed_keys[key] = now

        # Ban permanent
        for admin_id, clients_bannis in ban_list.items():
            if user_id in clients_bannis:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.answer("🚫 Tu as été banni, tu ne peux plus envoyer de messages.")
                except Exception:
                    pass
                raise CancelHandler()

        # On ne prend du texte que si c'est du texte, sinon string vide
        text = (message.text or "").strip() if message.content_type == types.ContentType.TEXT else ""

        # Autoriser /start (sécurisé si text == "")
        if text and text.startswith("/start"):
            return

        # Autoriser boutons ReplyKeyboard
        for b in BOUTONS_AUTORISES:
            if text.startswith(b):
                return

        # Autoriser liens admin dans le staff (vérifier que c'est bien du texte)
        if user_id == ADMIN_ID and message.content_type == types.ContentType.TEXT and message.text:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception:
                    pass
                raise CancelHandler()
            return

        # 🔥 Règle finale : SEULS LES VIP peuvent envoyer des messages
        if user_id not in self.authorized_users:    # NON-VIP
            try:
                await message.delete()
            except Exception:
                pass

            kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("⭐ Devenir membre VIP", url=VIP_URL)
            )

            try:
                await message.answer(
                    "Désolée mon coeur, mais pour discuter librement avec moi, tu dois être un vip ! "
                    "Pour valider ton accès, tu n'as qu'à cliquer sur le lien juste ici ",
                    reply_markup=kb
                )
            except Exception:
                pass
            raise CancelHandler()

        # Si VIP → on laisse passer normalement
        return
