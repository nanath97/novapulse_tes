# vip_topics.py

import os
from aiogram import types
from core import bot  # pas besoin de dp ici
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Mémoire en RAM : user_id -> topic_id et topic_id -> user_id
_user_to_topic = {}
_topic_to_user = {}


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Garantit qu'un VIP possède un topic dédié dans le STAFF_GROUP_ID.
    - Si le topic existe déjà, on renvoie juste son ID.
    - Sinon, on crée un nouveau topic et on enregistre le mapping.
    """
    user_id = user.id

    # Si on a déjà un topic en mémoire, on le renvoie
    if user_id in _user_to_topic:
        topic_id = _user_to_topic[user_id]
        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return topic_id

    # Nom du topic : VIP + pseudo ou prénom
    title = f"VIP {user.username or user.first_name or str(user_id)}"

    print(f"[VIP_TOPICS] Création d'un nouveau topic pour {user_id} dans {STAFF_GROUP_ID} avec le nom '{title}'")

    # Appel brut à l'API Telegram pour créer le topic (forum)
    res = await bot.request(
        "createForumTopic",
        {
            "chat_id": STAFF_GROUP_ID,
            "name": title
        }
    )

    topic_id = res.get("message_thread_id")
    if topic_id is None:
        raise RuntimeError(f"[VIP_TOPICS] Impossible de créer un topic pour {user_id} : {res}")

    # On mémorise les deux sens
    _user_to_topic[user_id] = topic_id
    _topic_to_user[topic_id] = user_id

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} → {topic_id}")

    # 🔹 Panneau de contrôle figé en haut du topic
    try:
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton(
                "✅ Prendre en charge",
                callback_data=f"prendre_{user_id}"
            ),
            InlineKeyboardButton(
                "📝 Prendre une note",
                callback_data=f"annoter_{user_id}"
            )
        )

        # IMPORTANT : on passe par l’API brute pour pouvoir utiliser message_thread_id
        await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": (
                    "📌 *Panneau de contrôle de ce client VIP*\n\n"
                    "• Utilise `✅ Prendre en charge` pour t'assigner ce client.\n"
                    "• Utilise `📝 Prendre une note` pour ajouter des infos sur lui.\n"
                ),
                "parse_mode": "Markdown",
                "reply_markup": kb.to_python()
            }
        )
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")

    return topic_id


def is_vip(user_id: int) -> bool:
    """
    Retourne True si on a déjà un topic pour ce user_id.
    (Attention : ça teste juste la présence en mémoire, pas Airtable.)
    """
    return user_id in _user_to_topic


def get_user_id_by_topic_id(topic_id: int):
    """
    Permet au bot de retrouver le client associé à un topic staff.
    Utilisé dans bott_webhook quand l'admin parle dans un topic.
    """
    return _topic_to_user.get(topic_id)
