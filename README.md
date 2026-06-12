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

## API

The grading engine is exposed as a JSON API under `/api/v1`. **The browser UI
is just another client of these endpoints** — it has no grading routes of its
own, so anything the UI can do, your app can do.

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/grade` | Grade a zip against a rubric. Returns the full result JSON (or CSV with `?format=csv`). |
| `POST /api/v1/rubric/parse` | Parse pasted LMS rubric text into criteria with suggested checks. |
| `GET /api/v1/checks` | The check registry (names, required params, descriptions). |
| `GET /api/v1/health` | Liveness + environment (exec enabled, upload limit, auth required). |

`POST /grade` takes `multipart/form-data` with a `submissions` zip and exactly
one rubric source:

- **`rubric_csv`** — the canonical CSV, as an uploaded file or a string field;
- **`rubric_json`** — a JSON array of `{criterion, points, check_type, target,
  params}` objects (`params` may be a `key=value;…` string or an object) —
  use this when your app does its own review step after `/rubric/parse`;
- **`rubric_text`** — a raw LMS paste. Criteria the rule table can't map to a
  check are **excluded from scoring** and listed in `unmapped_criteria` (with
  a warning) — never guessed.

```powershell
# CSV rubric
curl -s -X POST http://127.0.0.1:5000/api/v1/grade `
  -F "submissions=@samples/sample_submissions.zip" `
  -F "rubric_csv=@samples/rubric_python.csv"

# Pasted LMS text, grades CSV back
curl -s -X POST "http://127.0.0.1:5000/api/v1/grade?format=csv" `
  -F "submissions=@samples/sample_submissions.zip" `
  -F "rubric_text=Submitted main.py 5 pts"

# Parse-then-grade with full control
curl -s -X POST http://127.0.0.1:5000/api/v1/rubric/parse `
  -H "Content-Type: application/json" -d "{\"rubric_text\": \"Uses the math module 10 pts\"}"
```

Success response (abridged): `{"criteria": [...], "students": [{"student",
"total", "possible", "criteria": [{"criterion", "passed", "points_earned",
"points_possible", "detail"}]}], "warnings": [], "unmapped_criteria": [],
"csv": "..."}` — the `csv` field is rendered from the same result object as
the rest of the payload. Errors always use `{"error": "<code>",
"messages": [...]}` with proper status codes (400/401/413).

**Auth**: set the `GRADING_API_KEY` env var and every endpoint except
`/health` requires a matching `X-API-Key` header. The UI prompts for the key
and stores it in localStorage. **CORS**: set `GRADING_CORS_ORIGINS` to a
comma-separated origin list (or `*`) if browser apps on other origins will
call the API.

## Pasting a rubric from your LMS

Instead of writing a CSV, you can copy a rubric straight out of your LMS and
paste it into the textbox on the upload page. Everything is deterministic —
no LLM at any step:

1. **Structure parsing** (`grading/paste_parser.py`) extracts criterion names
   and point values. Recognized formats: LMS table copies (tab-separated, e.g.
   Canvas), `Criterion name (10 points)`, `Criterion name … 10 pts`,
   `Criterion (out of 10)`, `Criterion worth 10 points`, `Criterion / 10`,
   percent-weight rubrics (criterion followed by `25% of total grade` or a
   Blackboard-style `Weight: 25.00%`; points = the percent), D2L/Brightspace
   rating-block exports (criterion name, rating levels each with their own
   `N pts`, and a `Criterion Score … /20 pts` footer carrying the max points —
   falls back to the highest rating value if the footer is missing), and a
   criterion followed by rating-level points lines, where the criterion is
   worth the highest value in the run (so Canvas's high-to-low and Moodle's
   low-to-high rating orders both work, including `5 to >3.0 pts` ranges).
   "marks" is accepted wherever pts/points are. Header rows, titles, "Total",
   rating noise ("Full Marks", "Excellent", "Satisfactory"), comment prompts,
   and duplicated criteria-column footers are filtered out.
2. **Check suggestion** (`grading/suggest.py`) maps each criterion's wording
   to a check via an ordered regex rule table — e.g. *"function called
   calculate_average"* → `python_function_exists`, *"Main.java compiles"* →
   `run_command command=javac Main.java`, *"at least 50 words"* →
   `word_count min=50`. Every suggestion shows which rule produced it.
3. **Review page**: the reconstructed rubric appears as an editable table.
   Rows with no matching rule (or missing required params) are highlighted —
   nothing is guessed silently; you pick the check. Then upload the zip and
   grade. A **Download rubric CSV** button saves the (edited) rubric in the
   canonical format so you only paste once per assignment.

New phrasings your LMS uses can be supported by adding a rule to the table in
`grading/suggest.py` — one regex plus a small builder function.

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
