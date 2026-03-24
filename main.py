import logging
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Configuration du logging ─────────────────────────────────────
from config import APP_DIR
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(os.path.join(APP_DIR, "foyio.log"),
                            encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QTabWidget, QComboBox
)
from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QLocale, QEasingCurve, Signal
from PySide6.QtGui import QIcon

from db import Base, engine, Session
from models import Category, Transaction

import period_state

from services.init_categories import init_categories, migrate_category_icons, init_savings_categories
from services.account_service import init_accounts, migrate_transactions_to_default_account
import account_state
from services.recurring_service import apply_recurring
from services.backup_service import backup_database
from services.transaction_service import (
    add_transaction, get_transactions, get_month_summary,
    set_budget, get_budget_status, delete_transaction
)
from services.dashboard_service import (
    dashboard_stats, top_expenses, forecast_balance, biggest_category
)

from utils.theme import DARK_THEME, LIGHT_THEME, BANK_THEME

from ui.dashboard_view import DashboardView
from ui.transactions_view import Transactions
from ui.budget_view import BudgetView
from ui.categories_view import CategoryView
from ui.statistics_view import StatisticsView
from ui.recurring_view import RecurringView
from ui.accounts_view import AccountsView
from ui.savings_view import SavingsView
from ui.calculator import Calculator
from ui.tools_view import ToolsView
from ui.about_view import AboutView
from ui.features_view import FeaturesView
from ui.settings_view import SettingsView
from ui.loans_view import LoansView
from services.update_service import check_async, get_current_version
from ui.password_dialog import PasswordDialog


class AnimatedNavBtn(QPushButton):
    """Bouton sidebar avec animation d'icône au survol."""

    _ICON_NORMAL = QSize(26, 26)
    _ICON_HOVER  = QSize(30, 30)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hover_anim = QPropertyAnimation(self, b"iconSize")
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.OutQuad)

    def enterEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.iconSize())
        self._hover_anim.setEndValue(self._ICON_HOVER)
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self.iconSize())
        self._hover_anim.setEndValue(self._ICON_NORMAL)
        self._hover_anim.start()
        super().leaveEvent(event)


