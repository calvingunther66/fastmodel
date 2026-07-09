"""L1: backup zips the data dir and restore round-trips it; path traversal is rejected."""

import io
import zipfile

import pytest

from server.backup import make_backup, restore_backup


def test_backup_restore_roundtrip(tmp_path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "users.json").write_text('{"users": []}')
    (src / "schedule.json").write_text('{"people": []}')
    (src / "inbox").mkdir()
    (src / "inbox" / "big.xlsx").write_bytes(b"x" * 1000)  # should be excluded

    data = make_backup(src)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert "users.json" in names and "schedule.json" in names
    assert not any(n.startswith("inbox/") for n in names)  # inbox excluded

    dest = tmp_path / "restored"
    dest.mkdir()
    result = restore_backup(dest, data)
    assert result["restored"] == 2
    assert (dest / "users.json").read_text() == '{"users": []}'


def test_restore_rejects_bad_zip(tmp_path):
    with pytest.raises(ValueError):
        restore_backup(tmp_path, b"not a zip")


def test_restore_rejects_path_traversal(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.json", "{}")
    with pytest.raises(ValueError):
        restore_backup(tmp_path, buf.getvalue())
