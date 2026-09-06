"""Host-memory watchdog for a benchmark ComfyUI process (second line of defence behind the VRAM guard).

Samples GetPerformanceInfo twice a second and force-kills the watched process tree as soon as
available RAM, commit headroom or the kernel non-paged pool cross a limit. Only ever kills the
PID it was started with (the benchmark server on port 8190), never the production instance.

  python host_guard.py --pid 12345 --log raw/host_guard.jsonl [--min-avail-gib 6] [--min-commit-headroom-gib 8]
  python host_guard.py --run-dir raw/server_xxx ...   (reads server.pid)
Exits 0 when the watched process ends by itself, 3 when it had to kill it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vram_probe import host_snapshot  # noqa: E402


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in out.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--run-dir")
    ap.add_argument("--log", required=True)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--min-avail-gib", type=float, default=6.0)
    ap.add_argument("--min-commit-headroom-gib", type=float, default=8.0)
    ap.add_argument("--max-nonpaged-gib", type=float, default=6.0)
    a = ap.parse_args()
    pid = a.pid
    if pid is None:
        if not a.run_dir:
            ap.error("--pid or --run-dir required")
        pid = int(Path(a.run_dir, "server.pid").read_text(encoding="utf-8").strip())
    if pid in (0, 4) or not pid_alive(pid):
        print(f"host_guard: pid {pid} not running", file=sys.stderr)
        return 2
    Path(a.log).parent.mkdir(parents=True, exist_ok=True)

    def emit(**kw):
        kw.setdefault("t", time.time())
        with open(a.log, "a", encoding="utf-8") as f:
            f.write(json.dumps(kw) + "\n")

    emit(event="start", pid=pid, min_avail_gib=a.min_avail_gib, min_commit_headroom_gib=a.min_commit_headroom_gib,
         max_nonpaged_gib=a.max_nonpaged_gib, host=host_snapshot())
    peaks = {"min_avail_gib": 1e9, "max_commit_gib": 0.0, "max_nonpaged_gib": 0.0}
    try:
        import psutil
        proc = psutil.Process(pid)
    except Exception:
        proc = None

    def proc_mem():
        if proc is None:
            return {}
        try:
            mi = proc.memory_info()
            return {"rss_gib": round(mi.rss / 2**30, 2), "private_gib": round(getattr(mi, "private", 0) / 2**30, 2),
                    "pagefile_gib": round(getattr(mi, "pagefile", 0) / 2**30, 2)}
        except Exception:
            return {}

    last_log = 0.0
    while True:
        time.sleep(a.interval)
        h = host_snapshot()
        peaks["min_avail_gib"] = min(peaks["min_avail_gib"], h["avail_gib"])
        peaks["max_commit_gib"] = max(peaks["max_commit_gib"], h["commit_gib"])
        peaks["max_nonpaged_gib"] = max(peaks["max_nonpaged_gib"], h["nonpaged_gib"])
        headroom = h["commit_limit_gib"] - h["commit_gib"]
        reason = None
        if h["avail_gib"] < a.min_avail_gib:
            reason = f"available RAM {h['avail_gib']} GiB < {a.min_avail_gib}"
        elif headroom < a.min_commit_headroom_gib:
            reason = f"commit headroom {headroom:.1f} GiB < {a.min_commit_headroom_gib}"
        elif h["nonpaged_gib"] > a.max_nonpaged_gib:
            reason = f"non-paged pool {h['nonpaged_gib']} GiB > {a.max_nonpaged_gib}"
        if reason:
            emit(event="kill", pid=pid, reason=reason, host=h, peaks=peaks, proc=proc_mem())
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            print(f"host_guard: killed {pid}: {reason}", file=sys.stderr)
            return 3
        if time.time() - last_log > 5:
            emit(event="sample", host=h, proc=proc_mem())
            last_log = time.time()
        if not pid_alive(pid):
            emit(event="exited", pid=pid, peaks=peaks, host=h)
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
