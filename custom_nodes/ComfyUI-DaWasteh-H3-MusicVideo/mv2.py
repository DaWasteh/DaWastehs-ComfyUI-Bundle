"""Planning core of the v1.2.2 FastH3 music-video pipeline.

Pure Python + numpy: song analysis, lyric parsing, lyric-to-audio alignment,
scene splitting, frame accounting, shot variety and MiniMax prompt assembly.
Nothing here imports ComfyUI, so the whole plan is unit-testable.

Frame accounting (24 fps, H3 grid 17k + 5):

    scene k covers song frames [start_frame, end_frame)            (new frames)
    prefix = 0 for scene 0, else ``overlap`` frames of scene k-1's tail
    gen_frames = align(prefix + new), +17 when the latent length is odd  (sampled, see fast_gen_frames)
    audio for the whole generated clip starts at start_frame - prefix

The prefix frames and the grid padding are generated but never written; the
joined film therefore has exactly ceil(duration * 24) frames and the original
audio stream fits it without resampling.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

FPS = 24
H3_TRAINED_MAX_FRAMES = 362
SCHEMA = "dawasteh-h3-mv2/1"
PROMPT_VERSION = 10  # bump whenever a prompt template or the assembly changes

LANGUAGE_TAGS = {
    "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "nl": "Dutch", "pl": "Polish", "ru": "Russian", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "tr": "Turkish", "sv": "Swedish", "da": "Danish", "no": "Norwegian", "fi": "Finnish", "cs": "Czech",
}


def align_frames(count: int) -> int:
    count = max(5, int(count))
    return count + ((5 - count) % 17)


def latent_frames(frames: int) -> int:
    """H3 video latent length for an aligned pixel-frame count (5 -> 2, then +5 per 17 frames)."""
    return 2 if frames <= 5 else ((frames - 5) // 17) * 5 + 2


def fast_gen_frames(frames: int, limit: int = H3_TRAINED_MAX_FRAMES) -> int:
    """Aligned clip length for FastH3/VSA. Measured on the R9700 (864x480, 8 steps): odd latent lengths run
    slower than the next even one despite fewer tokens (192 frames 15.0 s/it vs 209 frames 12.5 s/it;
    226 frames 18.9 s/it). One extra 17-frame block (generated, never written) is the cheaper clip."""
    aligned = align_frames(frames)
    if latent_frames(aligned) % 2 and aligned + 17 <= limit:
        aligned += 17
    return aligned


def stable_hash(value: Any, length: int = 16) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def scene_seed(base_seed: int, index: int) -> int:
    return (int(base_seed) + int(index) * 1000003) & 0xFFFFFFFFFFFFFFFF


# ---------------------------------------------------------------------------
# Lyrics
# ---------------------------------------------------------------------------

_LRC = re.compile(r"^\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]\s*(.*)$")
_HEADER = re.compile(r"^\[([^\]]+)\]\s*$")
_WORD = re.compile(r"[a-z0-9À-ɏЀ-ӿ぀-ヿ一-鿿]+")


@dataclass
class LyricLine:
    text: str
    section: int
    start: float | None = None
    end: float | None = None
    source: str = "lyrics"

    def as_dict(self) -> dict[str, Any]:
        return {"text": self.text, "section": self.section, "start": self.start, "end": self.end, "source": self.source}


@dataclass
class Section:
    name: str
    kind: str  # "sung" or "instrumental"
    lines: list[int] = field(default_factory=list)
    start: float | None = None
    end: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "lines": self.lines, "start": self.start, "end": self.end}


def section_family(name: str) -> str:
    """Map '[Verse 2]' / '[Chorus x2]' / '[Guitar Solo / Outro]' to a family used for location reuse."""
    low = name.lower()
    for key in ("pre-chorus", "chorus", "verse", "bridge", "intro", "outro", "hook", "solo", "break", "interlude", "drop", "refrain"):
        if key in low:
            return key
    return re.sub(r"[^a-z]+", " ", low).strip() or "section"


def normalize_words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("'", "")
    return _WORD.findall(text)


def parse_lyrics(text: str) -> tuple[list[Section], list[LyricLine], bool]:
    """Return (sections, lines, has_timestamps). Headers like [Chorus] open sections."""
    sections: list[Section] = []
    lines: list[LyricLine] = []
    timed = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        lrc = _LRC.match(line)
        if lrc:
            body = lrc.group(4).strip()
            header = _HEADER.match(body) if body else None
            if body and not header:
                if not sections:
                    sections.append(Section("Song", "sung"))
                frac = lrc.group(3) or "0"
                start = int(lrc.group(1)) * 60 + int(lrc.group(2)) + int(frac) / (10 ** len(frac))
                sections[-1].lines.append(len(lines))
                sections[-1].kind = "sung"
                lines.append(LyricLine(body, len(sections) - 1, start=start, source="lrc"))
                timed = True
                continue
            line = body
            if not line:
                continue
        header = _HEADER.match(line)
        if header:
            sections.append(Section(header.group(1).strip(), "instrumental"))
            continue
        if not sections:
            sections.append(Section("Song", "sung"))
        sections[-1].lines.append(len(lines))
        sections[-1].kind = "sung"
        lines.append(LyricLine(line, len(sections) - 1))
    return sections, lines, timed


# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------

def align_lines_to_words(lines: list[LyricLine], words: list[dict[str, Any]], duration: float) -> float:
    """Assign start/end to every lyric line from ASR words [{word,start,end}]. Returns word coverage 0..1."""
    lyric_tokens: list[tuple[str, int]] = []
    for index, line in enumerate(lines):
        for token in normalize_words(line.text):
            lyric_tokens.append((token, index))
    asr_tokens: list[tuple[str, float, float]] = []
    for word in words:
        for token in normalize_words(str(word.get("word", ""))):
            asr_tokens.append((token, float(word["start"]), float(word["end"])))
    if not lyric_tokens or not asr_tokens:
        return 0.0
    matcher = difflib.SequenceMatcher(None, [t for t, _ in lyric_tokens], [t for t, _, _ in asr_tokens], autojunk=False)
    matched: dict[int, tuple[float, float]] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            matched[block.a + offset] = asr_tokens[block.b + offset][1:]
    # Fuzzy second pass: map unmatched lyric tokens inside replace-opcodes position-wise.
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag != "replace":
            continue
        span_a, span_b = a1 - a0, b1 - b0
        for offset in range(span_a):
            j = b0 + min(span_b - 1, int(offset * span_b / max(1, span_a)))
            if difflib.SequenceMatcher(None, lyric_tokens[a0 + offset][0], asr_tokens[j][0]).ratio() >= 0.5:
                matched.setdefault(a0 + offset, asr_tokens[j][1:])
    coverage = len(matched) / len(lyric_tokens)
    per_line: dict[int, list[tuple[float, float]]] = {}
    for token_index, (start, end) in matched.items():
        per_line.setdefault(lyric_tokens[token_index][1], []).append((start, end))
    for index, line in enumerate(lines):
        if line.source == "lrc":
            continue
        times = per_line.get(index)
        if times and len(times) >= max(1, len(normalize_words(line.text)) // 4):
            line.start = min(t[0] for t in times)
            line.end = max(t[1] for t in times)
            line.source = "asr"
        else:
            line.start = line.end = None
    _interpolate_missing(lines, duration)
    return coverage


def _interpolate_missing(lines: list[LyricLine], duration: float) -> None:
    """Fill unaligned lines proportionally to word count between aligned neighbours; enforce monotonic order."""
    n = len(lines)
    index = 0
    while index < n:
        if lines[index].start is not None:
            index += 1
            continue
        run_end = index
        while run_end < n and lines[run_end].start is None:
            run_end += 1
        left = lines[index - 1].end if index > 0 and lines[index - 1].end is not None else 0.0
        right = lines[run_end].start if run_end < n and lines[run_end].start is not None else duration
        right = max(right, left + 0.5 * (run_end - index))
        weights = [max(1, len(normalize_words(lines[k].text))) for k in range(index, run_end)]
        total = float(sum(weights))
        cursor = left
        for k, weight in zip(range(index, run_end), weights):
            span = (right - left) * weight / total
            lines[k].start, lines[k].end = cursor, cursor + span
            lines[k].source = "estimated"
            cursor += span
        index = run_end
    previous_end = 0.0
    for line in lines:
        start = min(max(0.0, float(line.start), previous_end), duration)
        line.start = start
        line.end = min(max(start + 0.2, float(line.end)), duration)
        previous_end = line.end


def distribute_lines_evenly(lines: list[LyricLine], vocal_start: float, vocal_end: float) -> None:
    weights = [max(1, len(normalize_words(line.text))) for line in lines]
    total = float(sum(weights)) or 1.0
    cursor = vocal_start
    for line, weight in zip(lines, weights):
        span = (vocal_end - vocal_start) * weight / total
        line.start, line.end, line.source = cursor, cursor + span * 0.92, "estimated"
        cursor += span


def resolve_sections(sections: list[Section], lines: list[LyricLine], duration: float) -> list[Section]:
    """Give every section a start/end on the song timeline; instrumental sections fill the gaps."""
    if not sections:
        return [Section("Song", "instrumental", start=0.0, end=duration)]
    for section in sections:
        if section.lines:
            section.start = lines[section.lines[0]].start
            section.end = lines[section.lines[-1]].end
    # Instrumental sections sit between the neighbouring sung ones.
    for index, section in enumerate(sections):
        if section.lines:
            continue
        before = next((s.end for s in reversed(sections[:index]) if s.end is not None), 0.0)
        after = next((s.start for s in sections[index + 1:] if s.start is not None), duration)
        section.start, section.end = before, max(before, after)
    resolved = [s for s in sections if s.end is not None and s.start is not None]
    first_start = resolved[0].start if resolved else duration
    if resolved and first_start > 1.5 and resolved[0].lines:
        resolved.insert(0, Section("Intro", "instrumental", start=0.0, end=first_start))
    # Close gaps so sections tile the timeline without overlap.
    for a, b in zip(resolved, resolved[1:]):
        if b.start is not None and a.end is not None and b.start < a.end:
            b.start = a.end
    if resolved:
        resolved[0].start = 0.0
        for a, b in zip(resolved, resolved[1:]):
            a.end = b.start
        resolved[-1].end = duration
    return [s for s in resolved if (s.end or 0) - (s.start or 0) > 1e-6]


def add_unmatched_sung_passages(lines: list[LyricLine], segments: list[dict[str, Any]], min_gap: float = 3.0) -> list[LyricLine]:
    """ASR segments that fall into long gaps between aligned lines (a repeated chorus that the text lists
    only once, ad-libs) become extra sung lines so the singer still performs there."""
    extras: list[LyricLine] = []
    covered = sorted((float(l.start), float(l.end)) for l in lines if l.start is not None)
    for seg in segments:
        start, end, text = float(seg["start"]), float(seg["end"]), str(seg.get("text", "")).strip()
        if len(normalize_words(text)) < 3:
            continue
        overlap = sum(max(0.0, min(end, b) - max(start, a)) for a, b in covered)
        if overlap < 0.25 * (end - start) and (end - start) >= 1.0 and not _near(covered, start, end, min_gap):
            extras.append(LyricLine(text, -1, start=start, end=end, source="asr-extra"))
    return extras


def _near(covered: list[tuple[float, float]], start: float, end: float, min_gap: float) -> bool:
    return any(a - min_gap < end and b + 0.05 > start and (a <= start <= b or a <= end <= b) for a, b in covered)


# ---------------------------------------------------------------------------
# Audio features (decoded mono float32)
# ---------------------------------------------------------------------------

def audio_features(samples: np.ndarray, sample_rate: int) -> dict[str, Any]:
    fft_size, hop = 1024, 256
    if samples.size < fft_size:
        samples = np.pad(samples, (0, fft_size - samples.size))
    frames = np.lib.stride_tricks.sliding_window_view(samples, fft_size)[::hop]
    weighted = frames * np.hanning(fft_size).astype(np.float32)
    rms = np.sqrt(np.mean(weighted * weighted, axis=1) + 1e-12).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(weighted, axis=1)).astype(np.float32)
    log_spectrum = np.log1p(spectrum)
    flux = np.zeros(frames.shape[0], dtype=np.float32)
    if frames.shape[0] > 1:
        flux[1:] = np.maximum(log_spectrum[1:] - log_spectrum[:-1], 0.0).sum(axis=1)
    rate = sample_rate / float(hop)
    onset = _normalize(_smooth(flux, max(1, int(rate * 0.08))))
    energy = _normalize(_smooth(rms, max(1, int(rate * 0.5))))
    novelty = np.zeros_like(energy)
    look = max(1, int(rate * 1.5))
    if energy.size > look:
        novelty[look:] = np.abs(energy[look:] - energy[:-look])
    novelty = _normalize(_smooth(novelty, max(1, int(rate * 0.35))))
    bpm, lag, phase = _tempo(onset, rate)
    beats = []
    search = max(1, int(round(0.12 * rate)))
    previous = -1
    for expected in range(phase, onset.size, max(1, lag)):
        lo, hi = max(0, expected - search), min(onset.size, expected + search + 1)
        refined = lo + int(np.argmax(onset[lo:hi]))
        if refined > previous:
            beats.append(refined / rate)
            previous = refined
    return {"rate": rate, "energy": energy, "onset": onset, "novelty": novelty, "bpm": bpm, "beats": beats}


def _normalize(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low, high = np.percentile(values, [10.0, 95.0])
    if not math.isfinite(float(low)) or not math.isfinite(float(high)) or high <= low + 1e-12:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0).astype(np.float32)


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or values.size < 3:
        return values.astype(np.float32, copy=True)
    kernel = np.ones(width, dtype=np.float32) / float(width)
    return np.convolve(values, kernel, mode="same").astype(np.float32)


def _tempo(onset: np.ndarray, rate: float) -> tuple[float, int, int]:
    centered = onset.astype(np.float64) - float(np.mean(onset)) if onset.size else onset
    if onset.size < 8 or not np.any(np.abs(centered) > 1e-7):
        return 120.0, max(1, round(rate * 0.5)), 0
    size = 1 << int(math.ceil(math.log2(max(2, centered.size * 2))))
    spec = np.fft.rfft(centered, n=size)
    ac = np.fft.irfft(spec * np.conjugate(spec), n=size)[:centered.size]
    lo, hi = max(1, int(round(rate * 60 / 190))), min(centered.size - 1, int(round(rate * 60 / 55)))
    if hi <= lo:
        return 120.0, max(1, round(rate * 0.5)), 0
    scores = ac[lo:hi + 1].copy()
    for offset, lag in enumerate(range(lo, hi + 1)):
        if lag * 2 < ac.size:
            scores[offset] += 0.35 * ac[lag * 2]
    lag = lo + int(np.argmax(scores))
    bpm = 60.0 * rate / lag
    while bpm < 78.0:
        bpm *= 2.0
        lag = max(1, int(round(lag / 2)))
    while bpm > 172.0:
        bpm /= 2.0
        lag *= 2
    phase_scores = [float(np.sum(onset[o::lag])) for o in range(lag)]
    return float(bpm), int(lag), int(np.argmax(phase_scores))


def mean_between(curve: np.ndarray, rate: float, start: float, end: float) -> float:
    if curve.size == 0:
        return 0.0
    a = max(0, min(curve.size - 1, int(start * rate)))
    b = max(a + 1, min(curve.size, int(math.ceil(end * rate))))
    return float(np.mean(curve[a:b]))


def max_between(curve: np.ndarray, rate: float, start: float, end: float) -> float:
    if curve.size == 0:
        return 0.0
    a = max(0, min(curve.size - 1, int(start * rate)))
    b = max(a + 1, min(curve.size, int(math.ceil(end * rate))))
    return float(np.max(curve[a:b]))


# ---------------------------------------------------------------------------
# Scene splitting
# ---------------------------------------------------------------------------

@dataclass
class SplitSettings:
    target: float = 7.0
    minimum: float = 4.0
    maximum: float = 9.0
    overlap_frames: int = 22

    def validate(self) -> None:
        if not (1.0 <= self.minimum <= self.target <= self.maximum):
            raise ValueError("Scene lengths must satisfy 1 <= min <= target <= max seconds")
        if align_frames(int(round(self.maximum * FPS)) + self.overlap_frames) > H3_TRAINED_MAX_FRAMES + 17:
            raise ValueError(
                f"max_scene_seconds {self.maximum} plus {self.overlap_frames} continuity frames exceeds the ~15 s "
                "MiniMax H3 training range; lower max_scene_seconds."
            )


def split_candidates(duration: float, lines: list[LyricLine], sections: list[Section], beats: list[float],
                     novelty: np.ndarray | None = None, rate: float = 1.0) -> dict[int, float]:
    """Frame -> extra cost of cutting there (negative = preferred)."""
    candidates: dict[int, float] = {}

    def put(t: float, cost: float) -> None:
        frame = int(round(t * FPS))
        if 0 < frame < int(math.ceil(duration * FPS - 1e-9)):
            candidates[frame] = min(candidates.get(frame, cost), cost)

    sung = sorted((float(l.start), float(l.end)) for l in lines if l.start is not None)

    def inside_line(t: float) -> bool:
        return any(a + 0.05 < t < b - 0.05 for a, b in sung)

    grid = 0.5
    t = grid
    while t < duration:
        put(t, 4.0 if inside_line(t) else 1.2)
        t += grid
    for beat in beats:
        extra = 0.0
        if novelty is not None and novelty.size:
            extra = -0.8 * max_between(novelty, rate, beat - 0.25, beat + 0.25)
        put(beat, (2.5 if inside_line(beat) else 0.4) + extra)
    ordered = sorted(sung)
    for (a0, a1), (b0, b1) in zip(ordered, ordered[1:]):
        gap = b0 - a1
        cut = b0 - min(0.15, max(0.0, gap) / 2.0) if gap > 0 else b0
        put(cut, -0.6 if gap > 0.25 else 0.2)
    for section in sections[1:]:
        if section.start is not None:
            lead = 0.12 if section.kind == "sung" else 0.0
            put(max(0.0, float(section.start) - lead), -3.0)
    return candidates


def plan_scene_frames(duration: float, candidates: dict[int, float], settings: SplitSettings) -> list[tuple[int, int]]:
    total = max(5, int(math.ceil(duration * FPS - 1e-9)))
    min_f, max_f, target_f = int(round(settings.minimum * FPS)), int(round(settings.maximum * FPS)), settings.target * FPS
    if total <= max_f:
        return [(0, total)]
    points = [0] + sorted(f for f in candidates if 0 < f < total) + [total]
    cost = {0: 0.0}
    back: dict[int, int] = {}
    for j in points[1:]:
        best, arg = math.inf, None
        extra = 0.0 if j == total else candidates.get(j, 0.0)
        for i in points:
            if i >= j:
                break
            length = j - i
            if length < min_f or length > max_f or i not in cost:
                continue
            value = cost[i] + extra + ((length - target_f) / FPS) ** 2 / 4.0
            if value < best:
                best, arg = value, i
        if arg is not None:
            cost[j], back[j] = best, arg
    if total not in cost:
        # Degenerate candidate set: fall back to an even split that respects max length.
        count = max(1, math.ceil(total / max_f))
        edges = [round(total * k / count) for k in range(count + 1)]
        return list(zip(edges[:-1], edges[1:]))
    edges = [total]
    while edges[-1] != 0:
        edges.append(back[edges[-1]])
    edges.reverse()
    return list(zip(edges[:-1], edges[1:]))


def build_scenes(duration: float, features: dict[str, Any], sections: list[Section], lines: list[LyricLine],
                 split: SplitSettings) -> list[dict[str, Any]]:
    """Scene skeletons with exact frame accounting; shots are attached later from the bible."""
    split.validate()
    candidates = split_candidates(duration, lines, sections, features["beats"], features["novelty"], features["rate"])
    frames = plan_scene_frames(duration, candidates, split)
    energy_median = float(np.median(features["energy"])) if features["energy"].size else 0.5
    scenes = []
    for index, (f0, f1) in enumerate(frames):
        start, end = f0 / FPS, f1 / FPS
        section_index = next((k for k, s in enumerate(sections) if (s.start or 0) <= start + 0.2 < (s.end or 0)), len(sections) - 1)
        section = sections[section_index] if sections else None
        prefix = 0 if index == 0 else min(split.overlap_frames, frames[index - 1][1] - frames[index - 1][0])
        gen = fast_gen_frames(prefix + (f1 - f0))
        energy = mean_between(features["energy"], features["rate"], start, end)
        sung = [l for l in lines if l.start is not None and start - 0.2 <= float(l.start) < end - 0.25]
        if index == 0:
            role = "opening"
        elif index == len(frames) - 1:
            role = "finale"
        elif energy > max(0.66, energy_median + 0.15):
            role = "peak"
        elif energy < 0.3:
            role = "calm"
        else:
            role = "development"
        scenes.append({
            "index": index, "start_frame": f0, "end_frame": f1, "frames": f1 - f0,
            "start": start, "end": end, "prefix_frames": prefix, "gen_frames": gen,
            "audio_start_frame": f0 - prefix,
            "section": section.name if section else "Song", "part": f"p{max(0, section_index)}",
            "family": section_family(section.name) if section else "song",
            "instrumental": not sung, "energy": round(energy, 4), "role": role,
        })
    return scenes


# ---------------------------------------------------------------------------
# Shot variety
# ---------------------------------------------------------------------------

SINGING_SIZES = ["medium close-up", "close-up", "medium shot", "low-angle medium close-up", "three-quarter profile close-up", "medium shot from a slightly high angle"]
BROLL_SIZES = ["wide establishing shot", "extreme close-up detail shot", "full shot", "over-the-shoulder shot", "high-angle wide shot", "low-angle full shot", "medium wide shot"]
CAMERA_LOW = [
    "The camera trucks left with small amplitude at slow speed",
    "The camera holds a static shot with gentle natural breathing of the frame",
    "The camera pedestals up with small amplitude at slow speed",
    "The camera arcs around the subject with small amplitude at slow speed",
    "The camera tilts up with small amplitude at slow speed",
    "The camera pans right with small amplitude at slow speed",
]
CAMERA_MID = [
    "The camera arcs around the subject at a steady pace",
    "The camera follows the subject in a smooth tracking shot",
    "The camera trucks right, revealing layered foreground elements",
    "The camera pedestals down while slowly pushing in",
    "The camera pans left with large amplitude, revealing more of the location",
    "The camera zooms in with small amplitude while drifting sideways",
]
CAMERA_HIGH = [
    "The camera arcs around the subject with large amplitude at fast speed",
    "The camera follows in an energetic handheld tracking shot that shakes slightly on the beat",
    "The camera pulls out with large amplitude at fast speed, revealing the whole location",
    "The camera rolls clockwise with small amplitude while trucking left at fast speed",
    "The camera pedestals up with large amplitude at fast speed",
    "The camera whips into a pan right with large amplitude at fast speed",
]


def camera_for(energy: float, index: int, previous: str | None) -> str:
    pool = CAMERA_HIGH if energy > 0.66 else CAMERA_LOW if energy < 0.33 else CAMERA_MID
    choice = pool[(index * 5 + 1) % len(pool)]
    if previous and choice.split(" ")[2] == previous.split(" ")[2]:
        choice = pool[(index * 5 + 2) % len(pool)]
    return choice


def shot_boundaries(scene_start: float, scene_end: float, lines: list[LyricLine], max_shot: float = 6.5) -> list[float]:
    """Relative cut times inside one scene, placed at lyric-line boundaries when possible."""
    length = scene_end - scene_start
    wanted = max(1, round(length / max_shot + 0.25))
    if wanted <= 1:
        return [0.0]
    options = []
    for line in lines:
        if line.start is None:
            continue
        rel = float(line.start) - scene_start - 0.1
        if 2.5 <= rel <= length - 2.5:
            options.append(rel)
    cuts = [0.0]
    for k in range(1, wanted):
        ideal = length * k / wanted
        pick = min(options, key=lambda value: abs(value - ideal)) if options else ideal
        if abs(pick - ideal) > length / (wanted * 2):
            pick = ideal
        if pick - cuts[-1] >= 2.0 and length - pick >= 2.0:
            cuts.append(round(pick, 3))
    return cuts


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def fmt_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    minutes = int(seconds // 60)
    return f"{minutes:02d}:{seconds - minutes * 60:06.3f}"


def clean_sentence(text: str, limit: int = 900) -> str:
    text = re.sub(r"<[^>]*>", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    text = text.replace('"', "'")
    if len(text) > limit:
        cut = text[:limit]
        text = cut[: cut.rfind(".") + 1] if "." in cut else cut
    if text and text[-1] not in ".!?":
        text += "."
    return text[:1].upper() + text[1:]


def lyric_block(lines: list[str], language: str) -> str:
    joined = " ".join(clean_sentence(line, 400).rstrip(".!?,;") + "," for line in lines if line.strip())
    joined = joined.rstrip(",") + "."
    return f"<d>[{language}] {joined}</d>"


ORDINALS = ["singer", "second character", "third character"]


def character_description(text: str) -> str:
    """'This character is a young woman ...' -> 'a young woman ...' (one clean clause, no trailing period)."""
    text = clean_sentence(text, 700).rstrip(".")
    text = re.sub(r"^(?:this|the)\s+(?:character|person|woman|man|girl|boy)\s+(?:is|appears to be)\s+", "", text, flags=re.I)
    text = re.sub(r"^(?:this is|it is|shown is)\s+", "", text, flags=re.I)
    return text[:1].lower() + text[1:] if text else text


def cast_sentences(bible: dict[str, Any], shots: list[dict[str, Any]]) -> str:
    characters = [character_description(c) for c in bible.get("characters") or []]
    singer = characters[0] if characters else character_description(bible.get("singer") or "")
    sentences = [f"The singer is {singer}." if singer else ""]
    joined = " ".join(str(s.get("action") or "") for s in shots).lower()
    for k, text in enumerate(characters[1:3], start=1):
        if f"character {k + 1}" in joined or ORDINALS[k] in joined:
            sentences.append(f"The {ORDINALS[k]} is {text}.")
    return " ".join(s for s in sentences if s)


def _name_characters(text: str) -> str:
    text = re.sub(r"\bCharacter 1\b", "the singer", text, flags=re.I)
    text = re.sub(r"\bCharacter 2\b", "the second character", text, flags=re.I)
    return re.sub(r"\bCharacter 3\b", "the third character", text, flags=re.I)


def assemble_prompt(scene: dict[str, Any], bible: dict[str, Any], *, index: int, total: int, language: str) -> str:
    """Base-guide T2VA prompt: integrated_multimodal_description / overall_soundscape / non_diegetic_music."""
    style = clean_sentence(bible.get("style") or "Live-action, cinematic music video.")
    cast = cast_sentences(bible, scene["shots"])
    parts: list[str] = []
    singer_introduced = False
    for shot_index, shot in enumerate(scene["shots"]):
        location = clean_sentence(shot.get("location") or "")
        action = clean_sentence(_name_characters(shot.get("action") or ""))
        camera = clean_sentence(shot.get("camera") or "")
        size = shot.get("size") or "medium shot"
        if shot_index == 0:
            text = f"[Shot 1] {style} {cast} ".replace("  ", " ")
            place = location[0].lower() + location[1:] if location else "the scene"
            if scene.get("prefix_frames"):
                # A new shot size here reads as an instant cut after the frozen frames; keep the running shot.
                text += (f"The running shot continues without any cut in {place.rstrip('.')}, keeping the framing, "
                         "subject position, wardrobe, lighting and camera direction of the previous frames. ")
            else:
                text += f"A {size} in {place} "
        else:
            text = f"[Shot {shot_index + 1}] At {fmt_ts(shot['start'] + scene.get('prefix_frames', 0) / FPS)}, the camera cuts to a {size} in {location[0].lower() + location[1:] if location else 'the scene'} "
        text += f"{action} {camera}"
        if shot.get("lyrics"):
            who = "The singer" if not singer_introduced else "The same singer"
            singer_introduced = True
            text += (f" {who} (S1) faces the camera, the mouth clearly visible, and sings with precise lip movements: "
                     f"{lyric_block(shot['lyrics'], language)}")
        elif scene.get("instrumental"):
            text += " No one sings in this shot; any visible singer keeps the lips closed and moves to the rhythm."
        parts.append(text.strip())
    ending = " The shot ends on a clean, deliberate final composition." if index == total - 1 else ""
    description = " ".join(parts) + ending
    description += (" Keep every face, hand and body anatomically correct and identities consistent; no subtitles, captions "
                    "or watermarks.")
    soundscape = clean_sentence(bible.get("soundscape") or "Faint ambient sound of the location sits under the music.")
    music = clean_sentence(bible.get("music") or "The original song plays throughout.")
    return (f"integrated_multimodal_description: {description}\n\n"
            f"overall_soundscape: {soundscape}\n\n"
            f"non_diegetic_music: {music}")


# ---------------------------------------------------------------------------
# Deterministic bible / shot text (template mode and LLM fallback)
# ---------------------------------------------------------------------------

DEFAULT_LOCATIONS = [
    "an intimate performance space lit by practical lamps and colored accent lights",
    "a rain-soaked city street at night with neon reflections on the wet asphalt",
    "a wide rooftop above the city skyline under a deep blue sky",
    "a dark studio stage with haze and moving spotlights",
    "an empty train platform with flickering fluorescent lights",
    "a quiet bedroom at dawn with soft window light and drifting dust",
    "a sunlit open field with tall grass moving in the wind",
    "a mirrored corridor with repeating reflections and cool color accents",
]
BROLL_ACTIONS = [
    "The environment reacts to the music with light pulses and subtle movement in the background.",
    "Small details of the location drift through the frame: hair and fabric moving, light flickering, particles floating.",
    "The character walks slowly through the space, glancing around with a thoughtful expression.",
    "Hands, objects and textures of the location are shown in a detailed, rhythmic composition.",
    "The scenery shifts gently as the lighting changes color with the music.",
]
SINGING_ACTIONS = [
    "The singer performs with emotional facial expressions and small natural hand gestures.",
    "The singer leans slightly toward the camera, eyes shifting between the lens and the distance.",
    "The singer moves the head and shoulders gently to the rhythm while performing.",
    "The singer performs while turning slowly, the light sweeping across the face.",
]


def story_parts(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ordered song sections that actually own scenes; the story advances part by part."""
    parts: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        part = parts.setdefault(scene["part"], {"key": scene["part"], "name": scene["section"], "family": scene["family"],
                                                "start": scene["start"], "end": scene["end"]})
        part["end"] = scene["end"]
    return list(parts.values())


