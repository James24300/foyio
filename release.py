"""
Script de release Foyio — bump version + commit + tag + push.

Usage :
    python release.py patch          # 1.1.0 → 1.1.1
    python release.py minor          # 1.1.0 → 1.2.0
    python release.py major          # 1.1.0 → 2.0.0
    python release.py 1.3.0          # version explicite
    python release.py patch --notes "Mon message de release"
"""

import sys
import json
import subprocess
import os
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE  = os.path.join(BASE_DIR, "version.json")
UPDATE_SVC    = os.path.join(BASE_DIR, "services", "update_service.py")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(cmd, check=True):
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERREUR :\n{result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def _bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    # Suppose c'est une version explicite
    parts = part.split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return part
    print(f"Argument invalide : '{part}'. Utiliser patch/minor/major ou X.Y.Z")
    sys.exit(1)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    part = sys.argv[1]

    # Notes personnalisées ?
    notes = ""
    if "--notes" in sys.argv:
        idx = sys.argv.index("--notes")
        if idx + 1 < len(sys.argv):
            notes = sys.argv[idx + 1]

    # 1. Lire la version actuelle
    with open(VERSION_FILE, encoding="utf-8") as f:
        data = json.load(f)
    old_version = data["version"]
    new_version = _bump(old_version, part)

    print(f"\n=== Release Foyio : {old_version} → {new_version} ===\n")

    # 2. Mettre à jour version.json
    data["version"]      = new_version
    data["release_date"] = str(date.today())
    if notes:
        data["notes"] = notes
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  version.json → {new_version}")

    # 3. Mettre à jour CURRENT_VERSION dans update_service.py
    with open(UPDATE_SVC, encoding="utf-8") as f:
        src = f.read()
    import re
    src = re.sub(
        r'^CURRENT_VERSION\s*=\s*"[^"]+"',
        f'CURRENT_VERSION = "{new_version}"',
        src, flags=re.MULTILINE
    )
    with open(UPDATE_SVC, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  update_service.py CURRENT_VERSION → {new_version}")

    # 4. Git commit + tag + push
    branch = _run("git rev-parse --abbrev-ref HEAD", check=False).strip() or "main"
    print(f"\nCommit & push sur '{branch}'...")
    _run("git add version.json services/update_service.py")
    _run(f'git commit -m "Release v{new_version}"')
    _run(f"git tag v{new_version}")
    _run(f"git push origin {branch}")
    push_tag = subprocess.run(
        f"git push origin v{new_version}", shell=True,
        capture_output=True, text=True
    )
    if push_tag.returncode != 0:
        print(f"  Tag push refusé par le serveur (normal en local) — créez le tag manuellement sur GitHub.")
    else:
        print(f"  Tag v{new_version} poussé.")

    print(f"\n✓ Release v{new_version} prête.")
    print(f"  → Rebuilder l'exe : python build_windows.py")
    print(f"  → Puis mettre à jour la release GitHub avec FoyioSetup-{new_version}.exe")


if __name__ == "__main__":
    main()
