from datetime import UTC, datetime
from pathlib import Path

from droiddesk.core.models import ApkInfo, BuildRecord, Device, Project
from droiddesk.infra.db import Repository


def test_repository_apk_crud(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    repo = Repository(db_file)

    apk_file = tmp_path / "app1.apk"
    apk_file.write_bytes(b"content1")

    info1 = ApkInfo(
        file_path=apk_file,
        file_hash="hash_abc1",
        package_name="com.example.app1",
        version_name="1.0.0",
        version_code=1,
        target_sdk=34,
        min_sdk=24,
        size_bytes=len(b"content1"),
    )

    # 1. Save APK
    repo.save_apk(info1)

    # 2. List APKs
    apks = repo.list_apks()
    assert len(apks) == 1
    assert apks[0].file_hash == "hash_abc1"
    assert apks[0].package_name == "com.example.app1"
    assert apks[0].version_name == "1.0.0"
    assert apks[0].version_code == 1
    assert apks[0].target_sdk == 34
    assert apks[0].min_sdk == 24
    assert apks[0].size_bytes == 8

    # 3. Get APK by hash
    fetched = repo.get_apk_by_hash("hash_abc1")
    assert fetched is not None
    assert fetched.file_hash == "hash_abc1"
    assert fetched.file_path == apk_file

    missing = repo.get_apk_by_hash("nonexistent")
    assert missing is None

    # 4. Save second APK
    apk_file2 = tmp_path / "app2.apk"
    apk_file2.write_bytes(b"content2")
    info2 = ApkInfo(
        file_path=apk_file2,
        file_hash="hash_def2",
        package_name="com.example.app2",
        version_name="2.0.0",
        version_code=2,
    )
    repo.save_apk(info2)

    apks_updated = repo.list_apks()
    assert len(apks_updated) == 2
    hashes = [a.file_hash for a in apks_updated]
    assert "hash_abc1" in hashes
    assert "hash_def2" in hashes

    # 5. Delete APK
    deleted = repo.delete_apk("hash_abc1")
    assert deleted is True

    assert repo.get_apk_by_hash("hash_abc1") is None
    remaining = repo.list_apks()
    assert len(remaining) == 1
    assert remaining[0].file_hash == "hash_def2"

    # Deleting nonexistent returns False
    assert repo.delete_apk("hash_abc1") is False

    repo.close()


def test_repository_device_history(tmp_path: Path) -> None:
    db_file = tmp_path / "test_devices.db"
    repo = Repository(db_file)

    device1 = Device(
        serial="emulator-5554",
        state="device",
        model="Pixel 7 Pro",
        android_version="14",
        api_level=34,
        abi="x86_64",
    )
    repo.record_device(device1)

    history = repo.list_device_history()
    assert len(history) == 1
    assert history[0]["serial"] == "emulator-5554"
    assert history[0]["model"] == "Pixel 7 Pro"
    assert history[0]["android_version"] == "14"
    assert history[0]["api_level"] == 34

    # Update same device
    device1_updated = Device(
        serial="emulator-5554",
        state="device",
        model="Pixel 7 Pro Updated",
    )
    repo.record_device(device1_updated)
    history2 = repo.list_device_history()
    assert len(history2) == 1
    assert history2[0]["model"] == "Pixel 7 Pro Updated"

    # Add second device
    device2 = Device(serial="DEVICE_USB_1", state="device", model="Galaxy S24")
    repo.record_device(device2)
    history3 = repo.list_device_history()
    assert len(history3) == 2

    repo.close()


def test_repository_project_and_build_record(tmp_path: Path) -> None:
    db_file = tmp_path / "test_records.db"
    repo = Repository(db_file)

    proj_dir = tmp_path / "my_android_proj"
    proj_dir.mkdir()

    # 1. Project saving and retrieval
    assert repo.get_project_by_root(proj_dir) is None

    proj = Project(
        name="My Android Project",
        root_path=proj_dir,
        package_name="com.example.android",
    )
    proj_id = repo.save_project(proj)
    assert proj_id > 0

    fetched = repo.get_project_by_root(proj_dir)
    assert fetched is not None
    assert fetched.id == proj_id
    assert fetched.name == "My Android Project"
    assert fetched.package_name == "com.example.android"

    # 2. Build record saving
    now = datetime.now(UTC)
    record = BuildRecord(
        project_id=proj_id,
        command="./gradlew assembleRelease",
        environment="production",
        started_at=now,
        gate_score=85,
        gate_verdict="GO",
        overridden=False,
        exit_code=0,
    )
    rec_id = repo.save_build_record(record)
    assert rec_id > 0

    repo.close()


def test_repository_multithreaded_access(tmp_path: Path) -> None:
    import concurrent.futures

    db_file = tmp_path / "test_threaded.db"
    repo = Repository(db_file)

    proj_dir = tmp_path / "concurrent_proj"
    proj_dir.mkdir()
    proj = Project(name="Concurrent", root_path=proj_dir, package_name="com.test.concurrent")
    repo.save_project(proj)

    def worker(worker_id: int) -> bool:
        # Cross-thread read and write
        fetched = repo.get_project_by_root(proj_dir)
        if fetched is None or fetched.package_name != "com.test.concurrent":
            return False
        apk = ApkInfo(
            file_path=tmp_path / f"app_{worker_id}.apk",
            file_hash=f"hash_{worker_id}",
            package_name=f"com.test.app{worker_id}",
            version_name="1.0.0",
            version_code=worker_id,
        )
        repo.save_apk(apk)
        found = repo.get_apk_by_hash(f"hash_{worker_id}")
        return found is not None

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in futures]

    assert all(results)
    assert len(repo.list_apks()) == 20
    repo.close()
