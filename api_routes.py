"""Public JSON API (/api/v1). The browser UI is just another client of these
endpoints - it has no grading routes of its own.

Errors always use the envelope {"error": "<code>", "messages": [...]} with an
appropriate HTTP status. Auth (optional) is a shared-secret X-API-Key header,
enabled by setting GRADING_API_KEY; /health stays open.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

import config
from grading.checks import CHECK_REGISTRY
from grading.engine import grade_all
from grading.extract import ExtractionError, extract_zip
from grading.paste_parser import parse_pasted_text
from grading.rubric import RubricError, build_criterion, parse_params, parse_rubric
from grading.suggest import suggest

api = Blueprint("api", __name__, url_prefix="/api/v1")


def error_response(error: str, messages: list[str], status: int):
    return jsonify({"error": error, "messages": list(messages)}), status


@api.before_request
def require_api_key():
    if request.method == "OPTIONS":
        return None
    if not config.API_KEY or request.endpoint == "api.health":
        return None
    if request.headers.get("X-API-Key") != config.API_KEY:
        return error_response("unauthorized", ["missing or invalid X-API-Key header"], 401)


@api.after_request
def cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and config.CORS_ORIGINS:
        if "*" in config.CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in config.CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
        if response.headers.get("Access-Control-Allow-Origin"):
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@api.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "exec_enabled": config.ALLOW_CODE_EXECUTION,
            "on_vercel": config.ON_VERCEL,
            "max_upload_mb": config.MAX_UPLOAD_MB,
            "auth_required": bool(config.API_KEY),
        }
    )


@api.get("/checks")
def checks():
    return jsonify(
        {
            "checks": [
                {
                    "name": c.name,
                    "required_params": list(c.required_params),
                    "description": c.description,
                }
                for c in sorted(CHECK_REGISTRY.values(), key=lambda c: c.name)
            ]
        }
    )


def _needs_setup(check_type: str, params_raw: str) -> bool:
    spec = CHECK_REGISTRY.get(check_type)
    if spec is None:
        return True
    try:
        params = parse_params(params_raw)
    except ValueError:
        return True
    return any(p not in params for p in spec.required_params)


def _suggestion_rows(text: str) -> list[dict]:
    rows = []
    for draft in parse_pasted_text(text):
        s = suggest(draft.name)
        row = {
            "criterion": draft.name,
            "points": draft.points,
            "check_type": s.check_type if s else "",
            "target": s.target if s else "",
            "params": s.params if s else "",
            "rule": s.rule if s else "no rule matched",
        }
        row["needs_setup"] = _needs_setup(row["check_type"], row["params"])
        rows.append(row)
    return rows


@api.post("/rubric/parse")
def rubric_parse():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("rubric_text") or request.form.get("rubric_text") or "").strip()
    if not text:
        return error_response("missing_rubric_text", ["provide 'rubric_text'"], 400)
    rows = _suggestion_rows(text)
    if not rows:
        return error_response(
            "unparseable_rubric",
            [
                "couldn't find any criteria in the rubric text; expected an LMS table copy, "
                "'Criterion (10 points)' / 'Criterion 10 pts' lines, percent weights, "
                "D2L score blocks, or criterion-then-points lines"
            ],
            400,
        )
    return jsonify({"criteria": rows, "count": len(rows)})


def _params_to_string(params) -> str:
    if isinstance(params, dict):
        return ";".join(f"{k}={str(v).replace(';', chr(92) + ';')}" for k, v in params.items())
    return str(params or "")


def _criteria_from_json(raw: str):
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError
    except ValueError:
        return None, ["rubric_json must be a JSON array of criterion objects"]
    criteria, errors = [], []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"item {i}: not an object")
            continue
        label = f"item {i} ({item.get('criterion') or '?'})"
        criterion, item_errors = build_criterion(
            label,
            str(item.get("criterion") or ""),
            str(item.get("points") if item.get("points") is not None else ""),
            str(item.get("check_type") or ""),
            str(item.get("target") or ""),
            _params_to_string(item.get("params")),
        )
        criteria.append(criterion)
        errors.extend(item_errors)
    if not criteria:
        errors.append("rubric has no criteria")
    return criteria, errors


def _resolve_rubric(req):
    """Returns (criteria, unmapped_names, warnings, error_response_or_None)."""
    csv_file = req.files.get("rubric_csv")
    csv_text = None
    if csv_file is not None and csv_file.filename:
        csv_text = csv_file.read().decode("utf-8-sig", errors="replace")
    elif req.form.get("rubric_csv"):
        csv_text = req.form["rubric_csv"]
    json_text = req.form.get("rubric_json")
    paste_text = req.form.get("rubric_text")

    provided = [s for s, v in (("rubric_csv", csv_text), ("rubric_json", json_text), ("rubric_text", paste_text)) if v]
    if len(provided) != 1:
        return None, None, None, error_response(
            "missing_rubric",
            ["provide exactly one rubric source: rubric_csv (file or string), rubric_json, or rubric_text"],
            400,
        )

    if csv_text:
        try:
            return parse_rubric(csv_text), [], [], None
        except RubricError as e:
            return None, None, None, error_response("rubric_invalid", e.errors[:20], 400)

    if json_text:
        criteria, errors = _criteria_from_json(json_text)
        if errors:
            return None, None, None, error_response("rubric_invalid", errors[:20], 400)
        return criteria, [], [], None

    # rubric_text: deterministic parse + rule-based suggestions; criteria that
    # no rule can map are EXCLUDED from scoring and reported, never guessed.
    rows = _suggestion_rows(paste_text)
    if not rows:
        return None, None, None, error_response(
            "unparseable_rubric", ["couldn't find any criteria in rubric_text"], 400
        )
    criteria, unmapped = [], []
    for row in rows:
        if row["needs_setup"]:
            unmapped.append(row["criterion"])
            continue
        criterion, errors = build_criterion(
            row["criterion"], row["criterion"], f"{row['points']:g}",
            row["check_type"], row["target"], row["params"],
        )
        if errors:
            unmapped.append(row["criterion"])
            continue
        criteria.append(criterion)
    if not criteria:
        return None, None, None, error_response(
            "unmapped_rubric",
            [
                "no criteria could be mapped to checks automatically; call "
                "/api/v1/rubric/parse, resolve the checks, and submit rubric_json instead"
            ],
            400,
        )
    warnings = []
    if unmapped:
        warnings.append(
            f"{len(unmapped)} criteria could not be mapped to checks and were "
            f"excluded from scoring: {', '.join(unmapped)}"
        )
    return criteria, unmapped, warnings, None


@api.post("/grade")
def grade():
    zip_file = request.files.get("submissions")
    if zip_file is None or not zip_file.filename:
        return error_response("missing_submissions", ["provide a 'submissions' zip file"], 400)

    criteria, unmapped, warnings, error = _resolve_rubric(request)
    if error is not None:
        return error

    if config.ON_VERCEL and any(
        c.check_type in ("python_runs", "run_command", "output_contains") for c in criteria
    ):
        warnings = [*warnings, "execution checks are disabled on Vercel and will grade as failed"]

    workdir = Path(tempfile.mkdtemp(prefix="grading_"))
    try:
        try:
            zip_warnings = extract_zip(zip_file.stream, workdir)
            result = grade_all(
                workdir,
                criteria,
                allow_exec=config.ALLOW_CODE_EXECUTION,
                warnings=[*warnings, *zip_warnings],
            )
        except ExtractionError as e:
            return error_response("invalid_zip", [str(e)], 400)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if request.args.get("format") == "csv":
        return Response(result.to_csv(), mimetype="text/csv")
    payload = result.to_dict()
    payload["csv"] = result.to_csv()
    payload["unmapped_criteria"] = unmapped
    return jsonify(payload)
