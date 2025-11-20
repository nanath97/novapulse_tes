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
            json.dump(data, f, ensure_ascii=False)
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
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier vip_topics.json à charger (normal si première exécution).")
        return
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des annotations depuis JSON : {e}")
        return

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
            if "panel_message_id" in d and d.get("panel_message_id") is not None:
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
            try:
                _topic_to_user[int(topic_id)] = user_id
            except Exception:
                pass

        merged += 1

    print(f"[VIP_TOPICS] Annotations restaurées depuis JSON pour {merged} VIP(s).")


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

    _topic_to_user[int(topic_id)] = user_id

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
        "topic_id": int(topic_id),
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
                    print(f"[VIP_TOPICS] Erreur POST Topic ID Airtable pour user {user_id}: {pr.status_code} {pr.text}")
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
                        print(f"[VIP_TOPICS] Erreur PATCH Topic ID Airtable pour user {user_id}: {pr.status_code} {pr.text}")
                    else:
                        print(f"[VIP_TOPICS] Topic ID {topic_id} enregistré dans Airtable pour user {user_id}")
        else:
            print("[VIP_TOPICS] Variables Airtable manquantes, impossible d'enregistrer Topic ID.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur mise à jour Airtable Topic ID pour user {user_id} : {e}")
    # ====================================================

    return int(topic_id)


def is_vip(user_id: int) -> bool:
    return user_id in _user_topics


def get_user_id_by_topic_id(topic_id: int):
    return _topic_to_user.get(int(topic_id))


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
                    _topic_to_user[int(d["topic_id"])] = user_id
                    print(f"[VIP_TOPICS] Topic restauré (JSON) : user_id={user_id} -> topic_id={d['topic_id']}")
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier de topics à charger.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des topics (JSON) : {e}")


def _find_annotation_record_for_user(user_id: int):
    """
    Cherche dans la table AnnotationsVIP une ligne correspondant à ID Telegram = user_id.
    Retourne l'ID de record Airtable si trouvé, sinon None.
    """
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        return None

    try:
        url = f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"
        headers = {"Authorization": f"Bearer {ANNOT_API_KEY}"}
        params = {"filterByFormula": f"{{ID Telegram}} = '{user_id}'"}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        records = r.json().get("records", [])
        if not records:
            return None
        # On prend la première ligne correspondante
        return records[0]["id"]
    except Exception as e:
        print(f"[ANNOTATION] Erreur recherche record annotation pour {user_id}: {e}")
        return None


def _upsert_annotation_to_airtable(user_id: int, note: str = None, admin_name: str = None):
    """
    Upsert simple : si un record existe pour cet user dans ANNOT_TABLE_NAME -> PATCH, sinon POST.
    """
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        # Pas de configuration, on skip proprement
        return False

    try:
        url = f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {ANNOT_API_KEY}",
            "Content-Type": "application/json"
        }

        rec_id = _find_annotation_record_for_user(user_id)
        fields = {"ID Telegram": str(user_id)}
        if note is not None:
            fields["Note"] = str(note)
        if admin_name is not None:
            fields["Admin"] = str(admin_name)

        data = {"fields": fields}

        if rec_id:
            # PATCH
            patch_url = f"{url}/{rec_id}"
            r = requests.patch(patch_url, json=data, headers=headers, timeout=10)
            if r.status_code not in (200, 201):
                print(f"[ANNOTATION] Erreur PATCH annotation pour {user_id}: {r.status_code} {r.text}")
                return False
            print(f"[ANNOTATION] Annotation mise à jour pour {user_id} (record {rec_id}).")
            return True
        else:
            r = requests.post(url, json=data, headers=headers, timeout=10)
            if r.status_code not in (200, 201):
                print(f"[ANNOTATION] Erreur POST annotation pour {user_id}: {r.status_code} {r.text}")
                return False
            print(f"[ANNOTATION] Annotation CRÉÉE pour {user_id}.")
            return True
    except Exception as e:
        print(f"[ANNOTATION] Exception upsert annotation pour {user_id}: {e}")
        return False


