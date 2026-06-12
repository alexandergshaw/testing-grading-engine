"""Generic command checks - grade any language with a toolchain installed on
the grading machine (javac/java, gcc, node, dotnet, Rscript, ...).

The command comes from the rubric (instructor-authored), runs with the student
folder as the working directory, and is gated behind allow_exec like all
execution checks. shell=False: on Windows the command string is passed to
CreateProcess directly; elsewhere it is shlex-split.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess

from . import CheckContext, param_bool, register

_DISABLED = "code execution disabled (set GRADING_ALLOW_EXEC=1 to enable command checks)"


def _run(ctx: CheckContext, command: str, timeout: float, stdin_text: str | None):
    args = command if os.name == "nt" else shlex.split(command)
    kwargs = dict(cwd=ctx.folder, capture_output=True, text=True, timeout=timeout)
    if stdin_text is not None:
        kwargs["input"] = stdin_text
    else:
        kwargs["stdin"] = subprocess.DEVNULL
    return subprocess.run(args, **kwargs)


def _tail(proc) -> str:
    return (proc.stderr or proc.stdout or "").strip()[-1024:]


@register(
    "run_command",
    required_params=("command",),
    description=(
        "Passes when command= exits with expect_exit= (default 0) within timeout= "
        "seconds (default 10), run inside the student folder. Works for any language "
        "(e.g. command=javac Main.java, command=node main.js). Disabled unless "
        "GRADING_ALLOW_EXEC=1."
    ),
)
def run_command(ctx: CheckContext) -> tuple[bool, str]:
    if not ctx.allow_exec:
        return False, _DISABLED
    command = ctx.params["command"]
    timeout = float(ctx.params.get("timeout", "10"))
    expected = int(ctx.params.get("expect_exit", "0"))
    try:
        proc = _run(ctx, command, timeout, None)
    except subprocess.TimeoutExpired:
        return False, f"{command!r} timed out after {timeout:g}s"
    except (FileNotFoundError, OSError) as e:
        return False, f"could not run {command!r}: {e}"
    if proc.returncode == expected:
        return True, f"{command!r} exited {proc.returncode}"
    return False, f"{command!r} exited {proc.returncode} (expected {expected}): {_tail(proc)}"


@register(
    "output_contains",
    required_params=("command",),
    description=(
        "Passes when the output of command= contains text= or matches regex pattern= "
        "(ignore_case= optional; stdin= feeds input, use \\n for newlines). Functional "
        "grading for any language. Disabled unless GRADING_ALLOW_EXEC=1."
    ),
)
def output_contains(ctx: CheckContext) -> tuple[bool, str]:
    if not ctx.allow_exec:
        return False, _DISABLED
    command = ctx.params["command"]
    text = ctx.params.get("text")
    pattern = ctx.params.get("pattern")
    if text is None and pattern is None:
        raise ValueError("provide text= or pattern= in params")
    timeout = float(ctx.params.get("timeout", "10"))
    stdin_text = ctx.params.get("stdin")
    if stdin_text is not None:
        stdin_text = stdin_text.replace("\\n", "\n")
    try:
        proc = _run(ctx, command, timeout, stdin_text)
    except subprocess.TimeoutExpired:
        return False, f"{command!r} timed out after {timeout:g}s"
    except (FileNotFoundError, OSError) as e:
        return False, f"could not run {command!r}: {e}"

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    ignore_case = param_bool(ctx.params, "ignore_case")
    if text is not None:
        found = text.lower() in output.lower() if ignore_case else text in output
        wanted = f"text {text!r}"
    else:
        flags = re.IGNORECASE if ignore_case else 0
        found = re.search(pattern, output, flags) is not None
        wanted = f"pattern {pattern!r}"
    if found:
        return True, f"{wanted} found in output of {command!r}"
    return False, f"{wanted} not in output of {command!r} (exit {proc.returncode}): {_tail(proc)}"
