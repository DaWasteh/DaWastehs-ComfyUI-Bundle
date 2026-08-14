# DaWasteh AutoSongwriter Genre Selector

Adds `DaW AutoSongwriter Genre Selector` for the two consolidated ACE-Step 1.5 XL SFT AutoSongwriter workflows.

## Bundled profiles

- POP · 120 BPM · C major
- GLOW · 96 BPM · G major
- DRIVE · 108 BPM · A minor
- CLUB · 126 BPM · F# minor
- NIGHT · 84 BPM · E minor
- RUSH · 138 BPM · D major
- CUSTOM · own genre / new style

The six presets retain the musical direction, BPM, key, and output filename prefix from the former per-genre workflows. Select `CUSTOM`, enter any new genre or detailed musical direction, and choose its BPM and key. With a bundled profile selected, the same text field adds optional details without replacing the curated preset. The language dropdown applies to every profile and is forwarded to both the songwriter prompt and ACE-Step.

The node outputs:

- a structured music-direction block for the songwriter LLM,
- the matching integer BPM,
- the ACE-Step key-scale combo value,
- the selected lyrics language,
- a profile-specific output filename prefix.

The node does not generate audio itself. The connected ACE-Step encoder remains responsible for validating and using BPM and key metadata.