def default_bible(idea: str, characters: list[str], parts: list[dict[str, Any]], music_hint: str) -> dict[str, Any]:
    idea = clean_sentence(idea or "", 600)
    family_slot: dict[str, str] = {}
    locations = {}
    for part in parts:
        if part["family"] not in family_slot:
            family_slot[part["family"]] = DEFAULT_LOCATIONS[len(family_slot) % len(DEFAULT_LOCATIONS)]
        locations[part["key"]] = family_slot[part["family"]]
    singer = character_description(characters[0]) if characters else "a charismatic lead singer who fits the song"
    return {
        "style": ("Live-action, cinematic music video: " + idea[:1].lower() + idea[1:]) if idea else "Live-action, cinematic music video with rich lighting.",
        "singer": singer,
        "characters": characters,
        "locations": locations,
        "music": music_hint,
        "soundscape": "Faint ambient sound of the location sits under the music.",
        "source": "template",
    }


def parse_bible_text(text: str, fallback: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    result = dict(fallback)
    result["locations"] = dict(fallback["locations"])
    found_locations: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-*# ").strip()
        match = re.match(r"^(STYLE|SINGER|MUSIC|LOCATION\s*\d+)\s*[:\-]\s*(.+)$", line, flags=re.I)
        if not match:
            continue
        key, value = match.group(1).upper(), clean_sentence(match.group(2), 500)
        if len(value) < 8:
            continue
        if key == "STYLE":
            result["style"] = value
        elif key == "SINGER":
            result["singer"] = value.rstrip(".")
        elif key == "MUSIC":
            result["music"] = value
        else:
            found_locations.append(value.rstrip("."))
    for k, part in enumerate(parts):
        if found_locations:
            result["locations"][part["key"]] = found_locations[min(k, len(found_locations) - 1)]
    if found_locations or text:
        result["source"] = "llm"
    return result


def parse_shot_text(text: str, count: int) -> list[str | None]:
    shots: list[str | None] = [None] * count
    for raw in (text or "").splitlines():
        match = re.match(r"^\s*(?:\*\*)?SHOT\s*(\d+)(?:\*\*)?\s*[:\-.]\s*(.+)$", raw.strip(), flags=re.I)
        if match:
            k = int(match.group(1)) - 1
            if 0 <= k < count and len(match.group(2).strip()) > 12:
                shots[k] = clean_sentence(match.group(2), 600)
    if count == 1 and shots[0] is None and len((text or "").strip()) > 20:
        shots[0] = clean_sentence(text, 600)
    return shots


def build_scene_shots(scene: dict[str, Any], lines: list[LyricLine], bible: dict[str, Any], *,
                      index: int, previous_camera: str | None, previous_location: str | None = None,
                      previous_part: str | None = None) -> list[dict[str, Any]]:
    """Shots of one scene. Shot 1 of an extended scene stays in the previous location (the frozen
    continuity frames come from there); a new song section then cuts to its own location."""
    start, end = scene["start"], scene["end"]
    cuts = shot_boundaries(start, end, lines)
    new_section = index > 0 and previous_part is not None and previous_part != scene["part"]
    if new_section and len(cuts) == 1 and end - start >= 4.0:
        early = [float(l.start) - start - 0.1 for l in lines if l.start is not None and 1.5 <= float(l.start) - start - 0.1 <= 3.5]
        cuts = [0.0, round(early[0] if early else 2.0, 3)]
    location_main = bible["locations"].get(scene["part"]) or next(iter(bible["locations"].values()), DEFAULT_LOCATIONS[0])
    all_locations = list(dict.fromkeys(bible["locations"].values())) or DEFAULT_LOCATIONS
    shots = []
    camera = previous_camera
    for k, rel in enumerate(cuts):
        rel_end = cuts[k + 1] if k + 1 < len(cuts) else end - start
        abs0, abs1 = start + rel, start + rel_end
        sung = [l.text for l in lines if l.start is not None and abs0 - 0.2 <= float(l.start) < abs1 - 0.25]
        energy = scene["energy"]
        camera = camera_for(energy, index * 3 + k, camera)
        if sung:
            size = SINGING_SIZES[(index + k) % len(SINGING_SIZES)]
            location = location_main
            action = SINGING_ACTIONS[(index + k) % len(SINGING_ACTIONS)]
        else:
            size = BROLL_SIZES[(index * 2 + k) % len(BROLL_SIZES)]
            location = location_main if k == 0 else all_locations[(index + k) % len(all_locations)]
            action = BROLL_ACTIONS[(index + k) % len(BROLL_ACTIONS)]
        if k == 0 and index > 0 and previous_location:
            location = previous_location
        shots.append({"start": round(rel, 3), "end": round(rel_end, 3), "size": size, "location": location,
                      "camera": camera + ".", "action": action, "lyrics": sung})
    return shots


def scene_llm_request(scene: dict[str, Any], bible: dict[str, Any], *, index: int, total: int,
                      idea: str, previous_summary: str, next_location: str | None = None) -> str:
    rows = []
    for k, shot in enumerate(scene["shots"]):
        lyric = " / ".join(shot["lyrics"]) if shot["lyrics"] else "(instrumental - nobody sings)"
        rows.append(f"SHOT {k + 1}: {shot['end'] - shot['start']:.1f} s, {shot['size']}, location: {shot['location']}; "
                    f"lyrics sung here: {lyric}")
    cast = "\n".join(f"CHARACTER {k + 1}: {c}" for k, c in enumerate(bible.get("characters") or [])) or "CHARACTER 1: the lead singer"
    return (
        f"Music video idea: {idea}\n"
        f"Visual style: {bible.get('style')}\n{cast}\n"
        f"Song part: scene {index + 1} of {total}, section '{scene['section']}', musical energy {scene['energy']:.2f} (0 calm .. 1 intense).\n"
        f"Previous scene (do NOT repeat its actions, continue the story from there): {previous_summary or 'none, this is the opening'}\n"
        f"Next scene takes place in: {next_location or 'nothing, this is the ending of the video'}\n\n"
        + "\n".join(rows)
        + "\n\nFor every SHOT write one or two vivid English sentences describing only what is visible: what the characters do, "
          "how they move and feel, and what happens in the location. Make this scene clearly different from the previous one "
          "in action and staging and move the story forward as the idea describes; if the next scene takes place somewhere "
          "else, let the last shot lead there. When lyrics are sung in a shot, the singer (Character 1) must be visible and performing. "
          "Do not mention the camera, the lyrics, credits, subtitles or any on-screen text. Refer to people as the singer, "
          "Character 2 or Character 3. Answer exactly in the form\n"
        + "\n".join(f"SHOT {k + 1}: ..." for k in range(len(scene["shots"])))
    )


BIBLE_SYSTEM = (
    "You are an experienced music video director. You write concise, concrete production notes in English. "
    "You never add explanations, markdown or extra lines."
)


def bible_llm_request(idea: str, lyrics: str, characters: list[str], parts: list[dict[str, Any]], music_facts: str) -> str:
    cast = "\n".join(f"CHARACTER {k + 1}: {c}" for k, c in enumerate(characters)) or "No character sheet: invent one lead singer that fits the song."
    location_lines = "\n".join(
        f"LOCATION {k + 1}: <one sentence describing only the place while '{part['name']}' plays ({fmt_ts(part['start'])[:5]}-{fmt_ts(part['end'])[:5]})>"
        for k, part in enumerate(parts))
    return (
        f"Music video idea from the artist: {idea or '(none, derive it from the lyrics)'}\n"
        f"{cast}\nSong facts: {music_facts}\nLyrics:\n{lyrics[:6000]}\n\n"
        "Write the production bible. The locations are listed in playback order: follow the story of the idea step by step, "
        "so that each location continues where the previous one ended. Every location must look clearly different "
        "(setting, light, colors) while fitting one story; reuse a place only if the story returns there. "
        "LOCATION lines describe only the place (architecture, objects, light, weather, colors): no people, no actions, "
        "no camera terms. Never ask for visible text, titles, credits, subtitles or logos anywhere. "
        "Answer with exactly these lines and nothing else:\n"
        "STYLE: <one sentence: live-action or animation style, camera look, color palette>\n"
        "SINGER: <one sentence describing the on-screen lead singer's appearance and outfit; copy CHARACTER 1 if given>\n"
        f"{location_lines}\n"
        "MUSIC: <one sentence describing the instrumentation, tempo and dynamics of the song>"
    )


CHARACTER_REQUEST = (
    "This is a character reference sheet for a music video. Describe this one person so that a video model can recreate "
    "them consistently: apparent age range, gender presentation, face, skin tone, eye color, hair color, length and style, "
    "then every clothing item one by one with its exact colors and material, then accessories. Mention logos, mascots or "
    "prints only as small printed details on a named garment, never as separate costume parts. One English paragraph of "
    "50 to 80 words. Do not describe the background, the sheet layout or any text, and do not invent a name."
)


def summarize_for_next(shots: list[dict[str, Any]]) -> str:
    return clean_sentence(" ".join(str(s.get("action") or "") for s in shots), 300)


def plan_text(manifest: dict[str, Any]) -> str:
    rows = [
        f"Song: {manifest['song_name']} · {manifest['duration']:.2f} s · ~{manifest['analysis']['bpm']:.0f} BPM · "
        f"{len(manifest['scenes'])} Szenen · Lyrics-Abdeckung {manifest['alignment']['coverage'] * 100:.0f} % ({manifest['alignment']['method']})",
        f"Format {manifest['width']}×{manifest['height']} · Übergang {manifest['overlap_frames']} Frames · Seed {manifest['seed']}",
        "",
    ]
    for scene in manifest["scenes"]:
        lyric = " / ".join(l for s in scene["shots"] for l in s["lyrics"])[:90]
        rows.append(f"{scene['index'] + 1:>3}. {fmt_ts(scene['start'])}–{fmt_ts(scene['end'])} ({scene['end'] - scene['start']:.1f} s, "
                    f"{len(scene['shots'])} Shot{'s' if len(scene['shots']) > 1 else ''}) [{scene['section']}] {lyric}")
    return "\n".join(rows)
