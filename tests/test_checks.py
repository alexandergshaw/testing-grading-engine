import sys
import textwrap

import pytest

from grading.checks import CHECK_REGISTRY, CheckContext


def run_check(name, folder, target="", params=None, allow_exec=False):
    ctx = CheckContext(folder=folder, target=target, params=params or {}, allow_exec=allow_exec)
    return CHECK_REGISTRY[name].func(ctx)


# ---- files ----

def test_file_exists(make_tree):
    root = make_tree({"main.py": "x"})
    assert run_check("file_exists", root, "main.py")[0] is True
    passed, detail = run_check("file_exists", root, "missing.py")
    assert passed is False
    assert "missing.py" in detail


def test_file_count(make_tree):
    root = make_tree({"a.html": "", "b.html": "", "c.html": ""})
    assert run_check("file_count", root, "*.html", {"min": "3"})[0] is True
    assert run_check("file_count", root, "*.html", {"min": "4"})[0] is False
    assert run_check("file_count", root, "*.html", {"max": "2"})[0] is False
    with pytest.raises(ValueError, match="min=/max="):
        run_check("file_count", root, "*.html")


# ---- text ----

def test_contains_text(make_tree):
    root = make_tree({"notes.txt": "Hello World"})
    assert run_check("contains_text", root, "*.txt", {"text": "Hello"})[0] is True
    assert run_check("contains_text", root, "*.txt", {"text": "hello"})[0] is False
    assert (
        run_check("contains_text", root, "*.txt", {"text": "hello", "ignore_case": "true"})[0]
        is True
    )
    assert run_check("contains_text", root, "*.md", {"text": "Hello"})[0] is False


def test_regex_match(make_tree):
    root = make_tree({"main.py": '"""Docstring."""\ndef main():\n    pass\n'})
    assert run_check("regex_match", root, "main.py", {"pattern": r"^def main"})[0] is True
    assert run_check("regex_match", root, "main.py", {"pattern": r"^class"})[0] is False


def test_word_and_line_count(make_tree):
    root = make_tree({"README.md": "one two three\nfour five\n"})
    assert run_check("word_count", root, "README*", {"min": "5"})[0] is True
    assert run_check("word_count", root, "README*", {"min": "6"})[0] is False
    assert run_check("line_count", root, "README*", {"min": "2", "max": "2"})[0] is True


# ---- python (static) ----

def test_python_syntax_ok(make_tree):
    root = make_tree({"good.py": "x = 1\n", "bad.py": "def broken(:\n"})
    assert run_check("python_syntax_ok", root, "good.py")[0] is True
    passed, detail = run_check("python_syntax_ok", root, "*.py")
    assert passed is False
    assert "bad.py" in detail


def test_python_function_exists(make_tree):
    root = make_tree({"main.py": "def calculate_average(nums):\n    return 0\n"})
    assert (
        run_check("python_function_exists", root, "*.py", {"name": "calculate_average"})[0] is True
    )
    assert run_check("python_function_exists", root, "*.py", {"name": "main"})[0] is False


def test_python_imports(make_tree):
    root = make_tree({"main.py": "import math\nfrom os.path import join\n"})
    assert run_check("python_imports", root, "*.py", {"module": "math"})[0] is True
    assert run_check("python_imports", root, "*.py", {"module": "os.path"})[0] is True
    assert run_check("python_imports", root, "*.py", {"module": "sys"})[0] is False


# ---- python_runs (execution) ----

def test_python_runs_disabled_by_default(make_tree):
    root = make_tree({"main.py": "print('ok')\n"})
    passed, detail = run_check("python_runs", root, "main.py")
    assert passed is False
    assert "disabled" in detail


def test_python_runs_exit_zero(make_tree):
    root = make_tree({"main.py": "print('ok')\n"})
    assert run_check("python_runs", root, "main.py", allow_exec=True)[0] is True


def test_python_runs_exit_nonzero(make_tree):
    root = make_tree({"main.py": "import sys\nsys.exit(2)\n"})
    passed, detail = run_check("python_runs", root, "main.py", allow_exec=True)
    assert passed is False
    assert "exited 2" in detail


def test_python_runs_timeout(make_tree):
    root = make_tree({"main.py": "import time\ntime.sleep(30)\n"})
    passed, detail = run_check(
        "python_runs", root, "main.py", {"timeout": "1"}, allow_exec=True
    )
    assert passed is False
    assert "timed out" in detail


# ---- generic commands (any language) ----

PY = f'"{sys.executable}"'


