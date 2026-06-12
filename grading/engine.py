"""Grading engine: runs every rubric criterion against every student folder.

A crashing check never aborts the run - it becomes a failed criterion with a
"check error" detail message.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .checks import CHECK_REGISTRY, CheckContext
from .extract import find_student_folders
from .results import CriterionResult, GradingResult, StudentResult
from .rubric import Criterion


def grade_student(folder: Path, rubric: list[Criterion], allow_exec: bool = False) -> StudentResult:
    results = []
    for criterion in rubric:
        spec = CHECK_REGISTRY[criterion.check_type]
        ctx = CheckContext(
            folder=folder,
            target=criterion.target,
            params=criterion.params,
            allow_exec=allow_exec,
        )
        try:
            passed, detail = spec.func(ctx)
        except Exception as e:
            passed, detail = False, f"check error: {e}"
        results.append(
            CriterionResult(
                criterion=criterion.name,
                passed=passed,
                points_earned=criterion.points if passed else 0.0,
                points_possible=criterion.points,
                detail=detail,
            )
        )
    return StudentResult(student=folder.name, criteria=tuple(results))


def grade_all(
    submissions_dir: Path,
    rubric: list[Criterion],
    allow_exec: bool = False,
    warnings: Iterable[str] = (),
) -> GradingResult:
    student_dirs, detect_warnings = find_student_folders(submissions_dir)
    return GradingResult(
        students=[grade_student(d, rubric, allow_exec) for d in student_dirs],
        criterion_names=[c.name for c in rubric],
        warnings=[*warnings, *detect_warnings],
    )
