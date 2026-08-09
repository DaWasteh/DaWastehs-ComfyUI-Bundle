# Live Avatar Workflows 12–14 · v0.8.5

## Capability boundary

| Mode | Real function | Expected output | Important limit |
|---|---|---|---|
| 12-I | ComfyUI preflight for an external DirectML candidate | No sender from the graph itself; the external service must create the declared Spout sender | Running the graph only validates configuration; it never launches or processes video |
| 12-II | Continuous local LivePortrait face-quality mode with smoothed face ROI tracking | `ComfyLiveAvatarQuality`, normally presented at 30 Hz | Face/head only: no hands, arms, torso deformation or walking |
| 12-III | Existing local browser/VRM renderer | Chrome/OBS window capture at normal WebGL frame rate | Reliable rigged avatar, not a photoreal one-image clone |
| 13 | Offline Qwen Image Edit character-sheet generation | Six consistent turnaround/full-body views plus two expression references | The views guide multiview conditioning but still do not guarantee shared geometry |
| 14 | Installed ComfyUI-Core Hunyuan3D 2.1 multiview shape generation | Genuine locally generated GLB mesh geometry | Static, untextured and unrigged; not yet an animation-ready VRM |

Workflow 12-I deliberately contains no image path and no Spout producer. A completed ComfyUI run means only that preflight executed. DeepFaceLive, Deep-Live-Cam, and FaceFusion remain external measured candidates. The external adapter receives a unique per-run `{SPOUT_SENDER}` name and must return the resolved name, `output_width` and `output_height`; the supervisor waits on that sender's frame-sync event, receives multiple frames, requires changing pixel hashes and refuses READY when the real sender is absent or frozen. Licenses, models, DirectML support, image quality, and adapter selection must still be checked before enabling a local profile.

## Hardware ownership

- **Radeon AI Pro R9700:** video inference, Spout sender, and preferably OBS. Keeping
  OBS and the sender on this adapter avoids an unverified cross-adapter Spout copy.
- **RX 9070 XT:** separate DirectML RVC voice service. Do not run a heavy ComfyUI
  workload on port 8189 during a live voice session.
- The 32 GB and 16 GB VRAM spaces are **not** a 48 GB pool. Ports 8188 and 8189 isolate independent workloads; a ComfyUI bridge cannot accelerate one serial Live-Avatar graph past its slowest stage.
- `HIP_VISIBLE_DEVICES` and `CUDA_VISIBLE_DEVICES` do not select or prove a DirectML
  adapter. A candidate health response must attest `DmlExecutionProvider`, AMD vendor
  `0x1002`, the expected adapter name, and its DXGI LUID.
- Keep one camera owner. OBS consumes the processed Spout/browser output and must not
  open the BRIO simultaneously with the active video service.

## Create the local fail-closed configuration

1. Copy `assets/live-avatar-v080/workflow12-candidates.example.json` to:

   ```text
   L:/ComfyUI/config/live-avatar-12.json
   ```

2. Keep the example itself disabled. In the local copy, configure only paths under
   `allowed_roots` and replace every placeholder hash with the exact SHA-256.
3. Create one consent record with:
   - local identity ID and attestation ID,
   - subject marked as clearly adult or fully synthetic,
   - no public-figure identity,
   - status `active`, no revocation/deletion, and a timezone-aware expiry,
   - allowed destinations,
   - separate face and voice authorization,
   - every face/voice/VRM asset bound to its exact SHA-256.
4. Face authorization is required only for face-clone/quality modes. Voice
   authorization and a hash-bound voice asset are required only when RVC is enabled.
5. Configure a persistent visible disclosure such as `AI AVATAR / SYNTHETIC VOICE`.
   Add the same text as a visible OBS scene element. A README warning is not a viewer
   disclosure.
6. For every enabled service, configure executable/model hashes, a trusted working directory, string-array arguments, loopback health/warm-up/shutdown URLs, and an expected health identity. Runtime arguments must use typed placeholders (`{FACE_ASSET}`, `{VOICE_ASSET}`, `{VRM_ASSET}`, `{IDENTITY_ID}`, `{MODEL_0}` and `{RUN_TOKEN_FILE}`); this binds the launched service to the exact preflight-verified files instead of accepting another arbitrary path.
7. The external adapter reads the bearer secret from `{RUN_TOKEN_FILE}` (never from the command line), rejects absent/wrong tokens, rejects hostile browser Origins on health, warm-up and shutdown, reports its listener `process_id`, and returns the expected identity ID, authorized-asset-set hash, pinned-model-set hash, provider, vendor, adapter name and DXGI LUID. The supervisor actively probes all three denial cases on every control endpoint. Warm-up POST must acknowledge with Boolean `accepted=true` within three seconds; long work continues behind the cancellation-aware health poll. Each set hash is SHA-256 over the newline-joined, lexicographically sorted lowercase member SHA-256 strings.
8. OBS arguments may select a profile and scene collection, but `--startstreaming` and `--startrecording` are rejected. A public stream always requires a separate human action. Because a third-party OBS plugin/profile can have its own behavior, manually confirm the OBS output state after launch; the supervisor claims only that it did not request a stream command.

