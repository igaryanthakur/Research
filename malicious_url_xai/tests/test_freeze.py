import pytest

from src.freeze import check_frozen, freeze_path, write_freeze


@pytest.fixture
def frozen(tmp_path):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "model.bin").write_bytes(b"weights")
    (tmp_path / "notes.txt").write_text("hello")
    write_freeze("vt", ["artifacts/model.bin", "notes.txt"], root=tmp_path, policy="test")
    return tmp_path


def test_unchanged_files_pass(frozen):
    manifest = check_frozen("vt", root=frozen)
    assert set(manifest["sha256"]) == {"artifacts/model.bin", "notes.txt"}
    assert manifest["policy"] == "test"


def test_changed_file_fails(frozen):
    (frozen / "notes.txt").write_text("hello!")
    with pytest.raises(SystemExit, match="changed"):
        check_frozen("vt", root=frozen)


def test_missing_file_fails(frozen):
    (frozen / "artifacts" / "model.bin").unlink()
    with pytest.raises(SystemExit, match="missing"):
        check_frozen("vt", root=frozen)


def test_refuses_to_overwrite(frozen):
    with pytest.raises(SystemExit, match="already frozen"):
        write_freeze("vt", ["notes.txt"], root=frozen)
    assert freeze_path("vt", frozen).exists()


def test_unfrozen_version_fails(tmp_path):
    with pytest.raises(SystemExit, match="not been frozen"):
        check_frozen("nope", root=tmp_path)
