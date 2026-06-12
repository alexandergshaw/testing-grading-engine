"""Python code checks. Static AST checks are preferred; python_runs executes
student code and is therefore disabled unless allow_exec is set."""
from __future__ import annotations

import ast
import shlex
import subprocess
import sys
from pathlib import Path

from . import CheckContext, no_files_detail, register
from .text import read_text


def _parse_file(path: Path) -> ast.Module:
    return ast.parse(read_text(path), filename=path.name)


@register(
    "python_syntax_ok",
    description="Passes when every matched .py file parses without a syntax error (static, safe).",
)
def python_syntax_ok(ctx: CheckContext) -> tuple[bool, str]:
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        try:
            _parse_file(f)
        except SyntaxError as e:
            return False, f"syntax error in {ctx.rel(f)}: line {e.lineno}: {e.msg}"
    return True, f"{len(files)} file(s) parsed cleanly"


@register(
    "python_function_exists",
    required_params=("name",),
    description="Passes when any matched file defines a function name= (static AST check).",
)
def python_function_exists(ctx: CheckContext) -> tuple[bool, str]:
    name = ctx.params["name"]
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        try:
            tree = _parse_file(f)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return True, f"def {name} found in {ctx.rel(f)} (line {node.lineno})"
    return False, f"no function named {name!r} in {len(files)} matched file(s)"


@register(
    "python_imports",
    required_params=("module",),
    description="Passes when any matched file imports module= (static AST check).",
)
def python_imports(ctx: CheckContext) -> tuple[bool, str]:
    module = ctx.params["module"]
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        try:
            tree = _parse_file(f)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(a.name == module or a.name.startswith(module + ".") for a in node.names):
                    return True, f"import {module} found in {ctx.rel(f)}"
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == module or node.module.startswith(module + "."):
                    return True, f"from {module} import ... found in {ctx.rel(f)}"
    return False, f"{module!r} not imported in {len(files)} matched file(s)"


@register(
    "python_runs",
    description=(
        "Passes when the first matched script exits 0 within timeout= seconds "
        "(default 10; args= optional). Executes student code - disabled unless "
        "GRADING_ALLOW_EXEC=1."
    ),
)
def python_runs(ctx: CheckContext) -> tuple[bool, str]:
    if not ctx.allow_exec:
        return False, "code execution disabled (set GRADING_ALLOW_EXEC=1 to enable python_runs)"
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    script = files[0]
    timeout = float(ctx.params.get("timeout", "10"))
    args = shlex.split(ctx.params.get("args", ""))
    try:
        proc = subprocess.run(
            [sys.executable, script.name, *args],
            cwd=script.parent,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"{ctx.rel(script)} timed out after {timeout:g}s"
    if proc.returncode == 0:
        return True, f"{ctx.rel(script)} exited 0"
    output = (proc.stderr or proc.stdout or "").strip()[-1024:]
    return False, f"{ctx.rel(script)} exited {proc.returncode}: {output}"
