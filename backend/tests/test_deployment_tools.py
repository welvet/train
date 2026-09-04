from __future__ import annotations

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
from _deployment import DeploymentConfig, RuntimeTarget, build_bundle, publish_bundle


def _runtime_target() -> RuntimeTarget:
    return _deployment._local_runtime()


def _write_workspace(root: Path) -> None:
    (root / "backend.json").write_text(json.dumps({
        "api": {"host": "127.0.0.1", "port": 8080, "url": "http://host:8080"},
        "arduino_server": {"host": "127.0.0.1", "port": 9000},
    }))
    (root / "trains.json").write_text(json.dumps({
        "trains": [{"id": "train_1", "ble_address": "AA:BB", "tag_id": ""}]
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
    (root / "automation.py").write_text(
        "def configure(ctx):\n    pass\n\nasync def run(ctx):\n    await ctx.forever()\n"
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

    def fake_build(command: list[str], *, check: bool) -> None:
        assert check is True
        commands.append(command)
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
            "data/automation.py",
        }
        manifest = json.load(archive.extractfile("manifest.json"))
    assert set(manifest["files"]) == names - {"manifest.json"}
    assert manifest["runtime"] == target.as_dict()
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


def test_publish_updates_release_pointer_last(tmp_path: Path) -> None:
    bundle = tmp_path / "backend.tar.gz"
    bundle.write_bytes(b"release")
    digest = "a" * 64
    ftp = FakeFtp()
    config = DeploymentConfig(
        "server",
        2121,
        "operator",
        "secret",
        "/train/deploy",
        "http://server:8080",
        _runtime_target(),
    )

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
