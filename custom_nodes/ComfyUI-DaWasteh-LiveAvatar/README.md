# ComfyUI-DaWasteh-LiveAvatar

Two deliberately separate Windows/RDNA4 paths live in this package:

- **LivePortrait Continuous Spout** (`LiveAvatar-05`) remains experimental and strictly face-only.
- **VRM Full-Body Live Avatar** (`LiveAvatar-06`) is the productive browser path: MediaPipe Holistic runs locally in the browser and drives a local VRM renderer (head, gaze, blink, mouth visemes, torso, arms, hands/fingers, hips and legs). v0.8.5 adds adaptive source framing, stale-target decay, unique-camera-frame scheduling, honest tracking/render FPS, and a quality-neutral Full-HD pixel-ratio cap. It does not upload camera frames to ComfyUI or the network.
- **Buffered AI Mirror** (`LiveAvatar-07`) is a separate experimental SD1.5-LCM OpenPose/IPAdapter webcam graph. `LiveAvatar-11` adds a distinct cached/speed-tuned variant without replacing Workflow 07. Neither is VRM mocap or a live-FPS path.

## VRM path

1. Install audited CC0 presets into the global model root served by this node: `python tools/install_live_avatar_vrm_models.py --comfy-root L:/ComfyUI/ComfyUI`.
2. Open `LiveAvatar-06...json`, press **Run** once and open the returned `http://127.0.0.1:8188/dawasteh/vrm-live/` URL.
3. Grant camera permission only in the browser. Choose a preset or a local `.vrm` file; local uploads remain in that browser tab.
4. OBS: press **OBS-Präsentationsmodus** (or P) to hide controls, then capture the browser window. Enable **OBS Chroma Green** in the page and use an OBS Chroma Key filter if alpha is required.

Automatic mode uses hysteresis: it enables full-body only after stable hips/knees/ankles and falls back to a stable upper-body pose after sustained loss. A manual mode is available. **Follow webcam framing** solves a smoothed screen-space fit from visible shoulder, hip, knee and ankle anchors: walking closer zooms the avatar, and out-of-frame head/legs are cropped rather than replaced by a fixed full-body portrait. Webcam hand tracking is best-effort: occlusion, fast movement and out-of-frame hands reduce accuracy. The browser preserves joints through VRM construction, records each model's actual local rest quaternions, slew-limits/clamps wrist, finger, body and leg targets, rejects degenerate palms, and decays lost hands, ordinary body targets, gaze and expressions toward rest. The calmer default interpolation reduces abrupt extreme poses. Spring updates use a capped 50-ms physics delta and reset after swaps, calibration and long pauses.

The local img00031 v5 preset keeps the validated v2 body rig but adds a head-bone-bound, alpha-feathered face detail derived from the user's original local source. Its own blink and vowel morphs preserve expression control. This improves frontal resemblance without claiming a complete volumetric one-image reconstruction; extreme profiles remain less source-faithful.

The current pinned `@pixiv/three-vrm` importer supports legacy VRM 0.x (`VRM` extension); local VRM 1.0 (`VRMC_vrm`) uploads show a clear error until the importer is upgraded. The bundled frontend is built from local npm packages (`npm ci && npm run build` in `frontend/`); production does not use a CDN runtime dependency. Its `/dawasteh/vrm-live/` and preset routes enforce loopback clients and reject traversal paths.

## Presets and content boundary

`assets/live-avatar-vrm/model-manifest.json` records sources, exact hashes, licence statements and audited VRM0 secondary-animation counts. Amazonas, Olivia and Panda Bear have no spring groups/colliders. Lady Koi has one authored spring group but no collider group; only Lady Koi may therefore show limited authored secondary motion, with no collision claim. Amazonas and Olivia are CC0 lightly-clothed fantasy avatars. Lady Koi is an unclothed, non-explicit **nonhuman fantasy** avatar; no verified human age is claimed. Panda Bear is a deterministic black/white derivative of the CC0 Teddy asset, not a TeddyLong-Panda download.

## Local VRM creator (Workflow 08)

