# vip_topics.py

import os
import json
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot
from bott_webhook import authorized_users

# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Fichier pour persister les topics
VIP_TOPICS_FILE = "vip_topics.json"

# Mémoire en RAM :
#   user_id -> {"topic_id": int, "panel_message_id": int, "note": str, "admin_id": int, "admin_name": str, ...}
_user_topics = {}
#   topic_id -> user_id
_topic_to_user = {}


def save_vip_topics():
    """
    Sauvegarde _user_topics tel quel dans le fichier JSON.
    On ne jette plus les champs (note, admin_id, admin_name, etc.).
    """
    data = {str(user_id): d for user_id, d in _user_topics.items()}
    try:
        with open(VIP_TOPICS_FILE, "w") as f:
            json.dump(data, f)
        print(f"[VIP_TOPICS] Sauvegarde : {len(data)} topics enregistrés.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur lors de la sauvegarde : {e}")


def load_vip_topics_from_disk():
    """
    Ancienne fonction de chargement, gardée si tu l'utilises ailleurs.
    """
    try:
        with open(VIP_TOPICS_FILE, "r") as f:
            data = json.load(f)
            for user_id_str, d in data.items():
                user_id = int(user_id_str)
                _user_topics[user_id] = d
                if "topic_id" in d:
                    _topic_to_user[d["topic_id"]] = user_id
        print(f"[VIP_TOPICS] Chargement : {len(_user_topics)} topics rechargés depuis le fichier.")
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier de topics à charger.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des topics : {e}")


async def ensure_topic_for_vip(user: types.User) -> int:
    user_id = user.id
    print(f"[VIP_TOPICS] ensure_topic_for_vip() appelé pour user_id={user_id}")

    # Topic déjà existant pour ce VIP
    if user_id in _user_topics:
        topic_id = _user_topics[user_id]["topic_id"]
        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return topic_id

    title = f"VIP {user.username or user.first_name or str(user_id)}"

    # Création du topic dans le forum staff
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
        return 0

    topic_id = res.get("message_thread_id")
    if topic_id is None:
        print(f"[VIP_TOPICS] Pas de message_thread_id dans la réponse pour {user_id} : {res}")
        return 0

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} dans {STAFF_GROUP_ID} -> topic_id={topic_id}")

    _topic_to_user[topic_id] = user_id

    # Clavier du panneau de contrôle
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
    )

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
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
                "reply_markup": kb
            }
        )
        panel_message_id = panel_res.get("message_id")
        print(f"[VIP_TOPICS] Panneau de contrôle envoyé pour {user_id} → msg_id={panel_message_id}")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")

    # On initialise l'entrée avec topic + panneau, sans note ni admin pour l'instant
    _user_topics[user_id] = {
        "topic_id": topic_id,
        "panel_message_id": panel_message_id,
        "note": "Aucune note",
        "admin_id": None,
        "admin_name": "Aucun",
    }
    save_vip_topics()

    return topic_id


def is_vip(user_id: int) -> bool:
    return user_id in _user_topics


def get_user_id_by_topic_id(topic_id: int):
    return _topic_to_user.get(topic_id)


def get_panel_message_id_by_user(user_id: int):
    data = _user_topics.get(user_id)
    if not data:
        return None
    return data.get("panel_message_id")


async def load_vip_topics():
    """
    Autre fonction de chargement (version async) si tu la uses au démarrage.
    """
    try:
        with open(VIP_TOPICS_FILE, "r") as f:
            data = json.load(f)
            for user_id_str, d in data.items():
                if "topic_id" in d:
                    user_id = int(user_id_str)
                    _user_topics[user_id] = d
                    _topic_to_user[d["topic_id"]] = user_id
                    print(f"[VIP_TOPICS] Topic restauré : user_id={user_id} -> topic_id={d['topic_id']}")
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier de topics à charger.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des topics : {e}")


def update_vip_info(user_id: int, note: str = None, admin_id: int = None, admin_name: str = None):
    """
    Met à jour les infos VIP (note, admin en charge) pour un user_id.
    Retourne le dict complet pour ce user_id.
    """
    if user_id not in _user_topics:
        _user_topics[user_id] = {}

    data = _user_topics[user_id]

    if note is not None:
        data["note"] = note

    if admin_id is not None:
        data["admin_id"] = admin_id

    if admin_name is not None:
        data["admin_name"] = admin_name

    _user_topics[user_id] = data
    save_vip_topics()
    return data
