"""
Copier/Coller global pour tous les QAbstractItemView (tableaux).
- Ctrl+C  : copie la sélection (une ou plusieurs cellules)
- Ctrl+V  : colle depuis le presse-papiers (tables éditables uniquement)
- Clic droit : menu contextuel Copier / Coller

Utilisation : remplacer QApplication par FoyioApp dans main.py.
"""
from PySide6.QtWidgets import QApplication, QAbstractItemView, QTableWidget, QMenu
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


def _paste_selection(view: QAbstractItemView):
    """Colle le presse-papiers dans les cellules sélectionnées (tables éditables)."""
    if not isinstance(view, QTableWidget):
        return
    if view.editTriggers() == QTableWidget.EditTrigger.NoEditTriggers:
        return
    text = QApplication.clipboard().text()
    if not text:
        return
    current = view.currentIndex()
    if not current.isValid():
        return
    start_row = current.row()
    start_col = current.column()
    for r, line in enumerate(text.split("\n")):
        for c, cell in enumerate(line.split("\t")):
            row = start_row + r
            col = start_col + c
            if row < view.rowCount() and col < view.columnCount():
                item = view.item(row, col)
                if item:
                    item.setText(cell)


def _is_editable(view: QAbstractItemView) -> bool:
    return (
        isinstance(view, QTableWidget)
        and view.editTriggers() != QTableWidget.EditTrigger.NoEditTriggers
    )


class FoyioApp(QApplication):
    def notify(self, obj, event):
        if isinstance(obj, QAbstractItemView):
            if event.type() == QEvent.Type.KeyPress:
                if event.matches(QKeySequence.StandardKey.Copy):
                    _copy_selection(obj)
                    return True
                if event.matches(QKeySequence.StandardKey.Paste):
                    _paste_selection(obj)
                    return True
            elif event.type() == QEvent.Type.ContextMenu:
                menu = QMenu(obj)
                copy_act = menu.addAction("Copier")
                copy_act.triggered.connect(lambda: _copy_selection(obj))
                paste_act = menu.addAction("Coller")
                paste_act.triggered.connect(lambda: _paste_selection(obj))
                paste_act.setEnabled(_is_editable(obj))
                menu.exec(event.globalPos())
                return True
        return super().notify(obj, event)
