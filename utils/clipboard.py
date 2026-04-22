"""
Copier/Coller global pour tous les QAbstractItemView (tableaux).
- Ctrl+C  : copie la sélection (une ou plusieurs cellules)
- Clic droit : menu contextuel avec "Copier"

Utilisation : remplacer QApplication par FoyioApp dans main.py.
"""
from PySide6.QtWidgets import QApplication, QAbstractItemView, QMenu
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeySequence


def _copy_selection(view: QAbstractItemView):
    model = view.model()
    if model is None:
        return

    indexes = sorted(
        view.selectedIndexes(),
        key=lambda idx: (idx.row(), idx.column()),
    )
    if not indexes:
        return

    rows = {}
    for idx in indexes:
        rows.setdefault(idx.row(), []).append(
            (idx.column(), idx.data() or "")
        )

    lines = []
    for _row, cols in sorted(rows.items()):
        lines.append("\t".join(text for _, text in sorted(cols)))

    QApplication.clipboard().setText("\n".join(lines))


class FoyioApp(QApplication):
    def notify(self, obj, event):
        if isinstance(obj, QAbstractItemView):
            if event.type() == QEvent.Type.KeyPress:
                if event.matches(QKeySequence.StandardKey.Copy):
                    _copy_selection(obj)
                    return True
            elif event.type() == QEvent.Type.ContextMenu:
                menu = QMenu(obj)
                copy_act = menu.addAction("Copier")
                copy_act.triggered.connect(lambda: _copy_selection(obj))
                menu.exec(event.globalPos())
                return True
        return super().notify(obj, event)
