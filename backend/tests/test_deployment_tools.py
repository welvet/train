from __future__ import annotations

import ftplib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import _deployment
from _deployment import (
    DeploymentConfig,
    RuntimeTarget,
    build_bundle,
    prepare_supervisor,
    pull_configuration,
    publish_bundle,
    push_configuration,
)
from _workspace import WorkspaceError


def _runtime_target() -> RuntimeTarget:
    return _deployment._local_runtime()


def _write_workspace(root: Path) -> None:
    (root / "backend.json").write_text(json.dumps({
        "api": {"host": "127.0.0.1", "port": 8080, "url": "http://host:8080"},
        "arduino_server": {"host": "127.0.0.1", "port": 9000},
    }))
    (root / "trains.json").write_text(json.dumps({
        "trains": [{"id": "train_1", "ble_address": "AA:BB", "tag_ids": []}]
    }))
    (root / "arduinos.json").write_text(json.dumps({
        "devices": {
            "arduino_1": {
                "hub_id": "hub_1",
                "port": "/dev/test",
                "fqbn": "vendor:board:model",
                "backend_host": "host",
                "baudrate": 9600,
                "backend_port": 9000,
                "servo_settle_ms": 500,
                "reconnect_ms": 2000,
                "switches": [],
                "readers": [],
            }
        }
    }))
    (root / "automations.json").write_text(
        json.dumps({"version": 4, "signals": [], "rules": []})
    )
    (root / "deployment.json").write_text(json.dumps({
        "ftp": {
            "host": "server",
            "port": 2121,
            "username": "operator",
            "remote_dir": "/train/deploy",
            "tls": False,
        },
        "health_url": "http://server:8080",
        "target": _runtime_target().as_dict(),
    }))
    (root / "secrets.json").write_text(json.dumps({
        "devices": {
            "arduino_1": {"wifi_ssid": "wifi", "wifi_password": "wifi-secret"}
        },
        "deployment": {"ftp_password": "ftp-secret"},
    }))


