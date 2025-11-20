# vip_topics.py

import os
import json
import requests  # pour appeler l'API Airtable
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot, authorized_users

# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Fichier pour persister les topics (annotations, panneau, etc.)
VIP_TOPICS_FILE = "vip_topics.json"

# Mémoire en RAM :
#   user_id -> {"topic_id": int, "panel_message_id": int, "note": str, "admin_id": int, "admin_name": str, ...}
_user_topics = {}
#   topic_id -> user_id
_topic_to_user = {}

# ====== CONFIG AIRTABLE PRINCIPAL (paiements / VIP / Topic ID) ======
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
# ============================================================

# ====== CONFIG AIRTABLE ANNOTATIONS (nouvelle table) ======
ANNOT_API_KEY = os.getenv("ANNOT_API_KEY") or AIRTABLE_API_KEY
ANNOT_BASE_ID = os.getenv("ANNOT_BASE_ID", BASE_ID)
ANNOT_TABLE_NAME = os.getenv("ANNOT_TABLE_NAME")  # doit être défini pour activer la sync
# =========================================================


def save_vip_topics():
    """
    Sauvegarde _user_topics dans le fichier JSON.
    Sert de persistance locale pour :
      - topic_id (en secours)
      - panel_message_id
      - note
      - admin_id
      - admin_name
    """
    data = {str(user_id): d for user_id, d in _user_topics.items()}
    try:
        with open(VIP_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"[VIP_TOPICS] Sauvegarde JSON : {len(data)} topics enregistrés.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur lors de la sauvegarde JSON : {e}")


