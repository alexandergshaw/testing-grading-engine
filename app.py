"""Flask web layer. All grading logic lives in the grading/ package.

Fully stateless so it can run as a serverless function (Vercel): no sessions,
no server-side result store. The grades CSV is embedded into the results page
of the same request that graded it, and a pasted rubric round-trips through
the review form rather than being stored server-side.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from flask import Flask, render_template, request

from grading.checks import CHECK_REGISTRY
from grading.engine import grade_all
from grading.extract import ExtractionError, extract_zip
from grading.paste_parser import parse_pasted_text
from grading.rubric import RubricError, build_criterion, parse_params, parse_rubric
from grading.suggest import suggest

ON_VERCEL = os.environ.get("VERCEL") == "1"
# Never execute student code on shared serverless infrastructure - the env
# flag only takes effect for local runs.
ALLOW_CODE_EXECUTION = (not ON_VERCEL) and os.environ.get("GRADING_ALLOW_EXEC") == "1"

app = Flask(__name__)
# Vercel serverless rejects request bodies over ~4.5 MB, so stay under that
# there; allow bigger class zips locally.
app.config["MAX_CONTENT_LENGTH"] = (4 if ON_VERCEL else 50) * 1024 * 1024

ROW_FIELDS = ("criterion", "points", "check_type", "target", "params", "rule")


def render_index(errors: list[str] | None = None, status: int = 200):
    checks = sorted(CHECK_REGISTRY.values(), key=lambda s: s.name)
    return (
        render_template(
            "index.html",
            checks=checks,
            allow_exec=ALLOW_CODE_EXECUTION,
            on_vercel=ON_VERCEL,
            errors=errors or [],
        ),
        status,
    )


def _needs_setup(row: dict[str, str]) -> bool:
    spec = CHECK_REGISTRY.get(row["check_type"])
    if spec is None:
        return True
    try:
        params = parse_params(row["params"])
    except ValueError:
        return True
    return any(p not in params for p in spec.required_params)


def render_review(rows: list[dict[str, str]], errors: list[str] | None = None, status: int = 200):
    checks = sorted(CHECK_REGISTRY.values(), key=lambda s: s.name)
    for row in rows:
        row["needs_setup"] = _needs_setup(row)
    return (
        render_template(
            "review.html",
            rows=rows,
            checks=checks,
            errors=errors or [],
            on_vercel=ON_VERCEL,
        ),
        status,
    )


def _rows_from_form(form) -> list[dict[str, str]]:
    names = form.getlist("criterion")
    if not names:
        return []
    columns = {}
    for field in ROW_FIELDS:
        values = form.getlist(field)
        columns[field] = [values[i] if i < len(values) else "" for i in range(len(names))]
    return [{field: columns[field][i] for field in ROW_FIELDS} for i in range(len(names))]


def _criteria_from_rows(rows: list[dict[str, str]]):
    criteria, errors = [], []
    for i, row in enumerate(rows, start=1):
        if not any(row[f].strip() for f in ("criterion", "points", "check_type", "target", "params")):
            continue  # row the user cleared out
        label = f"row {i} ({row['criterion'].strip() or '?'})"
        criterion, row_errors = build_criterion(
            label, row["criterion"], row["points"], row["check_type"], row["target"], row["params"]
        )
        criteria.append(criterion)
        errors.extend(row_errors)
    if not criteria:
        errors.append("rubric has no criteria rows")
    return criteria, errors


@app.get("/")
def index():
    return render_index()


@app.post("/parse")
def parse_paste():
    text = (request.form.get("rubric_text") or "").strip()
    if not text:
        return render_index(["Paste some rubric text first."], status=400)
    drafts = parse_pasted_text(text)
    if not drafts:
        return render_index(
            [
                "Couldn't find any criteria in the pasted text. Expected an LMS table copy "
                "(tab-separated), lines like \"Criterion name (10 points)\" or "
                "\"Criterion name 10 pts\", percent weights like \"25% of total grade\" "
                "after each criterion, D2L/Brightspace rating blocks with a "
                "\"Criterion Score ... /20 pts\" footer, or a criterion line followed "
                "by a points line."
            ],
            status=400,
        )
    rows = []
    for draft in drafts:
        s = suggest(draft.name)
        rows.append(
            {
                "criterion": draft.name,
                "points": f"{draft.points:g}",
                "check_type": s.check_type if s else "",
                "target": s.target if s else "",
                "params": s.params if s else "",
                "rule": s.rule if s else "no rule matched",
            }
        )
    return render_review(rows)


@app.post("/grade")
def grade():
    zip_file = request.files.get("submissions")
    rubric_file = request.files.get("rubric")
    form_rows = _rows_from_form(request.form)
    from_review = bool(form_rows)

    def fail(errors: list[str], status: int = 400):
        if from_review:
            return render_review(form_rows, errors, status)
        return render_index(errors, status)

    if rubric_file is not None and rubric_file.filename:
        try:
            rubric = parse_rubric(rubric_file.read().decode("utf-8-sig", errors="replace"))
        except RubricError as e:
            return fail([f"Rubric: {err}" for err in e.errors[:20]])
    elif from_review:
        rubric, errors = _criteria_from_rows(form_rows)
        if errors:
            return fail([f"Rubric: {err}" for err in errors[:20]])
    else:
        return fail(["Please provide a rubric: upload a CSV or paste rubric text."])

    if zip_file is None or not zip_file.filename:
        return fail(["Please choose a submissions zip file."])

    workdir = Path(tempfile.mkdtemp(prefix="grading_"))
    try:
        try:
            zip_warnings = extract_zip(zip_file.stream, workdir)
            result = grade_all(
                workdir, rubric, allow_exec=ALLOW_CODE_EXECUTION, warnings=zip_warnings
            )
        except ExtractionError as e:
            return fail([f"Submissions zip: {e}"])
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return render_template("results.html", result=result)


@app.errorhandler(413)
def upload_too_large(e):
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    msg = f"Upload exceeds the {limit_mb} MB limit."
    if ON_VERCEL:
        msg += " Run the app locally to grade larger zips."
    return render_index([msg], status=413)


if __name__ == "__main__":
    app.run(debug=True)
