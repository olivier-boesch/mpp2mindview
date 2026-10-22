"""Interface en ligne de commande : mpp2mindview fichier.mpp [...]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .converter import convert, find_mpp, target_for
from .reader import MppError


def _collect(inputs: list[str], recursive: bool) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            found = find_mpp(path, recursive)
            if not found:
                errors.append(f"{path} : aucun fichier .mpp trouvé")
            files.extend(found)
        elif path.is_file():
            files.append(path)
        else:
            errors.append(f"{path} : fichier introuvable")
    return files, errors


def _target(src: Path, output: Path | None, single: bool) -> Path:
    if single and output is not None and output.suffix.lower() == ".xml":
        return output
    return target_for(src, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mpp2mindview",
        description="Convertit des fichiers MS Project 2010 (.mpp) en XML MS Project, "
                    "à ouvrir avec l'import MS Project de MindView.",
    )
    parser.add_argument("entrees", nargs="+", metavar="ENTREE",
                        help="fichier(s) .mpp ou dossier(s) contenant des .mpp")
    parser.add_argument("-o", "--sortie", type=Path,
                        help="dossier de sortie (ou nom du fichier .xml si une seule entrée) ; "
                             "par défaut, à côté du fichier source")
    parser.add_argument("-r", "--recursif", action="store_true", help="parcourir aussi les sous-dossiers")
    parser.add_argument("-f", "--forcer", action="store_true", help="écraser les fichiers .xml existants")
    parser.add_argument("-q", "--silencieux", action="store_true", help="n'afficher que les erreurs")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    files, errors = _collect(args.entrees, args.recursif)
    for err in errors:
        print(f"erreur : {err}", file=sys.stderr)
    single = len(files) == 1 and len(args.entrees) == 1 and not Path(args.entrees[0]).is_dir()
    if args.sortie is not None and not (single and args.sortie.suffix.lower() == ".xml"):
        args.sortie.mkdir(parents=True, exist_ok=True)

    converted = skipped = 0
    failed = len(errors)
    for src in files:
        dst = _target(src, args.sortie, single)
        if dst.exists() and not args.forcer:
            print(f"ignoré : {dst} existe déjà (utilisez --forcer pour l'écraser)", file=sys.stderr)
            skipped += 1
            continue
        try:
            result = convert(src, dst)
        except MppError as exc:
            print(f"erreur : {src} : {exc}", file=sys.stderr)
            failed += 1
            continue
        except Exception as exc:  # fichier inattendu : on continue avec les autres
            print(f"erreur : {src} : lecture impossible ({type(exc).__name__}: {exc})", file=sys.stderr)
            failed += 1
            continue
        converted += 1
        if not args.silencieux:
            print(f"{src} -> {dst} ({result.summary()})")

    if not args.silencieux and len(files) > 1:
        print(f"\n{converted} converti(s), {skipped} ignoré(s), {failed} en erreur")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
