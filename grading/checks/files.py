"""File presence and count checks."""
from __future__ import annotations

from pathlib import Path

from . import CheckContext, in_range, param_int, range_text, register


def _names(ctx: CheckContext, files: list[Path], limit: int = 3) -> str:
    shown = ", ".join(ctx.rel(f) for f in files[:limit])
    extra = len(files) - limit
    return shown + (f" (+{extra} more)" if extra > 0 else "")


@register("file_exists", description="Passes when the target glob matches at least one file.")
def file_exists(ctx: CheckContext) -> tuple[bool, str]:
    files = ctx.matched_files()
    if files:
        return True, f"found {_names(ctx, files)}"
    return False, f"no file matching {ctx.target!r}"


@register(
    "file_count",
    description="Passes when the number of files matching the glob is within min=/max=.",
)
def file_count(ctx: CheckContext) -> tuple[bool, str]:
    n = len(ctx.matched_files())
    lo = param_int(ctx.params, "min")
    hi = param_int(ctx.params, "max")
    ok = in_range(n, lo, hi)
    return ok, f"{n} file(s) matching {ctx.target!r} ({range_text(lo, hi)})"
