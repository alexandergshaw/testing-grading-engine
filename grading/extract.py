"""Safe zip extraction and student-folder detection.

Protections: zip-slip path traversal, absolute/drive paths, symlink members,
member-count and declared-uncompressed-size limits (zip bombs).
"""
from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_MEMBERS = 5000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MB

_JUNK_PREFIXES = ("__MACOSX/",)
_JUNK_NAMES = (".DS_Store", "Thumbs.db")


class ExtractionError(ValueError):
    pass


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def extract_zip(source, dest: Path) -> list[str]:
    """Extract a zip (path or file-like object) into dest. Returns warnings."""
    warnings: list[str] = []
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile:
        raise ExtractionError("uploaded file is not a valid zip archive")

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ExtractionError(
                f"zip has {len(infos)} entries (limit {MAX_MEMBERS}) - refusing to extract"
            )
        total = sum(i.file_size for i in infos)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ExtractionError(
                f"zip declares {total // (1024 * 1024)} MB uncompressed "
                f"(limit {MAX_UNCOMPRESSED_BYTES // (1024 * 1024)} MB) - refusing to extract"
            )

        dest_resolved = dest.resolve()
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.startswith(_JUNK_PREFIXES) or PurePosixPath(name).name in _JUNK_NAMES:
                continue
            if _is_symlink(info):
                warnings.append(f"skipped symlink entry {name!r}")
                continue
            parts = PurePosixPath(name).parts
            if name.startswith("/") or ".." in parts or ":" in name:
                raise ExtractionError(f"zip entry {info.filename!r} has an unsafe path")
            target = (dest / name).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ExtractionError(f"zip entry {info.filename!r} escapes the extraction folder")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    return warnings


def find_student_folders(root: Path) -> tuple[list[Path], list[str]]:
    """Top-level directories are students; student name = folder name.

    If the zip has a single wrapper folder containing only directories
    (the classic "assignment1/student1, assignment1/student2" layout),
    descend one level. Loose top-level files are ignored with a warning.
    """
    warnings: list[str] = []
    dirs = sorted(p for p in root.iterdir() if p.is_dir())
    loose = sorted(p for p in root.iterdir() if p.is_file())
    if loose:
        shown = ", ".join(p.name for p in loose[:10])
        warnings.append(f"ignored {len(loose)} top-level file(s) in the zip: {shown}")

    if len(dirs) == 1 and not loose:
        inner = dirs[0]
        inner_dirs = sorted(p for p in inner.iterdir() if p.is_dir())
        inner_files = [p for p in inner.iterdir() if p.is_file()]
        if inner_dirs and not inner_files:
            warnings.append(f"unwrapped top-level folder {inner.name!r}")
            return inner_dirs, warnings

    if not dirs:
        raise ExtractionError(
            "zip contains no student folders (expected one folder per student at the top level)"
        )
    return dirs, warnings
