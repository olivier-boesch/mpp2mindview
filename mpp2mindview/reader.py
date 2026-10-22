"""Lecteur de fichiers .mpp au format MPP14 (Project 2010 ; aussi 2013 à 2019).

Logique portée depuis MPXJ (https://www.mpxj.org), LGPL-2.1.
Seules les données utiles à la conversion sont lues : projet, tâches, liens,
ressources et affectations.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import olefile

from . import fields
from .blocks import (EPOCH, FixedData, FixedMeta, Props, VarData, ansi_string, f64, i32, i64,
                     timestamp, u16, unicode_string)
from .model import Assignment, Project, Relation, Resource, Task


class MppError(Exception):
    """Fichier illisible ou format non pris en charge."""


# Clés de Props (PropsKey dans MPXJ)
PASSWORD_FLAG = 893386752
ENCRYPTION_CODE = 893386759
PROTECTION_PASSWORD_HASH = 893386756
TASK_FIELD_MAP = (131092, 50331668)
RESOURCE_FIELD_MAP = (131093, 50331669)
ASSIGNMENT_FIELD_MAP = (131095, 50331671)
PROJECT_START_DATE = 37748738
PROJECT_FINISH_DATE = 37748739
SCHEDULE_FROM = 37748740
MINUTES_PER_DAY = 37748765
MINUTES_PER_WEEK = 37748766
DAYS_PER_MONTH = 37753743
CURRENCY_SYMBOL = 37748752
CURRENCY_CODE = 37753787
START_TIME = 37748764
END_TIME = 37748769
TITLE = 37748744
AUTHOR = 37748748
COMPANY = 37748736
MANAGER = 37748737

PROJECT_2010 = 14
NULL_TASK_BLOCK_SIZE = 16
ASSIGNMENT_NULL_RESOURCE_ID = -65535
VALUE_LIST_MASKS = (0x0701, 0x0401)

# Taille en octets des types stockés en données fixes (FieldMap.getFixedDataFieldSize)
FIXED_SIZES = {
    "DATE": 4, "INTEGER": 4, "DURATION": 4,
    "TIME_UNITS": 2, "CONSTRAINT": 2, "PRIORITY": 2, "PERCENTAGE": 2, "TASK_TYPE": 2,
    "ACCRUE": 2, "SHORT": 2, "BOOLEAN": 2, "DELAY": 2, "WORKGROUP": 2, "RATE_UNITS": 2,
    "EARNED_VALUE_METHOD": 2, "RESOURCE_REQUEST_TYPE": 2,
    "CURRENCY": 8, "UNITS": 8, "RATE": 8, "WORK": 8,
    "WORK_UNITS": 1, "GUID": 16,
}


def _bits(data: bytes | None, off: int) -> int:
    """Lit un entier 32 bits, même partiellement hors du bloc (octets manquants = 0)."""
    if data is None or off >= len(data):
        return 0
    chunk = data[off:off + 4].ljust(4, b"\x00")
    return int.from_bytes(chunk, "little")


def _local(value: datetime | None) -> datetime | None:
    """Les dates des propriétés OLE sont en UTC : conversion en heure locale."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None, microsecond=0)


class Duration:
    """Durée MPP : `raw` en dixièmes de minute, `units` = code d'unité MS Project."""

    __slots__ = ("raw", "units")

    def __init__(self, raw: int, units: int):
        self.raw = raw
        self.units = units

    @property
    def minutes(self) -> float:
        return self.raw / 10

    def __repr__(self) -> str:
        return f"Duration({self.minutes} min, units={self.units})"


class FieldItem:
    __slots__ = ("name", "dtype", "units", "location", "block", "offset", "varkey")

    def __init__(self, name, dtype, units, location, block, offset, varkey):
        self.name, self.dtype, self.units = name, dtype, units
        self.location, self.block, self.offset, self.varkey = location, block, offset, varkey