class MainWindow(QWidget):

    _update_signal = Signal(str)   # émet la version distante

    def __init__(self):
        super().__init__()
        from services.settings_service import get as _get_s
        _uname = _get_s("user_name") or ""
        _title = f"Foyio — {_uname}" if _uname else "Foyio"
        self.setWindowTitle(_title)
        self.setWindowIcon(QIcon(os.path.join(BASE_DIR, "icons", "foyio_logo.png")))
        self.resize(1280, 760)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ══════════════════════════════════════
        # SIDEBAR
        # ══════════════════════════════════════
        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(10, 16, 10, 16)
        sidebar.setSpacing(4)
        self.sidebar_expanded = True

        # ── Logo Foyio ──
        logo_widget = QWidget()
        logo_widget.setStyleSheet("background:transparent; border:none;")
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(8, 4, 8, 4)
        logo_layout.setSpacing(10)

        logo_icon = QLabel()
        logo_icon.setPixmap(
            QIcon(os.path.join(BASE_DIR, "icons", "foyio_logo.png")).pixmap(32, 32)
        )
        logo_icon.setStyleSheet("background:transparent; border:none;")

        self._logo_text = QLabel("Foyio")
        self._logo_text.setStyleSheet(
            "font-size:18px; font-weight:700; color:#c8cdd4; "
            "letter-spacing:1px; background:transparent; border:none;"
        )

        self.btn_toggle_sidebar = QPushButton()
        self.btn_toggle_sidebar.setFixedSize(28, 28)
        self.btn_toggle_sidebar.setIcon(QIcon(os.path.join(BASE_DIR, "icons", "transactions.png")))
        self.btn_toggle_sidebar.setIconSize(QSize(16, 16))
        self.btn_toggle_sidebar.setToolTip("Réduire / étendre le menu")
        self.btn_toggle_sidebar.setStyleSheet("""
            QPushButton {
                background:transparent; border:none;
                border-radius:6px; color:#7a8494;
            }
            QPushButton:hover { background:#2e3238; }
        """)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)

        logo_layout.addWidget(logo_icon)
        logo_layout.addWidget(self._logo_text)
        logo_layout.addStretch()
        logo_layout.addWidget(self.btn_toggle_sidebar)

        sidebar.addWidget(logo_widget)

        # Séparateur sous le logo
        from PySide6.QtWidgets import QFrame
        sep_logo = QFrame()
        sep_logo.setFrameShape(QFrame.HLine)
        sep_logo.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        sidebar.addWidget(sep_logo)
        sidebar.addSpacing(6)

        nav_items = [
            ("btn_dashboard",    " Accueil",      "home.png"),
            ("btn_transactions", " Transactions", "transactions.png"),
            ("btn_budget",       " Budgets",      "budget.png"),
            ("btn_categories",   " Catégories",   "categories.png"),
            ("btn_stats",        " Statistiques", "stats.png"),
            ("btn_recurring",    " Récurrentes",  "transactions.png"),
            ("btn_savings",      " Épargne",      "epargne.png"),
            ("btn_accounts",     " Comptes",      "bank.png"),
            ("btn_loans",        " Prêts",        "money.png"),
            ("btn_tools",        " Outils",       "stats.png"),
            ("btn_settings",     " Paramètres",      "other.png"),
            ("btn_features",     " Fonctionnalités","reports.png"),
            ("btn_about",        " À propos",        "other.png"),
        ]

        self._nav_buttons = []
        for attr, label, icon_name in nav_items:
            btn = AnimatedNavBtn(label)
            btn.setIcon(QIcon(os.path.join(BASE_DIR, "icons", icon_name)))
            btn.setCheckable(True)
            btn.setMinimumHeight(54)
            btn.setIconSize(QSize(26, 26))
            btn.setStyleSheet("""
                QPushButton {
                    text-align:left; padding-left:12px;
                    border:none; border-radius:10px; background:transparent;
                    color:#5a6472; font-size:13px;
                }
                QPushButton:hover {
                    background:#23272b;
                    color:#c8cdd4;
                }
                QPushButton:checked {
                    background:#2e3238;
                    border-left:3px solid #c8cdd4;
                    border-radius:0px 10px 10px 0px;
                    color:#ffffff; font-weight:700;
                }
            """)
            setattr(self, attr, btn)
            self._nav_buttons.append(btn)
            sidebar.addWidget(btn)

        sidebar.addStretch()

        # Séparateur
        sep_quit = QFrame()
        sep_quit.setFrameShape(QFrame.HLine)
        sep_quit.setStyleSheet('background:#2e3238; max-height:1px; border:none;')
        sidebar.addWidget(sep_quit)

        # Bouton Quitter
        self._btn_quit = QPushButton('  Quitter')
        self._btn_quit.setIcon(QIcon(os.path.join(BASE_DIR, 'icons', 'logout.svg')))
        self._btn_quit.setMinimumHeight(44)
        self._btn_quit.setIconSize(QSize(22, 22))
        self._btn_quit.setStyleSheet("""
            QPushButton {
                text-align:left; padding-left:12px;
                border:1px solid #503030; border-radius:10px;
                background:#2e2020; color:#e89090;
                font-size:13px;
            }
            QPushButton:hover {
                background:#3a2020; color:#ff6b6b;
                border:1px solid #7a3030;
            }
        """)
        self._btn_quit.clicked.connect(self._confirm_quit)
        sidebar.addWidget(self._btn_quit)
        sidebar.addSpacing(6)

        self.sidebar_widget = QWidget()
        self.sidebar_widget.setLayout(sidebar)
        self.sidebar_widget.setFixedWidth(220)
        self.sidebar_widget.setStyleSheet("""
            background:#13151a;
            border-right:1px solid #2e3238;
        """)

        # ══════════════════════════════════════
        # BARRE DE TITRE avec sélecteur de période
        # ══════════════════════════════════════
        self.title_icon = QLabel()
        self.title_text = QLabel("Accueil")
        self.title_text.setStyleSheet("font-size:19px; font-weight:700; letter-spacing:0.5px; color:#e0e4ea;")

        title_layout = QHBoxLayout()
        title_layout.addWidget(self.title_icon)
        title_layout.addWidget(self.title_text)
        title_layout.addStretch()

        # Sélecteur de période
        period_widget = QWidget()
        period_widget.setStyleSheet("""
            QWidget {
                background:#23272b;
                border-radius:20px;
                border:1px solid #3a3f47;
            }
        """)
        period_layout = QHBoxLayout(period_widget)
        period_layout.setContentsMargins(4, 4, 4, 4)
        period_layout.setSpacing(0)

        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(32, 32)
        self.btn_prev.setToolTip("Mois précédent")
        self.btn_prev.setStyleSheet("""
            QPushButton { background:transparent; border:none; color:#7a8494; font-size:13px; border-radius:16px; font-weight:600; }
            QPushButton:hover { background:#3a3f47; color:#c8cdd4; }
        """)
        self.btn_prev.clicked.connect(self._go_prev)

        self.period_label = QLabel(period_state.label())
        self.period_label.setAlignment(Qt.AlignCenter)
        self.period_label.setMinimumWidth(130)
        self.period_label.setStyleSheet(
            "font-size:14px; font-weight:600; color:#c8cdd4; background:transparent; border:none;"
        )

        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(32, 32)
        self.btn_next.setToolTip("Mois suivant")
        self.btn_next.setStyleSheet("""
            QPushButton { background:transparent; border:none; color:#7a8494; font-size:13px; border-radius:16px; font-weight:600; }
            QPushButton:hover { background:#3a3f47; color:#c8cdd4; }
            QPushButton:disabled { color:#374151; }
        """)
        self.btn_next.clicked.connect(self._go_next)

        self.btn_today = QPushButton("Aujourd'hui")
        self.btn_today.setFixedHeight(32)
        self.btn_today.setToolTip("Revenir au mois courant")
        self.btn_today.setStyleSheet("""
            QPushButton { background:transparent; border:none; color:#7a8494; font-size:12px; border-radius:6px; padding:0 8px; }
            QPushButton:hover { background:#3e4550; }
            QPushButton:disabled { color:#374151; }
        """)
        self.btn_today.clicked.connect(self._go_today)

        period_layout.addWidget(self.btn_prev)
        period_layout.addWidget(self.period_label)
        period_layout.addWidget(self.btn_next)
        period_layout.addSpacing(4)
        period_layout.addWidget(self.btn_today)

        title_layout.addWidget(period_widget)
        title_layout.addSpacing(8)

        # ── Sélecteur de compte ──
        account_widget = QWidget()
        account_widget.setStyleSheet(
            "QWidget { background:#23272b; border-radius:20px; border:1px solid #3a3f47; }"
        )
        account_layout = QHBoxLayout(account_widget)
        account_layout.setContentsMargins(8, 4, 8, 4)
        account_layout.setSpacing(6)

        acc_icon_lbl = QLabel()
        acc_icon_lbl.setPixmap(
            QIcon(os.path.join(BASE_DIR, "icons", "bank.png")).pixmap(18, 18)
        )
        acc_icon_lbl.setStyleSheet("background:transparent; border:none;")
        account_layout.addWidget(acc_icon_lbl)

        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(150)
        self.account_combo.setStyleSheet("""
            QComboBox {
                background:transparent; border:none;
                color:#c8cdd4; font-size:13px; font-weight:600;
                padding:0 4px;
            }
            QComboBox::drop-down { border:none; width:18px; }
            QComboBox QAbstractItemView {
                background:#26292e; border:1px solid #3a3f47;
                color:#c8cdd4; selection-background-color:#6a7484;
                padding:4px;
            }
        """)
        self._reload_accounts()
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        account_layout.addWidget(self.account_combo)

        # Bouton accès espace client bancaire
        self.btn_bank_url = QPushButton("  Banque  ↗")
        self.btn_bank_url.setFixedHeight(32)
        self.btn_bank_url.setToolTip("")
        self.btn_bank_url.setStyleSheet("""
            QPushButton {
                background:transparent;
                border:1px solid #3d4248;
                color:#a0a8b0; font-size:12px; border-radius:6px;
                padding:0 10px;
                text-decoration: none;
            }
            QPushButton:hover {
                background:#2e3238;
                color:#d0d4d8;
                border:1px solid #5a6068;
            }
        """)
        self.btn_bank_url.clicked.connect(self._open_bank_url)
        account_layout.addWidget(self.btn_bank_url)

        title_layout.addWidget(account_widget)
        title_layout.addSpacing(4)

        # ── Bouton calculatrice ──
        self._btn_calc = QPushButton()
        self._btn_calc.setIcon(QIcon(os.path.join(BASE_DIR, 'icons', 'calculator.svg')))
        self._btn_calc.setIconSize(QSize(22, 22))
        self._btn_calc.setFixedSize(36, 32)
        self._btn_calc.setToolTip('Calculatrice (Ctrl+K)')
        self._btn_calc.setStyleSheet("""
            QPushButton {
                background:#23272b; border:1px solid #3a3f47;
                border-radius:8px; color:#848c94; font-size:16px;
            }
            QPushButton:hover { background:#3a3f47; color:#c8cdd4; }
        """)
        self._btn_calc.clicked.connect(self._open_calculator)
        title_layout.addWidget(self._btn_calc)
        title_layout.addSpacing(8)

        title_widget = QWidget()
        title_widget.setLayout(title_layout)
        title_widget.setContentsMargins(12, 6, 12, 6)
        title_widget.setStyleSheet(
            "QWidget { background:#1e2124; border-bottom:1px solid #2e3238; }"
        )

        # ══════════════════════════════════════
        # VUES
        # ══════════════════════════════════════
        self.stack = QTabWidget()
        self.stack.tabBar().hide()

        self.accueil      = DashboardView()
        self.transactions = Transactions(self.accueil)
        self.budget       = BudgetView()
        self.categories   = CategoryView(self)
        self.stats        = StatisticsView()
        self.recurring    = RecurringView()
        self.accounts     = AccountsView(self)
        self.savings      = SavingsView()
        self.loans        = LoansView()
        self.tools        = ToolsView()
        self.about        = AboutView()
        self.settings_v   = SettingsView()
        self.features_v   = FeaturesView()

        for view in [
            self.accueil, self.transactions, self.budget,
            self.categories, self.stats, self.recurring,
            self.savings, self.accounts, self.loans,
            self.tools, self.settings_v, self.features_v, self.about
        ]:
            self.stack.addTab(view, "")

        # ── Systray ──
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu
        self._tray = QSystemTrayIcon(QIcon(os.path.join(BASE_DIR, "icons", "foyio_logo.png")), self)
        self._tray.setToolTip("Foyio")
        tray_menu = QMenu()
        tray_menu.addAction("Ouvrir Foyio", self.showNormal)
        tray_menu.addSeparator()
        tray_menu.addAction("Quitter", self._confirm_quit)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        # Notifications de rappel pour les récurrentes à venir
        from PySide6.QtCore import QTimer as _QT
        _QT.singleShot(2000, self._notify_upcoming_recurring)

        self.btn_dashboard.clicked.connect(lambda: self.set_active(0))
        self.btn_transactions.clicked.connect(lambda: self.set_active(1))
        self.btn_budget.clicked.connect(lambda: self.set_active(2))
        self.btn_categories.clicked.connect(lambda: self.set_active(3))
        self.btn_stats.clicked.connect(lambda: self.set_active(4))
        self.btn_recurring.clicked.connect(lambda: self.set_active(5))
        self.btn_savings.clicked.connect(lambda: self.set_active(6))
        self.btn_accounts.clicked.connect(lambda: self.set_active(7))
        self.btn_loans.clicked.connect(lambda: self.set_active(8))
        self.btn_tools.clicked.connect(lambda: self.set_active(9))
        self.btn_settings.clicked.connect(lambda: self.set_active(10))
        self.btn_features.clicked.connect(lambda: self.set_active(11))
        self.btn_about.clicked.connect(lambda: self.set_active(12))

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(title_widget)
        content_layout.addWidget(self.stack, 1)

        content_widget = QWidget()
        content_widget.setStyleSheet("QWidget { background:#1e2023; }")
        content_widget.setLayout(content_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(content_widget)

        main_layout.addWidget(self.sidebar_widget)
        main_layout.addWidget(scroll, 1)
        self.setLayout(main_layout)

        self.set_active(0)
        # Notifications au démarrage
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, self._startup_notifications)
        # Vérification de mise à jour en arrière-plan
        self._update_signal.connect(self._show_update_toast)
        check_async(callback=self._on_update_checked)
        self._update_period_buttons()

        # ── Verrouillage automatique ──
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._auto_lock)
        self._restart_lock_timer()
        QApplication.instance().installEventFilter(self)

        # ── Raccourcis clavier ──
        from PySide6.QtGui import QShortcut, QKeySequence
        for key, slot in [
            ("Ctrl+1",     lambda: self.set_active(0)),
            ("Ctrl+2",     lambda: self.set_active(1)),
            ("Ctrl+3",     lambda: self.set_active(2)),
            ("Ctrl+4",     lambda: self.set_active(3)),
            ("Ctrl+5",     lambda: self.set_active(4)),
            ("Ctrl+6",     lambda: self.set_active(5)),
            ("Ctrl+7",     lambda: self.set_active(6)),
            ("Ctrl+8",     lambda: self.set_active(7)),
            ("Ctrl+9",     lambda: self.set_active(8)),
            ("Ctrl+F",     self._focus_search),
            ("Ctrl+Left",  self._go_prev),
            ("Ctrl+Right", self._go_next),
            ("Ctrl+T",     self._go_today),
            ("Ctrl+K",     self._open_calculator),
            ("Ctrl+N",     self._new_transaction),
            ("Ctrl+?",     self._show_shortcuts),
        ]:
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(slot)

    # ------------------------------------------------------------------
    def _show_shortcuts(self):
        """Affiche le panneau d'aide des raccourcis clavier."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        from PySide6.QtCore import Qt

        dlg = QDialog(self)
        dlg.setWindowTitle("Raccourcis clavier")
        dlg.setMinimumWidth(420)
        vl = QVBoxLayout(dlg)
        vl.setSpacing(4)
        vl.setContentsMargins(24, 20, 24, 20)

        title = QLabel("  Raccourcis clavier")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#c8cdd4;")
        vl.addWidget(title)
        vl.addSpacing(12)

        shortcuts = [
            ("Navigation", [
                ("Ctrl+1 … 9",  "Aller à la vue correspondante"),
                ("Ctrl+←  /  →","Mois précédent / suivant"),
                ("Ctrl+T",       "Revenir au mois courant"),
            ]),
            ("Actions", [
                ("Ctrl+N",  "Nouvelle transaction"),
                ("Ctrl+F",  "Recherche globale"),
                ("Ctrl+K",  "Ouvrir la calculatrice"),
                ("Ctrl+?",  "Afficher cette aide"),
            ]),
        ]

        for section, items in shortcuts:
            sec_lbl = QLabel(section.upper())
            sec_lbl.setStyleSheet(
                "font-size:10px; font-weight:700; color:#5a6472; "
                "letter-spacing:2px; margin-top:8px;"
            )
            vl.addWidget(sec_lbl)
            for key, desc in items:
                row = QHBoxLayout()
                key_lbl = QLabel(key)
                key_lbl.setFixedWidth(120)
                key_lbl.setStyleSheet(
                    "background:#292d32; color:#7aaee8; border-radius:6px; "
                    "padding:3px 8px; font-size:12px; font-weight:600; font-family:monospace;"
                )
                desc_lbl = QLabel(desc)
                desc_lbl.setStyleSheet("color:#848c94; font-size:12px;")
                row.addWidget(key_lbl)
                row.addSpacing(12)
                row.addWidget(desc_lbl)
                row.addStretch()
                vl.addLayout(row)

        vl.addSpacing(16)
        btn = QPushButton("Fermer")
        btn.setMinimumHeight(34)
        btn.clicked.connect(dlg.accept)
        vl.addWidget(btn)
        dlg.exec()

    def _startup_notifications(self):
        """Affiche une fenêtre de notifications détaillées au démarrage."""
        from services.settings_service import get as get_setting
        if not get_setting('startup_notifications'):
            return
        from services.savings_service import check_monthly_targets
        from services.recurring_service import get_overdue_recurring, get_upcoming_recurring
        from services.reminder_service import get_upcoming_reminders
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel,
            QPushButton, QScrollArea, QWidget, QHBoxLayout)
        from PySide6.QtCore import Qt

        savings_alerts = check_monthly_targets()
        overdue        = get_overdue_recurring()
        upcoming       = get_upcoming_recurring(3)
        reminders      = get_upcoming_reminders()

        if not savings_alerts and not overdue and not upcoming and not reminders:
            return  # Rien à signaler

        dlg = QDialog(self)
        dlg.setWindowTitle('Notifications')
        dlg.setMinimumWidth(460)
        dlg.setStyleSheet('background:#1e2124; color:#c8cdd4;')
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        title = QLabel('  Notifications du jour')
        title.setStyleSheet(
            'font-size:16px; font-weight:700; color:#c8cdd4; '
            'background:#292d32; border-radius:8px; padding:10px;'
        )
        vl.addWidget(title)

        # Récurrentes en retard
        if overdue:
            sec = QLabel(f'  Récurrentes en retard ({len(overdue)})')
            sec.setStyleSheet('font-size:12px; font-weight:700; color:#f59e0b;')
            vl.addWidget(sec)
            for r in overdue:
                row = QWidget()
                row.setStyleSheet(
                    'background:#2a2010; border-radius:8px; '
                    'border:1px solid #5a4010;'
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 8, 12, 8)
                name_lbl = QLabel(f'  {r["label"]}')
                name_lbl.setStyleSheet('color:#f59e0b; font-weight:600; font-size:12px;')
                amt_lbl  = QLabel(f'{r["amount"]:,.2f} €')
                amt_lbl.setStyleSheet('color:#f59e0b; font-size:12px;')
                amt_lbl.setAlignment(Qt.AlignRight)
                rl.addWidget(name_lbl, 1)
                rl.addWidget(amt_lbl)
                vl.addWidget(row)

        # Épargne en retard
        if savings_alerts:
            sec2 = QLabel(f'  Versements épargne manquants ({len(savings_alerts)})')
            sec2.setStyleSheet('font-size:12px; font-weight:700; color:#3b82f6;')
            vl.addWidget(sec2)
            for g in savings_alerts:
                row = QWidget()
                row.setStyleSheet(
                    'background:#101828; border-radius:8px; '
                    'border:1px solid #1e3a5f;'
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 8, 12, 8)
                name_lbl = QLabel(f'  {g["name"]}')
                name_lbl.setStyleSheet('color:#3b82f6; font-weight:600; font-size:12px;')
                amt_lbl  = QLabel(f'Objectif mensuel : {g["target"]:,.2f} €')
                amt_lbl.setStyleSheet('color:#7a8494; font-size:11px;')
                amt_lbl.setAlignment(Qt.AlignRight)
                rl.addWidget(name_lbl, 1)
                rl.addWidget(amt_lbl)
                vl.addWidget(row)

        # J-3 : récurrentes à venir
        if upcoming:
            sec3 = QLabel(f'  À venir dans 3 jours ({len(upcoming)})')
            sec3.setStyleSheet('font-size:12px; font-weight:700; color:#22c55e;')
            vl.addWidget(sec3)
            for r in upcoming:
                row = QWidget()
                row.setStyleSheet(
                    'background:#0f2010; border-radius:8px; '
                    'border:1px solid #1a4020;'
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 8, 12, 8)
                name_lbl = QLabel(f'  {r["label"]}  —  J-{r["days_until"]}')
                name_lbl.setStyleSheet('color:#22c55e; font-weight:600; font-size:12px;')
                amt_lbl  = QLabel(f'{r["amount"]:,.2f} €')
                amt_lbl.setStyleSheet('color:#22c55e; font-size:12px;')
                amt_lbl.setAlignment(Qt.AlignRight)
                rl.addWidget(name_lbl, 1)
                rl.addWidget(amt_lbl)
                vl.addWidget(row)

        # Rappels de paiement
        if reminders:
            sec4 = QLabel(f'  Rappels de paiement ({len(reminders)})')
            sec4.setStyleSheet('font-size:12px; font-weight:700; color:#f59e0b;')
            vl.addWidget(sec4)
            for r in reminders:
                row = QWidget()
                row.setStyleSheet(
                    'background:#2a2010; border-radius:8px; '
                    'border:1px solid #5a4010;'
                )
                rl = QHBoxLayout(row)
                rl.setContentsMargins(12, 8, 12, 8)
                day_text = "Aujourd'hui" if r['days_until'] == 0 else f"J-{r['days_until']}"
                prefix = "Dépense" if r['type'] == 'expense' else "Revenu"
                name_lbl = QLabel(f'  {r["label"]}  —  {day_text}')
                name_lbl.setStyleSheet('color:#f59e0b; font-weight:600; font-size:12px;')
                amt_lbl  = QLabel(f'{r["amount"]:,.2f} €')
                amt_lbl.setStyleSheet('color:#f59e0b; font-size:12px;')
                amt_lbl.setAlignment(Qt.AlignRight)
                rl.addWidget(name_lbl, 1)
                rl.addWidget(amt_lbl)
                vl.addWidget(row)

        btn_close = QPushButton('Fermer')
        btn_close.setMinimumHeight(36)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)
        dlg.exec()

    def _new_transaction(self):
        """Ctrl+N — Aller sur Transactions et ouvrir le dialogue d'ajout."""
        self.set_active(1)
        if hasattr(self, 'transactions'):
            self.transactions.add()

    def _open_calculator(self):
        """Ouvre la calculatrice flottante."""
        if not hasattr(self, '_calculator'):
            self._calculator = Calculator(self)
        if self._calculator.isVisible():
            self._calculator.raise_()
            self._calculator.activateWindow()
        else:
            # Positionner en haut à droite
            geo = self.geometry()
            self._calculator.move(
                geo.right() - self._calculator.width() - 20,
                geo.top() + 60
            )
            self._calculator.show()

    def _focus_search(self):
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _global_search(self):
        query = self._search_input.text().strip()
        if len(query) < 2:
            return
        from services.transaction_service import search_all_periods
        from utils.formatters import format_money
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
            QTableWidgetItem, QHeaderView, QPushButton, QComboBox,
            QLineEdit, QFrame
        )
        from PySide6.QtGui import QColor, QDoubleValidator
        from PySide6.QtCore import Qt
        from db import Session
        from models import Category

        with Session() as session:
            cats = {c.id: c.name for c in session.query(Category).all()}

        all_results = search_all_periods(query)
        self._search_input.clear()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Recherche : {query!r}")
        dlg.setMinimumSize(820, 560)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # ── Filtres ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        type_combo = QComboBox()
        type_combo.addItems(["Tous", "Revenus", "Dépenses"])
        type_combo.setMinimumHeight(32)
        type_combo.setFixedWidth(110)

        cat_filter = QComboBox()
        cat_filter.setMinimumHeight(32)
        cat_filter.setFixedWidth(140)
        cat_filter.addItem("Toutes catégories", None)
        for cid, cname in sorted(cats.items(), key=lambda x: x[1]):
            cat_filter.addItem(cname, cid)

        min_input = QLineEdit()
        min_input.setPlaceholderText("Montant min (€)")
        min_input.setValidator(QDoubleValidator(0, 9999999, 2))
        min_input.setMinimumHeight(32)
        min_input.setFixedWidth(130)

        max_input = QLineEdit()
        max_input.setPlaceholderText("Montant max (€)")
        max_input.setValidator(QDoubleValidator(0, 9999999, 2))
        max_input.setMinimumHeight(32)
        max_input.setFixedWidth(130)

        self._sr_count = QLabel()
        self._sr_count.setStyleSheet("font-size:12px; color:#848c94;")

        btn_filter = QPushButton("  Filtrer")
        btn_filter.setMinimumHeight(32)
        btn_filter.setFixedWidth(90)

        filter_row.addWidget(QLabel("Type :"))
        filter_row.addWidget(type_combo)
        filter_row.addWidget(cat_filter)
        filter_row.addWidget(min_input)
        filter_row.addWidget(max_input)
        filter_row.addWidget(btn_filter)
        filter_row.addStretch()
        filter_row.addWidget(self._sr_count)
        vl.addLayout(filter_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background:#2e3238; max-height:1px; border:none;")
        vl.addWidget(sep)

        # ── Tableau ──
        tbl = QTableWidget(0, 5)
        tbl.setHorizontalHeaderLabels(["Date", "Type", "Montant", "Catégorie", "Description"])
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.verticalHeader().setDefaultSectionSize(34)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed); tbl.setColumnWidth(0, 100)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed); tbl.setColumnWidth(1, 90)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed); tbl.setColumnWidth(2, 110)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed); tbl.setColumnWidth(3, 150)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        tbl.setStyleSheet(
            "QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }"
            "QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }"
            "QTableWidget::item:alternate { background:#202428; }"
            "QHeaderView::section { background:#292d32; color:#7a8494; border:none; "
            "border-bottom:1px solid #3a3f47; padding:6px 8px; }"
        )
        vl.addWidget(tbl, 1)

        def _populate(results):
            tbl.setRowCount(len(results))
            for i, t in enumerate(results):
                color = QColor("#22c55e") if t.type == "income" else QColor("#ef4444")
                sign  = "+" if t.type == "income" else "-"
                ttype = "Revenu" if t.type == "income" else "Dépense"
                tbl.setItem(i, 0, QTableWidgetItem(t.date.strftime("%d/%m/%Y")))
                ti = QTableWidgetItem(ttype); ti.setForeground(color)
                tbl.setItem(i, 1, ti)
                ai = QTableWidgetItem(f"{sign}{format_money(t.amount)}")
                ai.setForeground(color); ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tbl.setItem(i, 2, ai)
                tbl.setItem(i, 3, QTableWidgetItem(cats.get(t.category_id, "—")))
                ni = QTableWidgetItem(t.note or ""); ni.setForeground(QColor("#7a8494"))
                tbl.setItem(i, 4, ni)
            self._sr_count.setText(f"{len(results)} résultat(s)")

        def _apply_filters():
            filtered = list(all_results)
            ttype = type_combo.currentText()
            if ttype == "Revenus":
                filtered = [t for t in filtered if t.type == "income"]
            elif ttype == "Dépenses":
                filtered = [t for t in filtered if t.type == "expense"]
            try:
                mn = float(min_input.text().replace(",", "."))
                filtered = [t for t in filtered if t.amount >= mn]
            except ValueError:
                pass
            try:
                mx = float(max_input.text().replace(",", "."))
                filtered = [t for t in filtered if t.amount <= mx]
            except ValueError:
                pass
            _populate(filtered)

        btn_filter.clicked.connect(_apply_filters)
        _populate(all_results)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)
        dlg.exec()

    def _restart_lock_timer(self):
        """Relit le délai dans les paramètres et (re)démarre le timer."""
        from services.settings_service import load_settings
        minutes = load_settings().get("lock_after_minutes", 0)
        if minutes and minutes > 0:
            self._lock_timer.start(minutes * 60 * 1000)
        else:
            self._lock_timer.stop()

    def eventFilter(self, obj, event):
        """Remet à zéro le timer d'inactivité à chaque interaction."""
        from PySide6.QtCore import QEvent
        if event.type() in (
            QEvent.MouseMove, QEvent.MouseButtonPress,
            QEvent.KeyPress, QEvent.Wheel,
        ):
            if self._lock_timer.isActive():
                self._lock_timer.start(self._lock_timer.interval())
        return super().eventFilter(obj, event)

    def _auto_lock(self):
        """Verrouille l'appli après inactivité — redemande le mot de passe."""
        from ui.password_dialog import PasswordDialog, is_password_set
        if not is_password_set():
            return
        self.hide()
        dlg = PasswordDialog()
        if dlg.exec() != PasswordDialog.Accepted:
            QApplication.quit()
            return
        self.show()
        self.activateWindow()
        self._restart_lock_timer()

    def _on_update_checked(self, available, latest, notes):
        """Appelé depuis le thread de fond — émet un signal vers le thread principal."""
        if available and latest:
            self._update_signal.emit(latest)

    def _show_update_toast(self, latest: str):
        """Appelé sur le thread principal via le signal."""
        from ui.toast import Toast
        Toast.show(self,
            f"Mise a jour disponible : v{latest} — Voir A propos",
            kind='warning'
        )

    def _notify_upcoming_recurring(self):
        """Affiche une notification Windows pour chaque récurrente proche."""
        try:
            from services.recurring_service import get_upcoming_recurring
            from utils.formatters import format_money as _fmt
            upcoming = get_upcoming_recurring()
            if not upcoming:
                return
            if len(upcoming) == 1:
                r = upcoming[0]
                msg = f"{r['label']} — {_fmt(r['amount'])} dans {r['days_until']} jour(s)"
            else:
                msg = f"{len(upcoming)} échéances à venir ce mois"
            self._tray.showMessage(
                "Foyio — Rappel récurrentes",
                msg,
                QIcon(os.path.join(BASE_DIR, "icons", "foyio_logo.png")),
                5000
            )
        except Exception:
            pass

    def closeEvent(self, event):
        """Minimiser dans le systray au lieu de fermer."""
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "Foyio",
            "L'application tourne en arrière-plan.\nDouble-cliquez sur l'icône pour la rouvrir.",
            QIcon(os.path.join(BASE_DIR, "icons", "foyio_logo.png")),
            2500
        )

    def _on_tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def _confirm_quit(self):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Quitter Foyio")
        msg.setText("Voulez-vous quitter l'application ?")
        btn_ok = msg.addButton("Quitter", QMessageBox.AcceptRole)
        msg.addButton("Annuler", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == btn_ok:
            import sys
            sys.exit(0)

    def _go_prev(self):
        period_state.prev()
        self._on_period_changed()

    def _go_next(self):
        period_state.next_period()
        self._on_period_changed()

    def _go_today(self):
        from datetime import datetime
        now = datetime.now()
        period_state.set_period(now.year, now.month)
        self._on_period_changed()

    def _on_period_changed(self):
        self.period_label.setText(period_state.label())
        self._update_period_buttons()
        self.refresh_all()

    def _update_period_buttons(self):
        is_current = period_state.is_current_month()
        self.btn_next.setEnabled(not is_current)
        self.btn_today.setEnabled(not is_current)

    # ------------------------------------------------------------------
    def _open_bank_url(self):
        """Ouvre l'espace client bancaire du compte actif dans le navigateur."""
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        from services.account_service import get_accounts

        acc_id = account_state.get_id()
        accounts = get_accounts()
        acc = next((a for a in accounts if a.id == acc_id), None)

        if acc and getattr(acc, 'url', None):
            QDesktopServices.openUrl(QUrl(acc.url))
        else:
            # Pas d'URL configurée → ouvrir directement le dialogue de saisie
            self.set_active(7)  # aller sur la vue Comptes
            if hasattr(self, 'accounts'):
                self.accounts._edit_url(acc) if acc else None

    def _reload_accounts(self):
        """Recharge la liste des comptes dans le combo."""
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        accounts = account_state.get_all_accounts()
        for acc in accounts:
            self.account_combo.addItem(acc.name, acc.id)
            if acc.id == account_state.get_id():
                self.account_combo.setCurrentIndex(self.account_combo.count() - 1)
        self.account_combo.blockSignals(False)

    def _on_account_changed(self, index):
        acc_id   = self.account_combo.currentData()
        acc_name = self.account_combo.currentText()
        if acc_id:
            account_state.set_account(acc_id, acc_name)
            self.refresh_all()

    def toggle_sidebar(self):
        expanded = self.sidebar_expanded
        end_width = 60 if expanded else 220
        labels = ["", "", "", "", "", "", "", "", "", "", ""] if expanded else [
            " Accueil", " Transactions", " Budgets",
            " Catégories", " Statistiques", " Récurrentes",
            " Épargne", " Comptes", " Outils", " Paramètres", " À propos"
        ]
        for btn, label in zip(self._nav_buttons, labels):
            btn.setText(label)
        # Cacher le texte logo quand réduit
        if hasattr(self, "_logo_text"):
            self._logo_text.setVisible(not expanded)
        if hasattr(self, "_btn_quit"):
            self._btn_quit.setText('' if expanded else '  Quitter')

        self.animation = QPropertyAnimation(self.sidebar_widget, b"minimumWidth")
        self.animation.setDuration(200)
        self.animation.setStartValue(self.sidebar_widget.width())
        self.animation.setEndValue(end_width)
        self.animation.start()
        self.sidebar_expanded = not expanded

    def set_active(self, index):
        titles = [
            ("home.png",         "Accueil"),
            ("transactions.png", "Transactions"),
            ("budget.png",       "Budgets"),
            ("categories.png",   "Catégories"),
            ("stats.png",        "Statistiques"),
            ("transactions.png", "Récurrentes"),
            ("epargne.png",      "Épargne"),
            ("bank.png",         "Comptes"),
            ("money.png",        "Prêts"),
            ("stats.png",        "Outils"),
            ("other.png",        "Paramètres"),
            ("other.png",        "Fonctionnalités"),
            ("other.png",        "À propos"),
        ]
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

        # Transition fondu
        current_widget = self.stack.currentWidget()
        if current_widget:
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            from PySide6.QtCore import QPropertyAnimation, QEasingCurve
            effect = QGraphicsOpacityEffect(current_widget)
            current_widget.setGraphicsEffect(effect)
            self._fade_out_anim = QPropertyAnimation(effect, b"opacity")
            self._fade_out_anim.setDuration(120)
            self._fade_out_anim.setStartValue(1.0)
            self._fade_out_anim.setEndValue(0.0)
            self._fade_out_anim.setEasingCurve(QEasingCurve.OutCubic)
            def do_switch():
                self.stack.setCurrentIndex(index)
                new_w = self.stack.currentWidget()
                if new_w:
                    from PySide6.QtWidgets import QGraphicsOpacityEffect
                    eff2 = QGraphicsOpacityEffect(new_w)
                    new_w.setGraphicsEffect(eff2)
                    self._fade_in_anim = QPropertyAnimation(eff2, b"opacity")
                    self._fade_in_anim.setDuration(180)
                    self._fade_in_anim.setStartValue(0.0)
                    self._fade_in_anim.setEndValue(1.0)
                    self._fade_in_anim.setEasingCurve(QEasingCurve.InCubic)
                    self._fade_in_anim.start()
            self._fade_out_anim.finished.connect(do_switch)
            self._fade_out_anim.start()
        else:
            self.stack.setCurrentIndex(index)

        icon_name, text = titles[index]
        self.title_icon.setPixmap(
            QIcon(os.path.join(BASE_DIR, "icons", icon_name)).pixmap(24, 24)
        )
        self.title_text.setText(text)

    def _update_sidebar_badges(self):
        """Met à jour les badges de notification dans la sidebar."""
        try:
            from services.dashboard_service import budget_alerts
            from services.recurring_service import get_overdue_recurring, get_upcoming_recurring
            alerts  = budget_alerts()
            overdue = get_overdue_recurring()
            upcoming = get_upcoming_recurring(3)

            # Badge Budgets
            n_budget = len(alerts)
            if hasattr(self, "btn_budget"):
                if n_budget > 0:
                    self.btn_budget.setText(f" Budgets ({n_budget})")
                else:
                    self.btn_budget.setText(" Budgets")

            # Badge Récurrentes
            n_rec = len(overdue) + len(upcoming)
            if hasattr(self, "btn_recurring"):
                if n_rec > 0:
                    self.btn_recurring.setText(f" Récurrentes ({n_rec})")
                else:
                    self.btn_recurring.setText(" Récurrentes")
        except Exception:
            pass

    def refresh_all(self):
        self._update_sidebar_badges()
        if hasattr(self, "accueil"):      self.accueil.refresh()
        if hasattr(self, "transactions"): self.transactions.load()
        if hasattr(self, "categories"):   self.categories.load()
        if hasattr(self, "stats"):        self.stats.refresh()
        if hasattr(self, "budget"):       self.budget.refresh()
        if hasattr(self, "recurring"):    self.recurring.load()




# ──────────────────────────────────────────────────────────────
# Raccourci clavier global Windows — Ctrl+Shift+F
# ──────────────────────────────────────────────────────────────
try:
    import ctypes, ctypes.wintypes
    from PySide6.QtCore import QAbstractNativeEventFilter

    class _GlobalHotkeyFilter(QAbstractNativeEventFilter):
        _ID       = 9742          # identifiant arbitraire
        _MOD_CTRL = 0x0002
        _MOD_SHFT = 0x0004
        _VK_F     = 0x46          # touche F
        _WM_HOTKEY = 0x0312

        def __init__(self, callback):
            super().__init__()
            self._cb = callback
            ctypes.windll.user32.RegisterHotKey(
                None, self._ID,
                self._MOD_CTRL | self._MOD_SHFT,
                self._VK_F,
            )

        def nativeEventFilter(self, eventType, message):
            if eventType == b"windows_generic_MSG":
                try:
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                    if msg.message == self._WM_HOTKEY and msg.wParam == self._ID:
                        self._cb()
                except Exception:
                    pass
            return False, 0

        def unregister(self):
            ctypes.windll.user32.UnregisterHotKey(None, self._ID)

    _HOTKEY_AVAILABLE = True
except Exception:
    _HOTKEY_AVAILABLE = False


def main():
    # Supprimer les avertissements Qt sur les polices système
    os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts=false"

    backup_database()
    Base.metadata.create_all(engine)
    from db import migrate_database
    migrate_database()
    init_categories()
    migrate_category_icons()
    init_accounts()
    init_savings_categories()
    migrate_transactions_to_default_account()
    account_state.init_default()
    apply_recurring()

    # Nettoyer les règles de reconnaissance mal apprises
    try:
        from services.transaction_recognition import clean_bad_rules
        clean_bad_rules()
    except Exception:
        pass

    # Sync automatique épargne ↔ transactions
    try:
        from services.savings_service import sync_savings_from_transactions
        sync_savings_from_transactions()
    except Exception:
        pass

    # ── AppUserModelID Windows (icône correcte dans la barre des tâches) ──
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Foyio.App.1")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QLocale.setDefault(QLocale(QLocale.French, QLocale.France))
    app.setStyleSheet(BANK_THEME)

    # Icône .ico pour une meilleure résolution dans la barre des tâches / Alt+Tab
    _ico_path = os.path.join(BASE_DIR, "icons", "foyio.ico")
    if os.path.exists(_ico_path):
        app.setWindowIcon(QIcon(_ico_path))

    # ── Splash screen ──
    from PySide6.QtWidgets import QSplashScreen
    from PySide6.QtGui import QPixmap, QPainter, QFont, QColor
    from PySide6.QtCore import Qt, QTimer

    _logo_path = os.path.join(BASE_DIR, "icons", "foyio_logo.png")
    _splash_pix = QPixmap(_logo_path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    splash = QSplashScreen(_splash_pix, Qt.WindowStaysOnTopHint)
    splash.setFixedSize(200, 220)
    splash.show()
    splash.showMessage(
        "Chargement…",
        Qt.AlignHCenter | Qt.AlignBottom,
        QColor("#c8cdd4")
    )
    app.processEvents()

    # ── Authentification ──
    pwd_dlg = PasswordDialog()
    splash.finish(pwd_dlg)
    if pwd_dlg.exec() != PasswordDialog.Accepted:
        sys.exit(0)  # Fenêtre fermée sans authentification

    window = MainWindow()
    window.showMaximized()

    # ── Raccourci global Ctrl+Shift+F ──
    _hotkey = None
    if _HOTKEY_AVAILABLE:
        def _bring_to_front():
            window.showNormal()
            window.activateWindow()
            window.raise_()
        try:
            _hotkey = _GlobalHotkeyFilter(_bring_to_front)
            app.installNativeEventFilter(_hotkey)
        except Exception:
            pass

    ret = app.exec()
    if _hotkey:
        _hotkey.unregister()
    sys.exit(ret)


if __name__ == "__main__":
    main()
