from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list  # Import de la ban_list

import asyncio
import time  # pour la fenêtre glissante
import os


# Ces IDs DOIVENT être les mêmes que dans bott_webhook / Render
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))          # Admin vendeur (instance)
DIRECTEUR_ID = int(os.getenv("DIRECTEUR_ID", "0"))  # Toi (si tu veux être exclu aussi)
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))  # Supergroupe staff / topics


# ✅ Liste d'IDs qui ne doivent JAMAIS être limités par les 5 messages gratuits
EXCLUDED_IDS = {
    ADMIN_ID,
    DIRECTEUR_ID,
    7334072965,   # Ton ID perso (Nathan) → adapte si besoin
    7334072965,   # ID de l'admin vendeur spécifique à ce bot → garde-le si utile
}


# Boutons de ton ReplyKeyboard qui NE doivent PAS être comptés comme messages gratuits
BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour... tout en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# ===== Paramètres "messages gratuits" =====
FREE_MSGS_LIMIT = 5                          # nombre de messages gratuits
FREE_MSGS_WINDOW_SECONDS = 24 * 3600         # fenêtre glissante de 24h
SHOW_REMAINING_HINT = True                   # afficher "X/5 utilisés" au fil de l'eau
free_msgs_state = {}                         # user_id -> {"count": int, "window_start": float, "last": float}

# Lien VIP (existant)
VIP_URL = "https://buy.stripe.com/5kQ9AS60J2ET9wxfi57AI0W"

# ===== Anti-doublon par message =====
# clé = (chat_id, message_id) → timestamp
_processed_keys = {}
_PROCESSED_TTL = 60  # secondes


def _prune_processed(now: float):
    # Nettoyage simple pour éviter l'accumulation en mémoire
    for k, ts in list(_processed_keys.items()):
        if now - ts > _PROCESSED_TTL:
            del _processed_keys[k]


# Helper : à appeler quand un user devient VIP pour nettoyer son compteur
def reset_free_quota(user_id: int):
    free_msgs_state.pop(user_id, None)


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        chat = message.chat

        # DEBUG (facultatif, mais utile)
        print(
            f"[PAYMENT_MW] from user_id={user_id}, chat_id={chat.id}, "
            f"chat_type={chat.type}, ADMIN_ID={ADMIN_ID}, "
            f"DIRECTEUR_ID={DIRECTEUR_ID}, EXCLUDED_IDS={EXCLUDED_IDS}"
        )

        # 0) Staff / admins exclus de TOUT quota
        if user_id in EXCLUDED_IDS:
            return

        # 1) Le filtre "5 messages" NE s'applique QUE dans les MP client ↔ bot
        #    → groupes / supergroupes / topics = ignorés
        if chat.type != "private":
            return

        # 2) Anti-doublon par message
        now = time.time()
        _prune_processed(now)
        key = (chat.id, message.message_id)
        if key in _processed_keys:
            return
        _processed_keys[key] = now

        # 3) Bannis → suppression + message d’info
        for admin_id, clients_bannis in ban_list.items():
            if user_id in clients_bannis:
                try:
                    await message.delete()
                except Exception as e:
                    print(f"Erreur suppression message banni : {e}")
                try:
                    await message.answer("🚫 Tu as été banni, tu ne peux plus envoyer de messages.")
                except Exception as e:
                    print(f"Erreur envoi message banni : {e}")
                raise CancelHandler()

        # 4) Si ce n’est pas du texte → on ne compte pas (pas de quota sur les médias)
        if message.content_type != types.ContentType.TEXT:
            return

        text = (message.text or "").strip()

        # 5) Autoriser /start
        if text.startswith("/start"):
            return

        # 6) Autoriser les boutons prédéfinis (ReplyKeyboard)
        for b in BOUTONS_AUTORISES:
            if text.startswith(b):
                return

        # 7) VIP → aucune limite
        if user_id in self.authorized_users:
            return

        # =========================
        # 🚫 NON-VIP EN MP :
        #    5 messages gratuits / 24h, puis paywall VIP
        # =========================
        state = free_msgs_state.get(user_id)

        # Reset si première fois OU fenêtre expirée
        if (not state) or (now - state.get("window_start", 0) > FREE_MSGS_WINDOW_SECONDS):
            state = {"count": 0, "window_start": now}

        # Incrémenter pour CE message
        state["count"] += 1
        state["last"] = now
        free_msgs_state[user_id] = state

        if state["count"] <= FREE_MSGS_LIMIT:
            # Petit rappel "X/5"
            if SHOW_REMAINING_HINT:
                remaining = FREE_MSGS_LIMIT - state["count"]
                hint = (
                    f"💬 Messages gratuits utilisés ({state['count']}/{FREE_MSGS_LIMIT})."
                    f"{' Il t’en reste ' + str(remaining) + '.' if remaining > 0 else ' Tu viens d’utiliser le dernier 😉'}"
                )
                asyncio.create_task(
                    message.bot.send_message(
                        chat_id=chat.id,
                        text=hint,
                        reply_to_message_id=message.message_id
                    )
                )
            # laisser passer vers les handlers normaux
            return

        # Quota dépassé → push VIP + blocage
        pay_kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("💎 Deviens VIP", url=VIP_URL)
        )
        await message.bot.send_message(
            chat_id=chat.id,
            text=(
                "🚪 Tu as utilisé tes 5 messages gratuits.\n"
                "Pour continuer à discuter librement et recevoir des réponses prioritaires, "
                "rejoins mon VIP 💕."
            ),
            reply_markup=pay_kb
        )
        raise CancelHandler()
