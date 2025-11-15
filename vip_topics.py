# vip_topics.py

import os
import json
from typing import Dict, Any, Optional

import requests  # on utilise requests comme pour Airtable
from aiogram import types

from core import bot  # même bot que dans le reste de ton projet

STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
VIP_TOPICS_PATH = os.getenv("VIP_TOPICS_PATH", "vip_topics.json")

# On récupère le token depuis les variables d'environnement
BOT_TOKEN = os.getenv("BOT_TOKEN")

_vip_topics: Dict[str, Dict[str, Any]] = {}


def load_vip_topics():
    """Chargement du mapping user_id -> topic_id au démarrage."""
    global _vip_topics
    try:
        with open(VIP_TOPICS_PATH, "r", encoding="utf-8") as f:
            _vip_topics = json.load(f)
            print(f"[VIP_TOPICS] Chargé {len(_vip_topics)} topics VIP.")
    except FileNotFoundError:
        _vip_topics = {}
        print("[VIP_TOPICS] Aucun fichier trouvé, initialisation vide.")
    except Exception as e:
        _vip_topics = {}
        print(f"[VIP_TOPICS] Erreur chargement : {e}")


def save_vip_topics():
    """Sauvegarde immédiate dès qu'on crée un topic."""
    try:
        with open(VIP_TOPICS_PATH, "w", encoding="utf-8") as f:
            json.dump(_vip_topics, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur sauvegarde : {e}")


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Crée ou récupère le topic VIP de ce user dans le supergroupe staff,
    via l'API HTTP Telegram (compatible Aiogram 2).
    """
    uid = str(user.id)
    entry = _vip_topics.get(uid, {})

    # Si un topic existe déjà → on le renvoie
    if entry.get("topic_id"):
        return entry["topic_id"]

    if STAFF_GROUP_ID == 0:
        raise RuntimeError("[VIP_TOPICS] STAFF_GROUP_ID n'est pas configuré")

    if not BOT_TOKEN:
        raise RuntimeError("[VIP_TOPICS] BOT_TOKEN n'est pas configuré")

    topic_title = f"VIP {user.username or user.first_name} ({uid})"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createForumTopic"
    payload = {
        "chat_id": STAFF_GROUP_ID,
        "name": topic_title
    }

    try:
        r = requests.post(url, data=payload, timeout=10)
        data = r.json()
    except Exception as e:
        raise RuntimeError(f"[VIP_TOPICS] Requête HTTP vers Telegram échouée : {e}")

    if not data.get("ok"):
        # On loggue la réponse brute pour debug
        raise RuntimeError(f"[VIP_TOPICS] Erreur Telegram createForumTopic: {data}")

    topic_id = data["result"]["message_thread_id"]

    entry.update({
        "topic_id": topic_id,
        "username": user.username or "",
    })
    _vip_topics[uid] = entry
    save_vip_topics()

    print(f"[VIP_TOPICS] Nouveau topic créé pour {uid} → {topic_id}")
    return topic_id


def get_user_id_by_topic_id(topic_id: int) -> Optional[int]:
    """
    Permet de retrouver l'user_id à partir d'un topic_id (si besoin plus tard).
    """
    for uid, data in _vip_topics.items():
        if data.get("topic_id") == topic_id:
            return int(uid)
    return None
