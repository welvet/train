from __future__ import annotations

import ftplib
import gzip
import hashlib
import io
import json
import math
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from _workspace import REPO_ROOT, WorkspaceError, data_dir, read_json, validate_workspace

RUNTIME_DATA_FILES = (
    "backend.json",
    "trains.json",
    "arduinos.json",
    "automations.json",
)
LEGACY_AUTOMATION_FILE = "automation.py"
WEB_BUILD_INPUTS = (
    "app",
    "public",
    "src",
    "eslint.config.mjs",
    "next.config.ts",
    "package-lock.json",
    "package.json",
    "tsconfig.json",
)


@dataclass(frozen=True, slots=True)
class DeploymentConfig:
    host: str
    port: int
    username: str
    password: str
    remote_dir: str
    health_url: str
    target: RuntimeTarget
    tls: bool = False
    ca_file: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeTarget:
    system: str
    machine: str
    implementation: str
    python: str
    platform: str
    soabi: str

    def as_dict(self) -> dict[str, str]:
        return {
            "system": self.system,
            "machine": self.machine,
            "implementation": self.implementation,
            "python": self.python,
            "platform": self.platform,
            "soabi": self.soabi,
        }


@dataclass(frozen=True, slots=True)
class SyncedDocument:
    modified_at: float
    value: dict[str, object]


def load_deployment(root: Path | None = None) -> DeploymentConfig:
    workspace = root or data_dir()
    document = read_json("deployment.json", workspace)
    deployment = document.get("ftp")
    if not isinstance(deployment, dict):
        raise WorkspaceError("deployment.json: 'ftp' must be an object")
    secrets = read_json("secrets.json", workspace).get("deployment")
    if not isinstance(secrets, dict):
        raise WorkspaceError("secrets.json: 'deployment' must be an object")

    host = _required_string(deployment, "host", "deployment.json:ftp")
    username = _required_string(deployment, "username", "deployment.json:ftp")
    remote_dir = _required_string(deployment, "remote_dir", "deployment.json:ftp")
    health_url = _required_string(document, "health_url", "deployment.json")
    password = _required_string(secrets, "ftp_password", "secrets.json:deployment")
    port = deployment.get("port", 21)
    tls = deployment.get("tls", False)
    ca_file = deployment.get("ca_file")
    target_value = document.get("target")
    if not isinstance(target_value, dict):
        raise WorkspaceError("deployment.json: 'target' must be an object")
    target = RuntimeTarget(
        system=_required_string(target_value, "system", "deployment.json:target"),
        machine=_required_string(target_value, "machine", "deployment.json:target"),
        implementation=_required_string(
            target_value, "implementation", "deployment.json:target"
        ).lower(),
        python=_required_string(target_value, "python", "deployment.json:target"),
        platform=_required_string(target_value, "platform", "deployment.json:target"),
        soabi=_required_string(target_value, "soabi", "deployment.json:target"),
    )
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise WorkspaceError("deployment.json:ftp.port must be in 1..65535")
    if not isinstance(tls, bool):
        raise WorkspaceError("deployment.json:ftp.tls must be a boolean")
    if ca_file is not None and (not isinstance(ca_file, str) or not ca_file.strip()):
        raise WorkspaceError("deployment.json:ftp.ca_file must be a non-empty path")
    if ca_file is not None and not tls:
        raise WorkspaceError("deployment.json:ftp.ca_file requires tls=true")
    if not remote_dir.startswith("/"):
        raise WorkspaceError("deployment.json:ftp.remote_dir must be absolute")
    return DeploymentConfig(
        host,
        port,
        username,
        password,
        remote_dir.rstrip("/"),
        health_url,
        target,
        tls,
        ca_file.strip() if ca_file is not None else None,
    )