The ComfyUI `DaWastehWorkflow12Preflight` node validates the same local file and
returns only configuration readiness. `READY` means “eligible for the supervisor to
try a verified launch”; it never means that a service, camera, model, Spout sender, or
OBS is active.

## One-click supervisor and kill switch

Double-click:

```text
tools/Start-LiveAvatar-Workflow12.bat
```

The supervisor performs this order:

1. fail-closed Python consent/config preflight,
2. port collision refusal,
3. executable and model SHA-256 verification,
4. optional RVC start and application-specific health/warm-up,
5. video start and application-specific health/warm-up,
6. optional OBS start with the configured profile/scene collection,
7. `READY` only after all enabled checks pass.

Each run uses a current-user-only ACL directory and an immutable config snapshot. It writes `L:/ComfyUI/logs/live-avatar-12/<run-id>/manifest.json` with PID, process start time, executable/model/config/authorized-asset hashes, ports, redacted argument templates, log paths, mode, disclosure, and run state. The bearer secret is kept in a separate ACL-restricted token file, is not copied into the manifest, and is deleted on shutdown. The supervisor remains resident and checks the run-specific `STOP` file before/after every launch, inside readiness waits, and around warm-up.

Double-click the kill switch:

```text
tools/Stop-LiveAvatar-Workflow12.bat
```

Shutdown order is OBS/output, video, then RVC. The stop script verifies every PID,
start time, executable path, and executable hash before acting. It tries the
configured loopback shutdown endpoint and window close first, then uses a verified
local process stop if needed. It refuses malformed manifests, PID reuse, changed
executables, and non-loopback shutdown URLs.

## Mandatory DirectML bake-off

Prepare a neutral OBS test scene with no animated overlays. Capture each candidate's
preview/output and normalize it to one named Spout sender if the application does not
send Spout directly. Disable all face enhancers. Use the same consented reference,
BRIO movement sequence, lighting, occlusion cases, and candidate settings.

Run every candidate first at 720p and then at 1080p, on each GPU separately:

```powershell
powershell -ExecutionPolicy Bypass -File tools/benchmark_workflow12_spout.ps1 `
  -Candidate DeepFaceLive -Gpu R9700 -Height 720 `
  -SenderName LiveAvatar12Bakeoff -DurationSeconds 600 `
  -ProcessId 12345 -OutputPath L:/ComfyUI/logs/live-avatar-12/deepfacelive-r9700-720.json

powershell -ExecutionPolicy Bypass -File tools/benchmark_workflow12_spout.ps1 `
  -Candidate DeepFaceLive -Gpu R9700 -Height 1080 `
  -SenderName LiveAvatar12Bakeoff -DurationSeconds 600 `
  -ProcessId 12345 -OutputPath L:/ComfyUI/logs/live-avatar-12/deepfacelive-r9700-1080.json
```

Repeat for Deep-Live-Cam and FaceFusion, and then for RX-9070-XT. Test real movement,
profiles, glasses, hair, teeth, hands, and a microphone crossing the face. Keep the
raw PDH CSV produced beside each JSON.

The benchmark distinguishes:

- **presentation FPS:** received Spout presentations, including repeated images;
- **unique AI-FPS proxy:** consecutive pixel-hash changes;
- **duplicate ratio:** repeated latest frames;
- **p50/p95/p99 unique-frame intervals**;
- **PDH GPU evidence:** English wildcard GPU-engine and process-memory counters,
  optionally filtered by the verified process PID.

A candidate passes the 24-unique-FPS gate only after at least 600 seconds with:

- unique FPS at least 24,
- p95 unique-frame interval at most 41.67 ms,
- no interpolation or duplicate counted as a unique frame.

Pixel changes are still only an external proxy, not proof of inference completion. For
an authoritative full-frame latency, instrument capture and Spout timestamps in the
candidate adapter. Otherwise the report states capture-to-Spout as unavailable. A
manual high-speed clock/click test may be supplied through `-CaptureToSpoutMs`, but it
must be labeled manual.

If 720p already fails materially, classify that candidate as “fixed-rate presentation
with lower AI update rate”; do not promote it as 24 AI FPS.

## Workflow 12-II · quality mode

Open `LiveAvatar-12-II-LivePortrait-Quality-Mode.json` and select a consented source
image. The node captures the BRIO through DirectShow index 2 at 1280×720, runs once
normally, and stops through ComfyUI **Interrupt**. Never use Run (Instant) for this
blocking continuous node.

