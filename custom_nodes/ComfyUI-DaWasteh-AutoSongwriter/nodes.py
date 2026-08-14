"""Genre selection for the consolidated ACE-Step 1.5 AutoSongwriter workflows."""
from __future__ import annotations

from inspect import cleandoc
from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from .profiles import (
    CUSTOM_PROFILE,
    DEFAULT_PROFILE,
    KEYS,
    LANGUAGES,
    PROFILE_OPTIONS,
    resolve_profile,
)


class DaWAutoSongwriterGenreSelector(io.ComfyNode):
    """Select a bundled music profile or enter a new genre with custom BPM and key.

    Bundled profiles emit their curated musical direction, BPM, key, and output
    prefix exactly. Select CUSTOM to use the free-text genre/style field plus
    custom metadata. The language dropdown applies to every profile. For a
    bundled profile, the free-text field is appended as extra direction.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="DaWAutoSongwriterGenreSelector",
            display_name="DaW AutoSongwriter Genre Selector",
            category="DaWasteh/music",
            description=cleandoc(cls.__doc__),
            inputs=[
                io.Combo.Input("profile", options=list(PROFILE_OPTIONS), default=DEFAULT_PROFILE),
                io.String.Input(
                    "custom_genre_or_direction",
                    default="",
                    multiline=True,
                    dynamic_prompts=False,
                    tooltip=(
                        f"Select {CUSTOM_PROFILE!r} to define a new genre. With a bundled profile, "
                        "this text adds optional instruments, mood, vocals, or production details."
                    ),
                ),
                io.Int.Input("custom_bpm", default=120, min=10, max=300, step=1),
                io.Combo.Input("custom_key", options=list(KEYS), default="C major"),
                io.Combo.Input("lyrics_language", options=list(LANGUAGES), default="en"),
            ],
            outputs=[
                io.String.Output("music_direction"),
                io.Int.Output("bpm"),
                io.Combo.Output("keyscale"),
                io.Combo.Output("language"),
                io.String.Output("filename_prefix"),
            ],
        )

    @classmethod
    def validate_inputs(cls, **_kwargs):
        # Unknown saved profile labels fall back to a custom profile. This keeps
        # workflows usable when users maintain a locally extended dropdown.
        return True

    @classmethod
    def execute(
        cls,
        profile: str = DEFAULT_PROFILE,
        custom_genre_or_direction: str = "",
        custom_bpm: int = 120,
        custom_key: str = "C major",
        lyrics_language: str = "en",
    ) -> io.NodeOutput:
        direction, bpm, keyscale, language, filename_prefix = resolve_profile(
            profile,
            custom_genre_or_direction,
            custom_bpm,
            custom_key,
            lyrics_language,
        )
        return io.NodeOutput(direction, bpm, keyscale, language, filename_prefix)


class DaWAutoSongwriterExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [DaWAutoSongwriterGenreSelector]


async def comfy_entrypoint() -> DaWAutoSongwriterExtension:
    return DaWAutoSongwriterExtension()
