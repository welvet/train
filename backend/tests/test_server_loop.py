from __future__ import annotations

import io
import importlib.machinery
import importlib.util
import tarfile
import json
import platform
import sys
import sysconfig
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
