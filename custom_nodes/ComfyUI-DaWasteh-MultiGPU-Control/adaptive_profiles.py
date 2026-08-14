"""Model-aware, crop-free resolution profiles for adaptive media loaders."""
from __future__ import annotations

import math
from dataclasses import dataclass


AUTO_PROFILE = "Auto (connected model)"
FALLBACK_PROFILE = "General image/video (1024)"
QUALITY_SCALES: dict[str, float] = {
    "Model native (100%)": 1.0,
    "High draft (75%)": 0.75,
    "Draft (50%)": 0.5,
    "Fast preview (35%)": 0.35,
}


@dataclass(frozen=True)
class ResolutionProfile:
    native_width: int
    native_height: int
    multiple: int


PROFILES: dict[str, ResolutionProfile] = {
    FALLBACK_PROFILE: ResolutionProfile(1024, 1024, 64),
    "SD 1.5 (512)": ResolutionProfile(512, 512, 64),
    "SDXL / FLUX (1024)": ResolutionProfile(1024, 1024, 64),
    "Qwen Image (1328)": ResolutionProfile(1328, 1328, 16),
    "Wan 2.x / Animate 2 (480p)": ResolutionProfile(832, 480, 16),
    "Wan 2.x (720p)": ResolutionProfile(1280, 720, 16),
    "LTX Video (768x512)": ResolutionProfile(768, 512, 32),
    "Hunyuan Video (720p)": ResolutionProfile(1280, 720, 16),
    "SCAIL 2 (480p)": ResolutionProfile(832, 480, 16),
    "MiniMax H3 (768)": ResolutionProfile(768, 768, 16),
}
PROFILE_OPTIONS = [AUTO_PROFILE, *PROFILES]
DETECTED_OPTIONS = ["Not detected", "Ambiguous (select manually)", *PROFILES]


def resolve_profile(selected: str, detected: str) -> tuple[str, bool]:
    """Return a valid profile and whether automatic detection succeeded."""
    if selected != AUTO_PROFILE:
        return (selected if selected in PROFILES else FALLBACK_PROFILE), False
    if detected in PROFILES:
        return detected, True
    return FALLBACK_PROFILE, False


def target_dimensions(
    source_width: int,
    source_height: int,
    profile_name: str,
    quality_name: str,
) -> tuple[int, int]:
    """Fit a profile's pixel budget to the source aspect ratio without cropping.

    The native profile may rotate for portrait inputs. Both dimensions are rounded
    to the model's required multiple. No pixels are removed and the aspect ratio is
    preserved to within the unavoidable alignment rounding.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"Invalid source dimensions: {source_width}x{source_height}")
    profile = PROFILES.get(profile_name, PROFILES[FALLBACK_PROFILE])
    scale = QUALITY_SCALES.get(quality_name, 1.0)
    native_w, native_h = profile.native_width, profile.native_height
    if source_height > source_width and native_w > native_h:
        native_w, native_h = native_h, native_w

    pixel_budget = native_w * native_h * scale * scale
    aspect = source_width / source_height
    width = math.sqrt(pixel_budget * aspect)
    height = width / aspect

    max_side = max(native_w, native_h) * scale
    if max(width, height) > max_side:
        factor = max_side / max(width, height)
        width *= factor
        height *= factor

    multiple = profile.multiple
    minimum = multiple * 2
    smallest = min(width, height)
    if smallest < minimum:
        raise ValueError(
            f"Source aspect ratio {source_width}:{source_height} cannot be represented by "
            f"profile '{profile_name}' at quality '{quality_name}' without cropping, padding, "
            f"or distorting it. Choose a less extreme source or a larger manual profile."
        )

    def aligned(value: float) -> int:
        return max(minimum, int(round(value / multiple)) * multiple)

    return aligned(width), aligned(height)
