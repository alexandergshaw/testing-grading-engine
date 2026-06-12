"""Plain-text content checks: substring, regex, line/word counts."""
from __future__ import annotations

import re
from pathlib import Path

from . import (
    CheckContext,
    in_range,
    no_files_detail,
    param_bool,
    param_int,
    range_text,
    register,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


@register(
    "contains_text",
    required_params=("text",),
    description="Passes when any matched file contains the literal text= (ignore_case= optional).",
)
def contains_text(ctx: CheckContext) -> tuple[bool, str]:
    needle = ctx.params["text"]
    ignore_case = param_bool(ctx.params, "ignore_case")
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        haystack = read_text(f)
        if ignore_case:
            found = needle.lower() in haystack.lower()
        else:
            found = needle in haystack
        if found:
            return True, f"{needle!r} found in {ctx.rel(f)}"
    return False, f"{needle!r} not found in {len(files)} matched file(s)"


@register(
    "regex_match",
    required_params=("pattern",),
    description="Passes when the regex pattern= matches in any matched file (ignore_case= optional).",
)
def regex_match(ctx: CheckContext) -> tuple[bool, str]:
    flags = re.MULTILINE
    if param_bool(ctx.params, "ignore_case"):
        flags |= re.IGNORECASE
    pattern = re.compile(ctx.params["pattern"], flags)
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        if pattern.search(read_text(f)):
            return True, f"pattern {pattern.pattern!r} matched in {ctx.rel(f)}"
    return False, f"pattern {pattern.pattern!r} not found in {len(files)} matched file(s)"


def _count_check(ctx: CheckContext, unit: str, count_fn) -> tuple[bool, str]:
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    n = sum(count_fn(read_text(f)) for f in files)
    lo = param_int(ctx.params, "min")
    hi = param_int(ctx.params, "max")
    ok = in_range(n, lo, hi)
    return ok, f"{n} {unit}(s) across {len(files)} matched file(s) ({range_text(lo, hi)})"


@register(
    "line_count",
    description="Passes when total line count across matched files is within min=/max=.",
)
def line_count(ctx: CheckContext) -> tuple[bool, str]:
    return _count_check(ctx, "line", lambda s: len(s.splitlines()))


@register(
    "word_count",
    description="Passes when total word count across matched files is within min=/max=.",
)
def word_count(ctx: CheckContext) -> tuple[bool, str]:
    return _count_check(ctx, "word", lambda s: len(s.split()))