Workflow 08 is the no-credit, privacy-preserving way to make a new **realistic human/fantasy or stylized** appearance while retaining a known-working rig. It accepts three licensed/consented images of the same clearly adult person—recommended front, three-quarter and profile—batches them as equally averaged IPAdapter references, combines them with a prompt, and edits the embedded base-color UV texture locally through SD1.5/LCM at low denoise. Only a VRM0 base with one distinct embedded base-color image is accepted; multi-texture bases are rejected rather than partially edited, and original texture alpha is preserved. The save node is muted by default: first run and inspect the flat UV preview, then explicitly enable save and run again before inspecting the new variant on the rendered Workflow-06 model. It preserves the base skeleton, geometry, skinning, morph targets, UV layout and existing license fields; it does **not** reconstruct identity or create a new body mesh, fingers, hair geometry, or face rig. Realism remains limited by the selected base geometry and UV layout. Never use an unlicensed likeness; select the new file in Workflow 06 after pressing **Modellliste aktualisieren**. The complete German user path is documented in [`LIVE_AVATAR_ANLEITUNG.md`](../../LIVE_AVATAR_ANLEITUNG.md).

## Local 2D adult reference creator (Workflow 10)

Workflow 10 is a local RealVisXL V4 **2D reference generator**, never an automatic VRM creator. It provides three clothed, clearly-adult realistic presets plus a separate prompt-only, clearly-adult, neutral non-explicit artistic nude preset. Its optional licensed/consented portrait IPAdapter branch is bypassed by default and cannot reach the nude sampler. Strong shared negatives target writing, logos, UI, ambiguous age and malformed hands; every output still requires human rejection review.

## Local Blender portrait-style candidate

`tools/build_local_blender_vrm_avatar.py` builds a VRM0 derivative only from the hash-pinned CC0 Olivia base and entirely locally. The supplied upper-body portrait can guide conservative hair/clothing styling, but is **not** sufficient to reproduce identity, side/back geometry, legs or hands; those remain Olivia-derived. The candidate retains Olivia's hand/finger rig and adds a real custom `TongueOut` morph. In the browser, hold `T` (or the Zunge button) for manual tongue animation. Holistic does not supply a reliable tongue signal. The browser therefore supports manual `T` as the dependable path and an optional, disabled-by-default webcam color heuristic; lipstick, lighting and mouth shadows can still cause false triggers. See `docs/live-avatar-local-blender-vrm.md`.

## Optional Meshy candidate (Workflow 09)

Workflow 09 is deliberately optional and requires Comfy credits: it uploads a licensed/consented adult full-body A/T-pose image and model to Meshy. Meshy returns GLB/FBX rather than VRM. The strict local converter publishes VRM0 only after finding real skinning, required body bones, all finger chains and actual Blink/A/I/U/E/O targets. It rejects unsupported candidates with a capability report rather than pretending metadata creates animation. It was not run because this installation has no credits; Meshy provider privacy, retention, pricing and asset-rights terms apply.

## Persistent OBS output

Workflows 03, 04, 07 and 11 use `DaWastehPersistentSpout`: every completed prompt replaces a one-frame mailbox, while a background sender keeps the latest RGBA frame available to OBS between Run-(Instant)-iterations. RGBA now crosses GPU→CPU once per generated frame. Optional metrics keep generated frames, unique presentations and repeated sender frames separate; Workflows 07/11 write them under `L:/ComfyUI/logs/live-avatar-07/` and `live-avatar-11/`. Switching the shared sender between those workflow-specific paths resets the counters, and the sender refreshes presentation/duplicate JSON once per second even while AI inference is idle. Metrics destinations are restricted to `.json` files under the local ComfyUI log root. Workflow 06 is different: it is only a browser launcher and never creates a Spout sender; run it once normally and capture its Chrome/browser window. Before using webcam workflows 03, 04, 05, 07 or 11, close the Workflow-06 browser so it releases the selected camera.

## Buffered AI Mirror (experimental)

Required existing prerequisites are `models/checkpoints/v1-5-pruned-emaonly-fp16.safetensors` and `models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`. Stop Run (Instant), wait for empty queues, then run `python tools/install_live_avatar_ai_assets.py --comfy-root L:/ComfyUI/ComfyUI`; `--source-dir` is optional only for a verified offline cache. Restart the target ComfyUI for model combo refresh. Workflow 07 uses LCM-LoRA, OpenPose ControlNet, explicit IPAdapter Plus/CLIP Vision and a user-selectable reference. A fixed-fixture 8188 matrix compared denoise/IPAdapter/ControlNet at 0.45/0.50/0.75, 0.50/0.55/0.80 and 0.55/0.60/0.85; the middle setting was selected because it remained text/logo-free while preserving more source anatomy. Repeated warm throughput was about 0.36–0.50 FPS on 8188/R9700 and 0.125 FPS on 8189/RX 9070 XT, so it is explicitly buffered.

