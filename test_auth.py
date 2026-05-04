import os
import shutil
import hashlib
import bcrypt
import sys
from unittest.mock import MagicMock

# Mocker PySide6 pour tester sans interface graphique
mock_pyside = MagicMock()
sys.modules["PySide6"] = mock_pyside
sys.modules["PySide6.QtWidgets"] = mock_pyside
sys.modules["PySide6.QtCore"] = mock_pyside
sys.modules["PySide6.QtGui"] = mock_pyside

# Simuler l'environnement Foyio
APP_DIR = "test_foyio_data"
if os.path.exists(APP_DIR):
    shutil.rmtree(APP_DIR)
os.makedirs(APP_DIR)

# Mock de config.py pour le test
with open("config.py", "w") as f:
    f.write(f'APP_DIR = "{APP_DIR}"')

# Importer les fonctions modifiées (assurez-vous d'avoir appliqué les modifs sur password_dialog.py)
try:
    from ui.password_dialog import _save_hash, check_password, PASSWORD_FILE
except ImportError:
    print("❌ Erreur : Impossible de trouver ui/password_dialog.py. Vérifiez que le fichier existe.")
    sys.exit(1)

def test_new_password():
    print("Test 1: Création d'un nouveau mot de passe avec bcrypt...")
    password = "mon_super_password_123"
    _save_hash(password)
    with open(PASSWORD_FILE, "rb") as f:
        stored = f.read()
    if stored.startswith(b"$2b$"):
        print("✅ Succès: Le mot de passe est stocké au format bcrypt.")
    else:
        print("❌ Échec: Le format de stockage est incorrect.")
        return False
    if check_password(password):
        print("✅ Succès: Vérification du mot de passe bcrypt réussie.")
    else:
        print("❌ Échec: Impossible de vérifier le mot de passe bcrypt.")
        return False
    return True

def test_migration():
    print("\nTest 2: Migration d'un ancien mot de passe SHA-256...")
    password = "ancien_password_sha"
    old_hash = hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")
    with open(PASSWORD_FILE, "wb") as f:
        f.write(old_hash)
    if check_password(password):
        print("✅ Succès: L'ancien mot de passe a été reconnu.")
        with open(PASSWORD_FILE, "rb") as f:
            new_stored = f.read()
        if new_stored.startswith(b"$2b$"):
            print("✅ Succès: Le mot de passe a été automatiquement migré vers bcrypt.")
        else:
            print("❌ Échec: La migration vers bcrypt n'a pas eu lieu.")
            return False
    else:
        print("❌ Échec: L'ancien mot de passe n'a pas été reconnu.")
        return False
    return True

if __name__ == "__main__":
    if test_new_password() and test_migration():
        print("\n✨ Tous les tests d'authentification ont réussi !")
        # Nettoyage
        if os.path.exists(APP_DIR): shutil.rmtree(APP_DIR)
        if os.path.exists("config.py"): os.remove("config.py")
    else:
        print("\n❌ Certains tests ont échoué.")
