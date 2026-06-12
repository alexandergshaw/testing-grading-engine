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


def test_moodle_ascending_ratings_take_max():
    text = (
        "Criterion One\n"
        "0 points\n"
        "1 points\n"
        "2 points\n"
        "Criterion Two\n"
        "0 points\n"
        "5 points\n"
    )
    assert names_pts(text) == [("Criterion One", 2.0), ("Criterion Two", 5.0)]


def test_canvas_range_rating_lines():
    text = "Code compiles\n5 to >3.0 pts Full Marks\n3 to >0 pts Partial Credit\n"
    assert names_pts(text) == [("Code compiles", 5.0)]


def test_marks_vocabulary():
    assert names_pts("Question 1 10 marks\nQuestion 2 5 marks\n") == [
        ("Question 1", 10.0),
        ("Question 2", 5.0),
    ]
    assert names_pts("Essay structure\n20 marks\n") == [("Essay structure", 20.0)]


def test_out_of_and_worth_phrasing():
    text = "Code quality (out of 10)\nEssay worth 25 points\nPresentation out of 5\n"
    assert names_pts(text) == [
        ("Code quality", 10.0),
        ("Essay", 25.0),
        ("Presentation", 5.0),
    ]


def test_blackboard_weight_lines():
    text = "Organization\nWeight 25.00%\nGrammar and Mechanics\nWeight: 15%\n"
    assert names_pts(text) == [("Organization", 25.0), ("Grammar and Mechanics", 15.0)]


def test_blackboard_weight_inline():
    text = "Organization - Weight 25%\nGrammar, Weight: 15.00%\n"
    assert names_pts(text) == [("Organization", 25.0), ("Grammar", 15.0)]


def test_decimal_points():
    text = "Partial criterion (2.5 pts)\n"
    assert names_pts(text) == [("Partial criterion", 2.5)]


LMS_PERCENT_PASTE = """Excellent
Satisfactory
Unsatisfactory
Poor
Criteria
Excellent
Satisfactory
Unsatisfactory
Poor
Completion of Required Components
25% of total grade
100%
All required components are submitted exactly as listed in the assignment. Nothing missing. Fully follows instructions.
75%
Most components submitted, but one required piece is missing or incomplete.
50%
Multiple required elements are missing or incomplete.
25%
Submission is extremely incomplete or missing major required elements.
Screenshot / Artifact Quality
25% of total grade
100%
Screenshots/files load clearly, show the student’s own work, and capture everything needed (diagrams, tables, dashboards, etc.).
75%
Screenshots load but may be slightly unclear, cropped, or missing a small detail.
50%
Screenshots load partially or do not clearly show the required work.
25%
Broken/missing screenshots or no usable artifact included.
Accuracy & Alignment With Instructions
25% of total grade
100%
Work aligns well with the assignment requirements (e.g., correct type of diagram, correct structure, correct cycle format). Shows clear understanding of the task.
75%
Mostly aligned, but with minor mistakes or misunderstandings.
50%
Work is partially aligned but contains major errors or misapplied concepts.
25%
Work does not match the assignment instructions or uses the wrong type of artifact entirely.
Clarity & Organization
25% of total grade
100%
Work is neat, readable, and well-organized. Labels and structure are easy to understand.
75%
Mostly clear, but somewhat messy or disorganized.
50%
Cluttered, confusing, or hard to interpret.
25%
Unreadable, unorganized, or incoherent.
Criteria column
Completion of Required Components
25% of total grade
Screenshot / Artifact Quality
25% of total grade
Accuracy & Alignment With Instructions
25% of total grade
Clarity & Organization
25% of total grade
"""


def test_percent_weight_lms_paste():
    assert names_pts(LMS_PERCENT_PASTE) == [
        ("Completion of Required Components", 25.0),
        ("Screenshot / Artifact Quality", 25.0),
        ("Accuracy & Alignment With Instructions", 25.0),
        ("Clarity & Organization", 25.0),
    ]


