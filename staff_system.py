# staff_system.py

import json
import os
import requests  # ✅ pour appeler directement l’API Telegram en HTTP
from aiogram import types
from core import dp, bot, authorized_users

# ==========================
# CONFIGURATION
# ==========================

# Active/désactive la feature staff via ENV, par défaut : true
STAFF_FEATURE_ENABLED = os.getenv("STAFF_FEATURE_ENABLED", "true").lower() == "true"

# ID du groupe forum staff (on le lit en priorité depuis l'ENV)
# Si non défini dans l'ENV, on retombe sur la valeur en dur que tu as mise
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "-1003418175247"))

# Token du bot pour appeler l'API HTTP Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("[staff_system] ⚠️ BOT_TOKEN manquant dans les variables d'environnement. "
          "Les créations de topics échoueront.")

# Fichier pour stocker les correspondances utilisateur ↔ topic
TOPIC_MAP_FILE = "staff_topics.json"
_map = {}

# Charger les topics existants depuis fichier
if os.path.exists(TOPIC_MAP_FILE):
    try:
        with open(TOPIC_MAP_FILE, "r", encoding="utf-8") as f:
            _map = json.load(f)
    except Exception as e:
        print(f"[staff_system] ⚠️ Erreur chargement {TOPIC_MAP_FILE} : {e}")
        _map = {}


def save_topic_map():
    """Sauvegarde la correspondance user_id ↔ thread_id sur disque."""
    try:
        with open(TOPIC_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[staff_system] ⚠️ Erreur sauvegarde {TOPIC_MAP_FILE} : {e}")


# ==========================
# CRÉATION DU TOPIC VIA API HTTP
# ==========================

async def ensure_topic_for(bot, user_id, username="", email="", total_spent=0.0):
    """
    Garantit qu'un topic existe pour ce user_id dans le groupe staff.
    Si déjà enregistré dans _map, ne fait rien.
    Sinon, utilise l'API HTTP `createForumTopic` (compatible aiogram 2.x).
    """
    global _map

    # Staff désactivé → on ne fait rien
    if not STAFF_FEATURE_ENABLED:
        return

    # Si déjà connu, on ne recrée pas
    if str(user_id) in _map:
        return

    if not BOT_TOKEN:
        print(f"[staff_system] ⚠️ BOT_TOKEN manquant, impossible de créer un topic pour {user_id}.")
        return

    # Nom du topic
    thread_name = f"{username or user_id} – VIP"
    if total_spent and total_spent > 0:
        thread_name += f" ({int(total_spent)}€)"

    # Appel brut à l’API Telegram (pas besoin de aiogram 3)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/createForumTopic"
    payload = {
        "chat_id": STAFF_GROUP_ID,
        "name": thread_name
    }

    try:
        resp = requests.post(url, json=payload)
        data = resp.json()

        if not data.get("ok"):
            print(f"[staff_system] Erreur API createForumTopic pour {user_id} : {data}")
            return

        # Récupération du message_thread_id
        result = data.get("result", {})
        thread_id = result.get("message_thread_id")

        if thread_id is None:
            print(f"[staff_system] ⚠️ Pas de message_thread_id dans la réponse pour {user_id} : {data}")
            return

        _map[str(user_id)] = {
            "thread_id": thread_id,
            "owner_id": user_id,
            "username": username,
            "email": email,
            "total_spent": float(total_spent or 0.0),
        }
        save_topic_map()
        print(f"[staff_system] ✅ Topic créé pour {user_id} (thread_id={thread_id})")

    except Exception as e:
        print(f"[staff_system] Erreur création topic pour {user_id} : {e}")


# ==========================
# MIRROIR CLIENT → STAFF
# ==========================

async def mirror_client_to_staff(bot, message: types.Message):
    """
    Copie le message privé d’un client VIP vers son topic staff.
    """
    if not STAFF_FEATURE_ENABLED or message.chat.type != "private":
        return

    user_id = message.from_user.id

    # Si pas de topic connu, on en crée un automatiquement
    if str(user_id) not in _map:
        await ensure_topic_for(
            bot,
            user_id=user_id,
            username=message.from_user.username or message.from_user.first_name,
            email="",
            total_spent=0.0
        )

    # Si après tentative de création il n'y a toujours pas de topic, on arrête
    if str(user_id) not in _map:
        print(f"[staff_system] ⚠️ Aucun topic disponible pour {user_id}, message non copié.")
        return

    thread_id = _map[str(user_id)]["thread_id"]

    try:
        await bot.copy_message(
            chat_id=STAFF_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
        print(f"[staff_system] ✅ Message de {user_id} copié vers topic {thread_id}")
    except Exception as e:
        print(f"[staff_system] Erreur copie message VIP vers topic : {e}")


# ==========================
# RÉPONSE STAFF → CLIENT
# ==========================

@dp.message_handler(
    lambda m: m.chat.id == STAFF_GROUP_ID and getattr(m, "message_thread_id", None) is not None,
    content_types=types.ContentTypes.ANY
)
async def _outbound(m: types.Message):
    """
    Tout message envoyé dans un topic staff est renvoyé au client associé.
    """
    try:
        thread_id = m.message_thread_id

        # On cherche quel user_id correspond à ce thread_id dans le _map
        for uid, val in _map.items():
            if val.get("thread_id") == thread_id:
                user_id = int(uid)
                await m.send_copy(chat_id=user_id)
                print(f"[staff_system] ✅ Réponse staff depuis topic {thread_id} envoyée à {user_id}")
                break
        else:
            print(f"[staff_system] ⚠️ Aucun user associé au thread_id {thread_id}")

    except Exception as e:
        print(f"[staff_system] Erreur retour vers client : {e}")