class FieldMap:
    """Emplacement de chaque champ (données fixes, variables ou méta), lu dans Props."""

    def __init__(self, data: bytes, table: dict, table14: dict):
        self.items: dict[str, FieldItem] = {}
        self.max_size = [0, 0]
        last_offset = 0
        block = 0
        for pos in range(0, len(data) - 27, 28):
            offset = u16(data, pos + 4)
            type_value = i32(data, pos + 12) & 0xFFFFFFFF
            category = u16(data, pos + 20)
            index = type_value & 0xFFFF
            if index & 0x8000:
                continue  # champ d'entreprise : ignoré
            entry = table14.get(index) or table.get(index)
            if entry is None:
                continue
            name, dtype, units = entry
            varkey = index
            if category in (0x0B, 0x64):
                location = "META"
            elif offset != 65535:
                location = "FIXED"
                if offset < last_offset:
                    block += 1
                last_offset = offset
                if block < 2:
                    end = offset + FIXED_SIZES.get(dtype, 0)
                    self.max_size[block] = max(self.max_size[block], end)
            else:
                location = "VAR" if varkey else "UNKNOWN"
            self.items[name] = FieldItem(name, dtype, units, location, min(block, 1), offset, varkey)

    def offset(self, name: str) -> int:
        item = self.items.get(name)
        return item.offset if item else -1

    def varkey(self, name: str) -> int | None:
        item = self.items.get(name)
        return item.varkey if item else None

    def read_all(self, uid: int, fixed: list[bytes | None], var: VarData, wanted) -> dict:
        values = {}
        for name in wanted:
            item = self.items.get(name)
            if item is not None:
                values[name] = self._read(item, uid, fixed, var)
        return values

    def _read(self, item: FieldItem, uid, fixed, var):
        if item.location == "FIXED":
            data = fixed[item.block] if item.block < len(fixed) else None
            if data is None or item.offset >= len(data):
                return None
            return self._read_fixed(item, uid, data, fixed, var)
        if item.location == "VAR":
            return self._read_var(item, uid, fixed, var)
        return None

    def _units(self, item, uid, fixed, var) -> int | None:
        if not item.units or item.units not in self.items:
            return None
        return self._read(self.items[item.units], uid, fixed, var)

    def _read_fixed(self, item, uid, data, fixed, var):
        t, off = item.dtype, item.offset
        if t == "DATE":
            return timestamp(data, off)
        if t == "INTEGER":
            return i32(data, off)
        if t == "DURATION":
            raw = i32(data, off)
            if raw == -1:
                return None
            units = self._units(item, uid, fixed, var)
            return Duration(raw, units if units is not None else 7)
        if t == "TIME_UNITS":
            return u16(data, off)
        if t in ("CONSTRAINT", "PRIORITY", "TASK_TYPE", "ACCRUE", "SHORT", "WORKGROUP",
                 "EARNED_VALUE_METHOD", "RESOURCE_REQUEST_TYPE", "RATE_UNITS"):
            return u16(data, off)
        if t == "PERCENTAGE":
            v = u16(data, off)
            return v if 0 <= v <= 100 else None
        if t == "BOOLEAN":
            return u16(data, off) != 0
        if t in ("CURRENCY", "UNITS"):
            amount = f64(data, off)
            return 0.0 if abs(amount) < 0.1 else amount / 100
        if t == "RATE":
            return f64(data, off)
        if t == "WORK":
            v = f64(data, off)
            return 0.0 if abs(v) < 1000 else v / 60000  # heures
        if t == "DELAY":
            return Duration(u16(data, off), 5)
        return None

    def _read_var(self, item, uid, fixed, var):
        t, key = item.dtype, item.varkey
        if t == "STRING":
            if var.short(uid, key) in VALUE_LIST_MASKS:
                return None  # valeur issue d'une liste de champ personnalisé : non gérée
            return unicode_string(var.blob(uid, key))
        if t == "NOTES":
            return ansi_string(var.blob(uid, key))
        if t == "DATE":
            b = var.blob(uid, key)
            return timestamp(b, 0) if b and len(b) >= 4 else None
        if t == "NUMERIC":
            return var.double(uid, key)
        if t == "CURRENCY":
            amount = var.double(uid, key)
            return 0.0 if abs(amount) < 0.1 else amount / 100
        if t == "INTEGER":
            return var.int(uid, key)
        if t == "WORK":
            v = var.double(uid, key)
            return 0.0 if abs(v) < 1000 else v / 60000
        if t in ("SHORT", "PERCENTAGE", "TIME_UNITS"):
            return var.short(uid, key)
        if t == "BOOLEAN":
            return var.short(uid, key) != 0
        if t == "DURATION":
            b = var.blob(uid, key)
            if b and len(b) >= 4 and len(b) != 512:
                units = self._units(item, uid, fixed, var)
                return Duration(i32(b, 0), units if units is not None else 5)
        return None


