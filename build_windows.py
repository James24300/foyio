"""
Script de build Windows pour Foyio
Génère un exécutable via PyInstaller puis un installateur via Inno Setup.

Usage :
    python build_windows.py
    -- ou double-cliquer sur build.bat --

Prérequis :
    pip install pyinstaller
    Inno Setup 6 installé (https://jrsoftware.org/isdl.php)
"""

import os
import sys
import json
import shutil
import subprocess

# Securiser l'affichage console Windows (cp1252)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "Foyio"
VERSION  = "1.0.0"

try:
    with open(os.path.join(BASE_DIR, "version.json"), encoding="utf-8") as f:
        VERSION = json.load(f).get("version", VERSION)
except Exception:
    pass


def run(cmd, **kwargs):
    print(f"\n>>> {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    if result.returncode != 0:
        print(f"ERREUR (code {result.returncode})")
        sys.exit(result.returncode)


# ---------------------------------------------------------------
# 1. Build PyInstaller
# ---------------------------------------------------------------
def build_exe():
    dist_dir  = os.path.join(BASE_DIR, "dist")
    build_dir = os.path.join(BASE_DIR, "build")

    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)

    spec = os.path.join(BASE_DIR, "foyio.spec")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", spec], cwd=BASE_DIR)
    print(f"\nOK Executable : dist/{APP_NAME}/{APP_NAME}.exe")


# ---------------------------------------------------------------
# 2. Script Inno Setup
# ---------------------------------------------------------------
def create_iss():
    iss_path = os.path.join(BASE_DIR, "foyio_setup.iss")
    iss = f"""; Script Inno Setup — Foyio v{VERSION}
; Généré automatiquement par build_windows.py

#define MyAppName      "{APP_NAME}"
#define MyAppVersion   "{VERSION}"
#define MyAppPublisher "James-William PULSFORD"
#define MyAppURL       "https://github.com/James24300/foyio"
#define MyAppExeName   "{APP_NAME}.exe"

[Setup]
AppId={{{{F0Y10APP-2026-ABCD-EF12-34567890ABCD}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppPublisher={{#MyAppPublisher}}
AppPublisherURL={{#MyAppURL}}
AppSupportURL={{#MyAppURL}}
AppUpdatesURL={{#MyAppURL}}
DefaultDirName={{autopf}}\\{{#MyAppName}}
DefaultGroupName={{#MyAppName}}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=FoyioSetup-{{#MyAppVersion}}
SetupIconFile=icons\\foyio.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
MinVersion=10.0

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{{cm:CreateDesktopIcon}}"; GroupDescription: "{{cm:AdditionalIcons}}"
Name: "startupicon"; Description: "Lancer Foyio au démarrage de Windows"; GroupDescription: "Démarrage"; Flags: unchecked

[Files]
Source: "dist\\{APP_NAME}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{{group}}\\{{#MyAppName}}";                        Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{group}}\\{{cm:UninstallProgram,{{#MyAppName}}}}"; Filename: "{{uninstallexe}}"
Name: "{{commondesktop}}\\{{#MyAppName}}";                 Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon
Name: "{{userstartup}}\\{{#MyAppName}}";                   Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: startupicon

[Run]
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "{{cm:LaunchProgram,{{#MyAppName}}}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Supprime uniquement le dossier d'installation (pas les données utilisateur dans %APPDATA%)
Type: filesandordirs; Name: "{{app}}"
"""
    with open(iss_path, "w", encoding="utf-8") as f:
        f.write(iss.strip())
    print(f"OK Script Inno Setup : foyio_setup.iss")
    return iss_path


# ---------------------------------------------------------------
# 3. Build installateur
# ---------------------------------------------------------------
def build_installer(iss_path):
    inno_candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc = next((p for p in inno_candidates if os.path.exists(p)), None)

    if not iscc:
        print("\nATTENTION : Inno Setup non trouve -- installateur non genere.")
        print("   Télécharger : https://jrsoftware.org/isdl.php")
        print(f"   Puis relancer ce script, ou ouvrir {iss_path} dans Inno Setup.")
        return False

    run([iscc, iss_path], cwd=BASE_DIR)
    output = os.path.join(BASE_DIR, "Output", f"FoyioSetup-{VERSION}.exe")
    if os.path.exists(output):
        print(f"\nOK Installateur : Output/FoyioSetup-{VERSION}.exe")
    return True


# ---------------------------------------------------------------
# Point d'entree
# ---------------------------------------------------------------
if __name__ == "__main__":
    print(f"=== Build Foyio v{VERSION} ===\n")

    print("Etape 1/3 : Generation du script Inno Setup")
    iss_path = create_iss()

    print("\nEtape 2/3 : Compilation avec PyInstaller")
    build_exe()

    print("\nEtape 3/3 : Creation de l'installateur")
    build_installer(iss_path)

    print("\n=== Build termine avec succes ! ===")
    print(f"  Executable   : dist/{APP_NAME}/{APP_NAME}.exe")
    print(f"  Installateur : Output/FoyioSetup-{VERSION}.exe")
