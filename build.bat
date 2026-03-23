@echo off
chcp 65001 >nul
title Build Foyio

echo.
echo  ================================
echo   Build Foyio - Installation
echo  ================================
echo.

:: Vérifier que Python est disponible
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERREUR : Python introuvable.
    echo  Installez Python depuis https://python.org
    pause
    exit /b 1
)

:: Vérifier que PyInstaller est installé
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo  Installation de PyInstaller...
    pip install pyinstaller
)

:: Vérifier les dépendances
echo  Vérification des dépendances...
pip install -r requirements.txt --quiet

:: Lancer le build
echo.
python build_windows.py

echo.
pause