def test_bundle_contains_code_without_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)

    commands: list[list[str]] = []

    def fake_build(
        command: list[str],
        *,
        check: bool,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        assert check is True
        commands.append(command)
        if command == ["npm", "ci"]:
            assert cwd is not None
            assert env is not None
            assert not any(name.startswith("NEXT_PUBLIC_") for name in env)
            assert not (cwd / ".env").exists()
            return
        if command == ["npm", "run", "build"]:
            assert cwd is not None
            output = cwd / "out"
            output.mkdir()
            (output / "index.html").write_text("<h1>Train</h1>")
            return
        option = "--wheel-dir" if "wheel" in command else "--dest"
        wheel_dir = Path(command[command.index(option) + 1])
        name = (
            "train-0.1.0-py3-none-any.whl"
            if "wheel" in command
            else "aiohttp-3.14.3-py3-none-any.whl"
        )
        with zipfile.ZipFile(
            wheel_dir / name, "w"
        ) as wheel:
            if "wheel" in command:
                source = Path(command[-1])
                static_index = source / "train/modules/web_api/static/index.html"
                assert static_index.read_text() == "<h1>Train</h1>"
                wheel.writestr(
                    "train/modules/web_api/static/index.html",
                    static_index.read_bytes(),
                )
            else:
                wheel.writestr("package/__init__.py", "")

    monkeypatch.setattr(_deployment.subprocess, "run", fake_build)
    bundle = tmp_path / "backend.tar.gz"
    target = _runtime_target()
    digest = build_bundle(workspace, bundle, target)

    assert len(digest) == 64
    with tarfile.open(bundle, "r:gz") as archive:
        names = set(archive.getnames())
        assert names == {
            "manifest.json",
            "wheels/train-0.1.0-py3-none-any.whl",
            "wheels/aiohttp-3.14.3-py3-none-any.whl",
        }
        manifest = json.load(archive.extractfile("manifest.json"))
    assert set(manifest["files"]) == names - {"manifest.json"}
    assert manifest["runtime"] == target.as_dict()
    assert commands[:2] == [["npm", "ci"], ["npm", "run", "build"]]
    with tarfile.open(bundle, "r:gz") as archive:
        backend_wheel = archive.extractfile("wheels/train-0.1.0-py3-none-any.whl")
        assert backend_wheel is not None
        with zipfile.ZipFile(io.BytesIO(backend_wheel.read())) as wheel:
            assert wheel.read("train/modules/web_api/static/index.html") == b"<h1>Train</h1>"
    download = next(command for command in commands if "download" in command)
    assert download[download.index("--platform") + 1] == target.platform.replace(
        "-", "_"
    ).replace(".", "_")
    assert download[download.index("--python-version") + 1] == target.python
    assert download[download.index("--implementation") + 1] == "cp"
    assert download[download.index("--abi") + 1] == "cp314"


class FakeFtp:
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.operations: list[tuple] = []
        self.files = files or {}

    def connect(self, *args, **kwargs) -> None:
        self.operations.append(("connect", *args))

    def login(self, *args) -> None:
        self.operations.append(("login", *args))

    def cwd(self, path: str) -> None:
        self.operations.append(("cwd", path))

    def mkd(self, path: str) -> None:
        self.operations.append(("mkd", path))

    def storbinary(self, command: str, source: io.BufferedIOBase) -> None:
        self.operations.append(("store", command, source.read()))

    def retrbinary(self, command: str, callback) -> None:
        self.operations.append(("retrieve", command))
        name = command.removeprefix("RETR ")
        try:
            contents = self.files[name]
        except KeyError as exc:
            raise ftplib.error_perm("550 missing") from exc
        callback(contents)

    def nlst(self) -> list[str]:
        self.operations.append(("list",))
        return list(self.files)

    def rename(self, source: str, destination: str) -> None:
        self.operations.append(("rename", source, destination))

    def delete(self, path: str) -> None:
        self.operations.append(("delete", path))

    def rmd(self, path: str) -> None:
        self.operations.append(("rmd", path))

    def quit(self) -> None:
        self.operations.append(("quit",))


def _deployment_config() -> DeploymentConfig:
    return DeploymentConfig(
        "server",
        2121,
        "operator",
        "secret",
        "/train/deploy",
        "http://server:8080",
        _runtime_target(),
    )


def test_pull_configuration_replaces_all_persistent_files(tmp_path: Path) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    local_secrets = (workspace / "secrets.json").read_bytes()
    remote_workspace = tmp_path / "remote"
    remote_workspace.mkdir()
    _write_workspace(remote_workspace)
    (remote_workspace / "secrets.json").write_text('{"remote": "ignored"}')
    remote_trains = json.loads((remote_workspace / "trains.json").read_text())
    remote_trains["trains"][0]["id"] = "server_train"
    remote_trains["trains"][0]["lego_hub_id"] = "server_train"
    (remote_workspace / "trains.json").write_text(json.dumps(remote_trains))
    files = {
        name: (remote_workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    }
    ftp = FakeFtp(files)

    pull_configuration(
        _deployment_config(), workspace, ftp_factory=lambda: ftp
    )

    assert {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    } == files
    assert (workspace / "secrets.json").read_bytes() == local_secrets
    assert [
        operation[1] for operation in ftp.operations if operation[0] == "retrieve"
    ] == [
        f"RETR {name}"
        for _ in range(2)
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    ]


def test_pull_configuration_does_not_replace_any_file_when_validation_fails(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    before = {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    }
    files = dict(before)
    files["trains.json"] = b"not-json"

    with pytest.raises(WorkspaceError, match="invalid JSON"):
        pull_configuration(
            _deployment_config(),
            workspace,
            ftp_factory=lambda: FakeFtp(files),
        )

    assert {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    } == before


def test_pull_configuration_does_not_require_remote_device_secrets(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    arduinos = json.loads((workspace / "arduinos.json").read_text())
    arduinos["devices"]["arduino_2"] = {
        **arduinos["devices"]["arduino_1"],
        "hub_id": "hub_2",
    }
    remote = {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    }
    remote["arduinos.json"] = json.dumps(arduinos).encode()

    pull_configuration(
        _deployment_config(),
        workspace,
        ftp_factory=lambda: FakeFtp(remote),
    )

    assert json.loads((workspace / "arduinos.json").read_text()) == arduinos


def test_pull_configuration_rolls_back_a_partial_local_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    before = {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    }
    remote = {name: value + b"\n" for name, value in before.items()}
    replace = _deployment.os.replace
    failed = False

    def fail_once(source, destination) -> None:
        nonlocal failed
        if (
            str(source).endswith(".pulling")
            and Path(destination).name == "trains.json"
            and not failed
        ):
            failed = True
            raise OSError("disk full")
        replace(source, destination)

    monkeypatch.setattr(_deployment.os, "replace", fail_once)

    with pytest.raises(OSError, match="disk full"):
        pull_configuration(
            _deployment_config(),
            workspace,
            ftp_factory=lambda: FakeFtp(remote),
        )

    assert {
        name: (workspace / name).read_bytes()
        for name in _deployment.PERSISTENT_CONFIGURATION_FILES
    } == before


def test_push_configuration_replaces_all_persistent_files_only(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    ftp = FakeFtp()

    push_configuration(
        _deployment_config(), workspace, ftp_factory=lambda: ftp
    )

    stores = [operation for operation in ftp.operations if operation[0] == "store"]
    assert len(stores) == len(_deployment.PERSISTENT_CONFIGURATION_FILES)
    for name in _deployment.PERSISTENT_CONFIGURATION_FILES:
        store = next(operation for operation in stores if name in operation[1])
        assert store[2] == (workspace / name).read_bytes()
    assert any(
        operation[0] == "rename" and operation[2] == "data"
        for operation in ftp.operations
    )
    assert all(
        "secrets.json" not in operation[1] and "deployment.json" not in operation[1]
        for operation in stores
    )


def test_push_configuration_restores_previous_folder_when_switch_fails(
    tmp_path: Path,
) -> None:
    class FailedSwitchFtp(FakeFtp):
        def rename(self, source: str, destination: str) -> None:
            super().rename(source, destination)
            if source.endswith(".uploading") and destination == "data":
                raise ftplib.error_temp("temporary failure")

    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    ftp = FailedSwitchFtp()

    with pytest.raises(RuntimeError, match="Could not push"):
        push_configuration(
            _deployment_config(), workspace, ftp_factory=lambda: ftp
        )

    renames = [operation for operation in ftp.operations if operation[0] == "rename"]
    assert renames[-1][2] == "data"
    assert renames[-1][1].endswith(".previous")


def test_push_configuration_reports_incomplete_remote_rollback(
    tmp_path: Path,
) -> None:
    class FailedRollbackFtp(FakeFtp):
        def rename(self, source: str, destination: str) -> None:
            super().rename(source, destination)
            if destination == "data":
                raise ftplib.error_temp("temporary failure")

    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)

    with pytest.raises(RuntimeError, match="could not be restored"):
        push_configuration(
            _deployment_config(),
            workspace,
            ftp_factory=FailedRollbackFtp,
        )


def test_push_configuration_validates_before_connecting(tmp_path: Path) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    (workspace / "trains.json").write_text("not-json")
    connected = False

    def ftp_factory() -> FakeFtp:
        nonlocal connected
        connected = True
        return FakeFtp()

    with pytest.raises(WorkspaceError, match="invalid JSON"):
        push_configuration(
            _deployment_config(), workspace, ftp_factory=ftp_factory
        )

    assert connected is False


def test_push_configuration_does_not_require_device_secrets(tmp_path: Path) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    secrets = json.loads((workspace / "secrets.json").read_text())
    secrets["devices"] = {}
    (workspace / "secrets.json").write_text(json.dumps(secrets))
    ftp = FakeFtp()

    push_configuration(
        _deployment_config(), workspace, ftp_factory=lambda: ftp
    )

    assert len([
        operation for operation in ftp.operations if operation[0] == "store"
    ]) == len(_deployment.PERSISTENT_CONFIGURATION_FILES)


def test_publish_updates_release_pointer_last(tmp_path: Path) -> None:
    bundle = tmp_path / "backend.tar.gz"
    bundle.write_bytes(b"release")
    digest = "a" * 64
    ftp = FakeFtp()
    config = _deployment_config()

    attempt = publish_bundle(config, bundle, digest, ftp_factory=lambda: ftp)

    renames = [operation for operation in ftp.operations if operation[0] == "rename"]
    assert renames[-1] == (
        "rename",
        f"release.{attempt}.json.uploading",
        "release.json",
    )
    archive_name = f"release-{digest}.tar.gz"
    archive_delete = ("delete", archive_name)
    assert archive_delete in ftp.operations
    assert (
        "rename",
        f"{archive_name}.{attempt}.uploading",
        archive_name,
    ) in renames
    assert ftp.operations.index(archive_delete) < ftp.operations.index(
        ("rename", f"{archive_name}.{attempt}.uploading", archive_name)
    )
    pointer = next(
        operation[2]
        for operation in ftp.operations
        if operation[:2] == ("store", f"STOR release.{attempt}.json.uploading")
    )
    assert json.loads(pointer) == {"release": digest, "attempt": attempt}


def test_prepare_supervisor_requires_running_current_protocol() -> None:
    ftp = FakeFtp()

    with pytest.raises(RuntimeError, match="Restart server-loop"):
        prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)

    assert any(
        operation[0] == "rename" and operation[2] == "server-loop"
        for operation in ftp.operations
    )


def test_prepare_supervisor_accepts_running_current_protocol() -> None:
    ftp = FakeFtp({
        "supervisor.json": json.dumps({
            "protocol": _deployment.SUPERVISOR_PROTOCOL
        }).encode()
    })

    prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)


def test_prepare_supervisor_does_not_downgrade_newer_protocol() -> None:
    ftp = FakeFtp({
        "supervisor.json": json.dumps({
            "protocol": _deployment.SUPERVISOR_PROTOCOL + 1,
            "capabilities": ["future"],
        }).encode()
    })

    prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)

    assert not any(operation[0] == "store" for operation in ftp.operations)


@pytest.mark.parametrize(
    "state",
    [b"not-json", b"[]", b'{"protocol": true}', b'{"protocol": 0}'],
)
def test_prepare_supervisor_does_not_overwrite_invalid_state(state: bytes) -> None:
    ftp = FakeFtp({"supervisor.json": state})

    with pytest.raises(RuntimeError, match="invalid state"):
        prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)

    assert not any(operation[0] == "store" for operation in ftp.operations)


