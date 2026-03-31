# 💰 Foyio

**Gestion financière personnelle** — Simple, rapide et 100% locale.

Foyio est une application de bureau pour suivre vos revenus, dépenses, budgets et objectifs d'épargne. Toutes vos données restent sur votre ordinateur — rien n'est envoyé en ligne.

---

## Fonctionnalités

- **Transactions** — Suivi complet des revenus et dépenses avec catégorisation automatique
- **Budgets** — Plafonds mensuels par catégorie avec alertes de dépassement
- **Épargne** — Objectifs, versements manuels, simulateur et suivi de progression
- **Statistiques** — Graphiques interactifs, répartition par catégorie, comparaison mois par mois
- **Multi-comptes** — Gérez plusieurs comptes bancaires (courant, joint, livret...)
- **Import bancaire** — Import CSV et PDF depuis Société Générale
- **Export** — CSV et rapport PDF mensuel mis en page
- **Récurrentes** — Transactions automatiques chaque mois (loyer, abonnements...)
- **Recherche globale** — Recherche par libellé, catégorie, montant ou date
- **Calculatrice** — Accessible depuis n'importe quel écran (Ctrl+K)
- **Mot de passe** — Protection par mot de passe au démarrage
- **Sauvegarde** — Backup automatique de la base de données à chaque lancement

## Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl+1` à `Ctrl+9` | Navigation entre les vues |
| `Ctrl+N` | Nouvelle transaction |
| `Ctrl+F` | Recherche globale |
| `Ctrl+K` | Calculatrice |
| `Ctrl+←` / `Ctrl+→` | Mois précédent / suivant |
| `Ctrl+T` | Revenir au mois courant |

## Technologies

- **Python 3** + **PySide6** (Qt) — Interface graphique
- **SQLAlchemy** + **SQLite** — Base de données locale
- **ReportLab** — Génération de rapports PDF
- **pdfplumber** — Lecture de relevés bancaires PDF

## Installation

### Prérequis

- Python 3.10 ou supérieur
- pip

### Lancement depuis les sources

```bash
git clone https://github.com/James24300/foyio.git
cd foyio
pip install -r requirements.txt
python main.py
```

### Installation sur Linux

```bash
git clone https://github.com/James24300/foyio.git
cd foyio
bash install_linux.sh
```

Le script installe les dépendances, copie les fichiers dans `~/.local/share/Foyio`, crée un lanceur `foyio` et une entrée dans le menu application.

**Prérequis :** Python 3.10+, pip, rsync. Sur Ubuntu/Debian :
```bash
sudo apt install python3 python3-pip rsync
```

Après installation, lancez avec :
```bash
foyio
```

### Créer un exécutable Windows

```bash
pip install pyinstaller
python build_windows.py
```

L'exécutable est généré dans `dist/Foyio/Foyio.exe`.
Un installateur Windows est créé dans `Output/` si Inno Setup est installé.

## Structure du projet

```
foyio/
├── main.py                 # Point d'entrée + fenêtre principale
├── config.py               # Configuration (chemins, base de données)
├── db.py                   # Connexion SQLAlchemy + migrations
├── models.py               # Modèles de données (comptes, transactions...)
├── account_state.py        # État global du compte sélectionné
├── period_state.py         # État global de la période sélectionnée
├── services/               # Logique métier
│   ├── transaction_service.py
│   ├── recurring_service.py
│   ├── savings_service.py
│   ├── dashboard_service.py
│   ├── import_service.py
│   ├── export_service.py
│   └── ...
├── ui/                     # Interface graphique (vues PySide6)
│   ├── dashboard_view.py
│   ├── transactions_view.py
│   ├── statistics_view.py
│   ├── savings_view.py
│   └── ...
├── utils/                  # Utilitaires (thème, icônes, formatage)
│   ├── theme.py
│   ├── formatters.py
│   ├── icons.py
│   └── category_icons.py
└── icons/                  # Icônes PNG et SVG
```

## Données utilisateur

Les données sont stockées localement dans :

| Système | Emplacement |
|---------|-------------|
| Windows | `%APPDATA%\Foyio\` |
| macOS | `~/Library/Application Support/Foyio/` |
| Linux | `~/.local/share/Foyio/` |

Ce dossier contient la base de données (`finance.db`), les paramètres (`settings.json`) et les sauvegardes automatiques.

## Licence

Logiciel personnel — Tous droits réservés.

---

Développé par **James-William PULSFORD** — Conçu avec Python et Claude.ai
