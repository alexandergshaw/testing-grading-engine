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


def test_grade_all_and_renderers_from_same_source(tmp_path):
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

    data = result.to_dict()
    assert data["criteria"] == ["Has main.py", "Defines avg"]
    assert [s["student"] for s in data["students"]] == ["alice", "bob"]
    assert data["students"][0]["total"] == 15.0
    assert data["students"][1]["criteria"][0] == {
        "criterion": "Has main.py",
        "passed": False,
        "points_earned": 0.0,
        "points_possible": 5.0,
        "detail": "no file matching 'main.py'",
    }


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
