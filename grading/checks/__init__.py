"""Check registry: maps a rubric check_type to a deterministic check function.

A check receives a CheckContext (one student folder + the criterion's target
glob and params) and returns (passed, detail). Checks may raise; the engine
converts exceptions into a failed result with a "check error" detail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class CheckContext:
    folder: Path
    target: str
    params: dict[str, str] = field(default_factory=dict)
    allow_exec: bool = False

    def matched_files(self) -> list[Path]:
        if not self.target:
            return sorted(p for p in self.folder.rglob("*") if p.is_file())
        return sorted(p for p in self.folder.glob(self.target) if p.is_file())

    def rel(self, path: Path) -> str:
        return path.relative_to(self.folder).as_posix()


CheckFn = Callable[[CheckContext], tuple[bool, str]]


@dataclass(frozen=True)
class CheckSpec:
    name: str
    func: CheckFn
    required_params: tuple[str, ...]
    description: str


CHECK_REGISTRY: dict[str, CheckSpec] = {}


def register(name: str, required_params: tuple[str, ...] = (), description: str = ""):
    def decorator(func: CheckFn) -> CheckFn:
        CHECK_REGISTRY[name] = CheckSpec(name, func, tuple(required_params), description)
        return func

    return decorator


# ---- shared helpers for check implementations ----

def param_bool(params: dict, key: str, default: bool = False) -> bool:
    raw = params.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y")


def param_int(params: dict, key: str) -> int | None:
    raw = params.get(key)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"param {key}={raw!r} is not an integer")


def in_range(n: int, lo: int | None, hi: int | None) -> bool:
    if lo is None and hi is None:
        raise ValueError("provide at least one of min=/max= in params")
    return (lo is None or n >= lo) and (hi is None or n <= hi)


def range_text(lo: int | None, hi: int | None) -> str:
    parts = []
    if lo is not None:
        parts.append(f"min {lo}")
    if hi is not None:
        parts.append(f"max {hi}")
    return "expected " + ", ".join(parts)


def no_files_detail(ctx: CheckContext) -> str:
    return f"no file matching {ctx.target!r}"


# Import the check modules so their @register decorators populate the registry.
from . import commands, files, text, python_checks, web, docs  # noqa: E402,F401