def synchronize_configuration(
    config: DeploymentConfig,
    workspace: Path,
) -> str:
    """Synchronize editable configuration with the running backend."""
    local_path = workspace / "trains.json"
    endpoint = config.health_url.rstrip("/") + "/api/configuration"
    for _ in range(3):
        local = _local_trains_document(local_path, workspace)
        remote = _fetch_configuration(endpoint)
        if remote is None:
            return "unavailable"
        if local != _local_trains_document(local_path, workspace):
            continue
        if remote.value == local.value:
            return "unchanged"
        if remote.modified_at > local.modified_at:
            if local != _local_trains_document(local_path, workspace):
                continue
            _atomic_write_json(
                local_path,
                remote.value,
                remote.modified_at,
            )
            return "downloaded"
        if remote.modified_at == local.modified_at:
            raise RuntimeError(
                "Configuration sync found different trains.json documents with the "
                "same timestamp; touch the intended winner and retry"
            )

        uploaded = _upload_configuration(endpoint, local, remote.modified_at)
        if uploaded is None or local != _local_trains_document(local_path, workspace):
            continue
        _atomic_write_json(
            local_path,
            uploaded.value,
            uploaded.modified_at,
        )
        return "uploaded"
    raise RuntimeError(
        "Configuration changed repeatedly during synchronization; retry when edits stop"
    )


def _local_trains_document(path: Path, workspace: Path) -> SyncedDocument:
    for _ in range(3):
        before = path.stat()
        value = read_json("trains.json", workspace)
        after = path.stat()
        if _file_identity(before) == _file_identity(after):
            return SyncedDocument(after.st_mtime_ns / 1_000_000_000, value)
    raise RuntimeError(
        "Local trains.json changed repeatedly while being read; retry when edits stop"
    )


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _fetch_configuration(endpoint: str) -> SyncedDocument | None:
    try:
        request = urllib.request.Request(
            endpoint,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            contents = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(
            f"Configuration sync failed: backend returned HTTP {exc.code}"
        ) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(
            "Configuration sync failed: backend is unreachable"
        ) from exc
    try:
        remote = json.loads(contents)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Configuration sync failed: backend returned invalid JSON"
        ) from exc
    return _configuration_trains_document(remote)


