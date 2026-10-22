"""Conversion minimale RTF -> texte brut (les notes MS Project sont stockées en RTF)."""
from __future__ import annotations

import re

_TOKEN = re.compile(r"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}\r\n]+)|[\r\n]+")

# Groupes dont le contenu n'est pas du texte affiché
_SKIP = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer",
         "headerl", "headerr", "footerl", "footerr", "listtable", "listoverridetable",
         "generator", "themedata", "colorschememapping", "latentstyles", "datastore",
         "rsidtbl", "xmlnstbl", "mmathPr", "pgdsctbl"}


def rtf_to_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.lstrip().startswith("{\\rtf"):
        return value.strip() or None
    out: list[str] = []
    stack: list[tuple[bool, int]] = []
    skip = False
    uc = 1          # nombre de caractères de repli après \uN
    pending = 0     # caractères de repli restant à ignorer
    group_start = False
    for m in _TOKEN.finditer(value):
        word, arg, hexa, sym, brace, text = m.groups()
        if brace == "{":
            stack.append((skip, uc))
            group_start = True
            continue
        if brace == "}":
            skip, uc = stack.pop() if stack else (False, 1)
            group_start = False
            continue
        first = group_start
        group_start = False
        if word:
            if first and word in _SKIP:
                skip = True
            elif word == "uc" and arg:
                uc = int(arg)
            elif skip:
                pass
            elif word in ("par", "line", "sect", "page"):
                out.append("\n")
            elif word == "tab":
                out.append("\t")
            elif word == "u" and arg:
                code = int(arg)
                out.append(chr(code + 65536 if code < 0 else code))
                pending = uc
            elif word in ("emdash",):
                out.append("—")
            elif word in ("endash",):
                out.append("–")
            elif word in ("lquote", "rquote"):
                out.append("'")
            elif word in ("ldblquote", "rdblquote"):
                out.append('"')
            elif word == "bullet":
                out.append("•")
            continue
        if sym:
            if sym == "*" and first:
                skip = True
            elif not skip and sym in "\\{}":
                out.append(sym)
            elif not skip and sym == "~":
                out.append("\u00a0")
            continue
        if hexa:
            if pending:
                pending -= 1
            elif not skip:
                out.append(bytes([int(hexa, 16)]).decode("cp1252", errors="replace"))
            continue
        if text and not skip:
            if pending:
                drop = min(pending, len(text))
                text = text[drop:]
                pending -= drop
            out.append(text)
    result = "".join(out)
    result = re.sub(r"[ \t]+\n", "\n", result).strip()
    return result or None
