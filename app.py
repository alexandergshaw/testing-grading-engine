"""Flask app: serves the single-page testing UI and mounts the /api/v1
blueprint. All grading goes through the API - the UI calls it via fetch, so
the browser UI is a literal exercise of the public API."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request

import config
from api_routes import api
from grading.checks import CHECK_REGISTRY

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
app.register_blueprint(api)


@app.get("/")
def index():
    checks = sorted(CHECK_REGISTRY.values(), key=lambda s: s.name)
    return render_template(
        "index.html",
        checks=checks,
        allow_exec=config.ALLOW_CODE_EXECUTION,
        on_vercel=config.ON_VERCEL,
    )


@app.errorhandler(413)
def upload_too_large(e):
    limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    msg = f"Upload exceeds the {limit_mb} MB limit."
    if config.ON_VERCEL:
        msg += " Run the app locally to grade larger zips."
    return jsonify({"error": "payload_too_large", "messages": [msg]}), 413


if __name__ == "__main__":
    import os

    app.run(debug=True, port=int(os.environ.get("PORT", "5000")))