TASK_WANTED = (
    "UNIQUE_ID", "ID", "NAME", "WBS", "OUTLINE_LEVEL", "PARENT_TASK_UNIQUE_ID", "START", "FINISH",
    "DURATION", "SCHEDULED_START", "SCHEDULED_FINISH", "SCHEDULED_DURATION", "MANUAL_DURATION",
    "ACTUAL_DURATION_UNITS", "PERCENT_COMPLETE", "PERCENT_WORK_COMPLETE", "PRIORITY", "NOTES",
    "CONSTRAINT_TYPE", "CONSTRAINT_DATE", "DEADLINE", "CREATED", "LATE_START", "LATE_FINISH",
    "ACTUAL_START", "ACTUAL_FINISH", "WORK", "ACTUAL_WORK", "REMAINING_WORK", "COST",
    "FIXED_COST", "ACTUAL_DURATION", "REMAINING_DURATION", "TYPE", "HYPERLINK",
)
RESOURCE_WANTED = (
    "UNIQUE_ID", "ID", "NAME", "INITIALS", "GROUP", "CODE", "EMAIL_ADDRESS", "MAX_UNITS",
    "STANDARD_RATE", "STANDARD_RATE_UNITS", "OVERTIME_RATE", "OVERTIME_RATE_UNITS",
    "COST_PER_USE", "NOTES", "MATERIAL_LABEL", "WORK", "COST",
)
ASSIGNMENT_WANTED = (
    "UNIQUE_ID", "TASK_UNIQUE_ID", "RESOURCE_UNIQUE_ID", "ASSIGNMENT_UNITS", "WORK", "ACTUAL_WORK",
    "REMAINING_WORK", "START", "FINISH", "COST", "NOTES", "PERCENT_WORK_COMPLETE",
)


