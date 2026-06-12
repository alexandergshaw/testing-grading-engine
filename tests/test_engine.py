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

    result_id, result = next(reversed(app_module.RESULTS.items()))
    download = client.get(f"/download/{result_id}.csv")
    assert download.status_code == 200
    assert download.get_data(as_text=True) == result.to_csv()
    assert client.get("/download/nonexistent.csv").status_code == 404