def load_vip_topics_from_disk():
    """
    Recharge depuis vip_topics.json UNIQUEMENT les infos d'annotation :
        - panel_message_id
        - note
        - admin_id
        - admin_name
    Sans écraser les topic_id déjà chargés depuis Airtable.
    Si un user_id n'existe pas encore en mémoire, on recrée une entrée propre.
    """
    try:
        with open(VIP_TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        merged = 0

        for user_id_str, d in data.items():
            try:
                user_id = int(user_id_str)
            except Exception:
                continue

            existing = _user_topics.get(user_id)

            if not existing:
                # Cas : JSON connaît ce VIP mais Airtable n'a pas encore été chargé
                existing = {
                    "topic_id": d.get("topic_id"),
                    "panel_message_id": d.get("panel_message_id"),
                    "note": d.get("note", "Aucune note"),
                    "admin_id": d.get("admin_id"),
                    "admin_name": d.get("admin_name", "Aucun"),
                }
            else:
                # On fusionne uniquement les infos d'annotation
                if "panel_message_id" in d:
                    existing["panel_message_id"] = d["panel_message_id"]
                if "note" in d:
                    existing["note"] = d["note"]
                if "admin_id" in d:
                    existing["admin_id"] = d["admin_id"]
                if "admin_name" in d:
                    existing["admin_name"] = d["admin_name"]

            _user_topics[user_id] = existing

            # On complète aussi la map inverse si on connaît le topic_id
            topic_id = existing.get("topic_id")
            if topic_id is not None:
                _topic_to_user[topic_id] = user_id

            merged += 1

        print(f"[VIP_TOPICS] Annotations restaurées depuis JSON pour {merged} VIP(s).")

    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier vip_topics.json à charger (normal si première exécution).")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des annotations depuis JSON : {e}")


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Vérifie / crée le topic VIP pour un utilisateur.
    - Si déjà en mémoire → renvoie le topic existant.
    - Sinon → crée un topic, un panneau de contrôle,
      sauvegarde en JSON + enregistre le Topic ID dans Airtable.
    """
    user_id = user.id
    print(f"[VIP_TOPICS] ensure_topic_for_vip() appelé pour user_id={user_id}")

    # Topic déjà existant pour ce VIP en mémoire
    if user_id in _user_topics:
        topic_id = _user_topics[user_id].get("topic_id")
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
    # Sauvegarde JSON
    save_vip_topics()

    # ===== Enregistrement / mise à jour du Topic ID dans le Airtable principal =====
    try:
        if AIRTABLE_API_KEY and BASE_ID and TABLE_NAME:
            url_base = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
            headers = {
                "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                "Content-Type": "application/json"
            }

            # On cherche la/les lignes correspondant à ce user_id ET Type acces = VIP
            params = {
                "filterByFormula": f"AND({{ID Telegram}} = '{user_id}', {{Type acces}} = 'VIP')"
            }
            r = requests.get(url_base, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            records = r.json().get("records", [])

            if not records:
                # Aucun VIP trouvé pour cet ID → on crée une ligne dédiée au Topic ID
                data = {
                    "fields": {
                        "ID Telegram": str(user_id),
                        "Type acces": "VIP",
                        "Montant": 0,
                        "Contenu": "Création Topic VIP automatique",
                        "Topic ID": str(topic_id),  # en string
                    }
                }
                pr = requests.post(url_base, json=data, headers=headers, timeout=10)
                if pr.status_code not in (200, 201):
                    print(f"[VIP_TOPICS] Erreur POST Topic ID Airtable pour user {user_id}: {pr.text}")
                else:
                    print(f"[VIP_TOPICS] Topic ID {topic_id} CRÉÉ dans Airtable pour user {user_id}")
            else:
                # On met à jour toutes les lignes VIP existantes pour ce user
                for rec in records:
                    rec_id = rec["id"]
                    patch_url = f"{url_base}/{rec_id}"
                    data = {"fields": {"Topic ID": str(topic_id)}}  # en string
                    pr = requests.patch(patch_url, json=data, headers=headers, timeout=10)
                    if pr.status_code not in (200, 201):
                        print(f"[VIP_TOPICS] Erreur PATCH Topic ID Airtable pour user {user_id}: {pr.text}")
                    else:
                        print(f"[VIP_TOPICS] Topic ID {topic_id} enregistré dans Airtable pour user {user_id}")
        else:
            print("[VIP_TOPICS] Variables Airtable manquantes, impossible d'enregistrer Topic ID.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur mise à jour Airtable Topic ID pour user {user_id} : {e}")
    # ====================================================

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
    Ancienne version async de chargement depuis le JSON (plus vraiment utilisée).
    Gardée pour compatibilité éventuelle.
    """
    try:
        with open(VIP_TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for user_id_str, d in data.items():
                if "topic_id" in d:
                    user_id = int(user_id_str)
                    _user_topics[user_id] = d
                    _topic_to_user[d["topic_id"]] = user_id
                    print(f"[VIP_TOPICS] Topic restauré (JSON) : user_id={user_id} -> topic_id={d['topic_id']}")
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier de topics à charger.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des topics (JSON) : {e}")


# --------- NOUVELLE FONCTION : upsert annotation vers Airtable ----------
def upsert_annotation_to_airtable(user_id: int, note: str, admin_name: str = None):
    """
    Recherche une ligne {ID Telegram} = user_id dans ANNOT_TABLE_NAME.
    - Si existe -> PATCH (met à jour Note et Admin)
    - Sinon -> POST (crée une nouvelle ligne)
    Logs explicites pour debug dans Render.
    """
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        print("[VIP_TOPICS] Config Airtable annotations manquante, annotation non synchronisée.")
        return

    url_base = f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {ANNOT_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        # Recherche éventuelle
        params = {"filterByFormula": f"{{ID Telegram}} = '{user_id}'"}
        r = requests.get(url_base, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        records = r.json().get("records", [])

        fields = {"Note": str(note)}
        if admin_name:
            fields["Admin"] = str(admin_name)

        if records:
            # Mettre à jour toutes les lignes correspondantes (normalement 1)
            for rec in records:
                rec_id = rec.get("id")
                patch_url = f"{url_base}/{rec_id}"
                payload = {"fields": fields}
                pr = requests.patch(patch_url, json=payload, headers=headers, timeout=10)
                if pr.status_code not in (200, 201):
                    print(f"[VIP_TOPICS] Erreur PATCH annotation Airtable pour user {user_id}: {pr.text}")
                else:
                    print(f"[VIP_TOPICS] Annotation mise à jour dans Airtable pour user {user_id} (rec {rec_id})")
        else:
            # Créer une ligne si rien trouvé
            payload = {"fields": {"ID Telegram": str(user_id), "Note": str(note)}}
            if admin_name:
                payload["fields"]["Admin"] = str(admin_name)
            pr = requests.post(url_base, json=payload, headers=headers, timeout=10)
            if pr.status_code not in (200, 201):
                print(f"[VIP_TOPICS] Erreur POST annotation Airtable pour user {user_id}: {pr.text}")
            else:
                print(f"[VIP_TOPICS] Annotation CRÉÉE dans Airtable pour user {user_id}")
    except Exception as e:
        print(f"[VIP_TOPICS] Exception lors upsert annotation Airtable pour user {user_id}: {e}")


def update_vip_info(user_id: int, note: str = None, admin_id: int = None, admin_name: str = None):
    """
    Met à jour les infos VIP (note, admin en charge) pour un user_id.
    - Sauvegarde JSON locale (déjà en place)
    - Si note est fournie -> upsert dans la table ANNOT_TABLE_NAME d'Airtable
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
    # Sauvegarde JSON à chaque modification
    save_vip_topics()

    # -> Synchronisation vers Airtable Annotations (si note présente)
    if note is not None:
        # admin_name fallback (si non fourni)
        admin_for_upsert = admin_name or data.get("admin_name") or ""
        try:
            upsert_annotation_to_airtable(user_id=user_id, note=note, admin_name=admin_for_upsert)
        except Exception as e:
            print(f"[VIP_TOPICS] Erreur lors de l'upsert annotation (non critique) : {e}")

    return data


# ========= IMPORT TOPICS DEPUIS AIRTABLE TOPIC ID =========

async def load_vip_topics_from_airtable():
    """
    Charge dans _user_topics et _topic_to_user tous les Topic ID enregistrés dans Airtable
    pour les utilisateurs ayant Type acces = VIP.
    """
    if not (AIRTABLE_API_KEY and BASE_ID and TABLE_NAME):
        print("[VIP_TOPICS] Variables Airtable manquantes, impossible de charger les topics.")
        return

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"filterByFormula": "{Type acces}='VIP'"}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        records = resp.json().get("records", [])

        loaded = 0
        for rec in records:
            f = rec.get("fields", {})
            topic_id = f.get("Topic ID")
            telegram_id = f.get("ID Telegram")

            if not topic_id or not telegram_id:
                continue

            try:
                topic_id_int = int(topic_id)
                telegram_id_int = int(telegram_id)
            except Exception:
                continue

            _user_topics[telegram_id_int] = {
                "topic_id": topic_id_int,
                "panel_message_id": None,
                "note": "Aucune note",
                "admin_id": None,
                "admin_name": "Aucun",
            }
            _topic_to_user[topic_id_int] = telegram_id_int
            loaded += 1

        print(f"[VIP_TOPICS] {loaded} Topic IDs chargés depuis Airtable.")

    except Exception as e:
        print(f"[VIP_TOPICS] Erreur import topics Airtable : {e}")

# ========= FIN IMPORT TOPICS DEPUIS AIRTABLE =========


async def restore_missing_panels():
    """
    Après chargement via Airtable + fusion JSON, recrée un panneau de contrôle
    pour chaque VIP qui a un topic_id mais pas de panel_message_id.
    Utilise la note et l'admin_name si disponibles.
    """
    restored = 0

    for user_id, info in _user_topics.items():
        topic_id = info.get("topic_id")
        panel_message_id = info.get("panel_message_id")

        if not topic_id:
            continue
        if panel_message_id:
            # On suppose que le panneau existe encore
            continue

        note = info.get("note", "Aucune note")
        admin_name = info.get("admin_name", "Aucun")

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
            InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
        )

        panel_text = (
            "🧐 PANEL DE CONTRÔLE VIP\n\n"
            f"👤 Client : {user_id}\n"
            f"📒 Notes : {note}\n"
            f"👤 Admin en charge : {admin_name}"
        )

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
            new_panel_id = panel_res.get("message_id")
            info["panel_message_id"] = new_panel_id
            _user_topics[user_id] = info
            restored += 1
            print(f"[VIP_TOPICS] Panneau restauré pour user_id={user_id} dans topic_id={topic_id}, msg_id={new_panel_id}")
        except Exception as e:
            print(f"[VIP_TOPICS] Erreur restauration panneau de contrôle pour user_id={user_id} : {e}")

    if restored > 0:
        # On persiste les nouveaux panel_message_id
        save_vip_topics()

    print(f"[VIP_TOPICS] Panneaux restaurés pour {restored} VIP(s).")
