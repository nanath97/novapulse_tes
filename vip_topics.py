# vip_topics.py

import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot
from bott_webhook import authorized_users




# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Mémoire en RAM :
#   user_id -> {"topic_id": int, "panel_message_id": int}
_user_topics = {}
#   topic_id -> user_id
_topic_to_user = {}


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Garantit qu'un VIP possède un topic dédié dans STAFF_GROUP_ID.
    - Si le topic existe déjà, renvoie son ID.
    - Sinon, crée un topic + envoie un panneau de contrôle avec les boutons.
    """
    user_id = user.id
    print(f"[VIP_TOPICS] ensure_topic_for_vip() appelé pour user_id={user_id}")

    # Si on a déjà un topic connu en mémoire → on le renvoie
    if user_id in _user_topics:
        topic_id = _user_topics[user_id]["topic_id"]
        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return topic_id

    title = f"VIP {user.username or user.first_name or str(user_id)}"

    # 1) Créer le topic via l'API brute (aiogram.request)
    try:
        res = await bot.request(
            "createForumTopic",
            {
                "chat_id": STAFF_GROUP_ID,
                "name": title
            }
        )
    except Exception as e:
        print(f"[VIP_TOPICS] ERREUR createForumTopic pour {user_id} : {e}")
        # On ne bloque pas /start, on renvoie une valeur bidon
        return 0

    topic_id = res.get("message_thread_id")
    if topic_id is None:
        print(f"[VIP_TOPICS] Pas de message_thread_id dans la réponse pour {user_id} : {res}")
        return 0

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} dans {STAFF_GROUP_ID} -> topic_id={topic_id}")

    _topic_to_user[topic_id] = user_id

    # 2) Créer le panneau de contrôle AVEC boutons dans ce topic
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

    panel_message_id = None
    try:
        panel_res = await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "text": panel_text,
                "message_thread_id": topic_id,
                # On passe directement l'objet kb, aiogram sait le sérialiser
                "reply_markup": kb
            }
        )
        panel_message_id = panel_res.get("message_id")
        print(f"[VIP_TOPICS] Panneau de contrôle envoyé pour {user_id} → msg_id={panel_message_id}")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")

    # 3) Mémoriser topic + panneau
    _user_topics[user_id] = {
        "topic_id": topic_id,
        "panel_message_id": panel_message_id
    }

    return topic_id


def is_vip(user_id: int) -> bool:
    """
    True si on a déjà un topic pour ce user_id (en mémoire).
    ATTENTION : c'est de la RAM, donc perdu à chaque restart.
    """
    return user_id in _user_topics


def get_user_id_by_topic_id(topic_id: int):
    """
    Permet au bot de retrouver le client associé à un topic staff.
    Utilisé quand l'admin parle dans un topic.
    """
    return _topic_to_user.get(topic_id)


def get_panel_message_id_by_user(user_id: int):
    """
    Retourne l'ID du message 'panneau de contrôle' pour ce client (si existant).
    """
    data = _user_topics.get(user_id)
    if not data:
        return None
    return data.get("panel_message_id")
