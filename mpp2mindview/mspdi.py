"""Écriture au format XML MS Project (MSPDI), importable par MindView."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .model import Project, Resource, Task
from .rtf import rtf_to_text

NS = "http://schemas.microsoft.com/project"
NULL_RESOURCE_UID = -65535
RATE_FORMATS = {1, 2, 3, 4, 5, 7}


def _date(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%dT%H:%M:%S") if value else None


def _minutes(minutes: float | None) -> str:
    """Durée au format ISO 8601 utilisé par MS Project (PT8H0M0S)."""
    total = round((minutes or 0) * 60)
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}PT{total // 3600}H{(total % 3600) // 60}M{total % 60}S"


def _hours(hours: float | None) -> str:
    return _minutes((hours or 0) * 60)


def _bool(value: bool) -> str:
    return "1" if value else "0"


def _num(value: float | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text not in ("", "-0") else "0"
    return str(value)


class _Node:
    def __init__(self, parent: ET.Element, tag: str):
        self.el = ET.SubElement(parent, tag)

    def add(self, tag: str, value) -> None:
        if value is None or value == "":
            return
        child = ET.SubElement(self.el, tag)
        child.text = value if isinstance(value, str) else str(value)


def _project_header(root: ET.Element, p: Project) -> None:
    node = _Node.__new__(_Node)
    node.el = root
    node.add("SaveVersion", "14")
    node.add("Name", p.source_name)
    node.add("Title", p.title)
    node.add("Company", p.company)
    node.add("Manager", p.manager)
    node.add("Author", p.author)
    node.add("CreationDate", _date(p.creation_date))
    node.add("LastSaved", _date(p.last_saved))
    node.add("ScheduleFromStart", _bool(p.schedule_from_start))
    node.add("StartDate", _date(p.start_date))
    node.add("FinishDate", _date(p.finish_date))
    node.add("CurrencySymbol", p.currency_symbol)
    node.add("CurrencyCode", p.currency_code)
    node.add("CalendarUID", "1")
    node.add("DefaultStartTime", p.default_start_time)
    node.add("DefaultFinishTime", p.default_finish_time)
    node.add("MinutesPerDay", str(p.minutes_per_day))
    node.add("MinutesPerWeek", str(p.minutes_per_week))
    node.add("DaysPerMonth", str(p.days_per_month))


def _calendars(root: ET.Element) -> None:
    """Calendrier « Standard » : lundi-vendredi, 08:00-12:00 et 13:00-17:00."""
    cals = ET.SubElement(root, "Calendars")
    cal = _Node(cals, "Calendar")
    cal.add("UID", "1")
    cal.add("Name", "Standard")
    cal.add("IsBaseCalendar", "1")
    cal.add("IsBaselineCalendar", "0")
    cal.add("BaseCalendarUID", "-1")
    days = ET.SubElement(cal.el, "WeekDays")
    for day in range(1, 8):  # 1 = dimanche
        wd = _Node(days, "WeekDay")
        wd.add("DayType", str(day))
        working = day not in (1, 7)
        wd.add("DayWorking", _bool(working))
        if working:
            times = ET.SubElement(wd.el, "WorkingTimes")
            for start, end in (("08:00:00", "12:00:00"), ("13:00:00", "17:00:00")):
                wt = _Node(times, "WorkingTime")
                wt.add("FromTime", start)
                wt.add("ToTime", end)


def _task(parent: ET.Element, t: Task, links) -> None:
    n = _Node(parent, "Task")
    n.add("UID", t.uid)
    n.add("ID", t.id)
    if t.is_null:
        n.add("IsNull", "1")
        return
    n.add("Name", t.name)
    n.add("Active", "1")
    n.add("Manual", _bool(t.manual))
    n.add("Type", t.task_type if t.task_type in (0, 1, 2) else None)
    n.add("IsNull", "0")
    n.add("CreateDate", _date(t.created))
    n.add("WBS", t.wbs)
    n.add("OutlineNumber", t.outline_number)
    n.add("OutlineLevel", t.outline_level)
    n.add("Priority", t.priority)
    n.add("Start", _date(t.start))
    n.add("Finish", _date(t.finish))
    duration = t.duration.minutes if t.duration is not None else None
    n.add("Duration", _minutes(duration) if duration is not None else None)
    if t.manual:
        n.add("ManualStart", _date(t.start))
        n.add("ManualFinish", _date(t.finish))
        n.add("ManualDuration", _minutes(duration) if duration is not None else None)
    n.add("DurationFormat", t.duration_format or None)
    n.add("Work", _hours(t.work_hours) if t.work_hours is not None else None)
    n.add("Estimated", _bool(t.estimated))
    n.add("Milestone", _bool(t.milestone))
    n.add("Summary", _bool(t.summary))
    n.add("FixedCost", _num(t.fixed_cost))
    n.add("PercentComplete", t.percent_complete)
    n.add("PercentWorkComplete", t.percent_work_complete)
    n.add("Cost", _num(t.cost))
    n.add("ActualStart", _date(t.actual_start))
    n.add("ActualFinish", _date(t.actual_finish))
    if t.actual_duration is not None:
        n.add("ActualDuration", _minutes(t.actual_duration.minutes))
    n.add("ActualWork", _hours(t.actual_work_hours) if t.actual_work_hours is not None else None)
    if t.remaining_duration is not None:
        n.add("RemainingDuration", _minutes(t.remaining_duration.minutes))
    n.add("RemainingWork", _hours(t.remaining_work_hours) if t.remaining_work_hours is not None else None)
    n.add("ConstraintType", t.constraint_type)
    n.add("CalendarUID", "-1")
    if t.constraint_type not in (0, 1):
        n.add("ConstraintDate", _date(t.constraint_date))
    n.add("Deadline", _date(t.deadline))
    n.add("Notes", rtf_to_text(t.notes))
    for rel in links:
        pl = _Node(n.el, "PredecessorLink")
        pl.add("PredecessorUID", rel.predecessor_uid)
        pl.add("Type", rel.type)
        pl.add("CrossProject", "0")
        pl.add("LinkLag", rel.lag)
        pl.add("LagFormat", rel.lag_format or 7)


def _resource(parent: ET.Element, r: Resource) -> None:
    n = _Node(parent, "Resource")
    n.add("UID", r.uid)
    n.add("ID", r.id)
    n.add("Name", r.name)
    n.add("Type", "1" if r.type == 1 else "0")
    n.add("IsNull", "0")
    n.add("Initials", r.initials)
    if r.type == 0:
        n.add("MaterialLabel", r.material_label)
    n.add("Code", r.code)
    n.add("Group", r.group)
    n.add("EmailAddress", r.email)
    if r.type == 1 and r.max_units is not None:
        n.add("MaxUnits", _num(r.max_units / 100))
    n.add("Work", _hours(r.work_hours) if r.work_hours is not None else None)
    if r.type != 2:
        n.add("StandardRate", _num(r.standard_rate or 0.0))
        n.add("StandardRateFormat", r.standard_rate_format if r.standard_rate_format in RATE_FORMATS else 2)
    n.add("Cost", _num(r.cost))
    if r.type == 1:
        n.add("OvertimeRate", _num(r.overtime_rate or 0.0))
        n.add("OvertimeRateFormat", r.overtime_rate_format if r.overtime_rate_format in RATE_FORMATS else 2)
    if r.type != 2:
        n.add("CostPerUse", _num(r.cost_per_use or 0.0))
    n.add("Notes", rtf_to_text(r.notes))
    n.add("IsCostResource", _bool(r.type == 2))


def build_tree(p: Project) -> ET.ElementTree:
    root = ET.Element("Project", {"xmlns": NS})
    _project_header(root, p)
    _calendars(root)

    links: dict[int, list] = {}
    for rel in p.relations:
        links.setdefault(rel.successor_uid, []).append(rel)

    tasks = ET.SubElement(root, "Tasks")
    for t in p.tasks:
        _task(tasks, t, links.get(t.uid, []))

    resources = ET.SubElement(root, "Resources")
    for r in sorted(p.resources, key=lambda r: r.id):
        _resource(resources, r)

    assignments = ET.SubElement(root, "Assignments")
    for a in sorted(p.assignments, key=lambda a: a.uid):
        n = _Node(assignments, "Assignment")
        n.add("UID", a.uid)
        n.add("TaskUID", a.task_uid)
        n.add("ResourceUID", a.resource_uid if a.resource_uid is not None else NULL_RESOURCE_UID)
        n.add("PercentWorkComplete", a.percent_work_complete)
        n.add("ActualWork", _hours(a.actual_work_hours) if a.actual_work_hours is not None else None)
        n.add("Cost", _num(a.cost))
        n.add("Finish", _date(a.finish))
        n.add("RemainingWork", _hours(a.remaining_work_hours) if a.remaining_work_hours is not None else None)
        n.add("Start", _date(a.start))
        n.add("Units", _num((a.units or 0) / 100))
        n.add("Work", _hours(a.work_hours) if a.work_hours is not None else None)

    ET.indent(root, space="\t")
    return ET.ElementTree(root)


def write_mspdi(p: Project, path: str | Path) -> None:
    tree = build_tree(p)
    with open(path, "wb") as fh:
        fh.write(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n')
        tree.write(fh, encoding="utf-8", xml_declaration=False)
