from grading.paste_parser import parse_pasted_text


def names_pts(text):
    return [(d.name, d.points) for d in parse_pasted_text(text)]


def test_tsv_table_paste():
    text = (
        "Criteria\tRatings\tPts\n"
        "Code compiles\t10 pts Full Marks\t0 pts No Marks\t10 pts\n"
        "Has a README\t5 pts Full Marks\t0 pts No Marks\t5 pts\n"
        "Total Points: 15\n"
    )
    assert names_pts(text) == [("Code compiles", 10.0), ("Has a README", 5.0)]


def test_tsv_bare_numbers():
    text = "Quality of code\t20\nDocumentation\t10\n"
    assert names_pts(text) == [("Quality of code", 20.0), ("Documentation", 10.0)]


def test_inline_parentheses():
    text = "Submits main.py (5 points)\nCode compiles (10 pts)\n"
    assert names_pts(text) == [("Submits main.py", 5.0), ("Code compiles", 10.0)]


def test_inline_trailing_pts():
    text = (
        "Defines a function called calculate_average 15 pts\n"
        "README at least 50 words - 10 pts\n"
        "Total 25 pts\n"
    )
    assert names_pts(text) == [
        ("Defines a function called calculate_average", 15.0),
        ("README at least 50 words", 10.0),
    ]


def test_inline_slash():
    text = "Code quality / 10\nStyle / 5\n"
    assert names_pts(text) == [("Code quality", 10.0), ("Style", 5.0)]


def test_two_line_canvas_expanded():
    text = (
        "Code compiles\n"
        "\n"
        "5 pts Full Marks\n"
        "0 pts No Marks\n"
        "\n"
        "Has comments\n"
        "3 pts\n"
        "0 pts No Marks\n"
    )
    assert names_pts(text) == [("Code compiles", 5.0), ("Has comments", 3.0)]


def test_two_line_skips_rating_noise():
    text = "Full Marks\nEffort shown\n10 pts\n"
    assert names_pts(text) == [("Effort shown", 10.0)]


def test_decimal_points():
    text = "Partial criterion (2.5 pts)\n"
    assert names_pts(text) == [("Partial criterion", 2.5)]


def test_no_criteria_found():
    assert names_pts("Just some prose with no points anywhere.") == []
    assert names_pts("") == []


def test_crlf_handled():
    text = "First thing (5 pts)\r\nSecond thing (3 pts)\r\n"
    assert names_pts(text) == [("First thing", 5.0), ("Second thing", 3.0)]
