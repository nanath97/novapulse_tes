# vip_topics.py

import os
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
    - Sinon, on crée un nouveau topic, on enregistre le mapping,
      puis on envoie un panneau de contrôle dans ce topic.
    """
    user_id = user.id

    # Si on a déjà un topic en mémoire, on le renvoie
    if user_id in _user_to_topic:
        topic_id = _user_to_topic[user_id]
        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return topic_id

    if not STAFF_GROUP_ID:
        raise RuntimeError("[VIP_TOPICS] STAFF_GROUP_ID est 0 ou non défini dans les variables d'environnement.")

    # Nom du topic : VIP + pseudo ou prénom
    title = f"VIP {user.username or user.first_name or str(user_id)}"
    print(f"[VIP_TOPICS] Création d'un nouveau topic pour {user_id} dans {STAFF_GROUP_ID} avec le nom '{title}'")

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

    # 🔹 Envoi du panneau de contrôle dans le topic (boutons figés)
    try:
        await _send_control_panel_for_topic(topic_id, user)
        print(f"[VIP_TOPICS] Panneau de contrôle envoyé dans le topic {topic_id} pour {user_id}")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")

    return topic_id


async def _send_control_panel_for_topic(topic_id: int, user: types.User):
    """
    Envoie un message fixe dans le topic avec les boutons :
    - ✅ Prendre en charge
    - 📝 Prendre une note
    Ce message reste dans le topic et peut être épinglé par le vendeur.
    """
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user.id}"),
        InlineKeyboardButton("📝 Prendre une note", callback_data=f"annoter_{user.id}")
    )

    texte = "🧩 Panneau de contrôle pour ce client\n"
    texte += f"👤 ID : {user.id}\n"
    if user.username:
        texte += f"🔹 Pseudo : @{user.username}"

    payload = {
        "chat_id": STAFF_GROUP_ID,
        "message_thread_id": topic_id,   # ⬅️ on force l’envoi DANS le topic
        "text": texte,
        "reply_markup": kb.to_python(),  # ⬅️ on sérialise le clavier pour l'API brute
    }

    # Appel brut à l’API Telegram pour contourner la limite d’aiogram 2
    await bot.request("sendMessage", payload)
