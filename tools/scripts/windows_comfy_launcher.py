"""Windows console supervisor for graceful ComfyUI Ctrl+C shutdown."""
from __future__ import annotations

import argparse
import ctypes
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CREATE_NEW_PROCESS_GROUP = 0x00000200
GRACEFUL_TIMEOUT_SECONDS = 20


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--working-directory", required=True)
    parser.add_argument("comfy_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.comfy_args[:1] == ["--"]:
        args.comfy_args = args.comfy_args[1:]
    if args.comfy_args[:1] == ["main.py"]:
        args.comfy_args = args.comfy_args[1:]
    if not args.comfy_args:
        parser.error("missing ComfyUI arguments after --")
    return args


def isolated_temp_args(comfy_args: list[str], working_directory: Path,
                       instance_id: int | None = None) -> list[str]:
    """Every server owns its cleanup tree, even during a duplicate-port start.

    ComfyUI appends /temp to --temp-directory. Explicit caller overrides are
    respected; those callers are responsible for choosing a unique directory.
    """
    if any(arg == "--temp-directory" or arg.startswith("--temp-directory=")
           for arg in comfy_args):
        return list(comfy_args)
    port = "8188"
    for index, arg in enumerate(comfy_args):
        if arg == "--port" and index + 1 < len(comfy_args):
            port = comfy_args[index + 1]
        elif arg.startswith("--port="):
            port = arg.split("=", 1)[1]
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError(f"Invalid ComfyUI port: {port}")
    instance_id = os.getpid() if instance_id is None else instance_id
    root = working_directory.resolve().parent / "tmp" / f"comfyui-{port}-{instance_id}"
    return [*comfy_args, "--temp-directory", str(root)]


def main() -> int:
    if os.name != "nt":
        raise SystemExit("This launcher is Windows-only")

    args = parse_args()
    python_exe = Path(args.python).resolve()
    working_directory = Path(args.working_directory).resolve()
    if not python_exe.is_file():
        raise SystemExit(f"Python executable not found: {python_exe}")
    if not working_directory.is_dir():
        raise SystemExit(f"Working directory not found: {working_directory}")

    # A new process group lets the supervisor target only ComfyUI with
    # CTRL_BREAK. The bootstrap maps SIGBREAK to KeyboardInterrupt so current
    # ComfyUI executes its normal asset/temp cleanup instead of being killed.
    bootstrap = (
        "import runpy, signal, sys; "
        "signal.signal(signal.SIGBREAK, signal.default_int_handler); "
        "script = sys.argv.pop(1); sys.argv[0] = script; "
        "runpy.run_path(script, run_name='__main__')"
    )
    command = [
        str(python_exe),
        "-c",
        bootstrap,
        str(working_directory / "main.py"),
        *isolated_temp_args(args.comfy_args, working_directory),
    ]

    stop_requested = threading.Event()
    handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    @handler_type
    def console_handler(event_type: int) -> bool:
        if event_type in (CTRL_C_EVENT, CTRL_BREAK_EVENT):
            stop_requested.set()
            return True
        return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # PowerShell may temporarily mark foreground native children as ignoring
    # Ctrl+C. Explicitly re-enable handling and install our own callback.
    kernel32.SetConsoleCtrlHandler(None, False)
    if not kernel32.SetConsoleCtrlHandler(console_handler, True):
        raise ctypes.WinError(ctypes.get_last_error())

    process: subprocess.Popen[bytes] | None = None
    forced = False
    try:
        process = subprocess.Popen(
            command,
            cwd=working_directory,
            creationflags=CREATE_NEW_PROCESS_GROUP,
        )
        print(f"ComfyUI PID: {process.pid}", flush=True)

        while True:
            try:
                return_code = process.wait(timeout=0.25)
                return return_code
            except subprocess.TimeoutExpired:
                pass

            if not stop_requested.is_set():
                continue

            print("\nCtrl+C empfangen - ComfyUI wird sauber beendet ...", flush=True)
            process.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                return process.wait(timeout=GRACEFUL_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                forced = True
                print(
                    f"Keine Reaktion nach {GRACEFUL_TIMEOUT_SECONDS} Sekunden - "
                    "Prozessbaum wird beendet.",
                    file=sys.stderr,
                    flush=True,
                )
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
                return 1
    finally:
        kernel32.SetConsoleCtrlHandler(console_handler, False)
        if process is not None and process.poll() is None:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        if forced:
            print("ComfyUI musste hart beendet werden.", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
