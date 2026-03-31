#!/usr/bin/env bash
# install_linux.sh — Installe Foyio sur Linux
set -e

APP_NAME="Foyio"
INSTALL_DIR="$HOME/.local/share/$APP_NAME"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Vérification Python 3.10+ ──
PYTHON=$(command -v python3 || true)
if [ -z "$PYTHON" ]; then
    echo "Erreur : python3 introuvable. Installez Python 3.10 ou plus récent."
    exit 1
fi

PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
PY_VERSION="$PY_MAJOR.$PY_MINOR"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "Erreur : Python $PY_VERSION détecté. Python 3.10+ requis."
    exit 1
fi

echo "Python $PY_VERSION détecté."

# ── Copie des fichiers ──
echo "Installation dans $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='build' \
    --exclude='dist' \
    --exclude='Output' \
    --exclude='tests' \
    "$SCRIPT_DIR/" "$INSTALL_DIR/"

# ── Dépendances Python ──
echo "Installation des dépendances Python..."
"$PYTHON" -m pip install --quiet --user -r "$INSTALL_DIR/requirements.txt"

# ── Lanceur ──
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/foyio" << EOF
#!/usr/bin/env bash
cd "$INSTALL_DIR"
exec python3 "$INSTALL_DIR/main.py" "\$@"
EOF
chmod +x "$BIN_DIR/foyio"

# ── Entrée .desktop (menu application) ──
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/foyio.desktop" << EOF
[Desktop Entry]
Name=Foyio
Comment=Gestion de finances personnelles
Exec=$BIN_DIR/foyio
Icon=$INSTALL_DIR/foyio_icon.png
Terminal=false
Type=Application
Categories=Office;Finance;
StartupNotify=true
EOF

# ── Avertissement PATH ──
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "Attention : $BIN_DIR n'est pas dans votre PATH."
    echo "Ajoutez cette ligne à votre ~/.bashrc ou ~/.zshrc :"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
echo "Foyio installé. Lancez-le avec : foyio"
echo "Ou depuis le menu application de votre bureau."
