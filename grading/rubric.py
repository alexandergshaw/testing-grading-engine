"""Rubric CSV parsing and validation.

Canonical schema, same five columns for every assignment:
    criterion,points,check_type,target,params
params is key=value pairs separated by ';' (e.g. "pattern=def main;ignore_case=true").
All validation problems are collected and reported together before any grading runs.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from .checks import CHECK_REGISTRY

REQUIRED_COLUMNS = ("criterion", "points", "check_type", "target", "params")


@dataclass(frozen=True)
class Criterion:
    name: str
    points: float
    check_type: str
    target: str
    params: dict[str, str] = field(default_factory=dict)


class RubricError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def parse_params(raw: str) -> dict[str, str]:
    params: dict[str, str] = {}
    # split on ';' unless escaped as '\;' (commands etc. may contain semicolons)
    for part in re.split(r"(?<!\\);", raw or ""):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"malformed params entry {part!r} (expected key=value)")
        key, value = part.split("=", 1)
        params[key.strip()] = value.strip().replace("\\;", ";")
    return params


def build_criterion(
    label: str, name: str, points_raw: str, check_type: str, target: str, params_raw: str
) -> tuple[Criterion, list[str]]:
    """Validate one criterion's raw fields; shared by the CSV and review-form paths."""
    errors: list[str] = []
    name = (name or "").strip()
    if not name:
        errors.append(f"{label}: empty criterion name")

    points_raw = (points_raw or "").strip()
    try:
        points = float(points_raw)
    except ValueError:
        errors.append(f"{label}: points {points_raw!r} is not a number")
        points = 0.0

    check_type = (check_type or "").strip()
    spec = CHECK_REGISTRY.get(check_type)
    if spec is None:
        known = ", ".join(sorted(CHECK_REGISTRY))
        errors.append(f"{label}: unknown check_type {check_type!r} (known: {known})")

    try:
        params = parse_params(params_raw or "")
    except ValueError as e:
        errors.append(f"{label}: {e}")
        params = {}

    if spec is not None:
        for p in spec.required_params:
            if p not in params:
                errors.append(f"{label}: check {check_type!r} requires param {p!r}")

    return Criterion(name, points, check_type, (target or "").strip(), params), errors


def parse_rubric(text: str) -> list[Criterion]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fieldnames = [(f or "").strip().lower() for f in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise RubricError(
            [
                f"rubric is missing column(s): {', '.join(missing)} "
                f"(expected header: {','.join(REQUIRED_COLUMNS)})"
            ]
        )
    reader.fieldnames = fieldnames

    criteria: list[Criterion] = []
    errors: list[str] = []
    for lineno, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue  # blank line
        name = (row.get("criterion") or "").strip()
        label = f"row {lineno} ({name or '?'})"
        criterion, row_errors = build_criterion(
            label,
            name,
            row.get("points") or "",
            row.get("check_type") or "",
            row.get("target") or "",
            row.get("params") or "",
        )
        criteria.append(criterion)
        errors.extend(row_errors)

    if errors:
        raise RubricError(errors)
    if not criteria:
        raise RubricError(["rubric has no criteria rows"])
    return criteria
