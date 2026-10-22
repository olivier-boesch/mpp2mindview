"""Compare le XML produit à celui exporté par Project 2010 pour le même projet.

Les paires .mpp / .xml proviennent des jeux de test de MPXJ (LGPL-2.1).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import os

import pytest

from mpp2mindview.cli import main
from mpp2mindview.mspdi import write_mspdi
from mpp2mindview.reader import MppError, read_mpp

FIXTURES = Path(__file__).parent / "fixtures"
NS = "{http://schemas.microsoft.com/project}"
# MPP2MINDVIEW_EXTRA_FIXTURES : dossier supplémentaire de paires .mpp/.xml (facultatif)
_EXTRA = os.environ.get("MPP2MINDVIEW_EXTRA_FIXTURES")
PAIRS = sorted(FIXTURES.glob("*-project2010-mpp14.mpp")) + (
    sorted(Path(_EXTRA).glob("*-project20[0-9][0-9]-mpp14.mpp")) if _EXTRA else [])
PAIRS = [p for p in PAIRS if p.with_name(p.name.replace("-mpp14.mpp", "-mspdi.xml")).exists()]


def _ref(mpp: Path) -> Path:
    return mpp.with_name(mpp.name.replace("-mpp14.mpp", "-mspdi.xml"))


def _id(mpp: Path) -> str:
    return mpp.name.replace("-mpp14.mpp", "")


def _text(el, tag):
    child = el.find(NS + tag)
    return None if child is None else child.text


def _minutes(value):
    m = re.match(r"PT(\d+)H(\d+)M([\d.]+)S", value or "")
    return round(int(m[1]) * 60 + int(m[2]) + float(m[3]) / 60, 1) if m else None


def _convert(mpp: Path, tmp_path: Path) -> ET.Element:
    out = tmp_path / "out.xml"
    write_mspdi(read_mpp(mpp), out)
    return ET.parse(out).getroot()


def _by_uid(root, tag):
    return {_text(e, "UID"): e for e in root.iter(NS + tag)}


@pytest.mark.parametrize("mpp", PAIRS, ids=_id)
def test_tasks(mpp, tmp_path):
    mine = _by_uid(_convert(mpp, tmp_path), "Task")
    ref = _by_uid(ET.parse(_ref(mpp)).getroot(), "Task")
    assert set(mine) == set(ref)
    # Dans les fichiers task-*, le .mpp et le .xml n'ont pas été créés avec le même
    # réglage « nouvelles tâches manuelles » : on ne compare pas Manual pour ceux-là.
    check_manual = not mpp.name.startswith("task-")
    for uid, r in ref.items():
        m = mine[uid]
        if _text(r, "IsNull") == "1":
            assert _text(m, "IsNull") == "1"
            continue
        fields = ["ID", "OutlineLevel", "OutlineNumber", "Start", "Finish", "Milestone",
                  "Summary", "PercentComplete", "Priority", "DurationFormat"]
        if uid != "0":
            fields.append("Name")
        if check_manual:
            fields.append("Manual")
        for tag in fields:
            assert _text(m, tag) == _text(r, tag), f"tâche {uid} : {tag}"
        assert _minutes(_text(m, "Duration")) == _minutes(_text(r, "Duration")), f"tâche {uid} : Duration"


@pytest.mark.parametrize("mpp", PAIRS, ids=_id)
def test_links(mpp, tmp_path):
    def links(root):
        out = set()
        for task in root.iter(NS + "Task"):
            for pl in task.findall(NS + "PredecessorLink"):
                out.add((_text(pl, "PredecessorUID"), _text(task, "UID"), _text(pl, "Type"),
                         _text(pl, "LinkLag"), _text(pl, "LagFormat")))
        return out

    assert links(_convert(mpp, tmp_path)) == links(ET.parse(_ref(mpp)).getroot())


@pytest.mark.parametrize("mpp", PAIRS, ids=_id)
def test_resources(mpp, tmp_path):
    mine = _by_uid(_convert(mpp, tmp_path), "Resource")
    ref = _by_uid(ET.parse(_ref(mpp)).getroot(), "Resource")
    assert set(mine) == set(ref)
    for uid, r in ref.items():
        m = mine[uid]
        for tag in ("ID", "Name", "Type", "Initials", "Group", "IsCostResource"):
            assert (_text(m, tag) or None) == (_text(r, tag) or None), f"ressource {uid} : {tag}"
        if _text(r, "Type") == "1":
            assert float(_text(m, "MaxUnits")) == float(_text(r, "MaxUnits"))
        if _text(r, "StandardRate") is not None:
            assert float(_text(m, "StandardRate") or 0) == float(_text(r, "StandardRate"))


@pytest.mark.parametrize("mpp", PAIRS, ids=_id)
def test_assignments(mpp, tmp_path):
    def assignments(root):
        return {(_text(a, "TaskUID"), _text(a, "ResourceUID")): a for a in root.iter(NS + "Assignment")}

    mine = assignments(_convert(mpp, tmp_path))
    ref = assignments(ET.parse(_ref(mpp)).getroot())
    assert set(mine) == set(ref)
    for key, r in ref.items():
        m = mine[key]
        assert float(_text(m, "Units")) == float(_text(r, "Units")), key
        assert _minutes(_text(m, "Work")) == _minutes(_text(r, "Work")), key
        assert _text(m, "Start") == _text(r, "Start"), key
        assert _text(m, "Finish") == _text(r, "Finish"), key


def test_project_properties(tmp_path):
    mpp = FIXTURES / "task-links-project2010-mpp14.mpp"
    mine = _convert(mpp, tmp_path)
    ref = ET.parse(_ref(mpp)).getroot()
    for tag in ("ScheduleFromStart", "StartDate", "FinishDate", "MinutesPerDay", "MinutesPerWeek",
                "DaysPerMonth", "CurrencySymbol", "CurrencyCode", "DefaultStartTime", "DefaultFinishTime"):
        assert _text(mine, tag) == _text(ref, tag), tag


def test_not_an_mpp(tmp_path):
    bad = tmp_path / "faux.mpp"
    bad.write_bytes(b"ceci n'est pas un fichier MS Project")
    with pytest.raises(MppError):
        read_mpp(bad)


def test_cli_folder(tmp_path, capsys):
    src = tmp_path / "src"
    src.mkdir()
    for mpp in PAIRS[:2]:
        (src / mpp.name).write_bytes(mpp.read_bytes())
    (src / "casse.mpp").write_bytes(b"rien")
    out = tmp_path / "out"
    assert main([str(src), "-o", str(out)]) == 1  # un fichier en erreur
    assert sorted(p.name for p in out.iterdir()) == sorted(p.stem + ".xml" for p in PAIRS[:2])
    # deuxième passage : fichiers existants ignorés sans --forcer
    assert main([str(src / PAIRS[0].name), "-o", str(out)]) == 0
    assert "existe déjà" in capsys.readouterr().err


def test_cli_single_file_output_name(tmp_path):
    target = tmp_path / "plan.xml"
    assert main([str(PAIRS[0]), "-o", str(target), "-q"]) == 0
    assert target.exists()
    ET.parse(target)
