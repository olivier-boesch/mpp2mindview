"""Génère mpp2mindview/fields.py à partir des sources Java de MPXJ (LGPL-2.1).

Usage : python tools/gen_fields.py <dossier contenant MPP*Field.java et *Field.java>
"""
import re
import sys
from pathlib import Path

ENUM_RE = re.compile(r"^\s*([A-Z0-9_]+)\(DataType\.([A-Z_]+)(?:,\s*(?:\w+\.)?([A-Z0-9_]+))?\)", re.M)
ARRAY_RE = re.compile(r"^\s*FIELD_ARRAY\[(\d+)\]\s*=\s*\w+\.([A-Z0-9_]+);", re.M)
CASE_RE = re.compile(r"case\s+(\d+):\s*\{\s*result\s*=\s*\w+\.([A-Z0-9_]+);", re.S)


def parse(src: Path, enum_file: str, mpp_file: str):
    enum = {m[1]: (m[2], m[3]) for m in ENUM_RE.finditer((src / enum_file).read_text())}
    mpp = (src / mpp_file).read_text()
    table = {int(i): n for i, n in ARRAY_RE.findall(mpp)}
    over = {}
    m = re.search(r"mapMpp14\(int value\)(.*?)\n   }\n", mpp, re.S)
    if m:
        over = {int(i): n for i, n in CASE_RE.findall(m.group(1))}
    def entry(name):
        dtype, units = enum.get(name, ("UNKNOWN", None))
        return (name, dtype, units)
    return {k: entry(v) for k, v in sorted(table.items())}, {k: entry(v) for k, v in sorted(over.items())}


def main():
    src = Path(sys.argv[1])
    out = ['"""Tables de champs MS Project (générées par tools/gen_fields.py).',
           "",
           "Dérivées des sources de MPXJ (https://www.mpxj.org), LGPL-2.1.",
           "Clé : identifiant de champ MS Project ; valeur : (nom, type de donnée, champ d'unité).",
           '"""', ""]
    for label, enum_file, mpp_file in (("TASK", "TaskField.java", "MPPTaskField.java"),
                                       ("RESOURCE", "ResourceField.java", "MPPResourceField.java"),
                                       ("ASSIGNMENT", "AssignmentField.java", "MPPAssignmentField.java")):
        table, over = parse(src, enum_file, mpp_file)
        out.append(f"{label}_FIELDS = {{")
        out += [f"    {k}: {v!r}," for k, v in table.items()]
        out.append("}\n")
        out.append(f"{label}_FIELDS_MPP14 = {{")
        out += [f"    {k}: {v!r}," for k, v in over.items()]
        out.append("}\n")
    Path(__file__).resolve().parent.parent.joinpath("mpp2mindview", "fields.py").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
