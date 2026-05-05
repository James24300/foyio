# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QDialog, QLineEdit, QComboBox, QCheckBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from services.crypto_service import add_holding, link_to_transaction, get_prices
from services.watchlist_service import (
    get_watchlist, add_to_watchlist, remove_from_watchlist,
)
from ui.toast import Toast
from ui.crypto_threads import _SearchThread


class _CryptoWatchlistMixin:

    # ── Onglet Watchlist ──────────────────────────────────────────────────────
    def _build_watchlist_tab(self):
        w = QWidget()
        vl = QVBoxLayout(w)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        bar = QHBoxLayout()
        btn_add_watch = QPushButton("Ajouter à la watchlist")
        btn_add_watch.setMinimumHeight(36)
        btn_add_watch.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px;"
            "font-weight:700; padding:0 16px; text-align:center;"
        )
        btn_add_watch.clicked.connect(self._dialog_add_watchlist)
        bar.addWidget(btn_add_watch)
        bar.addStretch()
        vl.addLayout(bar)

        self._wl_table = QTableWidget(0, 6)
        self._wl_table.setHorizontalHeaderLabels([
            "Crypto", "Prix (€)", "24h %", "Note", "Depuis", "Action"
        ])
        self._wl_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._wl_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._wl_table.setShowGrid(False)
        self._wl_table.verticalHeader().setVisible(False)
        self._wl_table.verticalHeader().setDefaultSectionSize(46)
        hdr = self._wl_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed); self._wl_table.setColumnWidth(1, 130)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed); self._wl_table.setColumnWidth(2, 90)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed); self._wl_table.setColumnWidth(3, 160)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed); self._wl_table.setColumnWidth(4, 100)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed); self._wl_table.setColumnWidth(5, 170)
        self._wl_table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 8px; }
            QTableWidget::item:selected { background:#26292e; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:6px 8px; font-size:11px; }
        """)
        vl.addWidget(self._wl_table, 1)
        return w

    def _load_watchlist(self):
        items = get_watchlist()
        tbl = self._wl_table
        tbl.setRowCount(len(items))
        for i, item in enumerate(items):
            info  = self._prices.get(item.coingecko_id, {})
            price = info.get("price", 0)
            chg   = info.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""

            tbl.setItem(i, 0, QTableWidgetItem(f"{item.name}  ({item.symbol})"))

            price_str = (f"{price:,.4f} €" if price and price < 1 else f"{price:,.2f} €") if price else "—"
            p_item = QTableWidgetItem(price_str)
            p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tbl.setItem(i, 1, p_item)

            chg_item = QTableWidgetItem(f"{sign}{chg:.2f}%" if price else "—")
            chg_item.setTextAlignment(Qt.AlignCenter)
            chg_item.setForeground(QColor(color))
            tbl.setItem(i, 2, chg_item)

            tbl.setItem(i, 3, QTableWidgetItem(item.note or ""))
            tbl.setItem(i, 4, QTableWidgetItem(item.added_at.strftime("%d/%m/%Y")))

            btn_row = QHBoxLayout()
            btn_buy = QPushButton("Acheter")
            btn_buy.setMinimumWidth(72)
            btn_buy.setFixedHeight(30)
            btn_buy.setStyleSheet(
                "background:#22c55e; color:#000; border:none; border-radius:6px;"
                "font-size:12px; font-weight:700; text-align:center;"
            )
            btn_buy.clicked.connect(lambda _, it=item: self._buy_from_watchlist(it))

            btn_del = QPushButton("Retirer")
            btn_del.setMinimumWidth(66)
            btn_del.setFixedHeight(30)
            btn_del.setStyleSheet(
                "background:#2e2020; color:#e89090; border:1px solid #503030;"
                "border-radius:6px; font-size:12px; text-align:center;"
            )
            btn_del.clicked.connect(lambda _, it=item: self._remove_watchlist(it))

            cell_w = QWidget()
            hl = QHBoxLayout(cell_w)
            hl.setContentsMargins(4, 6, 4, 6)
            hl.setSpacing(4)
            hl.addWidget(btn_buy)
            hl.addWidget(btn_del)
            tbl.setCellWidget(i, 5, cell_w)

    def _refresh_watchlist_prices(self):
        """Met à jour uniquement les colonnes prix/variation sans recharger tout."""
        if not hasattr(self, "_wl_table"):
            return
        items = get_watchlist()
        tbl = self._wl_table
        if tbl.rowCount() != len(items):
            self._load_watchlist()
            return
        for i, item in enumerate(items):
            info  = self._prices.get(item.coingecko_id, {})
            price = info.get("price", 0)
            chg   = info.get("change_24h", 0) or 0
            color = "#22c55e" if chg >= 0 else "#ef4444"
            sign  = "+" if chg >= 0 else ""
            price_str = (f"{price:,.4f} €" if price < 1 else f"{price:,.2f} €") if price else "—"
            if tbl.item(i, 1):
                tbl.item(i, 1).setText(price_str)
            if tbl.item(i, 2):
                tbl.item(i, 2).setText(f"{sign}{chg:.2f}%" if price else "—")
                tbl.item(i, 2).setForeground(QColor(color))

    def _dialog_add_watchlist(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
        dlg = QDialog(self)
        dlg.setWindowTitle("Ajouter à la watchlist")
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(10)

        def lbl(t):
            l = QLabel(t); l.setStyleSheet("font-size:11px; color:#7a8494;"); return l

        search_row = QHBoxLayout()
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Rechercher : Bitcoin, ETH…")
        search_edit.setMinimumHeight(34)
        btn_search = QPushButton("Rechercher")
        btn_search.setMinimumHeight(34)
        search_row.addWidget(search_edit); search_row.addWidget(btn_search)
        vl.addWidget(lbl("Recherche :")); vl.addLayout(search_row)

        result_combo = QComboBox(); result_combo.setMinimumHeight(34)
        vl.addWidget(lbl("Résultats :")); vl.addWidget(result_combo)

        note_edit = QLineEdit()
        note_edit.setPlaceholderText("Note (optionnel)")
        note_edit.setMinimumHeight(34)
        vl.addWidget(lbl("Note :")); vl.addWidget(note_edit)

        _wl_search_thread = [None]

        def _on_wl_search_done(results):
            btn_search.setEnabled(True)
            btn_search.setText("Rechercher")
            result_combo.clear()
            if not results:
                result_combo.addItem("Aucun résultat")
                return
            for r in results:
                result_combo.addItem(f"{r['name']} ({r['symbol']})", r)

        def _do_search():
            q = search_edit.text().strip()
            if not q:
                return
            btn_search.setEnabled(False)
            btn_search.setText("Recherche…")
            result_combo.clear()
            t = _SearchThread(q)
            _wl_search_thread[0] = t
            t.done.connect(_on_wl_search_done)
            t.start()

        btn_search.clicked.connect(_do_search)
        search_edit.returnPressed.connect(_do_search)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Ajouter à la watchlist")
        btn_ok.setMinimumHeight(36)
        btn_ok.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px; font-weight:700;"
        )
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setMinimumHeight(36)
        btn_row.addWidget(btn_ok); btn_row.addWidget(btn_cancel)
        vl.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)

        def _do_add():
            coin = result_combo.currentData()
            if not coin:
                Toast.show(self, "✕  Sélectionnez une crypto", kind="error"); return
            ok = add_to_watchlist(coin["id"], coin["symbol"], coin["name"], note_edit.text())
            if not ok:
                Toast.show(self, f"✕  {coin['name']} est déjà dans la watchlist", kind="error"); return
            dlg.accept()
            self._load_watchlist()
            self._fetch_prices()
            Toast.show(self, f"✓  {coin['name']} ajouté à la watchlist", kind="success")

        btn_ok.clicked.connect(_do_add)
        dlg.exec()

    def _remove_watchlist(self, item):
        remove_from_watchlist(item.id)
        self._load_watchlist()
        Toast.show(self, f"✓  {item.name} retiré de la watchlist", kind="success")

    def _buy_from_watchlist(self, item):
        """Ouvre le dialog d'achat pré-rempli depuis la watchlist."""
        price = self._prices.get(item.coingecko_id, {}).get("price", 0)
        coin  = {"id": item.coingecko_id, "symbol": item.symbol, "name": item.name, "price": price}
        self._quick_add_from_top(coin)
