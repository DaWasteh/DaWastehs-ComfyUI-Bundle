# MiniMax Music 3 · official caption-rewriter sources

Pinned from [`MiniMax-AI/MiniMax-Music3`](https://github.com/MiniMax-AI/MiniMax-Music3/tree/main/skills/music-caption-rewriter) on 2026-08-14.

| File | SHA-256 |
|---|---|
| `SKILL.md` | `510f27d504bb06eb3859eb8a627773e655108e72df028d760be3ae98b3d4832c` |
| `genre-router.md` | `07cfe89ce0769982aa9c44c0f3d27476773acff3d785525da2442b9e77253ac6` |

The ComfyUI enhancer embeds the official core skill and genre router. It intentionally does not embed or claim to search the upstream library of roughly 1,000 complete templates: a one-pass `TextGenerate` node has no filesystem tools for the skill's progressive-disclosure procedure. The workflow therefore follows the official input, constraint, lyric-safety, section-timeline, output, and validation contracts while synthesizing directly from the user's brief.
