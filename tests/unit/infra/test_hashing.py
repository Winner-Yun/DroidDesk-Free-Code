from pathlib import Path

from droiddesk.infra.hashing import find_duplicates, hash_file


def test_hash_file_is_deterministic(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    assert hash_file(f) == hash_file(f)


def test_find_duplicates_groups_identical_content(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    c = tmp_path / "c.txt"
    a.write_bytes(b"same content")
    b.write_bytes(b"same content")
    c.write_bytes(b"different content, different size")

    duplicates = find_duplicates([a, b, c])

    assert len(duplicates) == 1
    (group,) = duplicates.values()
    assert {a, b} == set(group)


def test_find_duplicates_ignores_unique_files(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(b"one")
    b.write_bytes(b"two-two")

    assert find_duplicates([a, b]) == {}
