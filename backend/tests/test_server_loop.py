from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import io
import json
import platform
import sys
import sysconfig
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"


def _load_tool(name: str) -> ModuleType:
    path = TOOLS / name
    loader = importlib.machinery.SourceFileLoader(f"test_tool_{name}", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_safe_extract_rejects_parent_traversal(tmp_path: Path) -> None:
    server_loop = _load_tool("server-loop")
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"escape"
        member = tarfile.TarInfo("../escape")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(server_loop.ReleaseError, match="unsafe archive path"):
            server_loop._safe_extract(archive, tmp_path / "release")


def test_invalid_release_request_is_ignored(tmp_path: Path) -> None:
    server_loop = _load_tool("server-loop")
    root = tmp_path / "server"
    (root / "deploy").mkdir(parents=True)
    pointer = root / "deploy" / "release.json"
    pointer.write_text('{"release": "not-a-checksum", "attempt": "bad"}\n')

    loop = server_loop.ServerLoop(root)

    assert loop._read_request(pointer) is None


def test_new_attempt_can_retry_the_same_release(tmp_path: Path) -> None:
    server_loop = _load_tool("server-loop")
    root = tmp_path / "server"
    (root / "deploy").mkdir(parents=True)
    digest = "a" * 64
    pointer = root / "deploy" / "release.json"
    pointer.write_text(json.dumps({"release": digest, "attempt": "b" * 32}))
    loop = server_loop.ServerLoop(root)
    loop.failed_attempt = "c" * 32

    assert loop._read_request(pointer) == (digest, "b" * 32)


def test_runtime_manifest_must_match_server() -> None:
    server_loop = _load_tool("server-loop")
    runtime = {
        "system": platform.system(),
        "machine": platform.machine(),
        "implementation": platform.python_implementation().lower(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sysconfig.get_platform(),
        "soabi": str(sysconfig.get_config_var("SOABI")),
    }
    server_loop._verify_runtime(runtime)
    runtime["machine"] = "wrong-machine"

    with pytest.raises(server_loop.ReleaseError, match="does not match server"):
        server_loop._verify_runtime(runtime)


def test_release_without_automations_uses_compatible_empty_default(
    tmp_path: Path,
) -> None:
    server_loop = _load_tool("server-loop")
    release = tmp_path / "release"
    files = {
        "data/backend.json": b"{}",
        "data/trains.json": b"{}",
        "data/arduinos.json": b"{}",
        "wheels/train-0.1.0-py3-none-any.whl": b"wheel",
    }
    for name, contents in files.items():
        path = release / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
    manifest = {
        "format": 1,
        "runtime": {
            "system": platform.system(),
            "machine": platform.machine(),
            "implementation": platform.python_implementation().lower(),
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": sysconfig.get_platform(),
            "soabi": str(sysconfig.get_config_var("SOABI")),
        },
        "components": {
            "backend": {"wheelhouse": "wheels", "package": "train"},
            "data": {"path": "data"},
        },
        "files": {
            name: hashlib.sha256(contents).hexdigest()
            for name, contents in files.items()
        },
    }
    (release / "manifest.json").write_text(json.dumps(manifest))

    server_loop._verify_manifest(release)
    destination = tmp_path / "persistent" / "automations.json"
    server_loop.ServerLoop._seed_automations(
        release / "data" / "automations.json", destination
    )

    assert json.loads(destination.read_text()) == {"version": 1, "rules": []}


def test_remove_tree_does_not_follow_directory_symlinks(tmp_path: Path) -> None:
    server_loop = _load_tool("server-loop")
    target = tmp_path / "target"
    target.mkdir()
    protected = target / "keep.txt"
    protected.write_text("keep")
    link = tmp_path / "release"
    link.symlink_to(target, target_is_directory=True)

    server_loop._remove_tree(link)

    assert not link.exists()
    assert protected.read_text() == "keep"


def test_automation_seed_is_persistent_across_releases(tmp_path: Path) -> None:
    server_loop = _load_tool("server-loop")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    destination = tmp_path / "data" / "automations.json"
    first.write_text('{"version": 1, "rules": []}')
    second.write_text('{"version": 1, "rules": [{"id": "new"}]}')

    server_loop.ServerLoop._seed_automations(first, destination)
    server_loop.ServerLoop._seed_automations(second, destination)

    assert destination.read_text() == first.read_text()


def test_failed_automation_seed_does_not_leave_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server_loop = _load_tool("server-loop")
    source = tmp_path / "source.json"
    destination = tmp_path / "data" / "automations.json"
    source.write_text('{"version": 1, "rules": []}')

    def fail_read(path: Path) -> bytes:
        raise OSError("read failed")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    with pytest.raises(OSError, match="read failed"):
        server_loop.ServerLoop._seed_automations(source, destination)

    assert not destination.exists()
