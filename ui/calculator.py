"""
Calculatrice flottante Foyio.
Accessible via raccourci Ctrl+K depuis n'importe quelle vue.
Style cohérent avec le thème gris bancaire.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QKeySequence, QShortcut


class Calculator(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calculatrice")
        self.setFixedSize(300, 460)
        self.setWindowFlags(Qt.Tool | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

        self._expr   = ""   # expression en cours
        self._result = ""   # dernier résultat
        self._new_num = False  # après = ou erreur

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.setStyleSheet("""
            QDialog {
                background: #1e2124;
                border-radius: 14px;
            }
            QPushButton {
                border-radius: 10px;
                font-size: 16px;
                font-weight: 600;
                border: none;
                min-height: 56px;
            }
            QPushButton:hover { opacity: 0.85; }
            QPushButton:pressed { opacity: 0.7; }
        """)

        # ── Écran ──
        screen = QVBoxLayout()
        screen.setSpacing(2)

        self._expr_lbl = QLabel("")
        self._expr_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._expr_lbl.setStyleSheet(
            "font-size:13px; color:#5a6472; background:transparent; padding:0 6px;"
        )
        self._expr_lbl.setFixedHeight(22)

        self._display = QLabel("0")
        self._display.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._display.setStyleSheet(
            "font-size:36px; font-weight:700; color:#e0e4ea; "
            "background:#13151a; border-radius:10px; padding:8px 14px;"
        )
        self._display.setFixedHeight(72)
        self._display.setWordWrap(False)

        screen.addWidget(self._expr_lbl)
        screen.addWidget(self._display)
        layout.addLayout(screen)

        # ── Grille de boutons ──
        grid = QGridLayout()
        grid.setSpacing(8)

        buttons = [
            # (texte, ligne, col, rowspan, colspan, style)
            ("C",   0, 0, 1, 1, "clear"),
            ("±",   0, 1, 1, 1, "op"),
            ("%",   0, 2, 1, 1, "op"),
            ("÷",   0, 3, 1, 1, "operator"),
            ("7",   1, 0, 1, 1, "num"),
            ("8",   1, 1, 1, 1, "num"),
            ("9",   1, 2, 1, 1, "num"),
            ("×",   1, 3, 1, 1, "operator"),
            ("4",   2, 0, 1, 1, "num"),
            ("5",   2, 1, 1, 1, "num"),
            ("6",   2, 2, 1, 1, "num"),
            ("−",   2, 3, 1, 1, "operator"),
            ("1",   3, 0, 1, 1, "num"),
            ("2",   3, 1, 1, 1, "num"),
            ("3",   3, 2, 1, 1, "num"),
            ("+",   3, 3, 1, 1, "operator"),
            ("0",   4, 0, 1, 2, "num"),
            (",",   4, 2, 1, 1, "num"),
            ("=",   4, 3, 1, 1, "equals"),
        ]

        styles = {
            "num":      "background:#292d32; color:#e0e4ea;",
            "op":       "background:#3e4550; color:#e0e4ea;",
            "clear":    "background:#3e4550; color:#ef4444;",
            "operator": "background:#3b5bdb; color:#ffffff;",
            "equals":   "background:#22c55e; color:#ffffff;",
        }

        for text, row, col, rs, cs, style in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet(styles[style])
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            btn.clicked.connect(lambda _, t=text: self._on_btn(t))
            grid.addWidget(btn, row, col, rs, cs)

        layout.addLayout(grid, 1)

    def _on_btn(self, text: str):
        if text == "C":
            self._expr = ""
            self._result = ""
            self._new_num = False
            self._display.setText("0")
            self._expr_lbl.setText("")

        elif text == "=":
            self._calculate()

        elif text == "±":
            try:
                val = float(self._display.text().replace(",", ".").replace(" ", ""))
                val = -val
                self._display.setText(self._fmt(val))
                # Mettre à jour l'expression
                self._expr = str(val)
            except Exception:
                pass

        elif text == "%":
            try:
                val = float(self._display.text().replace(",", ".").replace(" ", ""))
                val = val / 100
                self._display.setText(self._fmt(val))
                self._expr = str(val)
            except Exception:
                pass

        elif text in ("+", "−", "×", "÷"):
            if self._display.text() not in ("Erreur", "0") or self._expr:
                op_map = {"−": "-", "×": "*", "÷": "/"}
                op = op_map.get(text, text)
                current = self._display.text().replace(",", ".").replace(" ", "")
                if not self._expr:
                    self._expr = current + " " + op + " "
                else:
                    if self._expr.rstrip().endswith(("−", "×", "÷", "+", "-", "*", "/")):
                        # Remplacer l'opérateur précédent
                        self._expr = self._expr.rstrip()[:-1].rstrip() + " " + op + " "
                    else:
                        self._expr += current + " " + op + " "
                self._expr_lbl.setText(self._expr.replace("*","×").replace("/","÷").replace("-","−"))
                self._new_num = True

        elif text == ",":
            cur = self._display.text()
            if "," not in cur:
                if self._new_num:
                    self._display.setText("0,")
                    self._new_num = False
                else:
                    self._display.setText(cur + ",")

        else:  # chiffres
            cur = self._display.text()
            if self._new_num or cur == "0":
                self._display.setText(text)
                self._new_num = False
            else:
                if len(cur.replace(" ", "").replace(",", "")) < 12:
                    self._display.setText(cur + text)

    def _calculate(self):
        try:
            current = self._display.text().replace(",", ".").replace(" ", "")
            expr = self._expr + current
            # Nettoyer
            expr = expr.replace("−", "-").replace("×", "*").replace("÷", "/")
            self._expr_lbl.setText(
                (self._expr + current).replace("*","×").replace("/","÷").replace("-","−") + " ="
            )
            result = eval(expr)  # noqa
            if isinstance(result, float) and result == int(result):
                result = int(result)
            self._display.setText(self._fmt(result))
            self._expr = ""
            self._new_num = True
        except Exception:
            self._display.setText("Erreur")
            self._expr = ""
            self._new_num = True

    def _fmt(self, val) -> str:
        """Formate un nombre pour l'affichage."""
        try:
            if isinstance(val, float):
                if val == int(val):
                    return f"{int(val):,}".replace(",", " ")
                return f"{val:,.6f}".rstrip("0").replace(",", " ").replace(".", ",")
            return f"{val:,}".replace(",", " ")
        except Exception:
            return str(val)

    def keyPressEvent(self, event):
        key = event.key()
        text = event.text()
        if text in "0123456789":
            self._on_btn(text)
        elif text in "+-":
            self._on_btn(text if text == "+" else "−")
        elif text == "*":
            self._on_btn("×")
        elif text == "/":
            self._on_btn("÷")
        elif text in ".,":
            self._on_btn(",")
        elif text == "%":
            self._on_btn("%")
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Equal):
            self._on_btn("=")
        elif key in (Qt.Key_Backspace, Qt.Key_Delete):
            cur = self._display.text()
            if cur not in ("0", "Erreur") and len(cur) > 1:
                self._display.setText(cur[:-1])
            else:
                self._display.setText("0")
        elif key == Qt.Key_Escape:
            self._on_btn("C")
        else:
            super().keyPressEvent(event)
