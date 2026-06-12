import pytest

from grading.rubric import Criterion, RubricError, parse_params, parse_rubric

VALID = """criterion,points,check_type,target,params
Submitted main.py,5,file_exists,main.py,
Has a docstring,10,regex_match,*.py,pattern=def main;ignore_case=true
"""


def test_parse_valid_rubric():
    criteria = parse_rubric(VALID)
    assert len(criteria) == 2
    assert criteria[0] == Criterion("Submitted main.py", 5.0, "file_exists", "main.py", {})
    assert criteria[1].params == {"pattern": "def main", "ignore_case": "true"}


def test_parse_params():
    assert parse_params("") == {}
    assert parse_params("a=1; b = x=y ") == {"a": "1", "b": "x=y"}
    with pytest.raises(ValueError, match="malformed"):
        parse_params("noequalsign")


def test_parse_params_escaped_semicolon():
    params = parse_params(r"command=python -c \;exit(0)\;;timeout=5")
    assert params == {"command": "python -c ;exit(0);", "timeout": "5"}


def test_bom_and_blank_lines():
    criteria = parse_rubric("﻿" + VALID + "\n,,,,\n")
    assert len(criteria) == 2


def test_errors_are_aggregated():
    bad = """criterion,points,check_type,target,params
Good row,5,file_exists,main.py,
Bad points,abc,file_exists,main.py,
Bad check,5,no_such_check,main.py,
Missing param,5,contains_text,main.py,
Bad params,5,file_exists,main.py,oops
"""
    with pytest.raises(RubricError) as exc:
        parse_rubric(bad)
    errors = exc.value.errors
    assert len(errors) == 4
    assert any("not a number" in e for e in errors)
    assert any("unknown check_type 'no_such_check'" in e for e in errors)
    assert any("requires param 'text'" in e for e in errors)
    assert any("malformed" in e for e in errors)


def test_missing_columns():
    with pytest.raises(RubricError, match="missing column"):
        parse_rubric("criterion,points\nA,5\n")


def test_empty_rubric():
    with pytest.raises(RubricError, match="no criteria"):
        parse_rubric("criterion,points,check_type,target,params\n")
