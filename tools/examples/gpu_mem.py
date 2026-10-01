"""Memory sampling for the example gallery (Windows only).

* DXGI adapter list (name + LUID) so the Windows GPU counters can be mapped to a card name.
* A background sampler for one process tree (the ComfyUI test server and its children, e.g. llama-server):
  - host: private bytes (commit) and working set of every process in the tree, plus the system commit charge,
  - GPU: dedicated and shared usage per adapter from the ``GPU Process Memory`` performance counters.

The torch allocator peaks come from the RDNA4 bench probe (``/rdna4/mem``); the counters add everything torch does not
see (HIP context, llama.cpp, DirectML).
"""
from __future__ import annotations

import ctypes
import re
import subprocess
import threading
import time
from ctypes import wintypes

import psutil

GIB = 2**30


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [("Description", wintypes.WCHAR * 128), ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT),
                ("DedicatedVideoMemory", ctypes.c_size_t), ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t), ("AdapterLuid", _LUID), ("Flags", wintypes.UINT)]


def _guid(text: str) -> _GUID:
    parts = text.split("-")
    tail = bytes.fromhex(parts[3] + parts[4])
    return _GUID(int(parts[0], 16), int(parts[1], 16), int(parts[2], 16), (ctypes.c_ubyte * 8)(*tail))