OBS uses `ComfyLiveAvatarQuality`. The node atomically updates:

```text
L:/ComfyUI/logs/live-avatar-12/quality-metrics.json
```

The JSON separates AI frames, presentation frames, unique and duplicate
presentations, dropped capture frames, AI FPS, presentation FPS, unique-frame
interval percentiles, and capture-to-first-Spout-send percentiles. A stable 30 Hz
sender does not turn 7–8 produced frames/s into 30 AI frames/s.

## Workflow 12-III · reliable mode

Workflow 12-III launches the same local browser VRM renderer used by Workflow 06. v0.8.5 selects the locally prepared `dawasteh-img00031-highrealism-local-v5.vrm` by default and enables adaptive source framing. Visible shoulder, hip, knee and ankle anchors drive a smoothed screen-space crop, so approaching the camera or moving the head/legs outside the webcam also changes which avatar region remains visible. Missing face, gaze, expression, torso, limb and hand targets decay to the model's captured rest pose instead of freezing. The browser displays separate tracking and render FPS and schedules MediaPipe only for unique camera frames. Start the camera in Chrome, calibrate, enable the OBS presentation view, and capture the Chrome window. The v5 preset retains the validated v2 body rig and adds a head-bound, alpha-feathered source-face detail with blink/vowel morphs; frontal resemblance improves substantially, while profiles remain less exact. This is the dependable 24/60 FPS renderer, but identity switching requires prepared rigged models and is not a photoreal one-image clone.

## Workflow 13 · character sheet

Use only own, expressly authorized, or fully synthetic input. v0.8.1 fixes the exposed batch-instance prompts that actually feed the nested Qwen graphs; changing only the overridden child widget previously had no effect and reproduced the old aerial/low/wide camera views. Workflow 13 now requests:

- level-camera full-body frontal A-pose,
- full-body three-quarter left and right,
- full-body profile left and right,
- full-body rear,
- frontal smile close-up,
- frontal mouth-open/different-gaze close-up.

Review every image before Workflow 14. Reject any low/high camera angle, crop, frontal image saved as a profile/rear view, or changed clothing/body proportions. Generated views guide multiview conditioning but are not guaranteed common geometry and cannot validate a real person's unseen side/back appearance.

## Workflow 14 · genuine local multiview 3D geometry

Workflow 14 uses the already installed `Hunyuan3D\\hunyuan_3d_v2.1.safetensors` through ComfyUI-Core. Four allowlisted `DaWastehLatestLiveAvatarOutput` nodes resolve the newest corrected semantic Workflow-13 files (never a hardcoded `_00001_`), then four `CLIPVisionEncode` nodes feed the real `Hunyuan3Dv2ConditioningMultiView` front/left/back/right inputs, followed by 4096 shape tokens, 40 sampling steps, voxel decode, surface-net mesh extraction and `SaveGLB`.

This differs fundamentally from Workflow 08: Workflow 14 generates new vertices and faces, and its KSampler uses `randomize`, so the seed changes geometry. Workflow 08 only denoises a flattened UV atlas at 0.20 and deliberately preserves the old VRM body/rig; prompts and seeds therefore have little visible effect and stronger denoise usually destroys UV seams.

The Workflow-14 result is a genuine static GLB under `output/LiveAvatar/`, but it remains:

- untextured (neutral mesh),
- unrigged and without skin weights,
- without humanoid bone mapping, finger rig or expression blendshapes,
- not directly usable as VRM/Workflow-12-III avatar.

The installed Hunyuan Paint/multiview bake wrapper relies on CUDA-oriented `nvdiffrast`/custom rasterizers and its paint models are not installed, so it is intentionally excluded on Windows RDNA4. Current local UniRig releases likewise depend on CUDA sparse-convolution packages. For animation, manually retopologize/rig/export in Blender or use the explicitly optional cloud rigging Workflow 09.

## Audio and final manual acceptance

- Set the physical microphone, VB-CABLE devices, RVC, and OBS to 48 kHz.
- Mute the original microphone in the final mix to prevent leakage/doubling.
- Record a clap/click and delay the faster path until audio and video align.
- Run the complete microphone → RVC → VB-CABLE → OBS chain for at least 60 minutes,
  then repeat the click test to detect clock drift.
- Confirm no feedback, no original-voice leak, acceptable quality, and a working
  kill switch.

## Rollback

Stop the run with the verified kill switch, disable the candidate in the local config,
and remove its Spout source from the active OBS scene. Workflow 06 remains the reliable
VRM fallback; Workflow 05 remains the previous LivePortrait path; Workflow 11 remains
the measured buffered diffusion mirror. Deleting or revoking an identity record must
also remove/disable its references and embeddings before the next launch.
