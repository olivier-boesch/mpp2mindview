"""Modèle de projet indépendant du format (lu depuis le .mpp, écrit en XML)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Task:
    uid: int
    id: int
    name: str | None = None
    is_null: bool = False
    wbs: str | None = None
    outline_level: int = 0
    outline_number: str | None = None
    parent_uid: int | None = None
    start: datetime | None = None
    finish: datetime | None = None
    duration: Any = None  # reader.Duration
    duration_format: int = 7
    estimated: bool = False
    percent_complete: int = 0
    percent_work_complete: int = 0
    priority: int = 500
    notes: str | None = None
    milestone: bool = False
    summary: bool = False
    manual: bool = False
    constraint_type: int = 0
    constraint_date: datetime | None = None
    deadline: datetime | None = None
    created: datetime | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None
    work_hours: float | None = None
    actual_work_hours: float | None = None
    remaining_work_hours: float | None = None
    cost: float | None = None
    fixed_cost: float | None = None
    actual_duration: Any = None
    remaining_duration: Any = None
    task_type: int | None = None
    expanded: bool = True


@dataclass
class Relation:
    uid: int
    predecessor_uid: int
    successor_uid: int
    type: int = 1  # 0=FF, 1=FS, 2=SF, 3=SS (même codage que le XML MS Project)
    lag: int = 0  # dixièmes de minute
    lag_format: int = 7


@dataclass
class Resource:
    uid: int
    id: int
    name: str | None = None
    initials: str | None = None
    group: str | None = None
    code: str | None = None
    email: str | None = None
    type: int = 1  # 0=matériel, 1=travail, 2=coût
    max_units: float | None = None
    standard_rate: float | None = None
    standard_rate_format: int | None = None
    overtime_rate: float | None = None
    overtime_rate_format: int | None = None
    cost_per_use: float | None = None
    notes: str | None = None
    material_label: str | None = None
    work_hours: float | None = None
    cost: float | None = None


@dataclass
class Assignment:
    uid: int
    task_uid: int
    resource_uid: int | None
    units: float | None = None
    work_hours: float | None = None
    actual_work_hours: float | None = None
    remaining_work_hours: float | None = None
    start: datetime | None = None
    finish: datetime | None = None
    cost: float | None = None
    notes: str | None = None
    percent_work_complete: int | None = None


@dataclass
class Project:
    title: str | None = None
    author: str | None = None
    company: str | None = None
    manager: str | None = None
    creation_date: datetime | None = None
    last_saved: datetime | None = None
    start_date: datetime | None = None
    finish_date: datetime | None = None
    schedule_from_start: bool = True
    minutes_per_day: int = 480
    minutes_per_week: int = 2400
    days_per_month: int = 20
    currency_symbol: str | None = None
    currency_code: str | None = None
    default_start_time: str = "08:00:00"
    default_finish_time: str = "17:00:00"
    source_name: str | None = None
    tasks: list[Task] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    assignments: list[Assignment] = field(default_factory=list)

    def finalize(self) -> None:
        """Calcule les tâches récapitulatives et les numéros hiérarchiques."""
        self.tasks.sort(key=lambda t: t.id)
        real = [t for t in self.tasks if not t.is_null]
        for i, task in enumerate(real):
            nxt = real[i + 1] if i + 1 < len(real) else None
            task.summary = task.outline_level == 0 or (nxt is not None and nxt.outline_level > task.outline_level)
        counters: list[int] = []
        for task in real:
            level = task.outline_level
            if level == 0:
                task.outline_number = "0"
                continue
            del counters[level:]
            while len(counters) < level:
                counters.append(0)
            counters[level - 1] += 1
            task.outline_number = ".".join(str(c) for c in counters)
            if not task.wbs:
                task.wbs = task.outline_number