class MppReader:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        try:
            self.ole = olefile.OleFileIO(str(self.path))
        except (OSError, olefile.olefile.OleFileError) as exc:  # type: ignore[attr-defined]
            raise MppError(f"{self.path.name} n'est pas un fichier MS Project (.mpp) valide") from exc

    # -- accès aux flux ---------------------------------------------------
    def _stream(self, *parts: str, decode: bool = False) -> bytes:
        path = ["   114", *parts]
        if not self.ole.exists("/".join(path)):
            raise MppError(f"flux absent : {'/'.join(parts)}")
        data = self.ole.openstream(path).read()
        if decode and self.encrypted:
            data = bytes(b ^ self.xor for b in data)
        return data

    def _has(self, *parts: str) -> bool:
        return self.ole.exists("/".join(["   114", *parts]))

    # -- lecture ----------------------------------------------------------
    def read(self) -> Project:
        try:
            return self._read()
        finally:
            self.ole.close()

    def _read(self) -> Project:
        self._check_format()
        root_props = Props(self.ole.openstream("Props14").read())
        flag = root_props.byte(PASSWORD_FLAG)
        if (flag & 0x1) and root_props.get(PROTECTION_PASSWORD_HASH) is not None:
            raise MppError(f"{self.path.name} est protégé par un mot de passe")
        self.encrypted = flag != 0
        code = root_props.byte(ENCRYPTION_CODE)
        self.xor = 0 if code == 0 else 0xFF - code
        self.props = Props(self._stream("Props", decode=True))

        project = self._read_project()
        self.project = project
        self._read_resources()
        self._read_tasks()
        self._read_relations()
        self._read_assignments()
        project.finalize()
        return project

    def _check_format(self) -> None:
        if not self.ole.exists("\x01CompObj"):
            raise MppError(f"{self.path.name} n'est pas un fichier MS Project")
        raw = self.ole.openstream("\x01CompObj").read()
        try:
            n = i32(raw, 28)
            app = raw[32:32 + n - 1].decode("latin-1")
            pos = 32 + n
            m = i32(raw, pos)
            fmt = raw[pos + 4:pos + 4 + m - 1].decode("latin-1") if m > 0 else ""
        except Exception as exc:  # pragma: no cover - CompObj corrompu
            raise MppError("en-tête CompObj illisible") from exc
        match = re.match(r"Microsoft.Project.(\d+)\.0", app)
        self.app_version = int(match.group(1)) if match else PROJECT_2010
        if not fmt.startswith(("MSProject.MPP14", "MSProject.MPT14", "MSProject.GLOBAL14")):
            raise MppError(f"format {fmt or 'inconnu'} non pris en charge : seuls les fichiers "
                           "Project 2010 (et 2013 à 2019) sont gérés")

    def _read_project(self) -> Project:
        p = self.props
        meta = self.ole.get_metadata()

        def text(value):
            if isinstance(value, bytes):
                value = value.decode("cp1252", errors="replace")
            return value.strip() if isinstance(value, str) and value.strip() else None

        def tod(key):
            v = p.get(key)
            if not v:
                return None
            minutes = (u16(v, 0) // 10) % 1440
            return f"{minutes // 60:02d}:{minutes % 60:02d}:00"

        return Project(
            title=text(meta.title) or text(p.unicode(TITLE)),
            author=text(meta.author) or text(p.unicode(AUTHOR)),
            company=text(getattr(meta, "company", None)) or text(p.unicode(COMPANY)),
            manager=text(getattr(meta, "manager", None)) or text(p.unicode(MANAGER)),
            creation_date=_local(meta.create_time),
            last_saved=_local(meta.last_saved_time),
            start_date=p.timestamp(PROJECT_START_DATE),
            finish_date=p.timestamp(PROJECT_FINISH_DATE),
            schedule_from_start=(p.short(SCHEDULE_FROM) == 1),
            minutes_per_day=p.int(MINUTES_PER_DAY) or 480,
            minutes_per_week=p.int(MINUTES_PER_WEEK) or 2400,
            days_per_month=p.short(DAYS_PER_MONTH) or 20,
            currency_symbol=p.unicode(CURRENCY_SYMBOL),
            currency_code=p.unicode(CURRENCY_CODE),
            default_start_time=tod(START_TIME) or "08:00:00",
            default_finish_time=tod(END_TIME) or "17:00:00",
            source_name=self.path.name,
        )

    def _field_map(self, keys, table, table14) -> FieldMap:
        for key in keys:
            data = self.props.get(key)
            if data:
                return FieldMap(data, table, table14)
        raise MppError("table des champs absente du fichier")

    # -- tâches -----------------------------------------------------------
    def _read_tasks(self) -> None:
        fm = self._field_map(TASK_FIELD_MAP, fields.TASK_FIELDS, fields.TASK_FIELDS_MPP14)
        var = VarData(self._stream("TBkndTask", "VarMeta"), self._stream("TBkndTask", "Var2Data"))
        fmeta = FixedMeta(self._stream("TBkndTask", "FixedMeta"), 47)
        fdata = FixedData.from_meta(fmeta, self._stream("TBkndTask", "FixedData"), fm.max_size[0])
        f2meta = FixedMeta(self._stream("TBkndTask", "Fixed2Meta"), [92, 93, 94, 95, 96], len(fdata))
        f2data = FixedData.from_meta(f2meta, self._stream("TBkndTask", "Fixed2Data"))

        task_map = self._task_map(fm, fmeta, fdata, f2data, var)
        v2010 = self.app_version <= PROJECT_2010
        milestone_bit = (8, 0x20) if v2010 else (10, 0x02)
        manual_bit = (8, 0x08) if v2010 else (8, 0x80)

        tasks: dict[int, Task] = {}
        by_id: dict[int, Task] = {}
        task_order: dict[int, int] = {}
        null_order: dict[int, int] = {}

        def add_null(data):
            nid = i32(data, 4)
            if nid not in null_order:
                t = Task(uid=i32(data, 0), id=nid, is_null=True)
                tasks[t.uid] = t
                null_order[nid] = t.uid

        for uid in sorted(task_map):
            index = task_map[uid]
            data = fdata.get(index)
            if data is None:
                continue
            meta = fmeta.get(index)
            tid = i32(data, fm.offset("ID"))
            if len(data) == NULL_TASK_BLOCK_SIZE:
                add_null(data)
                continue
            if len(data) < fm.max_size[0]:
                data = data.ljust(fm.max_size[0] + 8, b"\x00")
            meta2 = f2meta.get(index)
            data2 = f2data.get(index)

            existing = by_id.get(tid)
            if existing is not None:
                if uid not in var.ids():
                    continue
                if existing.name is None:
                    tasks.pop(existing.uid, None)

            v = fm.read_all(uid, [data, data2], var, TASK_WANTED)
            manual = bool(_bits(meta2, manual_bit[0]) & manual_bit[1])
            start, finish, duration = v.get("START"), v.get("FINISH"), v.get("DURATION")
            if start is None or (v.get("SCHEDULED_START") is not None and not manual):
                start = v.get("SCHEDULED_START")
            if finish is None or (v.get("SCHEDULED_FINISH") is not None and not manual):
                finish = v.get("SCHEDULED_FINISH")
            if duration is None or (v.get("SCHEDULED_DURATION") is not None and not manual):
                duration = v.get("SCHEDULED_DURATION")
            if manual and v.get("MANUAL_DURATION") is not None:
                duration = v["MANUAL_DURATION"]

            constraint = v.get("CONSTRAINT_TYPE") or 0
            if constraint == 1:  # dès que possible -> au plus tard (ALAP)
                if v.get("LATE_START") and (start is None or start < v["LATE_START"]):
                    start = v["LATE_START"]
                if v.get("LATE_FINISH") and (finish is None or finish < v["LATE_FINISH"]):
                    finish = v["LATE_FINISH"]
            elif constraint in (5, 7) and start and finish and finish < start:
                finish = v.get("LATE_FINISH")

            name = v.get("NAME")
            created = v.get("CREATED")
            if name is None and (start in (None, EPOCH) or finish in (None, EPOCH)
                                 or created in (None, EPOCH)):
                add_null(data)
                continue

            units_raw = v.get("ACTUAL_DURATION_UNITS") or 0
            task = Task(
                uid=uid, id=tid, name=name, wbs=v.get("WBS"),
                outline_level=v.get("OUTLINE_LEVEL") or 0,
                parent_uid=v.get("PARENT_TASK_UNIQUE_ID"),
                start=start, finish=finish, duration=duration,
                duration_format=units_raw & 0x3F,
                estimated=bool(units_raw & 0x20),
                percent_complete=v.get("PERCENT_COMPLETE") or 0,
                percent_work_complete=v.get("PERCENT_WORK_COMPLETE") or 0,
                priority=v.get("PRIORITY") if v.get("PRIORITY") is not None else 500,
                notes=v.get("NOTES"),
                milestone=bool(_bits(meta, milestone_bit[0]) & milestone_bit[1]),
                manual=manual,
                constraint_type=constraint,
                constraint_date=v.get("CONSTRAINT_DATE"),
                deadline=v.get("DEADLINE"),
                created=created,
                actual_start=v.get("ACTUAL_START"),
                actual_finish=v.get("ACTUAL_FINISH"),
                work_hours=v.get("WORK"),
                actual_work_hours=v.get("ACTUAL_WORK"),
                remaining_work_hours=v.get("REMAINING_WORK"),
                cost=v.get("COST"),
                fixed_cost=v.get("FIXED_COST"),
                actual_duration=v.get("ACTUAL_DURATION"),
                remaining_duration=v.get("REMAINING_DURATION"),
                task_type=v.get("TYPE"),
                expanded=not (meta[12] & 0x02) if meta and len(meta) > 12 else True,
            )
            tasks[uid] = task
            by_id[tid] = task
            if data2 is None or len(data2) < 24:
                null_order[tid] = uid
            else:
                task_order[i64(data2, 16)] = uid

        self._order_tasks(tasks, task_order, null_order)
        self.project.tasks = sorted(tasks.values(), key=lambda t: t.id)

    def _task_map(self, fm, fmeta, fdata, f2data, var) -> dict[int, int | None]:
        task_map: dict[int, int | None] = {}
        uid_off = fm.offset("UNIQUE_ID")
        for loop in range(fmeta.adjusted_count - 1, 2, -1):
            data = fdata.get(loop)
            data2 = f2data.get(loop)
            if data is None or data2 is None:
                continue
            flags = i32(fmeta.get(loop), 0)
            if flags & 0x02:
                uid = u16(data, 0)
                task_map.setdefault(uid, None)  # tâche supprimée
            elif len(data) == NULL_TASK_BLOCK_SIZE:
                task_map.setdefault(i32(data, 0), loop)
            else:
                max_size = fm.max_size[0]
                if max_size == 0 or (len(data) * 100) // max_size > 75:
                    uid = i32(data, uid_off)
                    if uid not in task_map or var.types(uid):
                        if uid not in task_map or (flags & 0x04) == 0:
                            task_map[uid] = loop
        return {k: v for k, v in task_map.items() if v is not None}

    @staticmethod
    def _order_tasks(tasks, task_order, null_order) -> None:
        """Recalcule les ID dans l'ordre d'affichage (postProcessTasks de MPXJ)."""
        increment = ((len(null_order) // 1000) + 1) * 2000
        has_zero = 0 in tasks
        next_id = 0 if has_zero else increment
        order: dict[int, int] = {}
        for key in sorted(task_order):
            order[next_id] = task_order[key]
            next_id += increment
        inserted = 0
        offsets: dict[int, int] = {}
        for nid in sorted(null_order):
            base = (nid - inserted) * increment
            target = base
            prev = offsets.get(base)
            off = 0 if prev is None else prev + 1
            inserted += 1
            while target in order:
                off += 1
                if off == increment:
                    raise MppError("impossible de rétablir l'ordre des tâches")
                target = base - (increment - off)
            offsets[base] = off
            order[target] = null_order[nid]
        new_id = 0 if has_zero else 1
        for key in sorted(order):
            task = tasks.get(order[key])
            if task is not None:
                task.id = new_id
            new_id += 1

    # -- liens ------------------------------------------------------------
    def _read_relations(self) -> None:
        if not self._has("TBkndCons", "FixedMeta"):
            return
        meta = FixedMeta(self._stream("TBkndCons", "FixedMeta"), 10)
        data = FixedData.from_meta_fixed_size(meta, 20, self._stream("TBkndCons", "FixedData", decode=True))
        later = self.app_version > PROJECT_2010
        units_off, lag_off = (18, 14) if later else (14, 16)
        tasks = {t.uid: t for t in self.project.tasks}
        for loop in range(meta.item_count):
            m = meta.get(loop)
            if m is None or u16(m, 0) != 0:
                continue
            index = data.index_from_offset(i32(m, 4))
            item = data.get(index)
            if item is None or len(item) < 14:
                continue
            pred, succ = i32(item, 4), i32(item, 8)
            if pred == 0 or succ == 0 or pred == succ or pred not in tasks or succ not in tasks:
                continue
            self.project.relations.append(Relation(
                uid=i32(item, 0), predecessor_uid=pred, successor_uid=succ,
                type=u16(item, 12), lag=i32(item, lag_off), lag_format=u16(item, units_off) & 0x1F,
            ))

    # -- ressources -------------------------------------------------------
    def _read_resources(self) -> None:
        fm = self._field_map(RESOURCE_FIELD_MAP, fields.RESOURCE_FIELDS,
                             fields.RESOURCE_FIELDS_MPP14)
        var = VarData(self._stream("TBkndRsc", "VarMeta"), self._stream("TBkndRsc", "Var2Data"))
        fmeta = FixedMeta(self._stream("TBkndRsc", "FixedMeta"), 37)
        fdata = FixedData.from_meta(fmeta, self._stream("TBkndRsc", "FixedData", decode=True))
        f2meta = FixedMeta(self._stream("TBkndRsc", "Fixed2Meta"), [50, 51], len(fdata))
        f2data = FixedData.from_meta(f2meta, self._stream("TBkndRsc", "Fixed2Data", decode=True))

        uid_off = fm.offset("UNIQUE_ID")
        res_map: dict[int, int] = {}
        for loop in range(fmeta.adjusted_count):
            data = fdata.get(loop)
            if data is None or len(data) < fm.max_size[0]:
                continue
            res_map.setdefault(u16(data, uid_off), loop)

        type_off, type_mask = (9, 0x02) if self.app_version <= PROJECT_2010 else (12, 0x10)
        for uid in sorted(var.ids()):
            index = res_map.get(uid)
            if index is None:
                continue
            data = fdata.get(index)
            meta = fmeta.get(index)
            meta2 = f2meta.get(index)
            v = fm.read_all(uid, [data, f2data.get(index)], var, RESOURCE_WANTED)
            if meta and len(meta) > type_off and meta[type_off] & type_mask:
                rtype = 1  # travail
            elif meta2 and len(meta2) > 8 and meta2[8] & 0x10:
                rtype = 2  # coût
            else:
                rtype = 0  # matériel
            self.project.resources.append(Resource(
                uid=uid, id=i32(data, fm.offset("ID")), name=v.get("NAME"), initials=v.get("INITIALS"),
                group=v.get("GROUP"), code=v.get("CODE"), email=v.get("EMAIL_ADDRESS"), type=rtype,
                max_units=v.get("MAX_UNITS"), standard_rate=v.get("STANDARD_RATE"),
                standard_rate_format=v.get("STANDARD_RATE_UNITS"), overtime_rate=v.get("OVERTIME_RATE"),
                overtime_rate_format=v.get("OVERTIME_RATE_UNITS"), cost_per_use=v.get("COST_PER_USE"),
                notes=v.get("NOTES"), material_label=v.get("MATERIAL_LABEL"),
                work_hours=v.get("WORK"), cost=v.get("COST"),
            ))

    # -- affectations -----------------------------------------------------
    def _read_assignments(self) -> None:
        fm = self._field_map(ASSIGNMENT_FIELD_MAP, fields.ASSIGNMENT_FIELDS, fields.ASSIGNMENT_FIELDS_MPP14)
        var = VarData(self._stream("TBkndAssn", "VarMeta"), self._stream("TBkndAssn", "Var2Data"))
        fmeta = FixedMeta(self._stream("TBkndAssn", "FixedMeta"), 34)
        fdata = FixedData.from_size(110, self._stream("TBkndAssn", "FixedData", decode=True))
        f2data = FixedData.from_size(48, self._stream("TBkndAssn", "Fixed2Data", decode=True))
        tasks = {t.uid for t in self.project.tasks if not t.is_null}
        resources = {r.uid for r in self.project.resources}
        seen: set[tuple[int, int]] = set()
        for loop in range(fmeta.item_count):
            meta = fmeta.get(loop)
            if meta is None or meta[0] != 0:
                continue
            index = fdata.index_from_offset(i32(meta, 4))
            data = fdata.get(index)
            if data is None:
                continue
            if len(data) < fm.max_size[0]:
                data = data.ljust(fm.max_size[0], b"\x00")
            uid = i32(data, fm.offset("UNIQUE_ID"))
            if uid not in var.ids():
                continue
            task_uid = i32(data, fm.offset("TASK_UNIQUE_ID"))
            res_uid = i32(data, fm.offset("RESOURCE_UNIQUE_ID"))
            if task_uid not in tasks or (task_uid, res_uid) in seen:
                continue
            seen.add((task_uid, res_uid))
            v = fm.read_all(uid, [data, f2data.get(index)], var, ASSIGNMENT_WANTED)
            if res_uid == ASSIGNMENT_NULL_RESOURCE_ID or res_uid not in resources:
                res_uid = None
            self.project.assignments.append(Assignment(
                uid=uid, task_uid=task_uid, resource_uid=res_uid, units=v.get("ASSIGNMENT_UNITS"),
                work_hours=v.get("WORK"), actual_work_hours=v.get("ACTUAL_WORK"),
                remaining_work_hours=v.get("REMAINING_WORK"), start=v.get("START"),
                finish=v.get("FINISH"), cost=v.get("COST"), notes=v.get("NOTES"),
                percent_work_complete=v.get("PERCENT_WORK_COMPLETE"),
            ))


def read_mpp(path: str | Path) -> Project:
    return MppReader(path).read()


__all__ = ["read_mpp", "MppReader", "MppError", "Duration", "datetime"]
