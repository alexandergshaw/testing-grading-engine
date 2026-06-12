"""Deterministic parser for rubric text pasted from an LMS.

Extracts (criterion name, points) pairs - no LLM, just format strategies
tried in order:

1. Tab-separated rows (copying an LMS rubric table - Canvas/Moodle/D2L):
   first cell is the criterion, rightmost points-looking cell is the points.
2. Inline points: "Criterion name (10 points)", "Criterion name 10 pts",
   "Criterion name / 10".
3. Percent weights: criterion name followed by "25% of total grade" (on the
   same or the next line); bare rating-level lines like "100%" / "75%" and
   their descriptions are ignored. Points = the percent weight.
4. Two-line pairs: criterion name on one line, "10 pts" (optionally with
   rating text like "Full Marks") on the next.

Duplicate criterion names (e.g. an LMS footer that repeats the criteria
column) are collapsed to the first occurrence.

Which automated check each criterion maps to is suggested separately by
grading.suggest and confirmed by the user on the review page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PTS_WORD = r"(?:pts?\.?|points?)"
_NUM = r"\d+(?:\.\d+)?"

_JUNK_NAMES = {
    "criteria",
    "criterion",
    "criteria column",
    "criterion column",
    "ratings",
    "rating",
    "pts",
    "points",
    "total",
    "total points",
    "description",
    "descriptions",
    "score",
    "scores",
}

_CELL_PTS = re.compile(rf"^\s*({_NUM})\s*(?:to\s*>?\s*-?{_NUM}\s*)?{_PTS_WORD}\b.*$", re.I | re.S)
_CELL_BARE_NUM = re.compile(rf"^\s*({_NUM})\s*$")

_INLINE_PATTERNS = (
    # "Criterion name (10 points)" / "[10 pts]"
    re.compile(rf"^(?P<name>.+?)\s*[\(\[]\s*(?P<pts>{_NUM})\s*{_PTS_WORD}\s*[\)\]]\s*$", re.I),
    # "Criterion name ... 10 pts"
    re.compile(rf"^(?P<name>.+?)[\s\-–—:|,]+(?P<pts>{_NUM})\s*{_PTS_WORD}\s*\.?\s*$", re.I),
    # "Criterion name / 10"
    re.compile(rf"^(?P<name>.+?)\s*/\s*(?P<pts>{_NUM})\s*$"),
)

# A points-only line, optionally followed by rating text ("5 pts Full Marks")
_PTS_LINE = re.compile(rf"^\s*({_NUM})\s*{_PTS_WORD}\b.*$", re.I)
_RATING_NOISE = re.compile(
    r"^(full marks|no marks|partial(?: credit)?|excellent|good|fair|poor|satisfactory"
    r"|unsatisfactory|exemplary|proficient|developing|emerging|beginning"
    r"|needs improvement|ratings?)$",
    re.I,
)

# Percent-weight rubrics: "25% of total grade" after (or appended to) the
# criterion name; "100%" / "75%" rating-level lines are noise.
_GRADE_OF = r"%\s*of\s+(?:the\s+)?(?:total\s+)?grade\b"
_WEIGHT_LINE = re.compile(rf"^\s*(?P<pts>{_NUM})\s*{_GRADE_OF}.*$", re.I)
_WEIGHT_INLINE = re.compile(rf"^(?P<name>.+?)[\s\-–—:|,]+(?P<pts>{_NUM})\s*{_GRADE_OF}.*$", re.I)
_BARE_PERCENT = re.compile(rf"^\s*{_NUM}\s*%\s*$")


@dataclass(frozen=True)
class DraftCriterion:
    name: str
    points: float


def _clean(name: str) -> str:
    return name.strip().strip("-–—:|.*").strip()


def _is_junk(name: str) -> bool:
    cleaned = _clean(name)
    if not cleaned or cleaned.lower() in _JUNK_NAMES:
        return True
    return _CELL_BARE_NUM.match(cleaned) is not None


def _cell_points(cell: str) -> float | None:
    m = _CELL_PTS.match(cell) or _CELL_BARE_NUM.match(cell)
    return float(m.group(1)) if m else None


def _parse_tsv(text: str) -> list[DraftCriterion]:
    out = []
    for line in text.splitlines():
        if "\t" not in line:
            continue
        cells = [c.strip() for c in line.split("\t") if c.strip()]
        if len(cells) < 2:
            continue
        name = cells[0]
        if _is_junk(name) or _cell_points(name) is not None:
            continue
        for cell in reversed(cells[1:]):
            pts = _cell_points(cell)
            if pts is not None:
                out.append(DraftCriterion(_clean(name), pts))
                break
    return out


def _parse_inline(text: str) -> list[DraftCriterion]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pattern in _INLINE_PATTERNS:
            m = pattern.match(line)
            if m and not _is_junk(m.group("name")):
                out.append(DraftCriterion(_clean(m.group("name")), float(m.group("pts"))))
                break
    return out


def _parse_percent_weights(text: str) -> list[DraftCriterion]:
    out: list[DraftCriterion] = []
    prev: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _WEIGHT_LINE.match(line)
        if m:
            if prev is not None:
                out.append(DraftCriterion(prev, float(m.group("pts"))))
                prev = None
            continue
        m = _WEIGHT_INLINE.match(line)
        if m and not _is_junk(m.group("name")):
            out.append(DraftCriterion(_clean(m.group("name")), float(m.group("pts"))))
            prev = None
            continue
        if _BARE_PERCENT.match(line) or _RATING_NOISE.match(line) or _is_junk(line):
            continue
        # the weight line directly follows the criterion name, so the most
        # recent non-noise line is the name; description prose in between
        # rating levels never immediately precedes a weight line
        prev = _clean(line)
    return out


def _parse_two_line(text: str) -> list[DraftCriterion]:
    out: list[DraftCriterion] = []
    prev: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _PTS_LINE.match(line)
        if m:
            if prev is not None:
                out.append(DraftCriterion(prev, float(m.group(1))))
                prev = None  # later rating lines ("0 pts No Marks") are ignored
        elif not _RATING_NOISE.match(line) and not _is_junk(line):
            prev = _clean(line)
    return out


def _dedupe(rows: list[DraftCriterion]) -> list[DraftCriterion]:
    seen: set[str] = set()
    out = []
    for row in rows:
        key = row.name.lower()
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def parse_pasted_text(text: str) -> list[DraftCriterion]:
    text = text.replace("\r\n", "\n")
    rows: list[DraftCriterion] = []
    if "\t" in text:
        rows = _parse_tsv(text)
    if not rows:
        rows = _parse_inline(text)
    if not rows:
        rows = _parse_percent_weights(text)
    if not rows:
        rows = _parse_two_line(text)
    return _dedupe(rows)
