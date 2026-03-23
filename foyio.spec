# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller pour Foyio
# Usage : pyinstaller foyio.spec

import json, os

BASE = os.path.dirname(os.path.abspath(SPEC))
try:
    VERSION = json.load(open(os.path.join(BASE, "version.json"))).get("version", "1.0.0")
except Exception:
    VERSION = "1.0.0"

a = Analysis(
    ['main.py'],
    pathex=[BASE],
    binaries=[],
    datas=[
        ('icons',        'icons'),
        ('version.json', '.'),
    ],
    hiddenimports=[
        # PySide6
        'PySide6.QtCharts',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtPrintSupport',
        # SQLAlchemy
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.sql.default_comparator',
        # PDF import
        'pdfplumber',
        'pdfplumber.display',
        'pdfminer',
        'pdfminer.high_level',
        'pdfminer.layout',
        # Rapport fiscal
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.pdfgen.canvas',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.platypus',
        # Correcteur orthographique
        'spellchecker',
        # Windows (pywin32)
        'win32api',
        'win32con',
        'win32gui',
        'win32com',
        'win32com.client',
        'pywintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL'],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Foyio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(BASE, 'icons', 'foyio.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Foyio',
)
