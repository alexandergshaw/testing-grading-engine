import io
import zipfile

import pytest

import grading.extract as extract
from grading.extract import ExtractionError, extract_zip, find_student_folders


def make_zip(entries: dict[str, str]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


def test_normal_multi_student_zip(tmp_path):
    src = make_zip(
        {
            "alice/main.py": "print('hi')",
            "alice/README.md": "hello",
            "bob/main.py": "print('yo')",
        }
    )
    warnings = extract_zip(src, tmp_path)
    assert warnings == []
    students, w = find_student_folders(tmp_path)
    assert [s.name for s in students] == ["alice", "bob"]
    assert (tmp_path / "alice" / "main.py").read_text() == "print('hi')"


def test_wrapper_folder_unwrap(tmp_path):
    src = make_zip({"assignment1/alice/main.py": "x", "assignment1/bob/main.py": "y"})
    extract_zip(src, tmp_path)
    students, warnings = find_student_folders(tmp_path)
    assert [s.name for s in students] == ["alice", "bob"]
    assert any("unwrapped" in w for w in warnings)


def test_loose_files_warned_and_ignored(tmp_path):
    src = make_zip({"alice/main.py": "x", "stray.txt": "loose"})
    extract_zip(src, tmp_path)
    students, warnings = find_student_folders(tmp_path)
    assert [s.name for s in students] == ["alice"]
    assert any("stray.txt" in w for w in warnings)


def test_no_student_folders(tmp_path):
    src = make_zip({"only_file.txt": "x"})
    extract_zip(src, tmp_path)
    with pytest.raises(ExtractionError, match="no student folders"):
        find_student_folders(tmp_path)


def test_macos_junk_skipped(tmp_path):
    src = make_zip({"alice/main.py": "x", "__MACOSX/alice/._main.py": "j", "alice/.DS_Store": "j"})
    extract_zip(src, tmp_path)
    assert not (tmp_path / "__MACOSX").exists()
    assert not (tmp_path / "alice" / ".DS_Store").exists()


def test_zip_slip_rejected(tmp_path):
    src = make_zip({"../evil.txt": "pwned"})
    with pytest.raises(ExtractionError, match="unsafe path"):
        extract_zip(src, tmp_path)
    assert not (tmp_path.parent / "evil.txt").exists()


def test_absolute_path_rejected(tmp_path):
    src = make_zip({"/abs/evil.txt": "pwned"})
    with pytest.raises(ExtractionError, match="unsafe path"):
        extract_zip(src, tmp_path)


def test_drive_path_rejected(tmp_path):
    src = make_zip({"C:/evil.txt": "pwned"})
    with pytest.raises(ExtractionError, match="unsafe path"):
        extract_zip(src, tmp_path)


def test_member_count_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "MAX_MEMBERS", 3)
    src = make_zip({f"s/f{i}.txt": "x" for i in range(4)})
    with pytest.raises(ExtractionError, match="entries"):
        extract_zip(src, tmp_path)


def test_uncompressed_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(extract, "MAX_UNCOMPRESSED_BYTES", 10)
    src = make_zip({"s/big.txt": "x" * 100})
    with pytest.raises(ExtractionError, match="uncompressed"):
        extract_zip(src, tmp_path)


def test_not_a_zip(tmp_path):
    with pytest.raises(ExtractionError, match="not a valid zip"):
        extract_zip(io.BytesIO(b"this is not a zip"), tmp_path)


def test_symlink_skipped(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("alice/link")
        info.external_attr = 0o120777 << 16  # symlink mode bits
        zf.writestr(info, "../../target")
        zf.writestr("alice/main.py", "x")
    buf.seek(0)
    warnings = extract_zip(buf, tmp_path)
    assert any("symlink" in w for w in warnings)
    assert not (tmp_path / "alice" / "link").exists()
