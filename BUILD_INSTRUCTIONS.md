# 📦 Créer un installateur Windows pour Foyio

## Prérequis

1. **PyInstaller**
   ```
   pip install pyinstaller
   ```

2. **Inno Setup 6**
   Télécharger et installer depuis : https://jrsoftware.org/isdl.php

3. **Icône** (optionnel)
   Placer un fichier `foyio.ico` dans le dossier `icons/`

---

## Build en une commande

```
python build_windows.py
```

Le script fait tout automatiquement :
1. Génère `foyio_setup.iss` (script Inno Setup)
2. Lance PyInstaller → crée `dist/Foyio/`
3. Lance Inno Setup → crée `Output/FoyioSetup-1.0.0.exe`

---

## Résultat

- `dist/Foyio/Foyio.exe` — exécutable standalone
- `Output/FoyioSetup-1.0.0.exe` — installateur Windows

---

## Mettre à jour la version

Modifier `version.json` :
```json
{
  "version": "1.0.1",
  "release_date": "2026-03-18",
  "notes": "Correction de bugs, nouvelles fonctionnalités..."
}
```

Puis pousser sur GitHub :
```
git add version.json
git commit -m "Release v1.0.1"
git push
```

Les utilisateurs verront la mise à jour au prochain démarrage.
