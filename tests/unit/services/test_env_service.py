from pathlib import Path

from droiddesk.core.profiles import Environment
from droiddesk.services.env_service import EnvService


def test_env_service_load_environments(tmp_path: Path) -> None:
    dd_dir = tmp_path / ".droiddesk"
    dd_dir.mkdir()
    toml_content = """
[environments.staging]
label = "Staging"
env_file = ".env.staging"
firebase = "staging-firebase.json"
flavor = "staging"
api_host = "https://staging.api.example.com"
allow_release_build = false
require_clean_git = false

[environments.production]
label = "Production"
env_file = ".env.prod"
firebase = "prod-firebase.json"
flavor = "prod"
api_host = "https://api.example.com"
allow_release_build = true
require_clean_git = true
"""
    (dd_dir / "environments.toml").write_text(toml_content, encoding="utf-8")

    service = EnvService(project_root=tmp_path)
    envs = service.load_environments()

    assert len(envs) == 2
    staging = next(e for e in envs if e.key == "staging")
    assert staging.label == "Staging"
    assert staging.allow_release_build is False

    prod = next(e for e in envs if e.key == "production")
    assert prod.label == "Production"
    assert prod.allow_release_build is True
    assert prod.require_clean_git is True


def test_env_service_switch_to_creates_backup_and_deploys(tmp_path: Path) -> None:
    # Set up initial .env and project files
    env_curr = tmp_path / ".env"
    env_curr.write_text("CURRENT_ENV=old", encoding="utf-8")

    env_prod = tmp_path / ".env.prod"
    env_prod.write_text("CURRENT_ENV=production", encoding="utf-8")

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    fb_curr = app_dir / "google-services.json"
    fb_curr.write_text('{"project_id": "old"}', encoding="utf-8")

    fb_prod = tmp_path / "prod-firebase.json"
    fb_prod.write_text('{"project_id": "prod"}', encoding="utf-8")

    service = EnvService(project_root=tmp_path)

    prod_env = Environment(
        key="production",
        label="Production",
        env_file=".env.prod",
        firebase="prod-firebase.json",
        allow_release_build=True,
    )

    received: list[Environment | None] = []
    service.active_environment_changed.connect(received.append)

    service.switch_to(prod_env)

    # Verify active state
    assert service.active_environment() == prod_env
    assert len(received) == 1
    assert received[0] == prod_env

    # Verify backups exist
    assert (tmp_path / ".env.backup").read_text(encoding="utf-8") == "CURRENT_ENV=old"
    backup_fb = (app_dir / "google-services.json.backup").read_text(encoding="utf-8")
    assert backup_fb == '{"project_id": "old"}'

    # Verify deployed content
    assert env_curr.read_text(encoding="utf-8") == "CURRENT_ENV=production"
    assert fb_curr.read_text(encoding="utf-8") == '{"project_id": "prod"}'


def test_env_service_switch_to_rolls_back_on_failure(tmp_path: Path) -> None:
    import contextlib

    env_curr = tmp_path / ".env"
    env_curr.write_text("ORIGINAL_ENV=initial", encoding="utf-8")

    # Target env file exists, but firebase file does not exist
    env_prod = tmp_path / ".env.staging"
    env_prod.write_text("ORIGINAL_ENV=staging", encoding="utf-8")

    service = EnvService(project_root=tmp_path)

    broken_env = Environment(
        key="staging",
        label="Staging",
        env_file=".env.staging",
        firebase="non_existent_firebase.json",
    )

    with contextlib.suppress(FileNotFoundError):
        service.switch_to(broken_env)

    # Verify that .env was restored to original content
    assert env_curr.read_text(encoding="utf-8") == "ORIGINAL_ENV=initial"
    assert service.active_environment() is None


def test_env_service_dynamic_crud_and_discovery(tmp_path: Path) -> None:
    service = EnvService(project_root=tmp_path)
    # Initially empty
    assert service.load_environments() == []

    # Create dummy project files
    (tmp_path / ".env.local").write_text("FOO=BAR", encoding="utf-8")
    (tmp_path / ".env.testing").write_text("FOO=TEST", encoding="utf-8")
    (tmp_path / "google-services.json").write_text("{}", encoding="utf-8")

    discovered_envs = service.discover_project_env_files()
    assert ".env.local" in discovered_envs
    assert ".env.testing" in discovered_envs

    discovered_fb = service.discover_project_firebase_files()
    assert "google-services.json" in discovered_fb

    # Add environment dynamically
    env1 = Environment(
        key="testing",
        label="Testing",
        env_file=".env.testing",
        allow_release_build=False,
    )
    service.add_or_update_environment(env1)

    loaded = service.load_environments()
    assert len(loaded) == 1
    assert loaded[0].key == "testing"
    assert loaded[0].label == "Testing"
    assert service.active_environment() == env1

    # Update environment
    env1_updated = Environment(
        key="testing",
        label="Automated Testing",
        env_file=".env.testing",
        allow_release_build=True,
    )
    service.add_or_update_environment(env1_updated)
    loaded = service.load_environments()
    assert len(loaded) == 1
    assert loaded[0].label == "Automated Testing"
    assert loaded[0].allow_release_build is True

    # Delete environment
    deleted = service.delete_environment("testing")
    assert deleted is True
    assert service.load_environments() == []
    assert service.active_environment() is None


def test_env_service_set_active_environment(tmp_path: Path) -> None:
    service = EnvService(project_root=tmp_path)
    env = Environment(
        key="staging",
        label="Staging",
        env_file=".env.staging",
    )
    received: list[Environment | None] = []
    service.active_environment_changed.connect(received.append)

    service.set_active_environment(env)
    assert service.active_environment() == env
    assert len(received) == 1
    assert received[0] == env

