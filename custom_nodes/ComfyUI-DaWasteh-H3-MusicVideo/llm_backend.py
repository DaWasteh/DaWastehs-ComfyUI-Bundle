"""Prompt writing through a local llama.cpp server (GGUF models, e.g. Qwen3.8 27B on the second GPU).

The start profile names the model (DAWASTEH_PROMPT_LLM_GGUF) and the server binary (DAWASTEH_LLAMA_SERVER). MV 2
starts the server only while prompts are written - like it loads and frees Qwen3.5 - and talks to it through the
OpenAI-compatible chat API. Measured on the RX 9070 XT (HIP, built-in MTP head as draft, the desktop on the same
card, 8k context, vision projector on the CPU): Qwen3.8-27B IQ4_XS 12.5 GiB VRAM + 0.9 GiB shared, ~28 tokens/s,
wikitext-2 perplexity 6.21; Ridge 3.7 bpw 12.5 + 0.3 GiB, ~40 tokens/s, but perplexity 6.59. 16k context with the
projector on the GPU spilled 2.3 GiB into host RAM (Windows reports no OOM, see the VRAM guard notes).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

TAG = "[DaWasteh H3 MV2 llama.cpp]"
AUTO = "auto (GGUF aus dem Startprofil, sonst Qwen3.5 4B)"
GGUF_PREFIX = "gguf: "
ENV_MODEL = "DAWASTEH_PROMPT_LLM_GGUF"
ENV_SERVER = "DAWASTEH_LLAMA_SERVER"
ENV_DEVICE = "DAWASTEH_LLAMA_HIP_DEVICE"   # HIP index of the GPU for the server (1 = RX 9070 XT here)
ENV_CTX = "DAWASTEH_LLAMA_CTX"
ENV_MMPROJ_GPU = "DAWASTEH_LLAMA_MMPROJ_GPU"   # 1 = vision projector on the GPU (0.9 GiB more VRAM, sheets 2x faster)
SPILL_WARN_GIB = 1.5   # shared GPU memory above this = real spill (IQ4_XS beside the desktop: 0.9 GiB, normal)


def configured_gguf() -> str | None:
    path = os.environ.get(ENV_MODEL, "").strip().strip('"')
    return path if path and os.path.isfile(path) else None


def gguf_option() -> str | None:
    path = configured_gguf()
    return GGUF_PREFIX + Path(path).name if path else None


def resolve(choice: str, fallback: str) -> tuple[str, str]:
    """(kind, name): kind "gguf" with an absolute path, or "comfy" with a text-encoder file name."""
    path = configured_gguf()
    if choice == AUTO:
        return ("gguf", path) if path else ("comfy", fallback)
    if choice.startswith(GGUF_PREFIX):
        if not path or Path(path).name != choice[len(GGUF_PREFIX):]:
            raise FileNotFoundError(f"{choice}: set {ENV_MODEL} in the start profile to this GGUF file")
        return "gguf", path
    return "comfy", choice


def find_mmproj(model: str) -> str | None:
    """Vision projector next to the model: prefer one that shares the quant tag (e.g. 'Ridge'), then any mmproj."""
    folder, stem = Path(model).parent, Path(model).stem
    candidates = sorted(folder.glob("mmproj*.gguf"))
    if not candidates:
        return None
    parts = stem.split("-")
    family = parts[0]   # e.g. Qwen3.8
    same_family = [c for c in candidates if family.lower() in c.name.lower()] or candidates
    sizes = [t for t in parts[1:] if t[:1].isdigit() and t.lower().endswith("b")]   # e.g. 27B
    same_family = [c for c in same_family if all(t.lower() in c.name.lower() for t in sizes)] or same_family
    tags = [t for t in parts[1:] if t not in sizes]
    for tag in tags:
        tagged = [c for c in same_family if tag.lower() in c.name.lower()]
        if tagged:
            return str(tagged[0])
    return str(same_family[0])


def comfy_device_index(device: str) -> int | None:
    """Torch index in this ComfyUI process of the HIP device the server gets (HIP reindexes HIP_VISIBLE_DEVICES)."""
    visible = [v.strip() for v in os.environ.get("HIP_VISIBLE_DEVICES", "").split(",") if v.strip()]
    if visible:
        return visible.index(device) if device in visible else None
    return int(device) if device.isdigit() else None


def shared_gpu_gib(pid: int) -> float | None:
    """Shared (host-backed) GPU memory of a process from the Windows GPU counters, None elsewhere or on error."""
    if os.name != "nt":
        return None
    command = (rf"(Get-Counter '\GPU Process Memory(pid_{pid}_*)\Shared Usage' -ErrorAction Stop).CounterSamples"
               " | Measure-Object CookedValue -Sum | ForEach-Object Sum")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        return float(out) / 2**30
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _kill_with_parent(process: subprocess.Popen):
    """Windows job object that kills the server when ComfyUI exits, even on a crash (else 12+ GiB VRAM stay taken)."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_ulonglong * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))   # ExtendedLimitInformation
            and kernel32.AssignProcessToJobObject(job, int(process._handle))):
        kernel32.CloseHandle(job)
        return None
    return lambda: kernel32.CloseHandle(job)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _jpeg_data_url(image) -> str:
    """ComfyUI IMAGE [B,H,W,C] float -> JPEG data URL (first image, longest side 1536)."""
    from PIL import Image
    import numpy as np
    array = (image[0, ..., :3].clamp(0, 1).mul(255).round().to("cpu").numpy()).astype(np.uint8)
    pil = Image.fromarray(array)
    pil.thumbnail((1536, 1536))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


