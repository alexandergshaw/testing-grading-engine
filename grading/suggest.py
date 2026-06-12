"""Deterministic keyword rules mapping criterion text to a suggested check.

Each rule is (label, regex, builder). The first rule whose regex matches and
whose builder returns a Suggestion wins. No rule matching means the user picks
the check on the review page - nothing is guessed silently. Rules are ordered
most-specific first; grow this table as new LMS phrasings show up.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Callable

_FILENAME = re.compile(
    r"\b([\w\-]+\.(?:py|java|c|cpp|cs|js|ts|html|css|md|txt|rb|go|rs|php|sql|ipynb))\b", re.I
)


@dataclass(frozen=True)
class Suggestion:
    check_type: str
    target: str = ""
    params: str = ""
    rule: str = ""


def _filename(text: str, ext: str | None = None) -> str | None:
    for m in _FILENAME.finditer(text):
        if ext is None or m.group(1).lower().endswith(ext):
            return m.group(1)
    return None


RULES: list[tuple[str, re.Pattern, Callable]] = []


def rule(label: str, pattern: str):
    def decorator(builder):
        RULES.append((label, re.compile(pattern, re.I), builder))
        return builder

    return decorator


@rule("expected output", r"(?:prints?|outputs?|displays?)\s+[`'\"](?P<out>[^`'\"]+)[`'\"]")
def _expected_output(m, text):
    params = f"text={m.group('out')}"
    f = _filename(text, ".py")
    if f:
        params = f"command=python {f};{params}"
    return Suggestion("output_contains", "", params)


def _function(name: str, text: str) -> Suggestion:
    return Suggestion("python_function_exists", _filename(text, ".py") or "*.py", f"name={name}")


@rule("function definition", r"(?:function|method)\s+(?:named|called)\s+[`'\"]?(?P<fn>[A-Za-z_]\w*)")
def _function_named(m, text):
    return _function(m.group("fn"), text)


@rule(
    "function definition",
    r"(?:defines?|implements?|writes?|has|includes?)\s+(?:an?\s+)?[`'\"]?(?P<fn>[A-Za-z_]\w*)[`'\"]?(?:\s*\(\s*\))?\s+(?:function|method)",
)
def _function_def(m, text):
    return _function(m.group("fn"), text)


@rule(
    "module import",
    r"(?:imports?|uses?)\s+(?:the\s+)?[`'\"]?(?P<mod>[A-Za-z_][\w.]*)[`'\"]?\s+(?:module|library|package)",
)
def _uses_module(m, text):
    return Suggestion("python_imports", "*.py", f"module={m.group('mod')}")


@rule("module import", r"\bimports?\s+(?:the\s+)?[`'\"]?(?P<mod>[A-Za-z_][\w.]*)")
def _imports(m, text):
    return Suggestion("python_imports", "*.py", f"module={m.group('mod')}")


@rule("word count", r"at least\s+(?P<n>\d+)\s+words")
def _word_min(m, text):
    target = _filename(text) or ("README*" if re.search(r"readme", text, re.I) else "")
    return Suggestion("word_count", target, f"min={m.group('n')}")


@rule("compiles / syntax", r"\b(?:compil\w*|syntax)\b")
def _compiles(m, text):
    for ext, compiler in ((".java", "javac"), (".c", "gcc"), (".cpp", "g++"), (".cs", "csc")):
        f = _filename(text, ext)
        if f:
            return Suggestion("run_command", "", f"command={compiler} {f}")
    return Suggestion("python_syntax_ok", "*.py", "")


@rule(
    "program runs",
    r"(?:runs?|executes?)\s+(?:cleanly|successfully|without\s+(?:errors?|crashing))|program\s+(?:runs?|executes?)\b",
)
def _runs(m, text):
    f = _filename(text, ".js")
    if f:
        return Suggestion("run_command", "", f"command=node {f}")
    return Suggestion("python_runs", _filename(text, ".py") or "*.py", "")


@rule("page title", r"\btitle\b")
def _title(m, text):
    if not re.search(r"page|tag|element|html", text, re.I):
        return None
    return Suggestion("html_has_tag", _filename(text, ".html") or "*.html", "tag=title")


@rule("image alt text", r"\balt\b")
def _alt(m, text):
    return Suggestion("html_has_tag", _filename(text, ".html") or "*.html", "tag=img;attr=alt")


@rule(
    "css selector",
    r"styles?\s+(?:the\s+)?(?P<sel>body|html|h[1-6]|p|nav|header|footer|main|section|div|a|ul|li|img)\b",
)
def _css_selector(m, text):
    return Suggestion("css_has_selector", "*.css", f"selector={m.group('sel')}")


@rule("stylesheet present", r"stylesheet|css\s+file|\.css\b")
def _stylesheet(m, text):
    return Suggestion("file_exists", "*.css", "")


@rule("readme present", r"\breadme\b")
def _readme(m, text):
    return Suggestion("file_exists", "README*", "")


@rule(
    "contains text",
    r"(?:mentions?|includes?|contains?)\s+(?:the\s+)?(?:word|phrase|text)?\s*[`'\"](?P<txt>[^`'\"]+)[`'\"]",
)
def _contains(m, text):
    return Suggestion("contains_text", _filename(text) or "", f"text={m.group('txt')}")


@rule("file submitted", r".")
def _file_submitted(m, text):
    f = _filename(text)
    return Suggestion("file_exists", f, "") if f else None


def suggest(text: str) -> Suggestion | None:
    for label, pattern, builder in RULES:
        m = pattern.search(text)
        if m is None:
            continue
        suggestion = builder(m, text)
        if suggestion is not None:
            return replace(suggestion, rule=label)
    return None
