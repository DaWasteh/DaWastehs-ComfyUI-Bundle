"""Start / stop an isolated ComfyUI benchmark instance.

Never touches port 8188. Uses the production venv, code and models read-only,
but writes outputs, temp and the SQLite DB to bench-specific locations.

Profile file (JSON):
{
  "name": "v098_baseline",
  "env": {"HIP_VISIBLE_DEVICES": "0,1", ...},
  "unset_env": ["PYTORCH_TUNABLEOP_ENABLED"],
  "args": ["--default-device", "0", "--use-pytorch-cross-attention", ...]
}

Usage:
  python comfy_server.py start --profile profiles/v098_baseline.json --run-dir raw/run01 [--port 8190]
  python comfy_server.py stop  --run-dir raw/run01
  python comfy_server.py status --port 8190
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("L:/ComfyUI")
COMFY = ROOT / "ComfyUI"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
BENCH_DIR = Path(__file__).resolve().parent
EXTRA_PATHS = BENCH_DIR / "extra_model_paths_bench.yaml"
FORBIDDEN_PORTS = {8188, 8189}

BOOTSTRAP = (
    "import runpy, signal, sys; "
    "signal.signal(signal.SIGBREAK, signal.default_int_handler); "
    "script = sys.argv.pop(1); sys.argv[0] = script; "
    "runpy.run_path(script, run_name='__main__')"
)


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_json(url: str, timeout: float = 10.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def start(args) -> int:
    port = args.port
    if port in FORBIDDEN_PORTS:
        print(f"refusing to use production port {port}", file=sys.stderr)
        return 2
    if port_in_use(port):
        print(f"port {port} already in use", file=sys.stderr)
        return 2
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "output"
    tmp_dir = run_dir / "temp"
    out_dir.mkdir(exist_ok=True)
    tmp_dir.mkdir(exist_ok=True)
    db = BENCH_DIR / "bench_state" / f"comfyui-bench-{port}.db"
    db.parent.mkdir(exist_ok=True)
    db_url = "sqlite:///" + str(db).replace("\\", "/")

    env = dict(os.environ)
    for k in ("HSA_OVERRIDE_GFX_VERSION", "PYTORCH_TUNABLEOP_ENABLED", "HIP_LAUNCH_BLOCKING", "CUDA_LAUNCH_BLOCKING",
              "TORCH_BLAS_PREFER_HIPBLASLT", "TORCH_BLAS_PREFER_CUBLASLT", "DISABLE_ADDMM_CUDA_LT"):
        env.pop(k, None)
    for k in profile.get("unset_env", []):
        env.pop(k, None)
    env.update({k: str(v) for k, v in profile.get("env", {}).items()})
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")

    comfy_args = [
        "--listen", "127.0.0.1",
        "--port", str(port),
        "--database-url", db_url,
        "--output-directory", str(out_dir),
        "--temp-directory", str(tmp_dir),
        "--extra-model-paths-config", str(EXTRA_PATHS),
        "--disable-auto-launch",
        "--dont-print-server",
    ] + list(profile.get("args", []))
    if "--enable-manager" in comfy_args and not profile.get("allow_manager"):
        comfy_args.remove("--enable-manager")  # no background installs in the bench instance

    cmd = [str(PYTHON), "-c", BOOTSTRAP, str(COMFY / "main.py"), *comfy_args]
    log_path = run_dir / "server.log"
    (run_dir / "server_cmd.json").write_text(
        json.dumps({"cmd": cmd, "profile": profile, "env_overrides": profile.get("env", {}), "port": port,
                    "started": time.time()}, indent=2), encoding="utf-8")
    log_f = open(log_path, "ab")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(cmd, cwd=str(COMFY), env=env, stdout=log_f, stderr=subprocess.STDOUT,
                            creationflags=creationflags)
    (run_dir / "server.pid").write_text(str(proc.pid), encoding="utf-8")
    print(f"started pid={proc.pid} port={port} log={log_path}")

    deadline = time.time() + args.startup_timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"server exited early with code {proc.returncode}; see {log_path}", file=sys.stderr)
            return 3
        try:
            stats = get_json(f"http://127.0.0.1:{port}/system_stats", timeout=3)
            info = get_json(f"http://127.0.0.1:{port}/rdna4/info", timeout=10)
            (run_dir / "server_info.json").write_text(json.dumps({"system_stats": stats, "probe": info}, indent=2),
                                                      encoding="utf-8")
            print(f"ready after {time.time() - (deadline - args.startup_timeout):.1f}s; attention={info.get('attention_function')} "
                  f"vram_state={info.get('vram_state')} streams={info.get('NUM_STREAMS')} pinned_max={info.get('MAX_PINNED_MEMORY')} "
                  f"aimdo={info.get('aimdo_enabled')}")
            return 0
        except Exception:
            time.sleep(1.0)
    print("startup timeout", file=sys.stderr)
    return 4


def stop(args) -> int:
    run_dir = Path(args.run_dir).resolve()
    pid_file = run_dir / "server.pid"
    if not pid_file.exists():
        print("no pid file", file=sys.stderr)
        return 1
    pid = int(pid_file.read_text().strip())
    # Safety: never kill the production instance.
    try:
        chk = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
                             capture_output=True, text=True, timeout=30)
        cmdline = chk.stdout.strip()
    except Exception:
        cmdline = ""
    if not cmdline:
        print(f"pid {pid} not running")
        pid_file.unlink(missing_ok=True)
        return 0
    if "--port 8188" in cmdline or "--port 8189" in cmdline or "main.py" not in cmdline:
        print(f"refusing to stop pid {pid}: {cmdline[:200]}", file=sys.stderr)
        return 2
    graceful = False
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)
        graceful = True
    except Exception as e:
        print(f"CTRL_BREAK failed ({e}); falling back to taskkill")
    deadline = time.time() + (args.grace if graceful else 0)
    while time.time() < deadline:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        if str(pid) not in r.stdout:
            print(f"stopped pid {pid} gracefully")
            pid_file.unlink(missing_ok=True)
            return 0
        time.sleep(0.5)
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print(f"stopped pid {pid} (forced)")
    pid_file.unlink(missing_ok=True)
    return 0


def status(args) -> int:
    try:
        stats = get_json(f"http://127.0.0.1:{args.port}/system_stats", timeout=5)
        q = get_json(f"http://127.0.0.1:{args.port}/queue", timeout=5)
        print(json.dumps({"argv": stats["system"]["argv"], "devices": stats["devices"],
                          "running": len(q["queue_running"]), "pending": len(q["queue_pending"])}, indent=1))
        return 0
    except Exception as e:
        print(f"not reachable: {e}")
        return 1


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--profile", required=True)
    s.add_argument("--run-dir", required=True)
    s.add_argument("--port", type=int, default=8190)
    s.add_argument("--startup-timeout", type=float, default=300)
    s.set_defaults(fn=start)
    t = sub.add_parser("stop")
    t.add_argument("--run-dir", required=True)
    t.add_argument("--grace", type=float, default=25)
    t.set_defaults(fn=stop)
    u = sub.add_parser("status")
    u.add_argument("--port", type=int, default=8190)
    u.set_defaults(fn=status)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
