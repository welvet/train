from __future__ import annotations

import io
import json
import sys
import tarfile
import urllib.error
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
    publish_bundle,
    synchronize_configuration,
)


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
        json.dumps({"version": 1, "rules": []})
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


def test_bundle_contains_wheel_and_runtime_data_only(
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
            "data/backend.json",
            "data/trains.json",
            "data/arduinos.json",
            "data/automations.json",
            "data/automation.py",
        }
        manifest = json.load(archive.extractfile("manifest.json"))
    assert set(manifest["files"]) == names - {"manifest.json"}
    assert manifest["runtime"] == target.as_dict()
    with tarfile.open(bundle, "r:gz") as archive:
        legacy_automation = archive.extractfile("data/automation.py")
        assert legacy_automation is not None
        assert legacy_automation.read() == b""
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
    def __init__(self) -> None:
        self.operations: list[tuple] = []

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

    def rename(self, source: str, destination: str) -> None:
        self.operations.append(("rename", source, destination))

    def delete(self, path: str) -> None:
        self.operations.append(("delete", path))

    def quit(self) -> None:
        self.operations.append(("quit",))


class FakeHttpResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()


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


def _configuration_snapshot(modified_at: float, train_id: str) -> dict:
    return {
        "version": 1,
        "documents": {
            "trains": {
                "modified_at": modified_at,
                "restart_required": True,
                "value": {
                    "trains": [
                        {
                            "id": train_id,
                            "lego_hub_id": train_id,
                            "ble_address": "AA:BB",
                            "tag_ids": [],
                        }
                    ]
                },
            }
        },
    }


def test_configuration_sync_downloads_newer_backend_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    trains = workspace / "trains.json"
    trains.write_text(json.dumps({
        "trains": [
            {
                "id": "local",
                "lego_hub_id": "local",
                "ble_address": "CC:DD",
                "tag_ids": [],
            }
        ]
    }))
    trains.touch()
    local_modified_at = trains.stat().st_mtime
    remote = _configuration_snapshot(local_modified_at + 10, "remote")
    monkeypatch.setattr(
        _deployment.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHttpResponse(json.dumps(remote).encode()),
    )

    result = synchronize_configuration(_deployment_config(), workspace)

    assert result == "downloaded"
    assert json.loads(trains.read_text()) == remote["documents"]["trains"]["value"]
    assert trains.stat().st_mtime == pytest.approx(local_modified_at + 10)


def test_configuration_sync_uploads_newer_local_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    trains = workspace / "trains.json"
    local_modified_at = trains.stat().st_mtime
    remote = _configuration_snapshot(local_modified_at - 10, "remote")
    requests: list[object] = []

    def urlopen(request, timeout):
        requests.append(request)
        if request.get_method() == "GET":
            return FakeHttpResponse(json.dumps(remote).encode())
        return FakeHttpResponse(json.dumps(
            _configuration_snapshot(local_modified_at, "train_1")
        ).encode())

    monkeypatch.setattr(_deployment.urllib.request, "urlopen", urlopen)

    result = synchronize_configuration(_deployment_config(), workspace)

    assert result == "uploaded"
    assert [request.get_method() for request in requests] == ["GET", "PUT"]
    payload = json.loads(requests[1].data)
    assert payload["documents"]["trains"]["base_modified_at"] == pytest.approx(
        local_modified_at - 10
    )
    assert payload["documents"]["trains"]["value"] == {
        "trains": [{"id": "train_1", "ble_address": "AA:BB", "tag_ids": []}]
    }
    assert json.loads(trains.read_text()) == (
        _configuration_snapshot(local_modified_at, "train_1")["documents"]
        ["trains"]["value"]
    )


def test_configuration_sync_retries_when_local_file_changes_during_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    trains = workspace / "trains.json"
    initial_modified_at = trains.stat().st_mtime
    remote = _configuration_snapshot(initial_modified_at + 10, "remote")
    newest = _configuration_snapshot(initial_modified_at + 20, "newest")
    get_count = 0

    def urlopen(request, timeout):
        nonlocal get_count
        if request.get_method() == "GET":
            get_count += 1
            if get_count == 1:
                _deployment._atomic_write_json(
                    trains,
                    newest["documents"]["trains"]["value"],
                    initial_modified_at + 20,
                )
            return FakeHttpResponse(json.dumps(remote).encode())
        return FakeHttpResponse(json.dumps(newest).encode())

    monkeypatch.setattr(_deployment.urllib.request, "urlopen", urlopen)

    result = synchronize_configuration(_deployment_config(), workspace)

    assert result == "uploaded"
    assert get_count == 2
    assert json.loads(trains.read_text()) == newest["documents"]["trains"]["value"]


def test_configuration_sync_ignores_timestamp_when_contents_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    trains = workspace / "trains.json"
    local = json.loads(trains.read_text())
    remote = {
        "version": 1,
        "documents": {
            "trains": {
                "modified_at": trains.stat().st_mtime + 10,
                "restart_required": True,
                "value": local,
            }
        },
    }
    monkeypatch.setattr(
        _deployment.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHttpResponse(json.dumps(remote).encode()),
    )

    assert synchronize_configuration(_deployment_config(), workspace) == "unchanged"


@pytest.mark.parametrize("modified_at", [0, float("nan"), float("inf")])
def test_configuration_sync_rejects_invalid_backend_timestamp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    modified_at: float,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    remote = _configuration_snapshot(modified_at, "remote")
    monkeypatch.setattr(
        _deployment.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHttpResponse(json.dumps(remote).encode()),
    )

    with pytest.raises(RuntimeError, match="invalid trains configuration"):
        synchronize_configuration(_deployment_config(), workspace)


def test_configuration_sync_rejects_malformed_success_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)
    monkeypatch.setattr(
        _deployment.urllib.request,
        "urlopen",
        lambda request, timeout: FakeHttpResponse(b"not-json"),
    )

    with pytest.raises(RuntimeError, match="backend returned invalid JSON"):
        synchronize_configuration(_deployment_config(), workspace)


def test_configuration_sync_fails_when_backend_is_unreachable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "data"
    workspace.mkdir()
    _write_workspace(workspace)

    def fail(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(_deployment.urllib.request, "urlopen", fail)

    with pytest.raises(RuntimeError, match="backend is unreachable"):
        synchronize_configuration(_deployment_config(), workspace)


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
    assert (
        "rename",
        f"server-loop.{attempt}.uploading",
        "server-loop",
    ) in renames
    pointer = next(
        operation[2]
        for operation in ftp.operations
        if operation[:2] == ("store", f"STOR release.{attempt}.json.uploading")
    )
    assert json.loads(pointer) == {"release": digest, "attempt": attempt}


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
