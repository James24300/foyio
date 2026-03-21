import os
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import QSize, Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter, QImage

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(BASE_DIR, "icons")

ICON_CACHE = {}
DEFAULT_ICON = "other.png"


def _svg_to_pixmap(svg_path: str, size: int) -> QPixmap:
    """Rasterise un SVG en QPixmap à la taille demandée."""
    renderer = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(0)  # transparent
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def get_icon(name, size=24):

    if not name:
        name = DEFAULT_ICON

    key = f"{name}:{size}"

    if key in ICON_CACHE:
        return ICON_CACHE[key]

    # Chercher SVG en priorité (même nom, extension .svg)
    svg_name = os.path.splitext(name)[0] + ".svg"
    svg_path = os.path.join(ICON_DIR, svg_name)
    png_path = os.path.join(ICON_DIR, name)

    pixmap = None

    if os.path.exists(svg_path):
        try:
            pixmap = _svg_to_pixmap(svg_path, size)
        except Exception:
            pixmap = None

    if pixmap is None or pixmap.isNull():
        # Fallback PNG
        path = png_path if os.path.exists(png_path) else os.path.join(ICON_DIR, DEFAULT_ICON)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            pixmap = QPixmap(os.path.join(ICON_DIR, DEFAULT_ICON))
        pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    icon = QIcon(pixmap)
    ICON_CACHE[key] = icon
    return icon
