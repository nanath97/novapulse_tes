# core.py
from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)
dp = Dispatcher(bot)

# ===== AJOUT NOVA PROTECTION PAIEMENT (NE PAS TOUCHER) =====
authorized_users = set()
# ===== Activation du middleware =====
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))


# ----------------- ADMINS / CHATTERS -----------------
# Super-admin (toi) — ID unique
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Liste par défaut d'admins autorisés (hardcodée ici, modifie si tu veux)
# Ajoute ici les IDs des chatters que tu veux autoriser par défaut
DEFAULT_AUTHORIZED_ADMIN_IDS = {ADMIN_ID, 7334072965, 6545079601}

# Lecture optionnelle d'une variable d'env ADMIN_IDS (CSV) pour ajouter des admins sans toucher le code
env_admins = os.getenv("ADMIN_IDS", "")
if env_admins:
    try:
        parts = [p.strip() for p in env_admins.split(",") if p.strip()]
        for p in parts:
            DEFAULT_AUTHORIZED_ADMIN_IDS.add(int(p))
    except Exception:
        print("[CORE] Warning: parsing ADMIN_IDS failed, using defaults.")

# Exposer la set globale utilisée par les autres modules
AUTHORIZED_ADMIN_IDS = set(DEFAULT_AUTHORIZED_ADMIN_IDS)

def is_authorized_admin(admin_id: int) -> bool:
    try:
        return int(admin_id) in AUTHORIZED_ADMIN_IDS
    except Exception:
        return False

# Optionnel : s'assurer que ces admins ne sont pas filtrés par le middleware paiement
try:
    # Si payment_filter définit EXCLUDED_IDS (ou similaire), on la merge
    import middlewares.payment_filter as _pf
    if hasattr(_pf, "EXCLUDED_IDS") and isinstance(_pf.EXCLUDED_IDS, set):
        _pf.EXCLUDED_IDS.update(AUTHORIZED_ADMIN_IDS)
        print(f"[CORE] EXCLUDED_IDS merged with AUTHORIZED_ADMIN_IDS: {_pf.EXCLUDED_IDS}")
except Exception:
    # ignore si le module n'existe pas dans ce runtime ou autre erreur
    pass

# Petit log utile au démarrage pour vérifier les admins chargés
print(f"[CORE] ADMIN_ID={ADMIN_ID}, AUTHORIZED_ADMIN_IDS={AUTHORIZED_ADMIN_IDS}")
# ----------------------------------------------------