def dxgi_adapters() -> list[dict]:
    """Return [{name, luid, dedicated_gib}] for every hardware DXGI adapter."""
    factory = ctypes.c_void_p()
    iid = _guid("770aae78-f26f-4dba-a829-253c83d1b387")  # IDXGIFactory1
    if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(factory)) != 0:
        return []
    vtbl = ctypes.cast(ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    enum_adapters1 = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_void_p))(vtbl[12])
    release = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
    out = []
    index = 0
    while True:
        adapter = ctypes.c_void_p()
        if enum_adapters1(factory, index, ctypes.byref(adapter)) != 0:
            break
        avtbl = ctypes.cast(ctypes.cast(adapter, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        get_desc1 = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                       ctypes.POINTER(_DXGI_ADAPTER_DESC1))(avtbl[10])
        desc = _DXGI_ADAPTER_DESC1()
        if get_desc1(adapter, ctypes.byref(desc)) == 0 and not (desc.Flags & 2):  # skip software adapters
            luid = (desc.AdapterLuid.HighPart & 0xFFFFFFFF) << 32 | desc.AdapterLuid.LowPart
            out.append({"name": desc.Description, "luid": luid,
                        "dedicated_gib": round(desc.DedicatedVideoMemory / GIB, 2)})
        release(avtbl[2])(adapter)
        index += 1
    release(vtbl[2])(factory)
    return out


_COUNTER_LINE = re.compile(r"pid_(\d+)_luid_0x([0-9a-f]+)_0x([0-9a-f]+)_phys_\d+\)\\(dedicated|shared) usage\t([\d.,Ee+-]+)",
                           re.IGNORECASE)


def system_commit_gib() -> float:
    """Current system commit charge (GetPerformanceInfo), in GiB."""
    from ctypes import wintypes as wt

    class PERF(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("CommitTotal", ctypes.c_size_t), ("CommitLimit", ctypes.c_size_t),
                    ("CommitPeak", ctypes.c_size_t), ("PhysicalTotal", ctypes.c_size_t),
                    ("PhysicalAvailable", ctypes.c_size_t), ("SystemCache", ctypes.c_size_t),
                    ("KernelTotal", ctypes.c_size_t), ("KernelPaged", ctypes.c_size_t),
                    ("KernelNonpaged", ctypes.c_size_t), ("PageSize", ctypes.c_size_t),
                    ("HandleCount", wt.DWORD), ("ProcessCount", wt.DWORD), ("ThreadCount", wt.DWORD)]

    info = PERF()
    info.cb = ctypes.sizeof(PERF)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        return 0.0
    return info.CommitTotal * info.PageSize / GIB


class TreeSampler:
    """Sample host and GPU memory of a process tree until ``stop()``."""

    def __init__(self, root_pid: int, interval: float = 1.0, on_danger=None, min_commit_headroom_gib: float = 0.25,
                 max_commit_gib: float | None = None, max_commit_seconds: float = 10.0):
        self.root_pid = root_pid
        self.on_danger = on_danger
        self.min_headroom = min_commit_headroom_gib * GIB
        # 2026-09-30: a 47 GB box went down with bug check 0x101 after LTX-2.3 runs had pushed the system commit to
        # 140-162 GiB (auto-grown page file); the headroom check never fired. A fixed ceiling interrupts earlier.
        self.max_commit = max_commit_gib * GIB if max_commit_gib else None
        self.max_commit_seconds = max_commit_seconds
        self._high_since = None
        self.danger_reason = ""
        self.danger = False
        self._low_since = None
        self.interval = interval
        self.adapters = {a["luid"]: a["name"] for a in dxgi_adapters()}
        self._stop = threading.Event()
        self.peak_private = 0
        self.peak_rss = 0
        self.peak_commit = 0
        self.commit_limit = 0
        self.peak_by_proc: dict[str, float] = {}
        self.gpu_peak: dict[str, dict[str, float]] = {}  # adapter name -> {"dedicated": gib, "shared": gib}
        self.gpu_peak_by_proc: dict[str, dict[str, float]] = {}  # "proc@adapter" -> dedicated gib
        self._threads: list[threading.Thread] = []
        self._counter_proc: subprocess.Popen | None = None
        self.started = time.time()

    # -- host -------------------------------------------------------------------------------------------------------
    def _tree(self) -> list[psutil.Process]:
        try:
            root = psutil.Process(self.root_pid)
            return [root, *root.children(recursive=True)]
        except psutil.Error:
            return []

    def _host_loop(self) -> None:
        from ctypes import wintypes as wt

        class PERF(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("CommitTotal", ctypes.c_size_t), ("CommitLimit", ctypes.c_size_t),
                        ("CommitPeak", ctypes.c_size_t), ("PhysicalTotal", ctypes.c_size_t),
                        ("PhysicalAvailable", ctypes.c_size_t), ("SystemCache", ctypes.c_size_t),
                        ("KernelTotal", ctypes.c_size_t), ("KernelPaged", ctypes.c_size_t),
                        ("KernelNonpaged", ctypes.c_size_t), ("PageSize", ctypes.c_size_t),
                        ("HandleCount", wt.DWORD), ("ProcessCount", wt.DWORD), ("ThreadCount", wt.DWORD)]

        while not self._stop.is_set():
            private = rss = 0
            for proc in self._tree():
                try:
                    mem = proc.memory_info()
                    private += mem.private
                    rss += mem.rss
                    name = proc.name().lower()
                    self.peak_by_proc[name] = max(self.peak_by_proc.get(name, 0.0), mem.private / GIB)
                except psutil.Error:
                    pass
            self.peak_private = max(self.peak_private, private)
            self.peak_rss = max(self.peak_rss, rss)
            info = PERF()
            info.cb = ctypes.sizeof(PERF)
            if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
                self.peak_commit = max(self.peak_commit, info.CommitTotal * info.PageSize)
                self.commit_limit = info.CommitLimit * info.PageSize
                # Windows grows the page file up to the commit limit; running out stalls the whole desktop.
                headroom = (info.CommitLimit - info.CommitTotal) * info.PageSize
                total = info.CommitTotal * info.PageSize
                if self.max_commit and total > self.max_commit:
                    self._high_since = self._high_since or time.time()
                    if time.time() - self._high_since > self.max_commit_seconds and not self.danger:
                        self.danger = True
                        self.danger_reason = f"system commit {total / GIB:.0f} GiB above {self.max_commit / GIB:.0f} GiB"
                        if self.on_danger:
                            try:
                                self.on_danger()
                            except Exception:
                                pass
                else:
                    self._high_since = None
                if headroom < self.min_headroom:
                    self._low_since = self._low_since or time.time()
                    if time.time() - self._low_since > 30 and not self.danger:
                        self.danger = True
                        self.danger_reason = f"commit headroom {headroom / GIB:.2f} GiB"
                        if self.on_danger:
                            try:
                                self.on_danger()
                            except Exception:
                                pass
                else:
                    self._low_since = None
            self._stop.wait(self.interval / 2)

    # -- GPU counters -----------------------------------------------------------------------------------------------
    def _gpu_loop(self) -> None:
        script = ("$ErrorActionPreference='SilentlyContinue'; "
                  "Get-Counter -Counter '\\GPU Process Memory(*)\\Dedicated Usage','\\GPU Process Memory(*)\\Shared Usage' "
                  f"-SampleInterval {max(1, int(self.interval))} -Continuous | ForEach-Object {{ "
                  "$_.CounterSamples | Where-Object { $_.CookedValue -gt 0 } | "
                  "ForEach-Object { $_.Path + [char]9 + $_.CookedValue }; '---' }")
        self._counter_proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        sample: dict[tuple[str, str, str], float] = {}
        names: dict[int, str] = {}
        for line in self._counter_proc.stdout:
            if self._stop.is_set():
                break
            line = line.strip()
            if line == "---":
                pids = {p.pid for p in self._tree()}
                for p in self._tree():
                    try:
                        names[p.pid] = p.name().lower()
                    except psutil.Error:
                        pass
                totals: dict[tuple[str, str], float] = {}
                for (pid, adapter, kind), value in sample.items():
                    if int(pid) not in pids:
                        continue
                    totals[(adapter, kind)] = totals.get((adapter, kind), 0.0) + value
                    if kind == "dedicated":
                        key = f"{names.get(int(pid), pid)}@{adapter}"
                        self.gpu_peak_by_proc[key] = max(self.gpu_peak_by_proc.get(key, 0.0), value / GIB)
                for (adapter, kind), value in totals.items():
                    slot = self.gpu_peak.setdefault(adapter, {"dedicated": 0.0, "shared": 0.0})
                    slot[kind] = max(slot[kind], value / GIB)
                sample = {}
                continue
            match = _COUNTER_LINE.search(line)
            if not match:
                continue
            pid, _high, low, kind, value = match.groups()
            luid = int(_high, 16) << 32 | int(low, 16)
            adapter = self.adapters.get(luid, f"luid_{luid:#x}")
            try:
                sample[(pid, adapter, kind.lower())] = sample.get((pid, adapter, kind.lower()), 0.0) + float(
                    value.replace(",", "."))
            except ValueError:
                pass

    def start(self) -> "TreeSampler":
        for target in (self._host_loop, self._gpu_loop):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)
        return self

    def stop(self) -> dict:
        # One more counter sample: the counter stream lags by about a second.
        time.sleep(min(2.0, self.interval * 2))
        self._stop.set()
        if self._counter_proc and self._counter_proc.poll() is None:
            self._counter_proc.kill()
        for thread in self._threads:
            thread.join(timeout=5)
        return self.result()

    def result(self) -> dict:
        return {
            "seconds": round(time.time() - self.started, 1),
            "peak_process_private_gib": round(self.peak_private / GIB, 2),
            "peak_process_rss_gib": round(self.peak_rss / GIB, 2),
            "peak_system_commit_gib": round(self.peak_commit / GIB, 2),
            "commit_limit_gib": round(self.commit_limit / GIB, 2),
            "peak_private_by_process_gib": {k: round(v, 2) for k, v in self.peak_by_proc.items()},
            "gpu_counters_gib": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in self.gpu_peak.items()},
            "gpu_dedicated_by_process_gib": {k: round(v, 2) for k, v in self.gpu_peak_by_proc.items()},
            "commit_guard_tripped": self.danger,
            "commit_guard_reason": self.danger_reason,
        }


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(dxgi_adapters(), indent=1))
    if len(sys.argv) > 1:
        s = TreeSampler(int(sys.argv[1])).start()
        time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 5)
        print(json.dumps(s.stop(), indent=1))
