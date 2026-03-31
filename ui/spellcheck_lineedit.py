"""
SpellCheckLineEdit — QLineEdit avec correction orthographique automatique.

Dépendance optionnelle : pyspellchecker
    pip install pyspellchecker

Si la librairie n'est pas installée, le widget fonctionne comme un QLineEdit normal.

Comportement :
- À chaque espace ou ponctuation, le mot précédent est vérifié
- S'il est mal orthographié et qu'une correction existe, il est remplacé silencieusement
- Les mots ignorés (noms propres, montants, abréviations) ne sont pas corrigés
- Un dictionnaire personnel est maintenu en mémoire pour les mots ajoutés par l'utilisateur
"""
from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt
import re

# ── Chargement optionnel du correcteur ──
_spell = None

def _load_spell():
    global _spell
    if _spell is not None:
        return _spell
    try:
        from spellchecker import SpellChecker
        _spell = SpellChecker(language="fr", distance=1)
        # Ajouter des mots courants en finance personnelle non reconnus
        _spell.word_frequency.load_words([
            "loyer", "carburant", "courses", "mutuelle", "prélèvement",
            "virement", "salaire", "remboursement", "facture", "abonnement",
            "assurance", "crédit", "épargne", "livret", "compte", "banque",
            "carte", "espèces", "chèque", "débit", "solde", "budget",
            "dépense", "revenu", "mensuel", "annuel", "trimestriel",
        ])
    except Exception:
        _spell = False  # False = indisponible
    return _spell


# Patterns à ne pas corriger
_RE_SKIP = re.compile(
    r"^("
    r"\d[\d\s,\.]*"     # nombres et montants
    r"|[A-Z]{2,}"       # sigles (SNCF, TVA...)
    r"|[a-z]{1,2}"      # mots très courts (à, le, un...)
    r"|https?://"       # URLs
    r")",
    re.IGNORECASE
)


class SpellCheckLineEdit(QLineEdit):
    """
    QLineEdit avec correction automatique à la volée.
    Remplace les mots mal orthographiés dès qu'un séparateur est tapé.
    """

    # Mots ignorés par l'utilisateur (partagés entre toutes les instances)
    _ignored: set = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_word_start = 0
        self._enabled = True  # peut être désactivé

    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        """Intercepte l'espace et la ponctuation pour corriger le mot précédent."""
        super().keyPressEvent(event)

        if not self._enabled:
            return

        # Déclencher sur espace, virgule, point, point-virgule
        if event.text() in (" ", ",", ".", ";", "!", "?"):
            self._autocorrect_last_word()

    # ------------------------------------------------------------------
    def _autocorrect_last_word(self):
        spell = _load_spell()
        if not spell:
            return

        text   = self.text()
        cursor = self.cursorPosition()

        # Trouver le mot juste avant le curseur (avant le séparateur qu'on vient de taper)
        before = text[:cursor - 1]  # -1 pour exclure le séparateur
        match  = re.search(r"(\S+)$", before)

        if not match:
            return

        word      = match.group(1)
        word_start = match.start(1)
        word_end   = match.end(1)

        # Ignorer les mots qui ne doivent pas être corrigés
        if self._should_skip(word):
            return

        # Vérifier l'orthographe
        clean = re.sub(r"[^\w]", "", word)  # strip ponctuation autour
        if not clean:
            return

        if clean.lower() in self._ignored:
            return

        candidates = spell.unknown([clean])
        if not candidates:
            return  # mot correct

        correction = spell.correction(clean)
        if not correction or correction == clean.lower():
            return  # pas de correction disponible

        # Préserver la casse
        if word[0].isupper():
            correction = correction.capitalize()

        # Remplacer dans le texte
        new_text = text[:word_start] + correction + text[word_end:]
        new_cursor = word_start + len(correction) + 1  # +1 pour le séparateur

        self.setText(new_text)
        self.setCursorPosition(new_cursor)

    # ------------------------------------------------------------------
    @staticmethod
    def _should_skip(word: str) -> bool:
        """Retourne True si le mot ne doit pas être corrigé."""
        if len(word) <= 2:
            return True
        if _RE_SKIP.match(word):
            return True
        # Noms propres (commence par majuscule et n'est pas en début de phrase)
        # → on les skip car pyspellchecker ne gère pas les NE
        return False

    # ------------------------------------------------------------------
    def correct_current(self):
        """
        Corrige le mot actuellement dans le champ (utile avant validation).
        Appeler avant de lire .text() pour s'assurer que le texte est corrigé.
        """
        spell = _load_spell()
        if not spell:
            return

        text = self.text().strip()
        if not text:
            return

        # Simuler un espace à la fin pour déclencher la correction
        words = text.split()
        if not words:
            return

        last = words[-1]
        if self._should_skip(last):
            return

        clean = __import__('re').sub(r'[^\w]', '', last)
        if not clean or clean.lower() in self._ignored:
            return

        candidates = spell.unknown([clean])
        if not candidates:
            return

        correction = spell.correction(clean)
        if not correction or correction == clean.lower():
            return

        if last[0].isupper():
            correction = correction.capitalize()

        # Remplacer le dernier mot
        new_text = ' '.join(words[:-1] + [correction])
        self.setText(new_text)
        self.setCursorPosition(len(new_text))

    @classmethod
    def ignore_word(cls, word: str):
        """Ajoute un mot au dictionnaire personnel (ne sera plus corrigé)."""
        cls._ignored.add(word.lower())

    def set_spell_enabled(self, enabled: bool):
        """Active/désactive la correction sur cette instance."""
        self._enabled = enabled
