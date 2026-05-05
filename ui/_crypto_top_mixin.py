# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDialog, QDoubleSpinBox, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from services.crypto_service import add_holding, link_to_transaction
from services.watchlist_service import add_to_watchlist, is_in_watchlist
from ui.toast import Toast
from ui.crypto_threads import _TopFetcher


class _CryptoTopMixin:

    # ── Onglet Top Cryptos ────────────────────────────────────────────────────
    def _build_top_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # Barre de recherche + bouton refresh
        top_bar = QHBoxLayout()
        self._top_search = QLineEdit()
        self._top_search.setPlaceholderText("Filtrer par nom ou symbole…")
        self._top_search.setMinimumHeight(34)
        self._top_search.setStyleSheet(
            "background:#26292e; border:1px solid #3a3f47; border-radius:8px;"
            "color:#c8cdd4; padding:0 10px; font-size:12px;"
        )
        self._top_search.textChanged.connect(self._filter_top_table)
        top_bar.addWidget(self._top_search)

        btn_refresh_top = QPushButton("Actualiser")
        btn_refresh_top.setMinimumHeight(34)
        btn_refresh_top.setStyleSheet(
            "background:#26292e; color:#c8cdd4; border:1px solid #3a3f47;"
            "border-radius:8px; padding:0 14px; text-align:center;"
        )
        btn_refresh_top.clicked.connect(self._fetch_top)
        top_bar.addWidget(btn_refresh_top)
        vl.addLayout(top_bar)

        # Tableau
        self._top_table = QTableWidget(0, 6)
        self._top_table.setHorizontalHeaderLabels([
            "#", "Crypto", "Prix (€)", "24h %", "Cap. marché (€)", "Action"
        ])
        self._top_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._top_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._top_table.setShowGrid(False)
        self._top_table.verticalHeader().setVisible(False)
        self._top_table.verticalHeader().setDefaultSectionSize(42)
        hdr = self._top_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed);  self._top_table.setColumnWidth(0, 40)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed);  self._top_table.setColumnWidth(2, 130)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed);  self._top_table.setColumnWidth(3, 90)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed);  self._top_table.setColumnWidth(4, 160)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed);  self._top_table.setColumnWidth(5, 200)
        self._top_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._top_table, 1)

        self._top_loading = QLabel("Chargement…")
        self._top_loading.setAlignment(Qt.AlignCenter)
        self._top_loading.setStyleSheet("color:#7a8494; font-size:13px;")
        vl.addWidget(self._top_loading)
        self._top_loading.hide()

        self._top_data: list = []
        return w

    def _on_tab_changed(self, index: int):
        # Index 2 = Top Cryptos ; Index 3 = Watchlist
        if index == 2 and not self._top_data:
            self._fetch_top()
        elif index == 3:
            self._load_watchlist()

    def _fetch_top(self):
        self._top_loading.show()
        self._top_table.setRowCount(0)
        self._top_fetcher = _TopFetcher()
        self._top_fetcher.done.connect(self._on_top_received)
        self._start_thread(self._top_fetcher)

    def _on_top_received(self, coins: list):
        self._top_loading.hide()
        self._top_data = coins
        self._populate_top_table(coins)

    def _filter_top_table(self, text: str):
        q = text.lower()
        filtered = [c for c in self._top_data
                    if q in c["name"].lower() or q in c["symbol"].lower()] if q else self._top_data
        self._populate_top_table(filtered)

    def _populate_top_table(self, coins: list):
        tbl = self._top_table
        tbl.setRowCount(len(coins))
        for i, c in enumerate(coins):
            chg   = c.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""

            rank = QTableWidgetItem(str(i + 1))
            rank.setTextAlignment(Qt.AlignCenter)
            rank.setForeground(QColor("#5a6472"))
            tbl.setItem(i, 0, rank)

            name_item = QTableWidgetItem(f"{c['name']}  ({c['symbol']})")
            name_item.setData(Qt.UserRole, c)
            tbl.setItem(i, 1, name_item)

            price_item = QTableWidgetItem(f"{c['price']:,.4f} €" if c['price'] < 1 else f"{c['price']:,.2f} €")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 2, price_item)

            chg_item = QTableWidgetItem(f"{sign}{chg:.2f}%")
            chg_item.setTextAlignment(Qt.AlignCenter)
            chg_item.setForeground(QColor(color))
            tbl.setItem(i, 3, chg_item)

            mcap = c.get("market_cap", 0) or 0
            if mcap >= 1_000_000_000:
                mcap_str = f"{mcap/1_000_000_000:.1f} Md €"
            elif mcap >= 1_000_000:
                mcap_str = f"{mcap/1_000_000:.1f} M €"
            else:
                mcap_str = f"{mcap:,.0f} €"
            mcap_item = QTableWidgetItem(mcap_str)
            mcap_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 4, mcap_item)

            cell_w = QWidget()
            hl = QHBoxLayout(cell_w)
            hl.setContentsMargins(3, 3, 3, 3)
            hl.setSpacing(3)

            btn_add = QPushButton("+ Acheter")
            btn_add.setFixedHeight(28)
            btn_add.setFixedWidth(90)
            btn_add.setStyleSheet(
                "background:#22c55e; color:#000; border:none; border-radius:6px;"
                "font-size:11px; font-weight:700; text-align:center;"
            )
            btn_add.clicked.connect(lambda _, coin=c: self._quick_add_from_top(coin))

            already = is_in_watchlist(c["id"])
            btn_watch = QPushButton("✓ WL" if already else "👁 WL")
            btn_watch.setFixedHeight(28)
            btn_watch.setFixedWidth(76)
            btn_watch.setStyleSheet(
                f"background:{'#374151' if already else '#26292e'}; color:#c8cdd4;"
                "border:1px solid #3a3f47; border-radius:6px; font-size:11px; text-align:center;"
            )
            btn_watch.setEnabled(not already)
            btn_watch.clicked.connect(lambda _, coin=c, b=btn_watch: self._watch_from_top(coin, b))

            hl.addWidget(btn_add)
            hl.addWidget(btn_watch)
            tbl.setCellWidget(i, 5, cell_w)

    def _watch_from_top(self, coin: dict, btn: QPushButton):
        ok = add_to_watchlist(coin["id"], coin["symbol"], coin["name"])
        if ok:
            btn.setText("✓ WL")
            btn.setEnabled(False)
            btn.setStyleSheet("background:#374151; color:#c8cdd4; border:1px solid #3a3f47; border-radius:6px; font-size:10px;")
            self._load_watchlist()
            self._fetch_prices()
            Toast.show(self, f"✓  {coin['name']} ajouté à la watchlist", kind="success")
        else:
            Toast.show(self, f"✕  Déjà dans la watchlist", kind="error")

    def _quick_add_from_top(self, coin: dict):
        """Ouvre le dialog d'ajout pré-rempli avec la crypto sélectionnée."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Ajouter — {coin['name']}")
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        vl.addWidget(lbl(f"Crypto : {coin['name']} ({coin['symbol']})"))
        vl.addSpacing(4)

        qty_spin = QDoubleSpinBox()
        qty_spin.setRange(0.000001, 999999); qty_spin.setDecimals(8)
        qty_spin.setValue(1.0); qty_spin.setMinimumHeight(34)

        price_spin = QDoubleSpinBox()
        price_spin.setRange(0.000001, 9_999_999); price_spin.setDecimals(2)
        price_spin.setSuffix(" €"); price_spin.setValue(round(coin["price"], 2))
        price_spin.setMinimumHeight(34)

        chk_link = QCheckBox("Enregistrer comme dépense dans les transactions")
        chk_link.setChecked(False)
        chk_link.setStyleSheet("color:#c8cdd4; font-size:12px;")

        vl.addWidget(lbl("Quantité :")); vl.addWidget(qty_spin)
        vl.addWidget(lbl("Prix d'achat unitaire :")); vl.addWidget(price_spin)
        vl.addWidget(chk_link)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Ajouter")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet("background:#22c55e; color:#000; border:none; border-radius:8px; font-weight:700;")
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do():
            qty = qty_spin.value(); price = price_spin.value()
            holding_id = add_holding(coin["symbol"], coin["name"], coin["id"], qty, price)
            if chk_link.isChecked():
                link_to_transaction(qty * price, "expense",
                                    f"Achat {qty} {coin['symbol']} à {price:.2f} €",
                                    holding_id=holding_id)
            dlg.accept(); self.load()
            Toast.show(self, f"✓  {coin['name']} ajouté au portefeuille", kind="success")

        btn_ok.clicked.connect(_do)
        dlg.exec()
