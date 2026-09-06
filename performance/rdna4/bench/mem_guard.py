"""Host-memory guard for the benchmark chain.

Exit 0 when it is safe to queue another job, 1 when the bench server should be restarted first
(host RAM available below --min-avail GiB, swap above --max-swap GiB, or the server unreachable).
Uses the probe endpoint of the bench instance so numbers are consistent with the run records.

The 2026-09-05 22:31 crash happened after swap had grown 2 -> 17 GiB across LTX/ACE runs
(dead-model leaks from device deep-clones + RAM cache); this guard forces a fresh process before
that state is reached.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8190")
    ap.add_argument("--min-avail", type=float, default=10.0)
    ap.add_argument("--max-swap", type=float, default=20.0)
    a = ap.parse_args()
    try:
        with urllib.request.urlopen(f"{a.url}/rdna4/mem", timeout=10) as r:
            d = json.load(r)
    except Exception as e:
        print(f"mem_guard: server unreachable ({e}) -> restart")
        return 1
    h = d["host"]
    avail = h.get("ram_available", 0) / 2**30
    swap = h.get("swap_used", 0) / 2**30
    rss = h.get("process_rss", 0) / 2**30
    ok = avail >= a.min_avail and swap <= a.max_swap
    print(f"mem_guard: avail {avail:.1f} GiB swap {swap:.1f} GiB rss {rss:.1f} GiB -> {'OK' if ok else 'RESTART'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