def _upload_configuration(
    endpoint: str,
    local: SyncedDocument,
    base_modified_at: float,
) -> SyncedDocument | None:
    payload = {
        "version": 1,
        "documents": {
            "trains": {
                "base_modified_at": base_modified_at,
                "modified_at": local.modified_at,
                "value": local.value,
            }
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=(json.dumps(payload) + "\n").encode(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return _configuration_trains_document(json.loads(response.read()))
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            return None
        try:
            detail = json.loads(exc.read()).get("error")
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
            detail = None
        message = detail if isinstance(detail, str) else f"HTTP {exc.code}"
        raise RuntimeError(f"Configuration upload failed: {message}") from exc
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as exc:
        raise RuntimeError("Configuration upload failed") from exc


def _configuration_trains_document(value: object) -> SyncedDocument:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise RuntimeError("Backend returned an unsupported configuration format")
    documents = value.get("documents")
    trains = documents.get("trains") if isinstance(documents, dict) else None
    if not isinstance(trains, dict):
        raise RuntimeError("Backend configuration is missing trains")
    modified_at = trains.get("modified_at")
    document = trains.get("value")
    if (
        not isinstance(modified_at, (int, float))
        or isinstance(modified_at, bool)
        or not math.isfinite(modified_at)
        or modified_at <= 0
        or not isinstance(document, dict)
    ):
        raise RuntimeError("Backend returned an invalid trains configuration")
    return SyncedDocument(float(modified_at), document)


def _atomic_write_json(path: Path, value: object, modified_at: float) -> None:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.utime(staged, ns=(int(modified_at * 1_000_000_000),) * 2)
        os.replace(staged, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        staged.unlink(missing_ok=True)


def build_bundle(workspace: Path, destination: Path, target: RuntimeTarget) -> str:
    validate_workspace(workspace)
    with tempfile.TemporaryDirectory(prefix="train-release-build-") as directory:
        build_dir = Path(directory)
        web_source = build_dir / "web-source"
        web_source.mkdir()
        for name in WEB_BUILD_INPUTS:
            source = REPO_ROOT / "web" / name
            destination_path = web_source / name
            if source.is_dir():
                shutil.copytree(source, destination_path)
            elif source.is_file():
                shutil.copy2(source, destination_path)
        build_environment = {
            name: value
            for name, value in os.environ.items()
            if not name.startswith("NEXT_PUBLIC_")
        }
        subprocess.run(
            ["npm", "ci"], cwd=web_source, env=build_environment, check=True
        )
        subprocess.run(
            ["npm", "run", "build"],
            cwd=web_source,
            env=build_environment,
            check=True,
        )
        web_output = web_source / "out"
        if not (web_output / "index.html").is_file():
            raise RuntimeError("Frontend build did not produce web/out/index.html")

        wheel_dir = build_dir / "wheels"
        wheel_dir.mkdir()
        source_dir = build_dir / "backend-source"
        shutil.copytree(
            REPO_ROOT / "backend",
            source_dir,
            ignore=shutil.ignore_patterns(
                ".venv", "build", ".pytest_cache", "*.egg-info", "__pycache__", "tests"
            ),
        )
        shutil.copytree(
            web_output,
            source_dir / "train" / "modules" / "web_api" / "static",
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(wheel_dir),
                str(source_dir),
            ],
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                *_pip_target_args(target),
                "--dest",
                str(wheel_dir),
                "--requirement",
                str(_requirements_lock(target)),
            ],
            check=True,
        )
        wheels = sorted(wheel_dir.glob("*.whl"))
        backend_wheels = [path for path in wheels if path.name.startswith("train-")]
        if not backend_wheels:
            raise RuntimeError("Backend wheel build did not produce the train package")
        if any(
            not path.name.endswith("-py3-none-any.whl") for path in backend_wheels
        ):
            raise RuntimeError("Cross-target deployment requires a pure Python backend wheel")
        for wheel in wheels:
            _normalize_wheel(wheel)

        # Supervisors from before the JSON migration require this path but do
        # not execute it when starting a current backend release.
        legacy_automation = build_dir / LEGACY_AUTOMATION_FILE
        legacy_automation.write_bytes(b"")
        payloads = {
            **{f"wheels/{path.name}": path for path in wheels},
            **{f"data/{name}": workspace / name for name in RUNTIME_DATA_FILES},
            f"data/{LEGACY_AUTOMATION_FILE}": legacy_automation,
        }
        manifest = {
            "format": 1,
            "runtime": target.as_dict(),
            "components": {
                "backend": {"wheelhouse": "wheels", "package": "train"},
                "data": {"path": "data"},
            },
            "files": {
                name: _sha256(path)
                for name, path in sorted(payloads.items())
            },
        }
        manifest_bytes = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode()
        _write_reproducible_tar(destination, manifest_bytes, payloads)
    return _sha256(destination)


def publish_bundle(
    config: DeploymentConfig,
    bundle: Path,
    digest: str,
    *,
    ftp_factory: Callable[[], ftplib.FTP] | None = None,
) -> str:
    attempt = uuid.uuid4().hex
    archive_name = f"release-{digest}.tar.gz"
    ftp = _connect(config, ftp_factory)
    try:
        _ensure_remote_dir(ftp, config.remote_dir)
        ftp.cwd(config.remote_dir)
        archive_temporary = f"{archive_name}.{attempt}.uploading"
        with bundle.open("rb") as source:
            ftp.storbinary(f"STOR {archive_temporary}", source)
        _replace_remote(ftp, archive_temporary, archive_name)

        bootstrap = REPO_ROOT / "tools" / "server-loop"
        bootstrap_temporary = f"server-loop.{attempt}.uploading"
        with bootstrap.open("rb") as source:
            ftp.storbinary(f"STOR {bootstrap_temporary}", source)
        _replace_remote(ftp, bootstrap_temporary, "server-loop")

        pointer_name = f"release.{attempt}.json.uploading"
        pointer = json.dumps({"release": digest, "attempt": attempt}) + "\n"
        ftp.storbinary(f"STOR {pointer_name}", io.BytesIO(pointer.encode()))
        _replace_remote(ftp, pointer_name, "release.json")
    finally:
        _close(ftp)
    return attempt


def wait_until_active(
    config: DeploymentConfig,
    digest: str,
    attempt: str,
    *,
    timeout: float = 90,
    ftp_factory: Callable[[], ftplib.FTP] | None = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _remote_json(config, "status.json", ftp_factory)
        if (
            status
            and status.get("release") == digest
            and status.get("attempt") == attempt
            and status.get("state") == "failed"
        ):
            raise RuntimeError(
                f"Server rejected release: {status.get('message', 'unknown error')}"
            )
        active = _remote_text(config, "active.sha256", ftp_factory)
        if active == digest and _healthy_release(config.health_url, digest):
            return
        time.sleep(2)
    raise TimeoutError(
        "Server did not activate the release. Start the uploaded server-loop on "
        "the server and inspect deploy/server-loop.log and deploy/status.json."
    )


def _healthy_release(url: str, digest: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=3) as response:
            value = json.loads(response.read())
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return value == {"status": "ok", "release": digest}


def _remote_text(
    config: DeploymentConfig,
    name: str,
    ftp_factory: Callable[[], ftplib.FTP] | None,
) -> str | None:
    ftp = None
    try:
        ftp = _connect(config, ftp_factory)
        ftp.cwd(config.remote_dir)
        output = io.BytesIO()
        ftp.retrbinary(f"RETR {name}", output.write)
        return output.getvalue().decode().strip()
    except (OSError, UnicodeError, ftplib.Error):
        return None
    finally:
        if ftp is not None:
            _close(ftp)


def _remote_json(
    config: DeploymentConfig,
    name: str,
    ftp_factory: Callable[[], ftplib.FTP] | None,
) -> dict | None:
    value = _remote_text(config, name, ftp_factory)
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _connect(
    config: DeploymentConfig,
    ftp_factory: Callable[[], ftplib.FTP] | None,
) -> ftplib.FTP:
    if ftp_factory:
        ftp = ftp_factory()
    else:
        if config.tls:
            context = ssl.create_default_context(cafile=config.ca_file)
            ftp = ftplib.FTP_TLS(context=context)
        else:
            ftp = ftplib.FTP()
    try:
        ftp.connect(config.host, config.port, timeout=15)
        ftp.login(config.username, config.password)
        if config.tls:
            if not isinstance(ftp, ftplib.FTP_TLS):
                raise RuntimeError("FTPS requires an FTP_TLS client")
            ftp.prot_p()
    except Exception:
        ftp.close()
        raise
    return ftp


def _replace_remote(ftp: ftplib.FTP, temporary: str, destination: str) -> None:
    try:
        ftp.delete(destination)
    except ftplib.error_perm:
        pass
    ftp.rename(temporary, destination)


def _close(ftp: ftplib.FTP) -> None:
    try:
        ftp.quit()
    except (OSError, ftplib.Error):
        ftp.close()


def _required_string(value: dict, key: str, source: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result.strip():
        raise WorkspaceError(f"{source}.{key} must be a non-empty string")
    return result.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_runtime() -> RuntimeTarget:
    return RuntimeTarget(
        system=platform.system(),
        machine=platform.machine(),
        implementation=platform.python_implementation().lower(),
        python=f"{sys.version_info.major}.{sys.version_info.minor}",
        platform=sysconfig.get_platform(),
        soabi=str(sysconfig.get_config_var("SOABI")),
    )


def _requirements_lock(target: RuntimeTarget) -> Path:
    key = f"{target.platform}--{target.soabi}"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
        raise RuntimeError(f"Deployment target cannot select a lock file: {key}")
    path = REPO_ROOT / "backend" / "requirements" / f"{key}.lock"
    if not path.is_file():
        raise RuntimeError(f"No dependency lock exists for deployment target: {key}")
    return path


def _pip_target_args(target: RuntimeTarget) -> list[str]:
    if target.implementation != "cpython":
        raise RuntimeError(
            f"Unsupported deployment Python implementation: {target.implementation}"
        )
    abi = re.fullmatch(r"cpython-(\d+)-.+", target.soabi)
    if abi is None:
        raise RuntimeError(f"Unsupported deployment SOABI: {target.soabi}")
    pip_platform = target.platform.replace("-", "_").replace(".", "_")
    return [
        "--platform",
        pip_platform,
        "--python-version",
        target.python,
        "--implementation",
        "cp",
        "--abi",
        f"cp{abi.group(1)}",
    ]


def _ensure_remote_dir(ftp: ftplib.FTP, path: str) -> None:
    ftp.cwd("/")
    for part in path.strip("/").split("/"):
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def _normalize_wheel(path: Path) -> None:
    temporary = path.with_suffix(".normalized")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED
    ) as destination:
        for name in sorted(source.namelist()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            destination.writestr(info, source.read(name))
    os.replace(temporary, path)


def _write_reproducible_tar(
    destination: Path, manifest: bytes, payloads: dict[str, Path]
) -> None:
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                _add_bytes(archive, "manifest.json", manifest)
                for name, path in sorted(payloads.items()):
                    _add_bytes(archive, name, path.read_bytes())


def _add_bytes(archive: tarfile.TarFile, name: str, value: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(value)
    info.mode = 0o644
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    archive.addfile(info, io.BytesIO(value))
