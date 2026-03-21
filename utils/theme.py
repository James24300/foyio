# Foyio — Thème unique gris froid
BANK_THEME = """

QWidget {
    background:#1e2124;
    color:#c8cdd4;
    font-size:13px;
    font-family: "Segoe UI", "Inter", sans-serif;
}
QMainWindow, QDialog { background:#1e2124; color:#c8cdd4; }

QFrame {
    background:#292d32;
    border-radius:10px;
    border:1px solid #3d4248;
}

QPushButton {
    background:#2e3238;
    border-radius:8px;
    padding:8px 14px;
    color:#c8cdd4;
    font-weight:600;
    border:1px solid #3d4248;
}
QPushButton:hover   { background:#383e46; color:#e0e4ea; }
QPushButton:pressed { background:#23272b; }
QPushButton:disabled{ background:#22252a; color:#4a5060; border:1px solid #30353c; }

QPushButton[objectName="danger"] {
    background:#2e2020;
    color:#e89090;
    border:1px solid #503030;
}
QPushButton[objectName="danger"]:hover { background:#382828; }

QPushButton[objectName="export"] {
    background:#1e2a20;
    color:#7ecb8f;
    border:1px solid #2e5038;
}
QPushButton[objectName="export"]:hover { background:#253322; }

QPushButton[objectName="import"] {
    background:#1a2030;
    color:#7aaee8;
    border:1px solid #2a3a58;
}
QPushButton[objectName="import"]:hover { background:#202840; }

QPushButton[objectName="restore"] {
    background:#1e2428;
    color:#a0b4c8;
    border:1px solid #2e4050;
}
QPushButton[objectName="restore"]:hover { background:#253040; }

QLineEdit {
    background:#191c20;
    border:1px solid #3d4248;
    border-radius:8px;
    padding:6px 10px;
    color:#c8cdd4;
    selection-background-color:#4a5060;
}
QLineEdit:focus { border:1px solid #5a6070; background:#1c1f22; }
QLineEdit:hover { border:1px solid #4a5060; }

QSpinBox, QDoubleSpinBox {
    background:#191c20;
    border:1px solid #3d4248;
    border-radius:8px;
    padding:4px 32px 4px 8px;
    color:#c8cdd4;
}
QSpinBox:focus, QDoubleSpinBox:focus { border:1px solid #5a6070; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width:26px;
    border-left:1px solid #3d4248;
    border-top-right-radius:8px;
    background:#23272b;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover { background:#3e4550; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url(icons/arrow_up.svg);
    width:10px; height:10px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width:26px;
    border-left:1px solid #3d4248;
    border-bottom-right-radius:8px;
    background:#23272b;
}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background:#3e4550; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url(icons/arrow_down.svg);
    width:10px; height:10px;
}

QComboBox {
    background:#191c20;
    border:1px solid #3d4248;
    border-radius:8px;
    padding:6px 10px 6px 10px;
    color:#c8cdd4;
    padding-right:28px;
}
QComboBox:focus { border:1px solid #5a6070; }
QComboBox:hover { border:1px solid #4a5060; background:#1c1f22; }
QDateEdit {
    background:#191c20;
    border:1px solid #3d4248;
    border-radius:8px;
    padding:4px 8px;
    color:#c8cdd4;
}
QDateEdit:focus   { border:1px solid #5a6070; }
QDateEdit:hover   { border:1px solid #4a5060; }
QDateEdit:disabled { color:#3a4050; border-color:#2a2e34; }
QDateEdit::drop-down {
    border:none;
    width:20px;
    background:transparent;
}
QDateEdit::down-arrow {
    image: url(icons/arrow_down.svg);
    width:10px;
    height:10px;
}
QComboBox::drop-down {
    border:none;
    width:20px;
    background:transparent;
}
QComboBox::down-arrow {
    image: url(icons/arrow_down.svg);
    width:12px;
    height:12px;
}
QComboBox QAbstractItemView {
    background:#292d32;
    border:1px solid #3d4248;
    color:#c8cdd4;
    selection-background-color:#383d44;
    outline:none;
}

QTableWidget {
    background:#191c20;
    border:none;
    gridline-color:#292d32;
    color:#c8cdd4;
    alternate-background-color:#202428;
}
QHeaderView::section {
    background:#292d32;
    border:none;
    border-bottom:1px solid #3d4248;
    padding:8px 10px;
    font-weight:600;
    color:#848c94;
    font-size:11px;
}
QTableWidget::item          { border-bottom:1px solid #292d32; padding:6px 10px; }
QTableWidget::item:selected { background:#383d44; color:#e0e4ea; }
QTableWidget::item:hover    { background:#23272b; }

QProgressBar {
    background:#191c20;
    border-radius:5px;
    border:none;
}
QProgressBar::chunk { background:#5a6472; border-radius:5px; }

QScrollBar:vertical { background:#191c20; width:8px; border:none; }
QScrollBar::handle:vertical { background:#3d4248; border-radius:4px; min-height:20px; }
QScrollBar::handle:vertical:hover { background:#4a5060; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar:horizontal { background:#191c20; height:8px; border:none; }
QScrollBar::handle:horizontal { background:#3d4248; border-radius:4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }

QToolTip {
    background:#292d32; color:#c8cdd4;
    border:1px solid #3d4248; border-radius:6px;
    padding:4px 8px; font-size:12px;
}
QMessageBox { background:#292d32; color:#c8cdd4; }
QDialog     { background:#1e2124; color:#c8cdd4; }

"""

DARK_THEME  = BANK_THEME
LIGHT_THEME = BANK_THEME
THEME       = BANK_THEME
