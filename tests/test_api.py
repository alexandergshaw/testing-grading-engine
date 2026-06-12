import io
import json
import zipfile

import pytest

import app as app_module
import config

RUBRIC_CSV = """criterion,points,check_type,target,params
Has main.py,5,file_exists,main.py,
Defines avg,10,python_function_exists,*.py,name=avg
"""

RUBRIC_JSON = json.dumps(
    [
        {"criterion": "Has main.py", "points": 5, "check_type": "file_exists", "target": "main.py", "params": ""},
        {"criterion": "Defines avg", "points": 10, "check_type": "python_function_exists", "target": "*.py", "params": {"name": "avg"}},
    ]
)

EXPECTED_CSV = (
    "Student,Has main.py,Defines avg,Total,Possible\n"
    "alice,5,10,15,15\n"
    "bob,0,0,0,15\n"
)


@pytest.fixture
def client():
    return app_module.app.test_client()


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alice/main.py", "def avg(xs):\n    return 0\n")
        zf.writestr("bob/notes.txt", "forgot")
    buf.seek(0)
    return buf


def post_grade(client, query="", **fields):
    data = {"submissions": (make_zip(), "submissions.zip")}
    data.update(fields)
    return client.post("/api/v1/grade" + query, data=data, content_type="multipart/form-data")


def test_health(client):
    data = client.get("/api/v1/health").get_json()
    assert data["status"] == "ok"
    assert data["auth_required"] is False
    assert "exec_enabled" in data and "max_upload_mb" in data


def test_checks(client):
    data = client.get("/api/v1/checks").get_json()
    by_name = {c["name"]: c for c in data["checks"]}
    assert "file_exists" in by_name
    assert by_name["contains_text"]["required_params"] == ["text"]
    assert by_name["file_exists"]["description"]


def test_grade_with_csv_file(client):
    resp = post_grade(client, rubric_csv=(io.BytesIO(RUBRIC_CSV.encode()), "rubric.csv"))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["criteria"] == ["Has main.py", "Defines avg"]
    assert [s["student"] for s in data["students"]] == ["alice", "bob"]
    assert data["students"][0]["total"] == 15.0
    assert data["csv"] == EXPECTED_CSV
    assert data["unmapped_criteria"] == []
    cell = data["students"][1]["criteria"][1]
    assert cell["passed"] is False and "detail" in cell


def test_grade_with_csv_string(client):
    resp = post_grade(client, rubric_csv=RUBRIC_CSV)
    assert resp.status_code == 200
    assert resp.get_json()["csv"] == EXPECTED_CSV


def test_grade_with_json_rubric_matches_csv_path(client):
    resp = post_grade(client, rubric_json=RUBRIC_JSON)
    assert resp.status_code == 200
    assert resp.get_json()["csv"] == EXPECTED_CSV  # all rubric modes converge


def test_grade_with_text_rubric_excludes_unmapped(client):
    text = "Submitted main.py 5 pts\nOverall effort 10 pts\n"
    resp = post_grade(client, rubric_text=text)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["criteria"] == ["Submitted main.py"]
    assert data["unmapped_criteria"] == ["Overall effort"]
    assert any("excluded from scoring" in w for w in data["warnings"])
    assert data["students"][0]["possible"] == 5.0


def test_grade_csv_format_param(client):
    resp = post_grade(client, query="?format=csv", rubric_csv=RUBRIC_CSV)
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    assert resp.get_data(as_text=True) == EXPECTED_CSV


def test_grade_requires_exactly_one_rubric_source(client):
    resp = post_grade(client)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_rubric"

    resp = post_grade(client, rubric_csv=RUBRIC_CSV, rubric_json=RUBRIC_JSON)
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_rubric"


def test_grade_missing_zip(client):
    resp = client.post(
        "/api/v1/grade", data={"rubric_csv": RUBRIC_CSV}, content_type="multipart/form-data"
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_submissions"


def test_grade_invalid_rubric_csv(client):
    bad = "criterion,points,check_type,target,params\nX,abc,no_such_check,*,\n"
    resp = post_grade(client, rubric_csv=bad)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "rubric_invalid"
    assert any("not a number" in m for m in data["messages"])
    assert any("unknown check_type" in m for m in data["messages"])


def test_grade_invalid_rubric_json(client):
    resp = post_grade(client, rubric_json="not json at all")
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "rubric_invalid"


def test_grade_invalid_zip(client):
    resp = client.post(
        "/api/v1/grade",
        data={"submissions": (io.BytesIO(b"not a zip"), "s.zip"), "rubric_csv": RUBRIC_CSV},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "invalid_zip"


def test_rubric_parse(client):
    resp = client.post(
        "/api/v1/rubric/parse",
        json={"rubric_text": "Uses the math module 10 pts\nOverall effort 5 pts"},
    )
    assert resp.status_code == 200
    rows = resp.get_json()["criteria"]
    assert rows[0]["check_type"] == "python_imports"
    assert rows[0]["params"] == "module=math"
    assert rows[0]["needs_setup"] is False
    assert rows[1]["check_type"] == ""
    assert rows[1]["needs_setup"] is True
    assert rows[1]["rule"] == "no rule matched"


def test_rubric_parse_unparseable(client):
    resp = client.post("/api/v1/rubric/parse", json={"rubric_text": "just prose"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "unparseable_rubric"

    resp = client.post("/api/v1/rubric/parse", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "missing_rubric_text"


def test_auth_when_key_configured(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "sekret")
    assert client.get("/api/v1/health").status_code == 200  # health stays open
    resp = client.get("/api/v1/checks")
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"
    assert client.get("/api/v1/checks", headers={"X-API-Key": "sekret"}).status_code == 200
    assert client.get("/api/v1/checks", headers={"X-API-Key": "wrong"}).status_code == 401


def test_413_returns_json_envelope(client, monkeypatch):
    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 1024)
    resp = client.post(
        "/api/v1/grade",
        data={"submissions": (io.BytesIO(b"x" * 5000), "big.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    assert resp.get_json()["error"] == "payload_too_large"


def test_index_serves_spa(client):
    resp = client.get("/")
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert "app.js" in page
    assert 'id="view-review"' in page and 'id="view-results"' in page
    assert "file_exists" in page  # check registry docs still server-rendered