class LlamaServer:
    """Context manager: llama-server for one prompt-writing run, stopped afterwards."""

    is_llama_server = True

    def __init__(self, model: str, ctx: int | None = None, device: str | None = None, log_dir: str | None = None):
        self.model = model
        self.mmproj = find_mmproj(model)
        self.ctx = int(ctx or os.environ.get(ENV_CTX, "").strip() or 8192)
        self.mmproj_gpu = os.environ.get(ENV_MMPROJ_GPU, "0").strip() == "1"
        self.device = device if device is not None else (os.environ.get(ENV_DEVICE, "").strip() or "1")
        self.server = os.environ.get(ENV_SERVER, "").strip().strip('"')
        self.log_path = Path(log_dir or os.environ.get("TEMP", ".")) / "dawasteh_llama_server.log"
        self.process = None
        self.port = None
        self.name = Path(model).name
        self._log = None
        self._release_job = None

    def _args(self, mtp: bool) -> list[str]:
        args = [self.server, "-m", self.model, "-ngl", "999", "-c", str(self.ctx), "-fa", "on", "-np", "1",
                "--reasoning", "off", "--host", "127.0.0.1", "--port", str(self.port)]
        if self.mmproj:
            args += ["--mmproj", self.mmproj]
            if not self.mmproj_gpu:
                args.append("--no-mmproj-offload")
        if mtp:
            args += ["--spec-type", "draft-mtp"]   # the model's own MTP head, no separate draft model
        return args

    def start(self) -> "LlamaServer":
        if not self.server or not os.path.isfile(self.server):
            raise FileNotFoundError(f"llama-server not found; set {ENV_SERVER} in the start profile")
        env = dict(os.environ, HIP_VISIBLE_DEVICES=str(self.device), CUDA_VISIBLE_DEVICES=str(self.device))
        for mtp in (True, False):
            self.port = _free_port()
            self._log = open(self.log_path, "w", encoding="utf-8", errors="replace")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.process = subprocess.Popen(self._args(mtp), stdout=self._log, stderr=subprocess.STDOUT, env=env, creationflags=flags)
            self._release_job = _kill_with_parent(self.process)
            deadline = time.time() + 600
            while time.time() < deadline and self.process.poll() is None:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=5) as r:
                        if b'"ok"' in r.read():
                            logging.info("%s %s ready on port %d (ctx=%d, mmproj=%s on %s, mtp=%s)", TAG, self.name, self.port,
                                         self.ctx, Path(self.mmproj).name if self.mmproj else None,
                                         "GPU" if self.mmproj_gpu else "CPU", mtp)
                            self._check_spill()
                            return self
                except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
                    pass
                time.sleep(2)
            self.stop()
            if mtp:
                logging.warning("%s start with the MTP head failed, retrying without speculative decoding", TAG)
        tail = self.log_path.read_text(encoding="utf-8", errors="replace")[-2000:] if self.log_path.is_file() else ""
        raise RuntimeError(f"llama-server did not start for {self.model}:\n{tail}")

    def _check_spill(self):
        shared = shared_gpu_gib(self.process.pid)
        if shared is not None and shared > SPILL_WARN_GIB:
            logging.warning("%s %.1f GiB of the server live in shared host memory (VRAM too full, prompt writing gets slow): "
                            "close GPU-heavy programs on HIP device %s or lower %s (now %d)", TAG, shared, self.device,
                            ENV_CTX, self.ctx)

    def generate(self, prompt: str, *, image=None, max_length: int = 400, temperature: float = 0.7, seed: int = 0,
                 system_prompt: str = "") -> str:
        content = prompt if image is None else [{"type": "image_url", "image_url": {"url": _jpeg_data_url(image)}},
                                                {"type": "text", "text": prompt}]
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [{"role": "user", "content": content}]
        body = {"messages": messages, "max_tokens": int(max_length), "temperature": float(temperature), "seed": int(seed),
                "top_k": 64, "top_p": 0.95, "min_p": 0.05, "repeat_penalty": 1.05,
                "chat_template_kwargs": {"enable_thinking": False}}
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=1800) as response:
            out = json.loads(response.read())
        text = out["choices"][0]["message"].get("content") or ""
        return text.split("</think>")[-1].strip()

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        self.process = None
        if self._release_job is not None:
            self._release_job()
            self._release_job = None
        if self._log is not None:
            self._log.close()
            self._log = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False
