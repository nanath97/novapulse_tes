# vip_topics.py

import os
from aiogram import types
from core import bot

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
        return _user_to_topic[user_id]

    # Nom du topic : VIP + pseudo ou prénom
    title = f"VIP {user.username or user.first_name or str(user_id)}"

    # Appel brut à l'API Telegram pour créer le topic
    res = await bot.request(
        "createForumTopic",
        {
            "chat_id": STAFF_GROUP_ID,
            "name": title
        }
    )

    # Telegram renvoie message_thread_id pour identifier le topic
    topic_id = res.get("message_thread_id")
    if topic_id is None:
        raise RuntimeError(f"[VIP_TOPICS] Impossible de créer un topic pour {user_id} : {res}")

    # On mémorise les deux sens
    _user_to_topic[user_id] = topic_id
    _topic_to_user[topic_id] = user_id

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} → {topic_id}")
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
