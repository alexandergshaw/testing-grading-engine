"""Document text checks (docx/pdf/txt). python-docx and pypdf are imported
lazily so the app runs without them unless a rubric actually uses doc checks."""
from __future__ import annotations

from pathlib import Path

from . import CheckContext, no_files_detail, param_bool, register
from .text import read_text


def extract_doc_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        try:
            import docx
        except ImportError:
            raise RuntimeError("python-docx is not installed (pip install python-docx)")
        document = docx.Document(str(path))
        return "\n".join(p.text for p in document.paragraphs)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("pypdf is not installed (pip install pypdf)")
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return read_text(path)


@register(
    "doc_contains_text",
    required_params=("text",),
    description="Passes when text extracted from any matched docx/pdf/txt file contains text=.",
)
def doc_contains_text(ctx: CheckContext) -> tuple[bool, str]:
    needle = ctx.params["text"]
    ignore_case = param_bool(ctx.params, "ignore_case")
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    for f in files:
        haystack = extract_doc_text(f)
        if ignore_case:
            found = needle.lower() in haystack.lower()
        else:
            found = needle in haystack
        if found:
            return True, f"{needle!r} found in {ctx.rel(f)}"
    return False, f"{needle!r} not found in {len(files)} matched file(s)"
