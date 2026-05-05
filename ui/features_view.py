"""
Vue Fonctionnalités — présentation visuelle de toutes les fonctionnalités de Foyio.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QGridLayout
)
from PySide6.QtCore import Qt


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _section_label(text, color):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        f"font-size:11px; font-weight:700; color:{color}; "
        "letter-spacing:2px; background:transparent; border:none;"
    )
    return lbl


def _feature_card(emoji, title, lines, accent):
    card = QWidget()
    card.setMinimumHeight(160)
    card.setStyleSheet("""
        QWidget {
            background:#26292e;
            border-radius:12px;
            border:1px solid #3a3f47;
        }
    """)

    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    # En-tête : icône + titre
    head = QHBoxLayout()
    head.setSpacing(10)

    icon_bg = QWidget()
    icon_bg.setFixedSize(40, 40)
    icon_bg.setStyleSheet(
        f"background:{accent}22; border-radius:10px; border:none;"
    )
    icon_lbl = QLabel(emoji, icon_bg)
    icon_lbl.setAlignment(Qt.AlignCenter)
    icon_lbl.setGeometry(0, 0, 40, 40)
    icon_lbl.setStyleSheet("font-size:18px; background:transparent; border:none;")

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        "font-size:13px; font-weight:700; color:#e0e4ea; "
        "background:transparent; border:none;"
    )
    title_lbl.setWordWrap(True)

    head.addWidget(icon_bg)
    head.addWidget(title_lbl, 1)
    layout.addLayout(head)

    # Séparateur coloré
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(2)
    sep.setStyleSheet(
        f"background:{accent}; border:none; border-radius:1px; max-height:2px;"
    )
    layout.addWidget(sep)

    # Points
    for line in lines:
        lbl = QLabel(f"• {line}")
        lbl.setStyleSheet(
            "font-size:11px; color:#848c94; background:transparent; border:none;"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

    layout.addStretch()
    return card


# ──────────────────────────────────────────────────────────────
# Données
# ──────────────────────────────────────────────────────────────

SECTIONS = [
    ("Gestion financière", "#22c55e", [
        ("📊", "Dashboard",
         ["Solde total & revenus/dépenses du mois",
          "Graphiques en donut par catégorie",
          "Transactions récentes & alertes budget"]),
        ("💸", "Transactions",
         ["Ajout rapide Ctrl+N, catégorie auto-détectée",
          "Filtres par période, catégorie, compte",
          "Recherche globale Ctrl+F · Export CSV"]),
        ("🎯", "Budgets",
         ["Barres de progression animées par catégorie",
          "Alertes toast à 90 % et au dépassement",
          "Historique & graphique d'évolution"]),
        ("📈", "Statistiques",
         ["Donut des dépenses par catégorie",
          "Évolution mensuelle revenus/dépenses",
          "Rapport mensuel détaillé avec tableau"]),
        ("🔄", "Récurrentes",
         ["Prélèvements & virements automatiques",
          "Rappels paramétrables (X jours avant)",
          "Génération automatique au démarrage"]),
        ("🐷", "Épargne",
         ["Objectifs avec barres de progression",
          "Ventilation de transactions sur objectifs",
          "Simulateur d'intérêts composés"]),
        ("🏦", "Comptes",
         ["Multi-comptes · Solde par compte",
          "Filtrage des transactions par compte",
          "Historique complet par compte"]),
        ("💳", "Prêts",
         ["Suivi avec tableau d'amortissement",
          "Taux d'intérêt & mensualités calculées",
          "Durée restante & capital remboursé"]),
    ]),
    ("Outils & Import", "#3b82f6", [
        ("🛠️", "Outils financiers",
         ["Convertisseur de devises (taux temps réel)",
          "Calculateur TVA/remise · Comparateur de prix",
          "Calcul de prêt · Intérêts composés"]),
        ("📄", "Rapport fiscal",
         ["Rapport in-app : KPIs, ventilation mensuelle",
          "Répartition par catégorie · Top 10 dépenses",
          "Export PDF optionnel (reportlab)"]),
        ("📥", "Import multi-format",
         ["CSV : SG, BNP, Crédit Agricole, LCL…",
          "Relevés PDF bancaires (multi-banques)",
          "OFX / QFX · QIF (Quicken)"]),
    ]),
    ("Sécurité & Confort", "#f59e0b", [
        ("🔒", "Sécurité",
         ["Mot de passe au démarrage (scrypt + sel)",
          "Délai anti-brute-force · min. 8 caractères",
          "Confirmation avant chaque suppression"]),
        ("🔔", "Notifications",
         ["Notifications OS natives (Windows/Linux/macOS)",
          "Toast budget dépassé ou bientôt atteint",
          "Vérification de mise à jour au démarrage"]),
        ("⚡", "Raccourcis clavier",
         ["Ctrl+Shift+F : ouvrir depuis n'importe où",
          "Systray : l'appli reste en arrière-plan",
          "Ctrl+1…9, Ctrl+N, Ctrl+F, Ctrl+K"]),
        ("✨", "Qualité & UX",
         ["Animations fluides (compteurs, barres, pages)",
          "Messages clairs quand les tableaux sont vides",
          "Aide contextuelle ? sur les pages complexes"]),
    ]),
]


# ──────────────────────────────────────────────────────────────
# Vue principale
# ──────────────────────────────────────────────────────────────

class FeaturesView(QWidget):

    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent; border:none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 32, 40, 40)
        layout.setSpacing(24)

        # ── Hero ──
        hero = QWidget()
        hero.setStyleSheet("""
            QWidget {
                background:#1c2a1c;
                border-radius:16px;
                border:1px solid #22c55e55;
            }
        """)
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(48, 30, 48, 30)
        hero_l.setSpacing(6)

        t = QLabel("Foyio")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(
            "font-size:38px; font-weight:800; color:#22c55e; "
            "background:transparent; border:none;"
        )

        s = QLabel("Gérez vos finances personnelles simplement")
        s.setAlignment(Qt.AlignCenter)
        s.setStyleSheet(
            "font-size:15px; color:#c8cdd4; background:transparent; border:none;"
        )

        d = QLabel(
            "Application de bureau Windows  ·  Interface sombre moderne  ·  12 modules intégrés"
        )
        d.setAlignment(Qt.AlignCenter)
        d.setStyleSheet(
            "font-size:11px; color:#5a6472; background:transparent; border:none;"
        )

        hero_l.addWidget(t)
        hero_l.addWidget(s)
        hero_l.addWidget(d)
        layout.addWidget(hero)

        # ── Sections de fonctionnalités ──
        for section_title, accent, features in SECTIONS:
            layout.addWidget(_section_label(section_title, accent))

            grid = QGridLayout()
            grid.setSpacing(12)
            cols = 3
            for i, (emoji, title, lines) in enumerate(features):
                grid.addWidget(
                    _feature_card(emoji, title, lines, accent),
                    i // cols, i % cols
                )
            layout.addLayout(grid)

        layout.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll)
