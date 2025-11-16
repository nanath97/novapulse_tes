# vip_topics.py

import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot

# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Mémoire en RAM :
# user_id -> {"topic_id": int, "panel_message_id": int}
_user_topics = {}
# topic_id -> user_id
_topic_to_user = {}


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Garantit qu'un VIP possède un topic dédié dans le STAFF_GROUP_ID.
    - Si le topic existe déjà, on renvoie juste son ID.
    - Sinon, on crée un nouveau topic ET on envoie un panneau de contrôle
      avec les boutons 'Prendre en charge' et 'Ajouter une note', puis
      on mémorise aussi l'ID de ce panneau.
    """
    user_id = user.id

    # Si on a déjà un topic en mémoire, on le renvoie
    if user_id in _user_topics:
        return _user_topics[user_id]["topic_id"]

    title = f"VIP {user.username or user.first_name or str(user_id)}"

    # 1) Créer le topic
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

    print(f"[VIP_TOPICS] Création d'un nouveau topic pour {user_id} dans {STAFF_GROUP_ID} avec le nom '{title}'")
    _topic_to_user[topic_id] = user_id

    # 2) Envoyer le panneau de contrôle dans ce topic, AVEC BOUTONS
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
    )

    panel_text = (
        "🧠 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {user.username or user.first_name or str(user_id)}\n"
        "📒 Notes : Aucune note\n"
        "👤 Admin en charge : Aucun"
    )

    try:
        panel_res = await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "text": panel_text,
                "message_thread_id": topic_id,
                "reply_markup": kb.to_python()
            }
        )
        panel_message_id = panel_res.get("message_id")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")
        panel_message_id = None

    # 3) Mémoriser topic + panneau
    _user_topics[user_id] = {
        "topic_id": topic_id,
        "panel_message_id": panel_message_id
    }

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} → {topic_id}")
    return topic_id


def is_vip(user_id: int) -> bool:
    """True si on a déjà un topic pour ce user_id (en mémoire)."""
    return user_id in _user_topics


def get_user_id_by_topic_id(topic_id: int):
    """Retrouver le client associé à un topic staff."""
    return _topic_to_user.get(topic_id)


def get_panel_message_id_by_user(user_id: int):
    """Retourne l'ID du message 'panneau de contrôle' pour ce client (si existant)."""
    data = _user_topics.get(user_id)
    if not data:
        return None
    return data.get("panel_message_id")
