# vip_topics.py
import os, json
from typing import Optional, Dict, Any
from core import bot  # ton Bot aiogram
from aiogram import types

STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
VIP_TOPICS_PATH = os.getenv("VIP_TOPICS_PATH", "vip_topics.json")

_vip_topics: Dict[str, Dict[str, Any]] = {}  # "user_id": {"topic_id": int, "username": str}


def load_vip_topics():
    global _vip_topics
    try:
        with open(VIP_TOPICS_PATH, "r", encoding="utf-8") as f:
            _vip_topics = json.load(f)
    except FileNotFoundError:
        _vip_topics = {}
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur chargement : {e}")
        _vip_topics = {}


def save_vip_topics():
    try:
        with open(VIP_TOPICS_PATH, "w", encoding="utf-8") as f:
            json.dump(_vip_topics, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur sauvegarde : {e}")


async def ensure_topic_for_vip(user: types.User) -> int:
    uid = str(user.id)
    entry = _vip_topics.get(uid, {})
    if "topic_id" in entry and entry["topic_id"]:
        return entry["topic_id"]

    # 🔹 Créer un topic forum dans ton supergroupe staff
    topic_title = f"VIP {user.username or user.first_name} ({uid})"
    topic = await bot.create_forum_topic(chat_id=STAFF_GROUP_ID, name=topic_title)

    topic_id = topic.message_thread_id
    entry.update({
        "topic_id": topic_id,
        "username": user.username or "",
    })
    _vip_topics[uid] = entry
    save_vip_topics()
    return topic_id


def get_user_id_by_topic_id(topic_id: int) -> Optional[int]:
    for uid, data in _vip_topics.items():
        if data.get("topic_id") == topic_id:
            return int(uid)
    return None