def update_vip_info(user_id: int, note: str = None, admin_id: int = None, admin_name: str = None):
    """
    Met à jour les infos VIP (note, admin en charge) pour un user_id.
    Retourne le dict complet pour ce user_id.
    """
    if user_id not in _user_topics:
        # pré-structure minimale
        _user_topics[user_id] = {
            "topic_id": None,
            "panel_message_id": None,
            "note": "Aucune note",
            "admin_id": None,
            "admin_name": "Aucun",
        }

    data = _user_topics[user_id]

    changed = False

    if note is not None and note != data.get("note"):
        data["note"] = note
        changed = True

    if admin_id is not None and admin_id != data.get("admin_id"):
        data["admin_id"] = admin_id
        changed = True

    if admin_name is not None and admin_name != data.get("admin_name"):
        data["admin_name"] = admin_name
        changed = True

    _user_topics[user_id] = data

    # Si on a des changements, on persiste localement et dans ANNOT table
    if changed:
        save_vip_topics()
        # push vers la table AnnotationsVIP si configurée (note + admin_name)
        try:
            _upsert_annotation_to_airtable(user_id, note=data.get("note"), admin_name=data.get("admin_name"))
        except Exception as e:
            print(f"[ANNOTATION] Erreur lors de l'upsert depuis update_vip_info: {e}")

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

            # Si une entrée existe déjà (ex: data loaded from JSON), on ne perd rien : on merge le topic_id
            existing = _user_topics.get(telegram_id_int, {})
            existing["topic_id"] = topic_id_int
            existing.setdefault("panel_message_id", existing.get("panel_message_id"))
            existing.setdefault("note", existing.get("note", "Aucune note"))
            existing.setdefault("admin_id", existing.get("admin_id"))
            existing.setdefault("admin_name", existing.get("admin_name", "Aucun"))
            _user_topics[telegram_id_int] = existing
            _topic_to_user[topic_id_int] = telegram_id_int
            loaded += 1

        print(f"[VIP_TOPICS] {loaded} Topic IDs chargés depuis Airtable.")

    except Exception as e:
        print(f"[VIP_TOPICS] Erreur import topics Airtable : {e}")


# ========= IMPORT ANNOTATIONS DEPUIS AIRTABLE (nouvelle table) =========
def load_annotations_from_airtable():
    """
    Charge les annotations (Note, Admin) depuis la table ANNOT_TABLE_NAME et merge dans _user_topics.
    Cette fonction est synchrone et doit être appelée pendant le startup (avant restore_missing_panels).
    """
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        print("[ANNOTATION] Variables ANNOT Airtable non configurées — skip.")
        return

    url = f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"
    headers = {"Authorization": f"Bearer {ANNOT_API_KEY}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        records = resp.json().get("records", [])

        loaded = 0
        for rec in records:
            f = rec.get("fields", {})
            telegram_id = f.get("ID Telegram")
            note = f.get("Note")
            admin = f.get("Admin")

            if not telegram_id:
                continue
            try:
                tid = int(telegram_id)
            except Exception:
                continue

            existing = _user_topics.get(tid, {})
            # Merge annotations (note/admin). On ne touche pas au topic_id ici.
            if note is not None:
                existing["note"] = str(note)
            if admin is not None:
                existing["admin_name"] = str(admin)
            # Ensure minimal keys
            existing.setdefault("topic_id", existing.get("topic_id"))
            existing.setdefault("panel_message_id", existing.get("panel_message_id"))
            existing.setdefault("admin_id", existing.get("admin_id"))
            _user_topics[tid] = existing
            loaded += 1

        print(f"[ANNOTATION] {loaded} annotations chargées depuis la table {ANNOT_TABLE_NAME}.")

        # After merging annotations, persist to local JSON so restore_missing_panels can use them
        if loaded > 0:
            save_vip_topics()

    except Exception as e:
        print(f"[ANNOTATION] Erreur chargement annotations Airtable : {e}")


# ========= FIN IMPORT ANNOTATIONS =========


async def restore_missing_panels():
    """
    Après chargement via Airtable + fusion JSON, recrée un panneau de contrôle
    pour chaque VIP qui a un topic_id but not panel_message_id.
    Utilise la note et l'admin_name si disponibles.
    """
    restored = 0

    for user_id, info in list(_user_topics.items()):
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
