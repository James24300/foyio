# No Qt parent needed — mixed into CryptoView which is a QWidget
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis, QAreaSeries,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen

from services.crypto_service import get_price_history


class _CryptoHistoryMixin:

    def _on_portfolio_double_click(self, row: int, _col: int):
        item = self._portfolio_table.item(row, 1)
        if not item:
            return
        holding_id = item.data(Qt.UserRole)
        h = next((x for x in self._holdings if x.id == holding_id), None)
        if h:
            self._dialog_history(h)

    def _dialog_history(self, h):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        info  = self._prices.get(h.coingecko_id, {})
        price = info.get("price", 0)
        chg   = info.get("change_24h", 0)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"{h.name} ({h.symbol})")
        dlg.setMinimumSize(600, 460)
        dlg.setStyleSheet("background:#1e2124; color:#c8cdd4;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        # En-tête
        header = QHBoxLayout()
        name_lbl = QLabel(f"{h.name}  <span style='color:#7a8494;font-size:13px;'>({h.symbol})</span>")
        name_lbl.setStyleSheet("font-size:18px; font-weight:700; color:#e0e4ea;")
        name_lbl.setTextFormat(Qt.RichText)
        header.addWidget(name_lbl)
        header.addStretch()

        chg_color = "#22c55e" if chg >= 0 else "#ef4444"
        chg_sign  = "+" if chg >= 0 else ""
        price_lbl = QLabel(
            f"<span style='font-size:20px; font-weight:700; color:#e0e4ea;'>"
            f"{price:,.2f} €</span>"
            f"  <span style='font-size:13px; color:{chg_color};'>"
            f"{chg_sign}{chg:.2f}% 24h</span>"
        )
        price_lbl.setTextFormat(Qt.RichText)
        header.addWidget(price_lbl)
        vl.addLayout(header)

        # Infos holding
        pnl   = h.quantity * price - h.quantity * h.avg_buy_price
        pnl_p = (pnl / (h.quantity * h.avg_buy_price) * 100) if h.avg_buy_price > 0 else 0
        pnl_c = "#22c55e" if pnl >= 0 else "#ef4444"
        pnl_s = "+" if pnl >= 0 else ""
        info_row = QHBoxLayout()
        for label, value in [
            ("Quantité",     f"{h.quantity:,.8f}".rstrip("0").rstrip(".")),
            ("Prix moyen",   f"{h.avg_buy_price:,.2f} €"),
            ("Valeur",       f"{h.quantity * price:,.2f} €"),
            ("P&L",          f"{pnl_s}{pnl:,.2f} € ({pnl_s}{pnl_p:.1f}%)"),
        ]:
            card = QLabel(f"<div style='color:#7a8494;font-size:10px;'>{label}</div>"
                          f"<div style='color:{'#c8cdd4' if label != 'P&L' else pnl_c};"
                          f"font-size:13px;font-weight:600;'>{value}</div>")
            card.setTextFormat(Qt.RichText)
            card.setStyleSheet("background:#26292e; border-radius:8px; padding:10px 14px;")
            info_row.addWidget(card)
        vl.addLayout(info_row)

        # Sélecteur de période
        period_row = QHBoxLayout()
        period_row.addStretch()
        _period_btns: dict[int, QPushButton] = {}
        _current_days = [30]

        chart_view = QChartView()
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setStyleSheet("background:transparent; border:none;")
        chart_view.setMinimumHeight(220)

        def _load_chart(days: int):
            _current_days[0] = days
            for d, b in _period_btns.items():
                b.setChecked(d == days)

            import threading
            result = [None]
            done_event = __import__("threading").Event()

            def _worker():
                result[0] = get_price_history(h.coingecko_id, days)
                done_event.set()

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            # Attente non-bloquante via QTimer
            def _check():
                if not done_event.is_set():
                    QTimer.singleShot(50, _check)
                    return
                _draw(result[0] or [])
            QTimer.singleShot(50, _check)

        def _draw(history):
            if len(history) < 2:
                return
            series = QLineSeries()
            pen = QPen(QColor("#3b82f6"))
            pen.setWidth(2)
            series.setPen(pen)
            for ts_ms, p in history:
                series.append(ts_ms, p)
            # Aire sous la courbe
            zero = QLineSeries()
            for ts_ms, _ in history:
                zero.append(ts_ms, 0)
            area = QAreaSeries(series, zero)
            from PySide6.QtGui import QLinearGradient, QGradient
            grad = QLinearGradient(0, 0, 0, 1)
            grad.setCoordinateMode(QGradient.ObjectMode)
            grad.setColorAt(0.0, QColor(59, 130, 246, 80))
            grad.setColorAt(1.0, QColor(59, 130, 246, 0))
            area.setBrush(grad)
            area.setPen(QPen(Qt.NoPen))

            chart = QChart()
            chart.addSeries(area)
            chart.addSeries(series)
            chart.setBackgroundBrush(QColor("#1e2124"))
            chart.setBackgroundRoundness(0)
            chart.legend().hide()
            chart.layout().setContentsMargins(0, 0, 0, 0)

            days = _current_days[0]
            ax = QDateTimeAxis()
            ax.setFormat("dd/MM" if days <= 90 else "MMM yy")
            ax.setLabelsColor(QColor("#7a8494"))
            ax.setGridLineColor(QColor("#2e3238"))
            ax.setTickCount(min(6, len(history)))
            chart.addAxis(ax, Qt.AlignBottom)
            series.attachAxis(ax)
            area.attachAxis(ax)

            prices_only = [p for _, p in history]
            ay = QValueAxis()
            ay.setRange(min(prices_only) * 0.97, max(prices_only) * 1.03)
            ay.setLabelsColor(QColor("#7a8494"))
            ay.setGridLineColor(QColor("#2e3238"))
            ay.setLabelFormat("%.2f €")
            ay.setTickCount(4)
            chart.addAxis(ay, Qt.AlignLeft)
            series.attachAxis(ay)
            area.attachAxis(ay)

            chart_view.setChart(chart)
            # Garder les références pour éviter GC
            chart_view._series = series
            chart_view._area   = area
            chart_view._zero   = zero

        for label, days in [("7J", 7), ("30J", 30), ("90J", 90), ("1AN", 365)]:
            btn = QPushButton(label)
            btn.setFixedSize(52, 26)
            btn.setCheckable(True)
            btn.setChecked(days == 30)
            btn.setStyleSheet("""
                QPushButton { background:#26292e; color:#7a8494; border:1px solid #3a3f47;
                    border-radius:6px; font-size:11px; font-weight:600; }
                QPushButton:hover { color:#c8cdd4; }
                QPushButton:checked { background:#3b82f6; color:#fff; border:none; }
            """)
            btn.clicked.connect(lambda _, d=days: _load_chart(d))
            period_row.addWidget(btn)
            _period_btns[days] = btn

        vl.addLayout(period_row)
        vl.addWidget(chart_view, 1)

        btn_close = QPushButton("Fermer")
        btn_close.setMinimumHeight(34)
        btn_close.clicked.connect(dlg.accept)
        vl.addWidget(btn_close)

        _load_chart(30)
        dlg.exec()