Workflow 11 uses `DaWastehCachedOpenPose`, which keeps the body/hand/face model weights resident after the cold start. Its speed preset uses 384×384, body+face and disabled hand detection; enabling hands remains available but costs roughly 0.54 seconds per frame. Unconsumed pretty-printed OpenPose diagnostics are disabled by default and can be explicitly enabled when debugging. Eight prior warm R9700 runs measured 0.62–0.68 seconds, median 0.645 seconds (about 1.55 new frames/s), versus roughly 2.05 seconds for Workflow 07. The cold run measured 13.8 seconds. This optimization removes repeated model loads and reduces CPU/websocket overhead without changing the pose image or diffusion settings; it deliberately does not overlap competing diffusion jobs on one GPU. Visible OBS composition remains manual.

## Live voice-conversion companion

Workflow 06 video remains separate from audio. v0.9.5 adds the independent `Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json` control workflow and `DaWastehLiveVoiceSwapLauncher`. The node verifies the complete pinned b2332 tree, identifies the listener executable, and can start, inspect, open, or stop only that local DirectML service. The older PowerShell helpers remain available. This is RVC speech-to-speech conversion, **not** Qwen TTS/Voice-LoRA and not OmniVoice TTS.

Supply only an RVC model you own or are explicitly licensed to use. No voice model is distributed in Git. For the local v0.9.5 demo, the official Amitaro Hakihaki v1.0 model was downloaded from its author page, kept outside the repository, credited, imported as Safetensors plus index, and converted by b2332 to its own compatible ONNX. On RX 9070 XT DirectML with `rmvpe_onnx`, 65 consecutive 100-ms chunks completed without errors; warm REST round-trip measured median 92.96 ms / p95 100.69 ms and the model stage median 70.24 ms / p95 78.74 ms. This validates conversion, not microphone/OBS routing or subjective voice quality.

The current machine exposes the RODE/BRIO inputs and headphone/display outputs but no virtual audio cable. Use headphones for a local demonstration. Install a virtual cable separately only when OBS routing is actually needed, capture only the converted cable output, and mute the original microphone. Physical microphone, cable, OBS, audible review and ten-minute stability remain manual gates. See `docs/LIVE_VOICE_SWAP_V095.md`, `docs/OMNIVOICE_LIVE_SWAP_EVALUATION.md`, and `docs/live-avatar-v072-voice-backend-evaluation.md`. Avoid heavy 8189 jobs while RVC uses the 9070.

## Existing continuous LivePortrait path

Use `LiveAvatar-05-LivePortrait-Continuous-Spout-OBS.json`. Start it once with normal **Run**. It deliberately holds the Comfy execution thread so use **Interrupt** to stop it and never use **Run (Instant)**. OBS receives `ComfyLiveAvatarFast` with Composite Mode `Default`.

## Workflow 12–15 · v0.8.5

`DaWastehWorkflow12Preflight` validates a local Workflow-12 config but never launches a process. It fails closed on missing/revoked/expired consent, asset substitution, unapproved face/voice scope, public-figure/minor identities, paths outside configured roots, non-loopback control URLs, changed executable/model hashes, non-DirectML providers, non-AMD vendor IDs, and missing R9700/9070-XT DXGI-LUID attestations. A true result means only that the external PowerShell supervisor may attempt its own verified readiness/warm-up sequence.

`DaWastehContinuousLiveAvatar` supports explicit `auto`/`DirectShow`/`Media Foundation` capture selection, an atomic metrics JSON, and optional smoothed OpenCV face/head ROI tracking. Workflow 12-II uses the BRIO through DirectShow index 2 at 1280×720, enlarges the detected driving face before LivePortrait's fixed 256px input, and publishes `ComfyLiveAvatarQuality`. AI production, Spout presentation, repeated presentations, capture drops, unique-frame intervals and capture-to-first-Spout-send latency remain separate metrics; the configured Spout rate is never called AI FPS. This improves face landmarks/jitter only—LivePortrait remains face/head-only and cannot animate hands, arms, torso deformation or walking.

Workflow 12-I remains an external DirectML candidate bake-off, 12-III reuses the browser VRM renderer, and Workflow 13 is an offline Qwen reference-sheet graph. `DaWastehLatestLiveAvatarOutput` safely resolves the newest allowlisted full-body front/left/back/right outputs so Workflow 14 never silently reuses `_00001_` after a later regeneration. See `docs/LIVE_AVATAR_WORKFLOW_12_13.md` in the repository root. No public stream is automatically started.
