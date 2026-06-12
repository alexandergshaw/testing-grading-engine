"""Deterministic parser for rubric text pasted from an LMS.

Extracts (criterion name, points) pairs - no LLM, just format strategies
tried in order:

1. Tab-separated rows (copying an LMS rubric table - Canvas/Moodle/D2L):
   first cell is the criterion, rightmost points-looking cell is the points.
2. Inline points: "Criterion name (10 points)", "Criterion name 10 pts",
   "Criterion name (out of 10)", "Criterion name worth 10 points",
   "Criterion name / 10". "marks" is accepted wherever pts/points are.
3. Percent weights: criterion name followed by "25% of total grade" or a
   Blackboard-style "Weight: 25.00%" (on the same or the next line); bare
   rating-level lines like "100%" / "75%" and their descriptions are
   ignored. Points = the percent weight.
4. Score blocks (D2L/Brightspace exports): each criterion is a block of
   rating levels ("Thorough / description / 20 pts" ...) ending in a
   "Criterion Score" footer with "/20 pts". The criterion name is the first
   line of the block; points come from the "/N pts" footer, falling back to
   the block's highest rating value when the footer is missing.
5. Two-line pairs: criterion name on one line, rating-level points lines
   below it ("10 pts", "5 pts Full Marks", "5 to >3.0 pts"); the criterion
   is worth the highest value in the run, so both Canvas (high-to-low) and
   Moodle (low-to-high) rating orders work.

Duplicate criterion names (e.g. an LMS footer that repeats the criteria
column) are collapsed to the first occurrence.

Which automated check each criterion maps to is suggested separately by
grading.suggest and confirmed by the user on the review page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_PTS_WORD = r"(?:pts?\.?|points?|marks?)"
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
    "marks",
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
    # "Criterion name (out of 10)" / "Criterion name worth 10 points"
    re.compile(
        rf"^(?P<name>.+?)[\s\-–—:|,(\[]+(?:out\s+of|worth)\s+(?P<pts>{_NUM})"
        rf"\s*{_PTS_WORD}?\s*[\)\]]?\s*\.?\s*$",
        re.I,
    ),
    # "Criterion name (10 points)" / "[10 pts]"
    re.compile(rf"^(?P<name>.+?)\s*[\(\[]\s*(?P<pts>{_NUM})\s*{_PTS_WORD}\s*[\)\]]\s*$", re.I),
    # "Criterion name ... 10 pts"
    re.compile(rf"^(?P<name>.+?)[\s\-–—:|,]+(?P<pts>{_NUM})\s*{_PTS_WORD}\s*\.?\s*$", re.I),
    # "Criterion name / 10"
    re.compile(rf"^(?P<name>.+?)\s*/\s*(?P<pts>{_NUM})\s*$"),
)

# A points-only line: "5 pts", "5 pts Full Marks", "5 to >3.0 pts" (Canvas ranges)
_PTS_LINE = re.compile(rf"^\s*({_NUM})\s*(?:to\s*>?\s*-?{_NUM}\s*)?{_PTS_WORD}\b.*$", re.I)
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
# Blackboard-style weights: "Weight 25.00%" / "Weight: 25%"
_BB_WEIGHT_LINE = re.compile(rf"^\s*weight:?\s*(?P<pts>{_NUM})\s*%?\s*$", re.I)
_BB_WEIGHT_INLINE = re.compile(
    rf"^(?P<name>.+?)[\s\-–—:|,]+weight:?\s*(?P<pts>{_NUM})\s*%?\s*$", re.I
)

# Score-block rubrics (D2L/Brightspace): "Criterion Score" footers with
# "/20 pts" (sometimes "-- /20 pts") carrying the criterion's max points.
_SCORE_PTS = re.compile(rf"^(?:--\s*)?/\s*(?P<pts>{_NUM})\s*{_PTS_WORD}\b.*$", re.I)
_BLOCK_BOUNDARY = re.compile(r"^(criterion score|comments?|leave a comment)$", re.I)
_SCORE_BLOCK_MARKER = re.compile(
    rf"^(?:criterion score|(?:--\s*)?/\s*{_NUM}\s*{_PTS_WORD}\b.*)$", re.I | re.M
)


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


def _is_header_line(line: str) -> bool:
    """A copied table header like 'Criteria<tab>Ratings<tab>Points'."""
    if "\t" not in line:
        return False
    cells = [c.strip().lower() for c in line.split("\t") if c.strip()]
    return bool(cells) and all(c in _JUNK_NAMES for c in cells)


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
        m = _WEIGHT_LINE.match(line) or _BB_WEIGHT_LINE.match(line)
        if m:
            if prev is not None:
                out.append(DraftCriterion(prev, float(m.group("pts"))))
                prev = None
            continue
        m = _WEIGHT_INLINE.match(line) or _BB_WEIGHT_INLINE.match(line)
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


def _parse_score_blocks(text: str) -> list[DraftCriterion]:
    if not _SCORE_BLOCK_MARKER.search(text):
        return []
    out: list[DraftCriterion] = []
    expecting_name = True  # the first text line of each block is the criterion
    current_name: str | None = None
    block_max: float | None = None  # highest rating value, fallback points
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line == "--":
            continue
        if _is_header_line(line) or _is_junk(line):
            expecting_name = True
            continue
        m = _SCORE_PTS.match(line)
        if m:
            if current_name is not None:
                out.append(DraftCriterion(current_name, float(m.group("pts"))))
                current_name = None
                block_max = None
            expecting_name = True
            continue
        if _BLOCK_BOUNDARY.match(line):
            expecting_name = True
            continue
        m = _PTS_LINE.match(line)
        if m:
            pts = float(m.group(1))
            block_max = pts if block_max is None else max(block_max, pts)
            continue
        if expecting_name and not _RATING_NOISE.match(line):
            # overwrites a stale candidate (e.g. a title line) that never
            # accumulated points before the next block started
            current_name = _clean(line)
            expecting_name = False
            block_max = None
    if current_name is not None and block_max is not None:
        out.append(DraftCriterion(current_name, block_max))
    return out


def _parse_two_line(text: str) -> list[DraftCriterion]:
    out: list[DraftCriterion] = []
    prev: str | None = None
    pending: DraftCriterion | None = None  # criterion accumulating a run of rating lines
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _PTS_LINE.match(line)
        if m:
            pts = float(m.group(1))
            if pending is not None:
                # a run of rating levels: the criterion is worth the highest
                # (Canvas lists high-to-low, Moodle low-to-high)
                pending = DraftCriterion(pending.name, max(pending.points, pts))
            elif prev is not None:
                pending = DraftCriterion(prev, pts)
                prev = None
            continue
        if _RATING_NOISE.match(line) or _is_junk(line):
            continue
        if pending is not None:
            out.append(pending)
            pending = None
        prev = _clean(line)
    if pending is not None:
        out.append(pending)
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
        rows = _parse_score_blocks(text)
    if not rows:
        rows = _parse_two_line(text)
    return _dedupe(rows)
