"""Flask web layer. All grading logic lives in the grading/ package."""
from __future__ import annotations

import os
import secrets
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for

from grading.checks import CHECK_REGISTRY
from grading.engine import grade_all
from grading.extract import ExtractionError, extract_zip
from grading.results import GradingResult
from grading.rubric import RubricError, parse_rubric

ALLOW_CODE_EXECUTION = os.environ.get("GRADING_ALLOW_EXEC") == "1"
MAX_RESULTS = 20

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit
app.secret_key = os.environ.get("GRADING_SECRET_KEY") or secrets.token_hex(16)

# Recent results kept in memory so the CSV download renders from the exact
# same GradingResult as the on-screen table.
RESULTS: OrderedDict[str, GradingResult] = OrderedDict()


@app.get("/")
def index():
    checks = sorted(CHECK_REGISTRY.values(), key=lambda s: s.name)
    return render_template("index.html", checks=checks, allow_exec=ALLOW_CODE_EXECUTION)


@app.post("/grade")
def grade():
    zip_file = request.files.get("submissions")
    rubric_file = request.files.get("rubric")
    if zip_file is None or not zip_file.filename:
        flash("Please choose a submissions zip file.")
        return redirect(url_for("index"))
    if rubric_file is None or not rubric_file.filename:
        flash("Please choose a rubric CSV file.")
        return redirect(url_for("index"))

    try:
        rubric = parse_rubric(rubric_file.read().decode("utf-8-sig", errors="replace"))
    except RubricError as e:
        for err in e.errors[:20]:
            flash(f"Rubric: {err}")
        return redirect(url_for("index"))

    workdir = Path(tempfile.mkdtemp(prefix="grading_"))
    try:
        try:
            zip_warnings = extract_zip(zip_file.stream, workdir)
            result = grade_all(
                workdir, rubric, allow_exec=ALLOW_CODE_EXECUTION, warnings=zip_warnings
            )
        except ExtractionError as e:
            flash(f"Submissions zip: {e}")
            return redirect(url_for("index"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    RESULTS[result.result_id] = result
    while len(RESULTS) > MAX_RESULTS:
        RESULTS.popitem(last=False)
    return render_template("results.html", result=result)


@app.get("/download/<result_id>.csv")
def download(result_id: str):
    result = RESULTS.get(result_id)
    if result is None:
        abort(404)
    return Response(
        result.to_csv(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=grades_{result_id[:8]}.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True)
