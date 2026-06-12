# Assignment Grading Engine

A small Flask app that grades a zip of student assignment submissions against a
rubric CSV using **deterministic, rule-based checks — no LLM is involved
anywhere in grading**. Upload a zip (one folder per student) and a rubric CSV,
get an on-screen results table and a downloadable grades CSV. Both are rendered
from the same in-memory result, so they can never disagree.

## Quickstart

```powershell
pip install -r requirements.txt
python samples/make_sample_zip.py   # builds samples/sample_submissions.zip
flask run                            # or: python app.py
```

Open http://127.0.0.1:5000, upload `samples/sample_submissions.zip` and
`samples/rubric_python.csv`, and click **Grade**. The grades CSV download is
embedded directly in the results page, generated from the exact same result
as the on-screen table.

## Deploying to Vercel

The app is fully stateless (no sessions, no server-side result store), so it
runs as a Vercel serverless function out of the box:

```powershell
npm i -g vercel
vercel          # preview deploy; `vercel --prod` for production
```

`api/index.py` exposes the Flask app and `vercel.json` rewrites all routes to
it. Two platform limits to know about:

- **Uploads are capped at 4 MB** on Vercel (the platform rejects bodies over
  ~4.5 MB). Grade large class zips locally.
- **Execution checks are always disabled on Vercel** (`python_runs`,
  `run_command`, `output_contains`), regardless of `GRADING_ALLOW_EXEC` —
  serverless has no student toolchains, and running untrusted code on shared
  infrastructure is unsafe. All static checks work unchanged.

Note the deployed URL is public — there is no auth. Use Vercel's deployment
protection if that matters.

## Rubric CSV format

Every rubric uses the same five columns; different assignments just have
different rows:

```csv
criterion,points,check_type,target,params
```

| Column | Meaning |
|---|---|
| `criterion` | Display name; becomes a column in the grades CSV |
| `points` | Awarded all-or-nothing when the check passes (partial credit: split into multiple rows) |
| `check_type` | One of the checks below |
| `target` | File glob relative to each student folder (`*.py`, `index.html`, `**/*.docx`); empty = all files |
| `params` | `key=value` pairs separated by `;` (e.g. `pattern=def main;ignore_case=true`) |

### Check types

| `check_type` | params | Passes when |
|---|---|---|
| `file_exists` | — | glob matches at least one file |
| `file_count` | `min=`, `max=` | number of matching files is in range |
| `contains_text` | `text=` (req), `ignore_case=` | any matched file contains the text |
| `regex_match` | `pattern=` (req), `ignore_case=` | regex matches in any matched file |
| `line_count` | `min=`, `max=` | total lines across matched files in range |
| `word_count` | `min=`, `max=` | total words across matched files in range |
| `python_syntax_ok` | — | every matched `.py` file parses (static AST, safe) |
| `python_function_exists` | `name=` (req) | a function with that name is defined (static AST, safe) |
| `python_imports` | `module=` (req) | the module is imported (static AST, safe) |
| `python_runs` | `timeout=` (default 10), `args=` | first matched script exits 0 — **opt-in, see below** |
| `html_has_tag` | `tag=` (req), `attr=`, `value=` | tag (optionally with attribute) found in matched HTML |
| `css_has_selector` | `selector=` (req) | a CSS rule for that selector exists |
| `doc_contains_text` | `text=` (req), `ignore_case=` | text extracted from docx/pdf/txt contains the text |
| `run_command` | `command=` (req), `timeout=`, `expect_exit=` | command exits with the expected code, run inside the student folder — **opt-in** |
| `output_contains` | `command=` (req), `text=` or `pattern=`, `stdin=`, `ignore_case=` | command output contains the text / matches the regex — **opt-in** |

See `samples/rubric_python.csv`, `samples/rubric_web.csv`, and
`samples/rubric_java.csv` for complete rubrics that all share the schema.

## Grading any language

The engine is language-agnostic. Three kinds of checks cover code in any
language:

- **Structure**: `file_exists`, `file_count` work on any file type.
- **Static content**: `regex_match` / `contains_text` inspect any source file —
  e.g. `pattern=public\s+static\s+void\s+main` on `*.java`, or
  `pattern=fn\s+main` on `*.rs`.
- **Build & run** (requires `GRADING_ALLOW_EXEC=1` and the toolchain installed
  on the grading machine): `run_command` for compiling/running anything, and
  `output_contains` for functional tests against program output.

Example rows for a few languages:

```csv
Java compiles,15,run_command,,command=javac Main.java;timeout=30
C compiles,15,run_command,,command=gcc -o prog main.c
C program prints result,10,output_contains,,command=./prog;text=42
Node script runs,10,run_command,,command=node main.js
R script output,10,output_contains,,command=Rscript analysis.R;pattern=mean: \d+
Handles user input,10,output_contains,,command=python quiz.py;stdin=blue\n7;text=correct
```

Commands run with the student folder as the working directory. If a param
value itself needs a semicolon, escape it as `\;`. `stdin=` feeds input to the
program; write `\n` for newlines between answers.

New check types can be added by dropping a function with a `@register(...)`
decorator into `grading/checks/` — the rubric validator, docs table on the
upload page, and engine pick it up automatically.

## Running student code (`python_runs`)

**Executing student code is inherently risky** — a submitted script runs with
your user's permissions. `python_runs` is therefore **disabled by default**:
those rows grade as failed with an explanatory message. Enable it only on a
machine where you accept that risk:

```powershell
$env:GRADING_ALLOW_EXEC = "1"; flask run
```

Scripts run via `subprocess` with a timeout, no stdin, and captured output.
All other Python checks (`python_syntax_ok`, `python_function_exists`,
`python_imports`) are static AST analysis and never execute anything.

## Zip expectations & safety

- Top-level folders in the zip are students; the folder name is the student name.
- A single wrapper folder (`assignment1/alice`, `assignment1/bob`) is unwrapped automatically.
- Loose top-level files are ignored with a warning; nested per-student zips are not supported.
- Uploads are capped at 50 MB; extraction rejects zip-slip paths, symlinks,
  more than 5,000 entries, or more than 200 MB declared uncompressed size.
- `__MACOSX/`, `.DS_Store`, and `Thumbs.db` junk entries are skipped.

`python-docx` / `pypdf` are only needed if a rubric uses `doc_contains_text`
on .docx/.pdf files; they are imported lazily.

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

The grading engine (`grading/`) has no Flask dependency and is fully covered by
unit tests, including zip-slip/zip-bomb rejection and every check type.
