# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QDialog, QSpinBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from services.crypto_service import compute_fifo_report
from ui.toast import Toast


class _CryptoFiscalMixin:

    # ── Rapport fiscal FIFO ──────────────────────────────────────────────────
    def _dialog_fifo_report(self):
        from datetime import date
        current_year = date.today().year

        dlg = QDialog(self)
        dlg.setWindowTitle("Rapport fiscal — Plus/moins-values FIFO")
        dlg.setMinimumSize(980, 580)
        dlg.setStyleSheet("""
            QDialog { background:#1e2023; color:#c8cdd4; }
            #fifoSummaryBar { background:#26292e; border-radius:10px; border:1px solid #3a3f47; }
            QSpinBox {
                background:#26292e; color:#c8cdd4;
                border:1px solid #3a3f47; border-radius:6px;
                padding:2px 8px; min-width:110px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width:16px; background:#3a3f47; border-radius:3px;
            }
        """)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(14)

        # Sélecteur d'année + bouton exporter
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        lbl_yr = QLabel("Année fiscale :")
        lbl_yr.setStyleSheet("font-size:12px; color:#7a8494;")
        top_row.addWidget(lbl_yr)

        year_spin = QSpinBox()
        year_spin.setRange(2015, current_year)
        year_spin.setValue(current_year - 1 if date.today().month < 6 else current_year)
        year_spin.setFixedWidth(110)
        year_spin.setFixedHeight(34)
        top_row.addWidget(year_spin)

        btn_calc = QPushButton("Calculer")
        btn_calc.setFixedHeight(34)
        btn_calc.setStyleSheet(
            "background:#3b82f6; color:#fff; border:none; border-radius:8px;"
            "font-weight:700; padding:0 16px; text-align:center;"
        )
        top_row.addWidget(btn_calc)

        btn_export_fifo = QPushButton("Exporter CSV")
        btn_export_fifo.setFixedHeight(34)
        btn_export_fifo.setStyleSheet(
            "background:#26292e; color:#c8cdd4; border:1px solid #3a3f47;"
            "border-radius:8px; padding:0 14px; text-align:center;"
        )
        btn_export_fifo.setEnabled(False)
        top_row.addWidget(btn_export_fifo)
        top_row.addStretch()
        vl.addLayout(top_row)

        # Barre résumé
        summary_bar = QWidget()
        summary_bar.setObjectName("fifoSummaryBar")
        summary_bar.setFixedHeight(72)
        sbl = QHBoxLayout(summary_bar)
        sbl.setContentsMargins(20, 10, 20, 10)
        sbl.setSpacing(40)

        def _summary_cell(title):
            col = QVBoxLayout()
            col.setSpacing(3)
            t = QLabel(title)
            t.setStyleSheet("font-size:10px; color:#5a6472; font-weight:600; background:transparent; border:none;")
            v = QLabel("—")
            v.setStyleSheet("font-size:15px; font-weight:700; color:#c8cdd4; background:transparent; border:none;")
            col.addWidget(t); col.addWidget(v)
            return col, v

        c1, lbl_gains   = _summary_cell("PLUS-VALUES")
        c2, lbl_losses  = _summary_cell("MOINS-VALUES")
        c3, lbl_net     = _summary_cell("NET IMPOSABLE")
        c4, lbl_nb_ops  = _summary_cell("OPÉRATIONS")
        for c in [c1, c2, c3, c4]:
            sbl.addLayout(c)
        sbl.addStretch()
        vl.addWidget(summary_bar)

        # Tableau des lots
        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels([
            "Crypto", "Qté vendue", "Date achat", "Prix achat unit.",
            "Date vente", "Prix vente unit.", "Coût total", "Gain / Perte"
        ])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(38)
        hdr = table.horizontalHeader()
        hdr.setMinimumSectionSize(100)
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for col_, w_ in [(1,100),(2,100),(3,120),(4,100),(5,120),(6,100),(7,100)]:
            hdr.setSectionResizeMode(col_, QHeaderView.Fixed)
            table.setColumnWidth(col_, w_)
        table.setStyleSheet("""
            QTableWidget { background:#1e2023; color:#c8cdd4; border:none; }
            QTableWidget::item { border-bottom:1px solid #292d32; padding:0 6px; }
            QHeaderView::section { background:#26292e; color:#7a8494; border:none;
                border-bottom:1px solid #3a3f47; padding:5px 8px; font-size:11px; }
        """)
        vl.addWidget(table, 1)

        # Avertissement légal
        disclaimer = QLabel(
            "Avertissement : ce rapport est fourni à titre indicatif. "
            "Consultez un conseiller fiscal pour votre déclaration officielle."
        )
        disclaimer.setStyleSheet("font-size:10px; color:#5a6472; font-style:italic;")
        disclaimer.setWordWrap(True)
        vl.addWidget(disclaimer)

        _report_data = [None]  # stockage pour l'export

        def _run_calc():
            year = year_spin.value()
            report = compute_fifo_report(year)
            _report_data[0] = report

            lots = report["lots"]
            table.setRowCount(0)
            for lot in lots:
                r = table.rowCount()
                table.insertRow(r)

                crypto_item = QTableWidgetItem(f"{lot['name']} ({lot['symbol']})")
                table.setItem(r, 0, crypto_item)

                qty_item = QTableWidgetItem(f"{lot['qty']:.6f}")
                qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 1, qty_item)

                buy_date_txt = lot["buy_date"].strftime("%d/%m/%Y") if lot["buy_date"] else "—"
                table.setItem(r, 2, QTableWidgetItem(buy_date_txt))

                buy_p_item = QTableWidgetItem(f"{lot['buy_price']:.4f} €")
                buy_p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 3, buy_p_item)

                sell_date_txt = lot["sell_date"].strftime("%d/%m/%Y") if lot["sell_date"] else "—"
                table.setItem(r, 4, QTableWidgetItem(sell_date_txt))

                sell_p_item = QTableWidgetItem(f"{lot['sell_price']:.4f} €")
                sell_p_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 5, sell_p_item)

                cost_item = QTableWidgetItem(f"{lot['buy_total']:.2f} €")
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, 6, cost_item)

                gain = lot["gain"]
                gain_item = QTableWidgetItem(
                    f"{'+'if gain>=0 else ''}{gain:.2f} €"
                )
                gain_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                gain_item.setForeground(
                    QColor("#22c55e") if gain >= 0 else QColor("#ef4444")
                )
                table.setItem(r, 7, gain_item)

            g = report["total_gains"]
            lo = report["total_losses"]
            net = report["net"]
            lbl_gains.setText(f"+{g:.2f} €")
            lbl_gains.setStyleSheet(
                "font-size:15px; font-weight:700; color:#22c55e; background:transparent; border:none;"
            )
            lbl_losses.setText(f"{lo:.2f} €")
            lbl_losses.setStyleSheet(
                "font-size:15px; font-weight:700; color:#ef4444; background:transparent; border:none;"
            )
            net_color = "#22c55e" if net >= 0 else "#ef4444"
            lbl_net.setText(f"{'+'if net>=0 else ''}{net:.2f} €")
            lbl_net.setStyleSheet(
                f"font-size:15px; font-weight:700; color:{net_color}; background:transparent; border:none;"
            )
            lbl_nb_ops.setText(str(len(lots)))
            lbl_nb_ops.setStyleSheet(
                "font-size:15px; font-weight:700; color:#c8cdd4; background:transparent; border:none;"
            )
            btn_export_fifo.setEnabled(bool(lots))

        def _export_fifo_csv():
            if not _report_data[0]:
                return
            from PySide6.QtWidgets import QFileDialog
            import csv
            year = year_spin.value()
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Exporter le rapport fiscal",
                f"rapport_fiscal_{year}.csv",
                "CSV (*.csv)"
            )
            if not path:
                return
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([
                    "Crypto", "Quantité vendue", "Date achat", "Prix achat unit. (€)",
                    "Date vente", "Prix vente unit. (€)",
                    "Coût d'achat total (€)", "Produit de vente (€)", "Gain / Perte (€)"
                ])
                for lot in _report_data[0]["lots"]:
                    w.writerow([
                        f"{lot['name']} ({lot['symbol']})",
                        f"{lot['qty']:.8f}",
                        lot["buy_date"].strftime("%d/%m/%Y") if lot["buy_date"] else "",
                        f"{lot['buy_price']:.4f}",
                        lot["sell_date"].strftime("%d/%m/%Y") if lot["sell_date"] else "",
                        f"{lot['sell_price']:.4f}",
                        f"{lot['buy_total']:.2f}",
                        f"{lot['sell_total']:.2f}",
                        f"{lot['gain']:.2f}",
                    ])
                r = _report_data[0]
                w.writerow([])
                w.writerow(["", "", "", "", "", "", "PLUS-VALUES", "", f"{r['total_gains']:.2f}"])
                w.writerow(["", "", "", "", "", "", "MOINS-VALUES", "", f"{r['total_losses']:.2f}"])
                w.writerow(["", "", "", "", "", "", "NET IMPOSABLE", "", f"{r['net']:.2f}"])
            Toast.show(self, f"Rapport exporté : {path}", "success")

        btn_calc.clicked.connect(_run_calc)
        btn_export_fifo.clicked.connect(_export_fifo_csv)
        _run_calc()  # calcul immédiat sur l'année sélectionnée
        dlg.exec()