def test_prepare_supervisor_does_not_overwrite_after_read_failure() -> None:
    class ReadFailureFtp(FakeFtp):
        def retrbinary(self, command: str, callback) -> None:
            raise ftplib.error_temp("temporary failure")

    ftp = ReadFailureFtp({"supervisor.json": b"unreadable"})

    with pytest.raises(RuntimeError, match="Could not inspect"):
        prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)

    assert not any(operation[0] == "store" for operation in ftp.operations)


def test_prepare_supervisor_does_not_treat_permission_denied_as_missing() -> None:
    class PermissionDeniedFtp(FakeFtp):
        def retrbinary(self, command: str, callback) -> None:
            raise ftplib.error_perm("550 Permission denied")

    ftp = PermissionDeniedFtp({"supervisor.json": b"unreadable"})

    with pytest.raises(RuntimeError, match="Could not inspect"):
        prepare_supervisor(_deployment_config(), ftp_factory=lambda: ftp)

    assert not any(operation[0] == "store" for operation in ftp.operations)


def test_pip_target_args_support_a_different_macos_version() -> None:
    actual = _runtime_target()
    server = RuntimeTarget(
        actual.system,
        actual.machine,
        actual.implementation,
        actual.python,
        "macosx-13.0-arm64",
        actual.soabi,
    )

    assert _deployment._pip_target_args(server) == [
        "--platform",
        "macosx_13_0_arm64",
        "--python-version",
        "3.14",
        "--implementation",
        "cp",
        "--abi",
        "cp314",
    ]


def test_failed_ftp_connection_is_closed() -> None:
    class BrokenFtp(FakeFtp):
        def connect(self, *args, **kwargs) -> None:
            raise OSError("offline")

        def close(self) -> None:
            self.operations.append(("close",))

    ftp = BrokenFtp()
    config = DeploymentConfig(
        "server",
        2121,
        "operator",
        "secret",
        "/train/deploy",
        "http://server:8080",
        _runtime_target(),
    )

    with pytest.raises(OSError, match="offline"):
        _deployment._connect(config, lambda: ftp)

    assert ftp.operations == [("close",)]
