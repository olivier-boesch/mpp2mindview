"""Conversion d'un fichier, partagée par la CLI et l'interface graphique."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .mspdi import write_mspdi
from .reader import read_mpp


@dataclass
class Result:
    source: Path
    target: Path
    tasks: int
    relations: int
    resources: int
    assignments: int

    def summary(self) -> str:
        return (f"{self.tasks} tâches, {self.relations} liens, "
                f"{self.resources} ressources, {self.assignments} affectations")


def find_mpp(folder: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() == ".mpp")


def target_for(source: Path, out_dir: Path | None = None) -> Path:
    """Fichier .xml de même nom, à côté de la source ou dans `out_dir`."""
    return (out_dir / (source.stem + ".xml")) if out_dir else source.with_suffix(".xml")


def convert(source: Path, target: Path) -> Result:
    """Lit `source` (.mpp) et écrit `target` (.xml). Lève MppError si le fichier est illisible."""
    project = read_mpp(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    write_mspdi(project, tmp)
    tmp.replace(target)  # pas de fichier .xml à moitié écrit en cas d'erreur
    return Result(
        source=source,
        target=target,
        tasks=sum(1 for t in project.tasks if not t.is_null and t.outline_level > 0),
        relations=len(project.relations),
        resources=sum(1 for r in project.resources if r.name),
        assignments=len(project.assignments),
    )
