"""Flask web layer. All grading logic lives in the grading/ package.

Fully stateless so it can run as a serverless function (Vercel): no sessions,
no server-side result store. The grades CSV is embedded into the results page
of the same request that graded it.
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
from grading.rubric import RubricError, parse_rubric

ON_VERCEL = os.environ.get("VERCEL") == "1"
# Never execute student code on shared serverless infrastructure - the env
# flag only takes effect for local runs.
ALLOW_CODE_EXECUTION = (not ON_VERCEL) and os.environ.get("GRADING_ALLOW_EXEC") == "1"

app = Flask(__name__)
# Vercel serverless rejects request bodies over ~4.5 MB, so stay under that
# there; allow bigger class zips locally.
app.config["MAX_CONTENT_LENGTH"] = (4 if ON_VERCEL else 50) * 1024 * 1024


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


@app.get("/")
def index():
    return render_index()


@app.post("/grade")
def grade():
    zip_file = request.files.get("submissions")
    rubric_file = request.files.get("rubric")
    errors = []
    if zip_file is None or not zip_file.filename:
        errors.append("Please choose a submissions zip file.")
    if rubric_file is None or not rubric_file.filename:
        errors.append("Please choose a rubric CSV file.")
    if errors:
        return render_index(errors, status=400)

    try:
        rubric = parse_rubric(rubric_file.read().decode("utf-8-sig", errors="replace"))
    except RubricError as e:
        return render_index([f"Rubric: {err}" for err in e.errors[:20]], status=400)

    workdir = Path(tempfile.mkdtemp(prefix="grading_"))
    try:
        try:
            zip_warnings = extract_zip(zip_file.stream, workdir)
            result = grade_all(
                workdir, rubric, allow_exec=ALLOW_CODE_EXECUTION, warnings=zip_warnings
            )
        except ExtractionError as e:
            return render_index([f"Submissions zip: {e}"], status=400)
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
