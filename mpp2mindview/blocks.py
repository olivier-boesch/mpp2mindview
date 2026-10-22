"""Structures binaires de bas niveau des fichiers MPP (Project 2010 et suivants).

Logique portée depuis MPXJ (https://www.mpxj.org), LGPL-2.1.
"""
from __future__ import annotations

import struct
from datetime import datetime, timedelta

MAGIC = 0xFADFADBA
EPOCH = datetime(1983, 12, 31)


def u8(data: bytes, off: int) -> int:
    return data[off]


def u16(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        return 0
    return struct.unpack_from("<H", data, off)[0]


def i32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        return 0
    return struct.unpack_from("<i", data, off)[0]


def u32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        return 0
    return struct.unpack_from("<I", data, off)[0]


def i64(data: bytes, off: int) -> int:
    if off < 0 or off + 8 > len(data):
        return 0
    return struct.unpack_from("<q", data, off)[0]


def f64(data: bytes, off: int) -> float:
    if off < 0 or off + 8 > len(data):
        return 0.0
    value = struct.unpack_from("<d", data, off)[0]
    return 0.0 if value != value else value  # NaN -> 0


def timestamp(data: bytes, off: int) -> datetime | None:
    """Date MPP : 2 octets d'heure (unités de 6 s) puis 2 octets de jours depuis 1983-12-31."""
    if data is None or off + 4 > len(data):
        return None
    days = u16(data, off + 2)
    if days <= 1 or days == 65535:
        return None
    time = u16(data, off)
    if time == 65535:
        time = 0
    result = EPOCH + timedelta(days=days, seconds=time * 6)
    if days < 100 and result.second != 0:
        return None
    return result


def unicode_string(data: bytes | None, off: int = 0) -> str | None:
    if data is None:
        return None
    end = len(data)
    for i in range(off, len(data) - 1, 2):
        if data[i] == 0 and data[i + 1] == 0:
            end = i
            break
    return data[off:end].decode("utf-16-le", errors="replace")


def ansi_string(data: bytes | None, off: int = 0) -> str | None:
    if data is None:
        return None
    end = data.find(b"\x00", off)
    if end == -1:
        end = len(data)
    return data[off:end].decode("cp1252", errors="replace")


class Props:
    """Bloc de propriétés clé -> octets (format Props14)."""

    def __init__(self, raw: bytes):
        self.map: dict[int, bytes] = {}
        if len(raw) < 16:
            return
        count = u16(raw, 12)
        pos = 16
        found = 0
        while found < count and len(raw) - pos >= 12:
            size = i32(raw, pos)
            key = i32(raw, pos + 4)
            pos += 12
            if size < 1 or len(raw) - pos < size:
                break
            self.map[key] = raw[pos:pos + size]
            pos += size
            found += 1
            if size % 2:
                pos += 1

    def get(self, key: int) -> bytes | None:
        return self.map.get(key)

    def byte(self, key: int) -> int:
        v = self.map.get(key)
        return v[0] if v else 0

    def short(self, key: int) -> int:
        v = self.map.get(key)
        return u16(v, 0) if v else 0

    def int(self, key: int) -> int:
        v = self.map.get(key)
        return i32(v, 0) if v else 0

    def timestamp(self, key: int) -> datetime | None:
        v = self.map.get(key)
        return timestamp(v, 0) if v else None

    def unicode(self, key: int) -> str | None:
        v = self.map.get(key)
        return unicode_string(v, 0) if v else None


class FixedMeta:
    HEADER = 16

    def __init__(self, raw: bytes, item_size: int | list[int], other_count: int | None = None):
        if len(raw) < self.HEADER or u32(raw, 0) != MAGIC:
            raise ValueError("FixedMeta : nombre magique invalide")
        self.item_count = i32(raw, 8)
        available = len(raw) - self.HEADER
        if isinstance(item_size, list):
            item_size = self._choose_size(item_size, available, other_count)
        self.item_size = item_size
        n = available // item_size
        self.items = [raw[self.HEADER + i * item_size:self.HEADER + (i + 1) * item_size] for i in range(n)]

    def _choose_size(self, sizes: list[int], available: int, other_count: int | None) -> int:
        size = sizes[0]
        distance = -(2 ** 31)
        for test in sizes:
            if available % test == 0:
                if other_count is not None and available // test == other_count:
                    return test
                d = self.item_count * test - available
                if distance < d <= 0:
                    size, distance = test, d
        return size

    @property
    def adjusted_count(self) -> int:
        return len(self.items)

    def get(self, index: int) -> bytes | None:
        return self.items[index] if 0 <= index < len(self.items) else None


class FixedData:
    """Bloc de données de taille fixe, découpé selon les offsets d'un FixedMeta."""

    def __init__(self, items: list[bytes | None], offsets: list[int]):
        self.items = items
        self.offsets = offsets

    @classmethod
    def from_meta(cls, meta: FixedMeta, raw: bytes, max_size: int = 0, min_size: int = 0) -> "FixedData":
        n = meta.adjusted_count
        items: list[bytes | None] = [None] * n
        offsets = [0] * n
        for i in range(n):
            off = i32(meta.items[i], 4)
            if off < 0 or off > len(raw):
                continue
            if i + 1 == n:
                size = len(raw) - off
            else:
                size = i32(meta.items[i + 1], 4) - off
            if size == 0:
                size = min_size
            available = len(raw) - off
            if size < 0 or size > available:
                size = available if max_size == 0 else min(max_size, available)
            if max_size and size > max_size:
                size = max_size
            if size > 0:
                items[i] = raw[off:off + size]
                offsets[i] = off
        return cls(items, offsets)

    @classmethod
    def from_meta_fixed_size(cls, meta: FixedMeta, item_size: int, raw: bytes) -> "FixedData":
        n = meta.adjusted_count
        items: list[bytes | None] = [None] * n
        offsets = [0] * n
        for i in range(n):
            off = i32(meta.items[i], 4)
            if off < 0 or off > len(raw):
                continue
            size = min(item_size, len(raw) - off)
            items[i] = raw[off:off + size]
            offsets[i] = off
        return cls(items, offsets)

    @classmethod
    def from_size(cls, item_size: int, raw: bytes) -> "FixedData":
        n = len(raw) // item_size
        return cls([raw[i * item_size:(i + 1) * item_size] for i in range(n)],
                   [i * item_size for i in range(n)])

    def __len__(self) -> int:
        return len(self.items)

    def get(self, index: int | None) -> bytes | None:
        if index is None or not 0 <= index < len(self.items):
            return None
        return self.items[index]

    def index_from_offset(self, offset: int) -> int:
        try:
            return self.offsets.index(offset)
        except ValueError:
            return -1


class VarData:
    """Données de taille variable : VarMeta (id, type -> offset) + Var2Data."""

    def __init__(self, meta_raw: bytes, data_raw: bytes):
        self.table: dict[int, dict[int, int]] = {}
        if len(meta_raw) >= 24:
            magic = u32(meta_raw, 0)
            if magic not in (0, MAGIC):
                raise ValueError("VarMeta : nombre magique invalide")
            count = i32(meta_raw, 8)
            pos = 24
            for _ in range(count):
                if len(meta_raw) - pos < 12:
                    break
                uid = i32(meta_raw, pos)
                off = i32(meta_raw, pos + 4)
                typ = u16(meta_raw, pos + 8)
                pos += 12
                self.table.setdefault(uid, {})[typ] = off
        self.blobs: dict[int, bytes] = {}
        for offsets in self.table.values():
            for off in offsets.values():
                if off in self.blobs or off < 0 or off + 4 > len(data_raw):
                    continue
                size = i32(data_raw, off)
                if size < 0 or size > len(data_raw) - off - 4:
                    continue
                self.blobs[off] = data_raw[off + 4:off + 4 + size]

    def ids(self) -> set[int]:
        return set(self.table)

    def types(self, uid: int) -> set[int]:
        return set(self.table.get(uid, {}))

    def blob(self, uid: int, typ: int | None) -> bytes | None:
        if typ is None:
            return None
        off = self.table.get(uid, {}).get(typ)
        return None if off is None else self.blobs.get(off)

    def blob_at(self, offset: int) -> bytes | None:
        return self.blobs.get(offset)

    def short(self, uid: int, typ: int | None) -> int:
        b = self.blob(uid, typ)
        return u16(b, 0) if b and len(b) >= 2 else 0

    def int(self, uid: int, typ: int | None, off: int = 0) -> int:
        b = self.blob(uid, typ)
        return i32(b, off) if b and len(b) >= off + 4 else 0

    def double(self, uid: int, typ: int | None) -> float:
        b = self.blob(uid, typ)
        return f64(b, 0) if b and len(b) >= 8 else 0.0
