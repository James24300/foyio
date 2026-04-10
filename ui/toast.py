"""
Widget Toast — notification visuelle temporaire.
Apparaît en bas de la fenêtre parente, reste 2,5s puis disparaît.

Usage :
    Toast.show(parent_widget, "Transaction ajoutée ✓", kind="success")
    Toast.show(parent_widget, "Erreur de saisie", kind="error")
    Toast.show(parent_widget, "Budget dépassé", kind="warning")
"""
from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, QPoint


class Toast(QLabel):

    STYLES = {
        "success": ("background:#166534; color:#bbf7d0; border:1px solid #22c55e;"),
        "error":   ("background:#7f1d1d; color:#fecaca; border:1px solid #ef4444;"),
        "warning": ("background:#78350f; color:#fde68a; border:1px solid #f59e0b;"),
        "info":    ("background:#3e4550; color:#c8cdd4; border:1px solid #7a8494;"),
    }

    def __init__(self, parent, message: str, kind: str = "success", duration: int = 2300):
        super().__init__(message, parent)

        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(False)

        style = self.STYLES.get(kind, self.STYLES["info"])
        self.setStyleSheet(f"""
            QLabel {{
                {style}
                border-radius: 10px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
        """)

        self.adjustSize()

        # Largeur max 420px, hauteur fixe
        w = min(self.sizeHint().width() + 48, 420)
        h = 42

        # Centré horizontalement, 24px du bas
        p = parent
        x = (p.width() - w) // 2
        y = p.height() - h - 24
        self.setGeometry(x, y, w, h)

        self.raise_()
        QLabel.show(self)

        # Position initiale : hors écran (bas)
        self.move(self.x(), self.parent().height())

        # Opacité
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)

        # Animation slide vers le haut + fade in
        from PySide6.QtCore import QPropertyAnimation, QParallelAnimationGroup, QPoint
        self._slide_in = QPropertyAnimation(self, b"pos")
        self._slide_in.setDuration(300)
        self._slide_in.setStartValue(QPoint(self.x(), self.parent().height()))
        target_y = self.parent().height() - self.height() - 24
        self._slide_in.setEndValue(QPoint(self.x(), target_y))
        self._slide_in.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_in_anim = QPropertyAnimation(self._effect, b"opacity")
        self._fade_in_anim.setDuration(300)
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)

        self._in_group = QParallelAnimationGroup()
        self._in_group.addAnimation(self._slide_in)
        self._in_group.addAnimation(self._fade_in_anim)
        self._in_group.start()

        # Timer : affichage puis fondu sortant sur 400ms
        QTimer.singleShot(duration, self._fade_out)

    def _fade_out(self):
        self._anim = QPropertyAnimation(self._effect, b"opacity")
        self._anim.setDuration(400)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()

    def resizeEvent(self, event):
        """Repositionne si la fenêtre parente est redimensionnée."""
        super().resizeEvent(event)
        p = self.parent()
        if p:
            w = self.width()
            h = self.height()
            x = (p.width() - w) // 2
            y = p.height() - h - 24
            self.move(x, y)

    @staticmethod
    def show(parent, message: str, kind: str = "success", duration: int = 2300):
        """Méthode statique de commodité."""
        # Remonter jusqu'à la fenêtre principale pour un positionnement correct
        root = parent
        while root.parent():
            root = root.parent()
        Toast(root, message, kind, duration)
