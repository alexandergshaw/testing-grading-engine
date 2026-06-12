from grading.suggest import suggest


def test_function_named():
    s = suggest("Defines a function called calculate_average")
    assert s.check_type == "python_function_exists"
    assert s.params == "name=calculate_average"
    assert s.target == "*.py"


def test_function_alt_phrasing():
    s = suggest("Has a main() method")
    assert s.check_type == "python_function_exists"
    assert s.params == "name=main"


def test_function_prefers_named_file():
    s = suggest("main.py defines a function called greet")
    assert s.target == "main.py"


def test_uses_module():
    s = suggest("Uses the math module")
    assert s.check_type == "python_imports"
    assert s.params == "module=math"


def test_imports_generic():
    s = suggest("Imports csv")
    assert s.check_type == "python_imports"
    assert s.params == "module=csv"


def test_word_count_readme():
    s = suggest("README contains at least 50 words")
    assert s.check_type == "word_count"
    assert s.params == "min=50"
    assert s.target == "README*"


def test_compile_java():
    s = suggest("Main.java compiles without errors")
    assert s.check_type == "run_command"
    assert s.params == "command=javac Main.java"


def test_compile_python_default():
    s = suggest("Code compiles with no syntax errors")
    assert s.check_type == "python_syntax_ok"
    assert s.target == "*.py"


def test_runs_python():
    s = suggest("main.py runs without errors")
    assert s.check_type == "python_runs"
    assert s.target == "main.py"


def test_runs_node():
    s = suggest("app.js runs without errors")
    assert s.check_type == "run_command"
    assert s.params == "command=node app.js"


def test_expected_output():
    s = suggest("Program prints 'Hello, World!' when main.py is run")
    assert s.check_type == "output_contains"
    assert s.params == "command=python main.py;text=Hello, World!"


def test_page_title():
    s = suggest("Page has a title")
    assert s.check_type == "html_has_tag"
    assert s.params == "tag=title"


def test_image_alt():
    s = suggest("All images have alt text")
    assert s.check_type == "html_has_tag"
    assert s.params == "tag=img;attr=alt"


def test_css_selector():
    s = suggest("Stylesheet styles body")
    assert s.check_type == "css_has_selector"
    assert s.params == "selector=body"


def test_stylesheet_present():
    s = suggest("Includes an external stylesheet")
    assert s.check_type == "file_exists"
    assert s.target == "*.css"


def test_readme_present():
    s = suggest("Includes a README")
    assert s.check_type == "file_exists"
    assert s.target == "README*"


def test_contains_quoted_text():
    s = suggest('Mentions "photosynthesis"')
    assert s.check_type == "contains_text"
    assert s.params == "text=photosynthesis"


def test_file_submitted_fallback():
    s = suggest("Submitted main.py")
    assert s.check_type == "file_exists"
    assert s.target == "main.py"


def test_no_rule_matches():
    assert suggest("Overall quality and effort") is None