D2L_SCORE_BLOCK_PASTE = """INFO 1031 Assignment Rubric
INFO 1031 Assignment Rubric
Criteria\tRatings\tPoints
Understanding of Agile Concepts

Thorough
Demonstrates a thorough understanding of Agile concepts, principles, and methodologies.
20 pts

Good
Demonstrates a good understanding, with minor gaps or inaccuracies.
15 pts

Basic
Demonstrates a basic understanding, with several gaps or inaccuracies.
10 pts

Limited
Demonstrates limited understanding, with significant gaps or inaccuracies.
5 pts

No Marks
Demonstrates no understanding of Agile concepts.
0 pts
Criterion Score
--
/20 pts
Comment
Leave a comment

Application of Agile Practices

Effectively
Effectively applies Agile practices and techniques to the assignment.
20 pts

Mostly
Mostly applies Agile practices effectively, with minor errors or omissions.
15 pts

Somewhat
Somewhat applies Agile practices, with several errors or omissions.
10 pts

Poorly
Poorly applies Agile practices, with significant errors or omissions.
5 pts

No Marks
Does not apply Agile practices.
0 pts
Criterion Score
--
/20 pts
Comment
Leave a comment

Clarity and Organization

Well
Information is clearly presented and well-organized.
20 pts

Mostly
Information is mostly clear and organized, with minor issues.
15 pts

Somewhat
Information is somewhat clear and organized, with several issues.
10 pts

Poorly
Information is unclear and poorly organized, with significant issues.
5 pts

No Marks
Information is unclear and disorganized.
0 pts
Criterion Score
--
/20 pts
Comment
Leave a comment

Critical Thinking and Analysis

Strong
Demonstrates strong critical thinking and thorough analysis.
20 pts

Good
Demonstrates good critical thinking and analysis, with minor gaps.
15 pts

Basic
Demonstrates basic critical thinking and analysis, with several gaps.
10 pts

Limited
Demonstrates limited critical thinking and analysis, with significant gaps.
5 pts

No Marks
Demonstrates no critical thinking or analysis.
0 pts
Criterion Score
--
/20 pts
Comment
Leave a comment

Adherence to Guidelines

Fully
Fully adheres to assignment guidelines and submission requirements.
20 pts

Mostly
Mostly adheres to guidelines, with minor deviations.
10 pts

No Marks
Does not adhere to guidelines or submission requirements.
0 pts
Criterion Score
"""


def test_d2l_score_block_paste():
    assert names_pts(D2L_SCORE_BLOCK_PASTE) == [
        ("Understanding of Agile Concepts", 20.0),
        ("Application of Agile Practices", 20.0),
        ("Clarity and Organization", 20.0),
        ("Critical Thinking and Analysis", 20.0),
        ("Adherence to Guidelines", 20.0),  # footer cut off: max rating used
    ]


def test_score_block_rating_descriptions_not_criteria():
    rows = names_pts(D2L_SCORE_BLOCK_PASTE)
    assert all("Demonstrates" not in name for name, _ in rows)
    assert all("INFO 1031" not in name for name, _ in rows)  # title filtered


def test_percent_weight_inline():
    text = "Clarity & Organization - 25% of total grade\nEffort: 75% of grade\n"
    assert names_pts(text) == [("Clarity & Organization", 25.0), ("Effort", 75.0)]


def test_duplicates_collapsed():
    text = "First thing (5 pts)\nSecond thing (3 pts)\nFirst thing (5 pts)\n"
    assert names_pts(text) == [("First thing", 5.0), ("Second thing", 3.0)]


def test_no_criteria_found():
    assert names_pts("Just some prose with no points anywhere.") == []
    assert names_pts("") == []


def test_crlf_handled():
    text = "First thing (5 pts)\r\nSecond thing (3 pts)\r\n"
    assert names_pts(text) == [("First thing", 5.0), ("Second thing", 3.0)]
