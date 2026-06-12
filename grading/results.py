"""Result data model.

This is the single source of truth for grading output: the on-screen HTML
table and the downloadable grades CSV are both rendered from GradingResult,
so they can never diverge.
"""
from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CriterionResult:
    criterion: str
    passed: bool
    points_earned: float
    points_possible: float
    detail: str


@dataclass(frozen=True)
class StudentResult:
    student: str
    criteria: tuple[CriterionResult, ...]

    @property
    def total(self) -> float:
        return sum(c.points_earned for c in self.criteria)

    @property
    def possible(self) -> float:
        return sum(c.points_possible for c in self.criteria)


def _fmt(value: float) -> str:
    return f"{value:g}"


@dataclass
class GradingResult:
    students: list[StudentResult]
    criterion_names: list[str]
    warnings: list[str] = field(default_factory=list)
    result_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def header_row(self) -> list[str]:
        return ["Student", *self.criterion_names, "Total", "Possible"]

    def to_table_rows(self) -> list[StudentResult]:
        return sorted(self.students, key=lambda s: s.student.lower())

    def to_dict(self) -> dict:
        return {
            "result_id": self.result_id,
            "criteria": list(self.criterion_names),
            "students": [
                {
                    "student": s.student,
                    "total": s.total,
                    "possible": s.possible,
                    "criteria": [
                        {
                            "criterion": c.criterion,
                            "passed": c.passed,
                            "points_earned": c.points_earned,
                            "points_possible": c.points_possible,
                            "detail": c.detail,
                        }
                        for c in s.criteria
                    ],
                }
                for s in self.to_table_rows()
            ],
            "warnings": list(self.warnings),
        }

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(self.header_row())
        for s in self.to_table_rows():
            writer.writerow(
                [
                    s.student,
                    *(_fmt(c.points_earned) for c in s.criteria),
                    _fmt(s.total),
                    _fmt(s.possible),
                ]
            )
        return buf.getvalue()
