import io
import zipfile

from grading.engine import grade_all, grade_student
from grading.rubric import parse_rubric

RUBRIC = """criterion,points,check_type,target,params
Has main.py,5,file_exists,main.py,
Defines avg,10,python_function_exists,*.py,name=avg
"""


def make_submissions(tmp_path):
    (tmp_path / "alice").mkdir()
    (tmp_path / "alice" / "main.py").write_text("def avg(xs):\n    return 0\n")
    (tmp_path / "bob").mkdir()
    (tmp_path / "bob" / "notes.txt").write_text("forgot to code")
    return tmp_path


def test_grade_all_and_csv_from_same_source(tmp_path):
    rubric = parse_rubric(RUBRIC)
    result = grade_all(make_submissions(tmp_path), rubric)

    assert result.header_row() == ["Student", "Has main.py", "Defines avg", "Total", "Possible"]
    rows = result.to_table_rows()
    assert [r.student for r in rows] == ["alice", "bob"]
    assert rows[0].total == 15.0
    assert rows[1].total == 0.0

    assert result.to_csv() == (
        "Student,Has main.py,Defines avg,Total,Possible\n"
        "alice,5,10,15,15\n"
        "bob,0,0,0,15\n"
    )


def test_crashing_check_becomes_error_detail(tmp_path):
    rubric = parse_rubric(
        "criterion,points,check_type,target,params\nBad regex,5,regex_match,*.py,pattern=([unclosed\n"
    )
    (tmp_path / "student").mkdir()
    (tmp_path / "student" / "main.py").write_text("x = 1")
    student = grade_student(tmp_path / "student", rubric)
    cell = student.criteria[0]
    assert cell.passed is False
    assert cell.points_earned == 0.0
    assert cell.detail.startswith("check error:")


def test_flask_smoke(tmp_path):
    import re
    import urllib.parse

    import app as app_module

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alice/main.py", "def avg(xs):\n    return 0\n")
        zf.writestr("bob/notes.txt", "forgot")
    buf.seek(0)

    client = app_module.app.test_client()
    resp = client.post(
        "/grade",
        data={
            "submissions": (buf, "submissions.zip"),
            "rubric": (io.BytesIO(RUBRIC.encode()), "rubric.csv"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert "alice" in page and "bob" in page

    # The CSV download is embedded in the results page as a data: URI and must
    # match the table's source exactly.
    match = re.search(r'href="data:text/csv;charset=utf-8,([^"]+)"', page)
    assert match, "embedded CSV download link not found"
    csv_text = urllib.parse.unquote(match.group(1))
    assert csv_text == (
        "Student,Has main.py,Defines avg,Total,Possible\n"
        "alice,5,10,15,15\n"
        "bob,0,0,0,15\n"
    )


def test_flask_validation_errors_rendered_inline():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post("/grade", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Please provide a rubric" in resp.get_data(as_text=True)

    resp = client.post(
        "/grade",
        data={"rubric": (io.BytesIO(RUBRIC.encode()), "rubric.csv")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "Please choose a submissions zip file." in resp.get_data(as_text=True)


def _submission_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alice/main.py", "def avg(xs):\n    return 0\n")
        zf.writestr("bob/notes.txt", "forgot")
    buf.seek(0)
    return buf


EXPECTED_CSV = (
    "Student,Has main.py,Defines avg,Total,Possible\n"
    "alice,5,10,15,15\n"
    "bob,0,0,0,15\n"
)


def _embedded_csv(page):
    import re
    import urllib.parse

    match = re.search(r'href="data:text/csv;charset=utf-8,([^"]+)"', page)
    assert match, "embedded CSV download link not found"
    return urllib.parse.unquote(match.group(1))


def test_parse_route_renders_review():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post(
        "/parse",
        data={"rubric_text": "Submitted main.py (5 points)\nUses the math module 10 pts"},
    )
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert 'value="Submitted main.py"' in page
    assert 'value="module=math"' in page  # suggestion prefilled
    assert "file submitted" in page  # rule label shown


def test_parse_route_unmapped_row_flagged():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post("/parse", data={"rubric_text": "Overall effort and style 10 pts"})
    page = resp.get_data(as_text=True)
    assert "needs-setup" in page
    assert "no rule matched" in page


def test_parse_route_no_criteria():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post("/parse", data={"rubric_text": "just prose, nothing useful"})
    assert resp.status_code == 400
    assert "Couldn&#39;t find any criteria" in resp.get_data(as_text=True)


def test_grade_from_review_form_matches_csv_path():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post(
        "/grade",
        data={
            "criterion": ["Has main.py", "Defines avg"],
            "points": ["5", "10"],
            "check_type": ["file_exists", "python_function_exists"],
            "target": ["main.py", "*.py"],
            "params": ["", "name=avg"],
            "rule": ["", ""],
            "submissions": (_submission_zip(), "submissions.zip"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    # Same rubric via form fields must produce the identical CSV as the CSV-upload path.
    assert _embedded_csv(resp.get_data(as_text=True)) == EXPECTED_CSV


def test_grade_from_review_form_validation_rerenders_review():
    import app as app_module

    client = app_module.app.test_client()
    resp = client.post(
        "/grade",
        data={
            "criterion": ["Broken row"],
            "points": ["abc"],
            "check_type": ["contains_text"],
            "target": ["*"],
            "params": [""],
            "rule": ["x"],
            "submissions": (_submission_zip(), "submissions.zip"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    page = resp.get_data(as_text=True)
    assert "not a number" in page
    assert "requires param" in page
    assert 'value="Broken row"' in page  # edits preserved in re-rendered review


def test_flask_upload_too_large(monkeypatch):
    import app as app_module

    monkeypatch.setitem(app_module.app.config, "MAX_CONTENT_LENGTH", 1024)
    client = app_module.app.test_client()
    resp = client.post(
        "/grade",
        data={"submissions": (io.BytesIO(b"x" * 5000), "big.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    assert "limit" in resp.get_data(as_text=True)