def test_run_command_disabled_by_default(make_tree):
    root = make_tree({"main.txt": ""})
    passed, detail = run_check("run_command", root, params={"command": f"{PY} -c pass"})
    assert passed is False
    assert "disabled" in detail


def test_run_command_exit_zero(make_tree):
    root = make_tree({"main.txt": ""})
    passed, _ = run_check(
        "run_command", root, params={"command": f'{PY} -c "exit(0)"'}, allow_exec=True
    )
    assert passed is True


def test_run_command_expected_exit(make_tree):
    root = make_tree({"main.txt": ""})
    params = {"command": f'{PY} -c "raise SystemExit(3)"', "expect_exit": "3"}
    assert run_check("run_command", root, params=params, allow_exec=True)[0] is True
    params["expect_exit"] = "0"
    passed, detail = run_check("run_command", root, params=params, allow_exec=True)
    assert passed is False
    assert "exited 3" in detail


def test_run_command_not_found(make_tree):
    root = make_tree({"main.txt": ""})
    passed, detail = run_check(
        "run_command", root, params={"command": "no_such_tool_xyz --version"}, allow_exec=True
    )
    assert passed is False
    assert "could not run" in detail or "exited" in detail


def test_run_command_uses_student_folder_as_cwd(make_tree):
    root = make_tree({"main.py": "print('from student folder')"})
    passed, _ = run_check(
        "run_command", root, params={"command": f"{PY} main.py"}, allow_exec=True
    )
    assert passed is True


def test_output_contains_text(make_tree):
    root = make_tree({"main.py": "print('Hello, World!')"})
    params = {"command": f"{PY} main.py", "text": "Hello, World!"}
    assert run_check("output_contains", root, params=params, allow_exec=True)[0] is True
    params["text"] = "Goodbye"
    assert run_check("output_contains", root, params=params, allow_exec=True)[0] is False


def test_output_contains_pattern_and_stdin(make_tree):
    root = make_tree({"echo.py": "print('got:', input())"})
    params = {"command": f"{PY} echo.py", "pattern": r"got: \w+", "stdin": "ping"}
    assert run_check("output_contains", root, params=params, allow_exec=True)[0] is True


def test_output_contains_requires_text_or_pattern(make_tree):
    root = make_tree({"main.txt": ""})
    with pytest.raises(ValueError, match="text= or pattern="):
        run_check("output_contains", root, params={"command": f"{PY} -V"}, allow_exec=True)


# ---- web ----

HTML = textwrap.dedent(
    """
    <!doctype html>
    <html><head><title>My Page</title></head>
    <body><img src="cat.jpg" alt="a cat"><table><tbody><tr><td>x</td></tr></tbody></table></body>
    </html>
    """
)


def test_html_has_tag(make_tree):
    root = make_tree({"index.html": HTML})
    assert run_check("html_has_tag", root, "index.html", {"tag": "title"})[0] is True
    assert run_check("html_has_tag", root, "index.html", {"tag": "img", "attr": "alt"})[0] is True
    assert (
        run_check(
            "html_has_tag", root, "index.html", {"tag": "img", "attr": "src", "value": "cat.jpg"}
        )[0]
        is True
    )
    assert run_check("html_has_tag", root, "index.html", {"tag": "video"})[0] is False


def test_css_has_selector(make_tree):
    root = make_tree(
        {"style.css": "/* body in a comment { } */\ntbody { color: red; }\nbody, html { margin: 0; }\n"}
    )
    assert run_check("css_has_selector", root, "*.css", {"selector": "body"})[0] is True
    assert run_check("css_has_selector", root, "*.css", {"selector": "h1"})[0] is False
    # "tbody" must not satisfy a "body" rule by substring
    root2 = make_tree({"only_tbody.css": "tbody { color: red; }\n"})
    assert (
        run_check("css_has_selector", root2, "only_tbody.css", {"selector": "body"})[0] is False
    )


# ---- docs ----

def test_doc_contains_text_txt(make_tree):
    root = make_tree({"essay.txt": "The mitochondria is the powerhouse of the cell."})
    assert run_check("doc_contains_text", root, "*.txt", {"text": "mitochondria"})[0] is True
    assert run_check("doc_contains_text", root, "*.txt", {"text": "ribosome"})[0] is False


def test_doc_contains_text_docx(make_tree, tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_paragraph("Findings: the hypothesis was supported.")
    path = tmp_path / "report.docx"
    document.save(str(path))
    assert run_check("doc_contains_text", tmp_path, "*.docx", {"text": "hypothesis"})[0] is True
