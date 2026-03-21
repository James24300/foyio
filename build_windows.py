"""
Script de build Windows pour Foyio
Génère un exécutable via PyInstaller puis un installateur via Inno Setup.

Usage :
    python build_windows.py

Prérequis :
    pip install pyinstaller
    Inno Setup installé dans C:/Program Files (x86)/Inno Setup 6/
"""

import os
import sys
import subprocess
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "Foyio"
VERSION  = "1.0.0"

# ── Lire la version depuis version.json ──
try:
    import json
    with open(os.path.join(BASE_DIR, "version.json")) as f:
        VERSION = json.load(f).get("version", VERSION)
except Exception:
    pass


def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    if result.returncode != 0:
        print(f"ERREUR (code {result.returncode})")
        sys.exit(result.returncode)


def build_exe():
    """Génère l'exécutable avec PyInstaller."""
    dist_dir = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    # Nettoyer les builds précédents
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",           # dossier (plus rapide au démarrage que --onefile)
        "--windowed",         # pas de console
        f"--name={APP_NAME}",
        "--icon=icons/foyio.ico" if os.path.exists("icons/foyio.ico") else "",
        "--add-data=icons;icons",
        "--add-data=version.json;.",
        "--hidden-import=PySide6.QtCharts",
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=reportlab",
        "main.py"
    ]
    cmd = [c for c in cmd if c]  # supprimer les vides
    run(cmd, cwd=BASE_DIR)
    print(f"\n✓ Exécutable généré dans : dist/{APP_NAME}/")


def build_installer():
    """Génère l'installateur avec Inno Setup."""
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc = next((p for p in inno_paths if os.path.exists(p)), None)

    if not iscc:
        print("\n⚠ Inno Setup non trouvé. Skipping installateur.")
        print("  Télécharger : https://jrsoftware.org/isdl.php")
        return

    iss_path = os.path.join(BASE_DIR, "foyio_setup.iss")
    run([iscc, iss_path])
    print(f"\n✓ Installateur généré dans : Output/FoyioSetup-{VERSION}.exe")


def create_iss_script():
    """Génère le script Inno Setup .iss."""
    iss = f"""
; Script Inno Setup pour Foyio
; Généré automatiquement par build_windows.py

#define MyAppName "{APP_NAME}"
#define MyAppVersion "{VERSION}"
#define MyAppPublisher "James-William PULSFORD"
#define MyAppURL "https://github.com/James24300/foyio"
#define MyAppExeName "{APP_NAME}.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
LicenseFile=
OutputDir=Output
OutputBaseFilename=FoyioSetup-{{#MyAppVersion}}
SetupIconFile=icons\\foyio.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"

[Files]
Source: "dist\\{APP_NAME}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#StringChange(MyAppName, '&', '&&')}}}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{{app}}"
"""
    with open(os.path.join(BASE_DIR, "foyio_setup.iss"), "w", encoding="utf-8") as f:
        f.write(iss.strip())
    print("✓ Script Inno Setup généré : foyio_setup.iss")


if __name__ == "__main__":
    print(f"=== Build Foyio v{VERSION} ===\n")

    print("1. Génération du script Inno Setup...")
    create_iss_script()

    print("\n2. Build PyInstaller...")
    build_exe()

    print("\n3. Build installateur Inno Setup...")
    build_installer()

    print(f"\n=== Build terminé ! ===")
    print(f"Exécutable : dist/{APP_NAME}/{APP_NAME}.exe")
    print(f"Installateur : Output/FoyioSetup-{VERSION}.exe")
