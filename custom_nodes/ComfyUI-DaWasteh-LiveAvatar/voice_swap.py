"""Fail-closed launcher for the pinned local DirectML RVC companion.

The node controls only the audited b2332 executable.  It never downloads a
voice model, accepts no arbitrary command line, and refuses to touch a process
whose executable path does not match the configured verified installation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path, PurePosixPath
from typing import Any

import psutil


PORT = 18888
EXE_NAME = "MMVCServerSIO.exe"
MANIFEST = Path(__file__).with_name("assets") / "voice-changer-b2332-tree.json"
TREE_FILES = 3400
TREE_BYTES = 806658313
TREE_SHA256 = "ddd816e470e4ff8765f11dd83ae927fa238ae36272017f71bf3977c19727e961"
ACTIONS = ("start / open UI", "status / open UI", "stop verified service")
DEFAULT_INSTALL_PATH = "L:/ComfyUI/voice-changer-dml-b2332"
UI_URL = f"http://127.0.0.1:{PORT}/"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    if (
        not value
        or relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or ":" in relative.parts[0]
    ):
        raise ValueError(f"unsafe voice-converter manifest path: {value!r}")
    return relative


def tree_digest(
    install_path: str | Path,
    manifest_path: str | Path = MANIFEST,
) -> tuple[int, int, str]:
    root = Path(install_path).resolve()
    manifest_file = Path(manifest_path)
    records = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(records, dict):
        raise ValueError("voice-converter manifest root must be an object")
    digest = hashlib.sha256()
    count = total = 0
    for relative_text, record in sorted(records.items()):
        relative = _safe_relative(relative_text)
        if not isinstance(record, list) or len(record) != 2:
            raise ValueError(f"invalid voice-converter manifest record: {relative_text!r}")
        size, expected_hash = record
        if not isinstance(size, int) or size < 0 or not isinstance(expected_hash, str):
            raise ValueError(f"invalid voice-converter manifest values: {relative_text!r}")
        candidate = root.joinpath(*relative.parts)
        if candidate.is_symlink() or not candidate.is_file():
            return -1, -1, ""
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            return -1, -1, ""
        if candidate.stat().st_size != size or sha256(candidate) != expected_hash:
            return -1, -1, ""
        digest.update(
            f"MMVCServerSIO/{relative.as_posix()}".encode("utf-8")
            + b"\0"
            + str(size).encode("ascii")
            + b"\0"
            + expected_hash.encode("ascii")
            + b"\n"
        )
        count += 1
        total += size
    return count, total, digest.hexdigest()


def installation_ok(install_path: str | Path) -> bool:
    root = Path(install_path)
    return (
        root.is_dir()
        and not root.is_symlink()
        and MANIFEST.is_file()
        and tree_digest(root) == (TREE_FILES, TREE_BYTES, TREE_SHA256)
    )


def require_installation(install_path: str | Path) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("DirectML RVC is supported by this launcher only on Windows")
    root = Path(install_path).expanduser().resolve()
    if not installation_ok(root):
        raise RuntimeError(
            "Pinned voice-converter verification failed. Run: python "
            "tools/install_live_voice_converter.py --destination " + str(root)
        )
    return root


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(os.path.abspath(str(right)))


def _listener_pids(port: int = PORT) -> set[int]:
    pids: set[int] = set()
    for connection in psutil.net_connections(kind="tcp"):
        if connection.status != psutil.CONN_LISTEN or not connection.laddr:
            continue
        if int(connection.laddr.port) == int(port) and connection.pid is not None:
            pids.add(int(connection.pid))
    return pids


def _health_ok(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(UI_URL, timeout=timeout) as response:
            return response.status == 200
    except OSError:
        return False


def service_status(install_path: str | Path) -> dict[str, Any]:
    root = Path(install_path).expanduser().resolve()
    expected = root / EXE_NAME
    pids = _listener_pids()
    if not pids:
        return {"state": "stopped", "ready": False, "pid": 0, "url": UI_URL}
    if len(pids) != 1:
        raise RuntimeError(f"Port {PORT} has multiple listeners: {sorted(pids)}")
    pid = next(iter(pids))
    try:
        executable = psutil.Process(pid).exe()
    except (psutil.Error, OSError) as error:
        raise RuntimeError(f"Cannot identify listener PID {pid}: {error}") from error
    if not _same_path(executable, expected):
        raise RuntimeError(
            f"Port {PORT} is owned by an untrusted executable: {executable}"
        )
    ready = _health_ok()
    return {
        "state": "ready" if ready else "starting",
        "ready": ready,
        "pid": pid,
        "url": UI_URL,
    }


def start_service(install_path: str | Path, timeout: float = 300.0) -> dict[str, Any]:
    root = require_installation(install_path)
    status = service_status(root)
    if status["ready"]:
        return status
    if status["state"] == "starting":
        process = psutil.Process(status["pid"])
    else:
        log_dir = root.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "voice-changer-b2332.log"
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        with log_path.open("ab", buffering=0) as log:
            launched = subprocess.Popen(
                [str(root / EXE_NAME), "--launch-browser", "false", "--log-level", "info"],
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creationflags,
            )
        process = psutil.Process(launched.pid)

    deadline = time.monotonic() + float(timeout)
    while time.monotonic() < deadline:
        if not process.is_running():
            raise RuntimeError("Pinned voice converter exited before becoming ready")
        try:
            status = service_status(root)
        except RuntimeError:
            time.sleep(0.5)
            continue
        if status["ready"]:
            return status
        time.sleep(0.5)
    if process.is_running():
        process.terminate()
    raise RuntimeError(f"Pinned voice converter did not become ready within {timeout:g} seconds")


def stop_service(install_path: str | Path, timeout: float = 15.0) -> dict[str, Any]:
    root = Path(install_path).expanduser().resolve()
    status = service_status(root)
    if status["state"] == "stopped":
        return status
    process = psutil.Process(status["pid"])
    executable = process.exe()
    if not _same_path(executable, root / EXE_NAME):
        raise RuntimeError("Refusing to stop a process outside the configured pinned installation")
    process.terminate()
    try:
        process.wait(timeout=float(timeout))
    except psutil.TimeoutExpired as error:
        raise RuntimeError("Verified voice converter did not stop within the timeout") from error
    final = service_status(root)
    if final["state"] != "stopped":
        raise RuntimeError("Verified voice converter still owns its port after termination")
    return final


def run_action(
    action: str,
    install_path: str = DEFAULT_INSTALL_PATH,
    open_browser: bool = True,
) -> dict[str, Any]:
    if action not in ACTIONS:
        raise ValueError(f"unsupported live voice action: {action!r}")
    if action == "start / open UI":
        result = start_service(install_path)
    elif action == "stop verified service":
        result = stop_service(install_path)
    else:
        result = service_status(install_path)
    if open_browser and result["ready"]:
        webbrowser.open_new_tab(result["url"])
    result["status"] = (
        f"{result['state'].upper()} · DirectML RVC b2332 · "
        f"PID {result['pid'] if result['pid'] else '-'} · {result['url']}"
    )
    return result


class DaWastehLiveVoiceSwapLauncher:
    """Start, inspect, or stop only the hash-verified local RVC service."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "action": (list(ACTIONS),),
                "install_path": ("STRING", {"default": DEFAULT_INSTALL_PATH}),
                "open_browser": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("status", "ui_url", "process_id")
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "DaWasteh/Live Avatar"

    @classmethod
    def IS_CHANGED(cls, **_kwargs):
        return float("nan")

    def run(self, action: str, install_path: str, open_browser: bool = True):
        result = run_action(action, install_path, open_browser)
        values = (result["status"], result["url"], int(result["pid"]))
        return {"ui": {"text": [result["status"], result["url"]]}, "result": values}
