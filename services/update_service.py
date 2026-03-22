"""
Service de vérification de mise à jour — Foyio
Vérifie si une nouvelle version est disponible sur GitHub.
"""
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── À mettre à jour quand tu auras créé ton dépôt GitHub ──────────
# Dépôt GitHub de Foyio
VERSION_URL = "https://raw.githubusercontent.com/James24300/foyio/main/version.json"

# Version actuelle de l'application
CURRENT_VERSION = "1.0.0"

# Résultat de la vérification (rempli après check async)
_update_available = False
_latest_version   = None
_release_notes    = None
_check_done       = False


def get_current_version() -> str:
    """Retourne la version actuelle depuis version.json local."""
    try:
        path = os.path.join(BASE_DIR, "version.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("version", CURRENT_VERSION)
    except Exception:
        return CURRENT_VERSION


def _version_tuple(v: str) -> tuple:
    """Convertit '1.2.3' en (1, 2, 3) pour comparaison."""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except Exception:
        return (0, 0, 0)


def check_for_update():
    """
    Vérifie en arrière-plan si une nouvelle version est disponible.
    Appelle callback(update_available, latest_version, notes) quand terminé.
    """
    global _update_available, _latest_version, _release_notes, _check_done

    if not VERSION_URL:
        _check_done = True
        return

    try:
        import urllib.request
        with urllib.request.urlopen(VERSION_URL, timeout=5) as resp:
            data = json.loads(resp.read())

        latest  = data.get("version", CURRENT_VERSION)
        notes   = data.get("notes", "")
        current = get_current_version()

        _latest_version   = latest
        _release_notes    = notes
        _update_available = _version_tuple(latest) > _version_tuple(current)
        _check_done       = True

        if _update_available:
            logger.info("Mise à jour disponible : v%s", latest)
        else:
            logger.info("Foyio est à jour (v%s)", current)

    except Exception as e:
        logger.warning("Vérification mise à jour impossible : %s", e)
        _check_done = True


def check_async(callback=None):
    """Lance la vérification en thread daemon."""
    def _run():
        check_for_update()
        if callback and _check_done:
            try:
                callback(_update_available, _latest_version, _release_notes)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def is_update_available() -> bool:
    return _update_available


def get_latest_version() -> str:
    return _latest_version or get_current_version()


def get_release_notes() -> str:
    return _release_notes or ""


def set_github_url(username: str, repo: str):
    """Configure l'URL GitHub une fois le dépôt créé."""
    global VERSION_URL
    VERSION_URL = (
        f"https://raw.githubusercontent.com/{username}/{repo}/main/version.json"
    )


# ── URL du ZIP de la dernière release ──────────────────────────
RELEASE_ZIP_URL = "https://github.com/James24300/foyio/archive/refs/heads/main.zip"


def download_and_install_update(progress_callback=None) -> tuple[bool, str]:
    """
    Télécharge et installe la mise à jour depuis GitHub.
    Retourne (succès, message).
    progress_callback(pct) : appelé de 0 à 100.
    """
    import urllib.request
    import zipfile
    import shutil
    import tempfile

    try:
        # 1. Télécharger le ZIP
        if progress_callback:
            progress_callback(5)

        tmp_zip = os.path.join(tempfile.gettempdir(), "foyio_update.zip")
        with urllib.request.urlopen(RELEASE_ZIP_URL, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_zip, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_callback:
                        progress_callback(5 + int(downloaded / total * 60))

        if progress_callback:
            progress_callback(65)

        # 2. Extraire le ZIP
        tmp_dir = os.path.join(tempfile.gettempdir(), "foyio_update_extracted")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        with zipfile.ZipFile(tmp_zip, "r") as z:
            z.extractall(tmp_dir)

        if progress_callback:
            progress_callback(75)

        # 3. Trouver le dossier extrait (foyio-main/)
        extracted = [d for d in os.listdir(tmp_dir)
                     if os.path.isdir(os.path.join(tmp_dir, d))]
        if not extracted:
            return False, "Archive vide ou corrompue."
        src = os.path.join(tmp_dir, extracted[0])

        # 4. Copier les fichiers Python (sans écraser la DB et les paramètres)
        EXCLUDE = {"finance.db", "settings.json", "backups", "__pycache__", ".git"}
        dst = BASE_DIR
        copied = 0
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d not in EXCLUDE]
            for fname in files:
                if fname.endswith((".py", ".json", ".svg", ".png", ".md")):
                    rel = os.path.relpath(os.path.join(root, fname), src)
                    dest_file = os.path.join(dst, rel)
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    shutil.copy2(os.path.join(root, fname), dest_file)
                    copied += 1

        if progress_callback:
            progress_callback(95)

        # 5. Nettoyer
        shutil.rmtree(tmp_dir, ignore_errors=True)
        os.remove(tmp_zip)

        if progress_callback:
            progress_callback(100)

        return True, f"{copied} fichier(s) mis à jour. Redémarrez Foyio."

    except Exception as e:
        return False, f"Erreur lors de la mise à jour : {e}"
