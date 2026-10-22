# mpp2mindview

Convertit les fichiers **MS Project 2010 (.mpp)** en **XML MS Project**, à ouvrir avec l'import
MS Project de MindView. Python uniquement, sans Java ni MS Project.

## Installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e .            # ligne de commande
USE_SDL2=1 .venv/bin/pip install --no-cache-dir -e ".[gui]"   # + interface graphique (Kivy)
```

Sous Linux avec Python 3.14, Kivy n'a pas de paquet précompilé et se compile depuis les sources.
Il faut les paquets `libsdl2-dev`, `libsdl2-image-dev`, `libsdl2-ttf-dev` et `libsdl2-mixer-dev`.
La variable `USE_SDL2=1` est nécessaire, sinon Kivy est compilé sans fenêtre et l'interface ne
démarre pas. Si Kivy est déjà installé sans SDL2 :

```bash
USE_SDL2=1 .venv/bin/pip install --no-cache-dir --force-reinstall --no-deps kivy
```

## Utilisation

Interface graphique :

```bash
.venv/bin/mpp2mindview-gui
```

Ajoutez des fichiers ou un dossier (ou glissez-déposez-les), choisissez où enregistrer les .xml,
puis cliquez sur **Convertir**.

Ligne de commande :

```bash
mpp2mindview planning.mpp                  # crée planning.xml à côté
mpp2mindview a.mpp b.mpp -o sortie/        # plusieurs fichiers vers un dossier
mpp2mindview projets/ -r -o sortie/        # tout un dossier, sous-dossiers compris
mpp2mindview planning.mpp -o plan.xml -f   # nom imposé, écrase s'il existe
```

Le code de retour vaut 1 si au moins un fichier n'a pas pu être converti.

## Ce qui est converti

- Projet : titre, auteur, dates de début et de fin, devise, heures par jour et par semaine.
- Tâches :
  - nom, hiérarchie (niveau, numéro hiérarchique, WBS), début, fin, durée et son unité ;
  - durée estimée, jalons, tâches récapitulatives, planification manuelle ou automatique ;
  - % achevé, priorité, contraintes, échéance, dates réelles, travail, coûts ;
  - notes, converties du RTF en texte.
- Liens entre tâches : type (FD, DD, FF, DF) et décalage.
- Ressources : nom, initiales, groupe, code, e-mail, type (travail, matériel, coût), capacité
  maximale, taux, coût par utilisation et notes.
- Affectations : tâche, ressource, unités, travail, début et fin.

## Limites

- Seul le format MPP14 est lu : Project 2010, et aussi 2013 à 2019. Les fichiers Project 2007
  ou plus anciens sont refusés avec un message clair.
- Les fichiers protégés par mot de passe à l'ouverture ne sont pas pris en charge.
- Non repris : calendriers réels (un calendrier « Standard » lun.-ven. 8 h-12 h / 13 h-17 h est
  écrit à la place), champs personnalisés, codes hiérarchiques, plannings de référence,
  données chronologiques, tâches périodiques, sous-projets.

## Exécutables Windows

Les fichiers sont dans `packaging/windows/`. PyInstaller ne compile pas pour une autre
plateforme : il faut construire l'exe **sur Windows**.

1. Installez Python **3.12** (ou 3.13) depuis python.org, avec le lanceur `py`. Kivy ne fournit
   pas encore de paquet Windows pour Python 3.14.
2. Copiez le dossier du projet sur la machine Windows et lancez :

   ```bat
   packaging\windows\build.bat
   ```

   Pour utiliser Python 3.13 : `packaging\windows\build.bat 3.13`.

Le script crée un environnement `.venv-win`, installe les dépendances, passe les tests puis
produit deux fichiers autonomes, sans installation de Python nécessaire :

- `dist\mpp2mindview-gui.exe` : l'interface graphique (double-clic) ;
- `dist\mpp2mindview.exe` : la ligne de commande.

Pour une icône, placez un fichier `mpp2mindview.ico` dans `packaging/windows/` avant de
construire.

Sans machine Windows, le workflow `.github/workflows/build-windows.yml` construit les deux exe
sur GitHub. Lancez-le depuis l'onglet *Actions* du dépôt ou en poussant une étiquette `v*`, puis
récupérez l'artefact `mpp2mindview-windows`.

Windows SmartScreen peut avertir au premier lancement, car l'exe n'est pas signé :
*Informations complémentaires > Exécuter quand même*.

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Les tests convertissent des fichiers .mpp enregistrés par Project 2010. Ils comparent le résultat
au XML que Project 2010 a exporté pour le même projet. Pour tester aussi d'autres paires
`*-projectAAAA-mpp14.mpp` / `*-projectAAAA-mspdi.xml`, indiquez leur dossier dans
`MPP2MINDVIEW_EXTRA_FIXTURES`. Les versions 2013, 2016 et 2019 ont été vérifiées ainsi.

## Licence et origine

Le décodage du format .mpp est un portage en Python de la rétro-ingénierie faite par le projet
[MPXJ](https://www.mpxj.org) de Jon Iles, distribué sous licence **LGPL 2.1**. Ce projet est donc
lui aussi sous LGPL 2.1 ou ultérieure (voir `LICENSE`). Les fichiers de `tests/fixtures/` proviennent des jeux de
test de MPXJ.

`tools/gen_fields.py` régénère `mpp2mindview/fields.py` (les tables de champs MS Project) à partir
des sources Java de MPXJ.
