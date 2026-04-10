import logging
"""
Service de paramètres utilisateur — Foyio
Stocke les préférences dans un fichier JSON local.
"""
import json, os
from config import APP_DIR
logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(APP_DIR, "settings.json")

DEFAULTS = {
    "user_name":     "",
    "currency":      "EUR",
    "currency_symbol": "€",
    "language":      "fr",
    "startup_notifications": True,
    "theme":         "dark",
}


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Compléter avec les valeurs par défaut manquantes
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULTS)


def save_settings(settings: dict):
    os.makedirs(APP_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def get(key: str):
    return load_settings().get(key, DEFAULTS.get(key))


def set(key: str, value):
    s = load_settings()
    s[key] = value
    save_settings(s)
