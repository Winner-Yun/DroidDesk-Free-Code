"""Unit tests for EmulatorManager error parsing and lock management."""

from pathlib import Path

from droiddesk.android.emulator_manager import clean_stale_locks, parse_emulator_error


def test_parse_emulator_multi_instance_error() -> None:
    raw_output = """
INFO         | Android emulator version 35.3.11.0 (build_id 12836668) (CL:N/A)
INFO         | Graphics backend: gfxstream
INFO         | Found systemPath C:\\Android\\sdk\\system-images\\android-35\\
ERROR        | Running multiple emulators with the same AVD 
ERROR        | is an experimental feature.
ERROR        | Please use -read-only flag to enable this feature.
"""
    title, details = parse_emulator_error(raw_output, exit_code=1)
    assert "Another emulator instance is already running" in title
    assert "Release Locks" in details
    assert "lock files" in details


def test_parse_emulator_disk_space_error() -> None:
    raw_output = "INFO | Checking: hasSufficientDiskSpace\nERROR | Failed: Disk space requirements"
    title, details = parse_emulator_error(raw_output, exit_code=1)
    assert "Insufficient disk space" in title
    assert "Free up disk space" in details


def test_clean_stale_locks(tmp_path: Path) -> None:
    avd_dir = tmp_path / "Pixel_8.avd"
    avd_dir.mkdir()

    # Create stale lock files
    lock1 = avd_dir / "multiinstance.lock"
    lock1.write_bytes(b"")
    lock2 = avd_dir / "hardware-qemu.ini.lock"
    lock2.write_bytes(b"")
    other_file = avd_dir / "config.ini"
    other_file.write_text("hw.ramSize=4096")

    assert lock1.exists()
    assert lock2.exists()

    removed = clean_stale_locks(avd_dir)
    assert "multiinstance.lock" in removed
    assert "hardware-qemu.ini.lock" in removed
    assert not lock1.exists()
    assert not lock2.exists()
    assert other_file.exists()  # Config must not be touched
