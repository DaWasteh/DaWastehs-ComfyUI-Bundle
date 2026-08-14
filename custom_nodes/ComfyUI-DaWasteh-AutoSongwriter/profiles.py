"""Genre profiles shared by the DaWasteh AutoSongwriter node and its tests."""
from __future__ import annotations

from dataclasses import dataclass
import re


CUSTOM_PROFILE = "CUSTOM · own genre / new style"
DEFAULT_PROFILE = "POP · 120 BPM · C major"
LANGUAGES = (
    "ar", "az", "bg", "bn", "ca", "cs", "da", "de", "el", "en", "es", "fa", "fi", "fr",
    "he", "hi", "hr", "ht", "hu", "id", "is", "it", "ja", "ko", "la", "lt", "ms", "ne",
    "nl", "no", "pa", "pl", "pt", "ro", "ru", "sa", "sk", "sr", "sv", "sw", "ta", "te",
    "th", "tl", "tr", "uk", "ur", "vi", "yue", "zh", "unknown",
)
KEYS = (
    "C major", "C# major", "Db major", "D major", "D# major", "Eb major",
    "E major", "F major", "F# major", "Gb major", "G major", "G# major",
    "Ab major", "A major", "A# major", "Bb major", "B major",
    "C minor", "C# minor", "Db minor", "D minor", "D# minor", "Eb minor",
    "E minor", "F minor", "F# minor", "Gb minor", "G minor", "G# minor",
    "Ab minor", "A minor", "A# minor", "Bb minor", "B minor",
)


@dataclass(frozen=True)
class GenreProfile:
    code: str
    label: str
    bpm: int
    keyscale: str
    direction: str


PROFILES = (
    GenreProfile(
        "POP",
        DEFAULT_PROFILE,
        120,
        "C major",
        "Bright synth-pop and indie dance, glassy arpeggiators, punchy electronic drums, "
        "warm bass, playful verses, a soaring chorus, hook-forward lyrics, and a clean wide mix.",
    ),
    GenreProfile(
        "GLOW",
        "GLOW · 96 BPM · G major",
        96,
        "G major",
        "Warm dream-pop and folktronica, fingerpicked acoustic guitar, soft analog pads, brushed "
        "electronic drums, intimate full narrative lyrics, a gentle chorus lift, and an airy natural mix.",
    ),
    GenreProfile(
        "DRIVE",
        "DRIVE · 108 BPM · A minor",
        108,
        "A minor",
        "Midtempo alternative synth-rock, pulsing bass, dry drums, muted guitar in the verses, a "
        "cinematic pre-chorus, full narrative lyrics, and an energetic final chorus.",
    ),
    GenreProfile(
        "CLUB",
        "CLUB · 126 BPM · F# minor",
        126,
        "F# minor",
        "Melodic house and liquid electro-pop, four-on-the-floor kick, rippling arpeggios, deep bass, "
        "rain-texture ambience, sparse poetic vocals, long instrumental breaks, and a glossy club mix.",
    ),
    GenreProfile(
        "NIGHT",
        "NIGHT · 84 BPM · E minor",
        84,
        "E minor",
        "Noir trip-hop and alternative R&B, dusty breakbeat, deep sub bass, muted Rhodes, close-miked "
        "vocal, full introspective narrative lyrics, a tense chorus, and shadowy production.",
    ),
    GenreProfile(
        "RUSH",
        "RUSH · 138 BPM · D major",
        138,
        "D major",
        "High-energy electronic pop-rock, driving live drums, crunchy guitars, bright synth leads, "
        "stop-start transitions, hook-forward lyrics, and bold clean production.",
    ),
)
PROFILE_OPTIONS = tuple(profile.label for profile in PROFILES) + (CUSTOM_PROFILE,)
_PROFILE_BY_LABEL = {profile.label: profile for profile in PROFILES}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def resolve_profile(
    profile: str = DEFAULT_PROFILE,
    custom_genre_or_direction: str = "",
    custom_bpm: int = 120,
    custom_key: str = "C major",
    lyrics_language: str = "en",
) -> tuple[str, int, str, str, str]:
    """Resolve one preset or a user-defined genre into ACE-Step-ready values."""
    selected = _PROFILE_BY_LABEL.get(str(profile))
    custom_text = _clean_text(custom_genre_or_direction)

    if selected is None:
        bpm = max(10, min(300, int(custom_bpm)))
        keyscale = str(custom_key) if str(custom_key) in KEYS else "C major"
        direction = custom_text or (
            _clean_text(profile) if str(profile) != CUSTOM_PROFILE else "User-defined contemporary song style"
        )
        code = "CUSTOM"
    else:
        bpm = selected.bpm
        keyscale = selected.keyscale
        direction = selected.direction
        code = selected.code
        if custom_text:
            direction = f"{direction} Additional user direction: {custom_text}"

    language = str(lyrics_language) if str(lyrics_language) in LANGUAGES else "en"
    filename_prefix = f"audio/ACE_Album/{code}_Track"
    prompt = (
        f"PROFILE: {code}\n"
        f"TARGET METADATA: {bpm} BPM, {keyscale}, 4/4\n"
        f"LYRICS LANGUAGE: {language}\n"
        f"MUSICAL DIRECTION: {direction}"
    )
    return prompt, bpm, keyscale, language, filename_prefix
