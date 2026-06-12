"""HTML/CSS structure checks using only the standard library."""
from __future__ import annotations

import re
from html.parser import HTMLParser

from . import CheckContext, no_files_detail, register
from .text import read_text


class _TagFinder(HTMLParser):
    def __init__(self, tag: str, attr: str | None, value: str | None):
        super().__init__()
        self.tag = tag.lower()
        self.attr = attr.lower() if attr else None
        self.value = value
        self.found = False

    def handle_starttag(self, tag, attrs):
        if self.found or tag != self.tag:
            return
        if self.attr is None:
            self.found = True
            return
        for key, val in attrs:
            if key == self.attr:
                if self.value is None or (val is not None and val.lower() == self.value.lower()):
                    self.found = True
                    return


@register(
    "html_has_tag",
    required_params=("tag",),
    description="Passes when any matched HTML file contains tag= (optionally with attr= and value=).",
)
def html_has_tag(ctx: CheckContext) -> tuple[bool, str]:
    tag = ctx.params["tag"]
    attr = ctx.params.get("attr")
    value = ctx.params.get("value")
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    wanted = f"<{tag}>" if not attr else f"<{tag} {attr}{'=' + value if value else ''}>"
    for f in files:
        finder = _TagFinder(tag, attr, value)
        finder.feed(read_text(f))
        if finder.found:
            return True, f"{wanted} found in {ctx.rel(f)}"
    return False, f"{wanted} not found in {len(files)} matched file(s)"


@register(
    "css_has_selector",
    required_params=("selector",),
    description="Passes when any matched CSS file has a rule for selector=.",
)
def css_has_selector(ctx: CheckContext) -> tuple[bool, str]:
    selector = ctx.params["selector"]
    files = ctx.matched_files()
    if not files:
        return False, no_files_detail(ctx)
    # selector must start at a token boundary and be followed by {, a comma
    # (selector group), or : (pseudo-class), so "body" does not match "tbody".
    pattern = re.compile(r"(?<![\w.#-])" + re.escape(selector) + r"\s*[,{:]")
    for f in files:
        css = re.sub(r"/\*.*?\*/", "", read_text(f), flags=re.S)
        if pattern.search(css):
            return True, f"selector {selector!r} found in {ctx.rel(f)}"
    return False, f"selector {selector!r} not found in {len(files)} matched file(s)"
