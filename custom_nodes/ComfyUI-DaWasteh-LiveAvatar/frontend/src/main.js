import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { VRM, VRMSchema } from "@pixiv/three-vrm";
import * as Kalidokit from "kalidokit";
import { ModeController } from "./tracking/mode-controller.js";
import { FpsMeter, handInputs, neutralLegs, loopController } from "./tracking/helpers.js";
import { disposeObject, fitCamera, serialLifecycle } from "./tracking/runtime.js";
import { poseTargets } from "./tracking/pose-targets.js";
import { constrainedHandEuler, validPalmLandmarks } from "./tracking/hand-solver.js";
import { tongueColorScore, tongueSmoother } from "./tracking/tongue-detector.js";
import {
  BODY_FRAME_ANCHORS,
  FramingController,
  frameProjectionElements,
  solveScreenFraming,
  visibleFramePairs,
} from "./tracking/framing-controller.js";
import "./styles.css";

const Holistic = globalThis.Holistic;
if (typeof Holistic !== "function") throw new Error("Local MediaPipe Holistic runtime failed to load");

const $ = (id) => document.getElementById(id);
const status = $("status");
const metrics = $("metrics");
const canvas = $("avatar");
const video = $("cameraVideo");
const lifecycle = serialLifecycle();
const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.outputEncoding = THREE.sRGBEncoding;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
const keyLight = new THREE.DirectionalLight(0xffffff, 1.25);
keyLight.position.set(1, 2, 3).normalize();
const fillLight = new THREE.DirectionalLight(0xbcd7ff, 0.45);
fillLight.position.set(-2, 1, 2).normalize();
const rimLight = new THREE.DirectionalLight(0xffd8c0, 0.35);
rimLight.position.set(1, 2, -3).normalize();
scene.add(keyLight, fillLight, rimLight);

let vrm;
let tracker;
let stream;
let loop;
let lastFace;
let lastFaceAt = 0;
let lastPoseAt = 0;
let objectUrl;
let modelBox;
let baseProjection = camera.projectionMatrix.clone();
let modelFramePoints = new Map();
let currentFraming = { scale: 1, offsetX: 0, offsetY: 0, matchedAnchors: 0 };
let loadGeneration = 0;
let bodyMode = new ModeController();
let calibration = { x: 0, y: 0, z: 0 };
let tongueHeld = false;
let lastMouthA = 0;
let lastMetricsUpdate = 0;
let gazeTarget = { x: 0, y: 0 };
let gazeCurrent = { x: 0, y: 0 };
const targets = poseTargets();
const framing = new FramingController();
const trackingMeter = new FpsMeter();
const renderMeter = new FpsMeter();
const tongueFilter = tongueSmoother();
const mouthCanvas = document.createElement("canvas");
const mouthContext = mouthCanvas.getContext("2d", { willReadFrequently: true });
const handState = new Map();
const handTimes = new Map();
mouthCanvas.width = mouthCanvas.height = 64;
const clock = new THREE.Clock();
const TRACKED_BONES = [
  "Neck", "Hips", "Spine", "Chest",
  "LeftUpperArm", "LeftLowerArm", "RightUpperArm", "RightLowerArm",
  ...neutralLegs,
  ...["Left", "Right"].flatMap((side) => [
    "Hand",
    ...["Thumb", "Index", "Middle", "Ring", "Little"].flatMap((finger) =>
      ["Proximal", "Intermediate", "Distal"].map((joint) => finger + joint)),
  ].map((name) => side + name)),
];

function backingPixelRatio() {
  const cssPixels = Math.max(1, innerWidth * innerHeight);
  const fullHdRatio = Math.sqrt((1920 * 1080) / cssPixels);
  return Math.max(1, Math.min(devicePixelRatio || 1, 2, fullHdRatio));
}

function bone(name) {
  return vrm?.humanoid?.getBoneNode(VRMSchema.HumanoidBoneName[name]);
}

function captureModelFramePoints() {
  modelFramePoints = new Map();
  if (!vrm) return;
  camera.projectionMatrix.copy(baseProjection);
  camera.projectionMatrixInverse.copy(baseProjection).invert();
  camera.updateMatrixWorld(true);
  for (const [, name] of BODY_FRAME_ANCHORS) {
    const node = bone(name);
    if (!node || modelFramePoints.has(name)) continue;
    const projected = node.getWorldPosition(new THREE.Vector3()).project(camera);
    modelFramePoints.set(name, { x: (projected.x + 1) / 2, y: (1 - projected.y) / 2 });
  }
}

function fitBaseCamera() {
  if (!modelBox) return;
  fitCamera(camera, modelBox, camera.aspect);
  camera.updateMatrixWorld(true);
  baseProjection = camera.projectionMatrix.clone();
  captureModelFramePoints();
}

function resize() {
  renderer.setPixelRatio(backingPixelRatio());
  renderer.setSize(innerWidth, innerHeight, false);
  camera.aspect = innerWidth / Math.max(1, innerHeight);
  camera.updateProjectionMatrix();
  if (vrm) fitBaseCamera();
}
addEventListener("resize", resize);
resize();

function applyFraming(value) {
  const selected = $("followFraming").checked ? value : { scale: 1, offsetX: 0, offsetY: 0 };
  camera.projectionMatrix.fromArray(frameProjectionElements(baseProjection.elements, selected));
  camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
}

function rig(name, rotation = {}, scale = 1, now = performance.now()) {
  targets.rotation(name, rotation, scale, now);
  if (/Hand|Thumb|Index|Middle|Ring|Little/.test(name)) targets.hand(name, now);
}

function expr(name, value, now = performance.now()) {
  targets.expression(name, value, now);
}

function tongue(value, now = performance.now()) {
  const amount = Math.max(0, Math.min(1, value)) * +$("tongueIntensity").value;
  expr("TongueOut", amount, now);
  expr(VRMSchema.BlendShapePresetName.A, Math.max(lastMouthA, amount * 0.45), now);
}

function detectTongue(landmarks) {
  if (video.readyState < 2 || !mouthContext) return 0;
  const left = landmarks[78];
  const right = landmarks[308];
  const upper = landmarks[13];
  const lower = landmarks[14];
  if (!left || !right || !upper || !lower) return 0;
  const width = Math.max(0.001, Math.abs(right.x - left.x));
  const openness = Math.abs(lower.y - upper.y) / width;
  mouthContext.drawImage(video, 0, 0, 64, 64);
  const x0 = Math.max(0, Math.floor(Math.min(left.x, right.x) * 64));
  const x1 = Math.min(64, Math.ceil(Math.max(left.x, right.x) * 64));
  const y0 = Math.max(0, Math.floor(Math.min(upper.y, lower.y) * 64));
  const y1 = Math.min(64, Math.ceil(Math.max(upper.y, lower.y) * 64));
  if (x1 <= x0 || y1 <= y0) return 0;
  return tongueColorScore(mouthContext.getImageData(x0, y0, x1 - x0, y1 - y0).data, openness);
}

function results(result) {
  if (!vrm) return;
  const now = performance.now();
  trackingMeter.tick(now);
  const selfie = $("mirror").checked;
  const legNames = ["leftHip", "rightHip", "leftKnee", "rightKnee", "leftAnkle", "rightAnkle"];
  const legIndexes = [23, 24, 25, 26, 27, 28];
  const mode = bodyMode.update(
    Object.fromEntries(legNames.map((name, index) => [name, result.poseLandmarks?.[legIndexes[index]]])),
    now,
    $("tracking").value,
  );

  if (result.faceLandmarks) {
    lastFaceAt = now;
    const face = lastFace = Kalidokit.Face.solve(result.faceLandmarks, { runtime: "mediapipe", video });
    rig("Neck", {
      x: face.head.x - calibration.x,
      y: face.head.y - calibration.y,
      z: face.head.z - calibration.z,
    }, 0.7, now);
    expr(VRMSchema.BlendShapePresetName.Blink, Math.min(1, 1 - (face.eye.l + face.eye.r) / 2), now);
    lastMouthA = face.mouth.shape.A || 0;
    for (const vowel of ["A", "I", "U", "E", "O"]) {
      const value = face.mouth.shape[vowel] || 0;
      expr(
        VRMSchema.BlendShapePresetName[vowel],
        vowel === "A" && tongueHeld ? Math.max(value, +$("tongueIntensity").value * 0.45) : value,
        now,
      );
    }
    if (!tongueHeld) {
      if ($("tongueHeuristic").checked) tongue(tongueFilter.update(detectTongue(result.faceLandmarks)), now);
      else {
        tongueFilter.reset();
        tongue(0, now);
      }
    }
    gazeTarget = { x: face.pupil.y, y: face.pupil.x };
  }

  const worldLandmarks = result.poseWorldLandmarks || result.ea;
  if (result.poseLandmarks && worldLandmarks) {
    lastPoseAt = now;
    const pose = Kalidokit.Pose.solve(worldLandmarks, result.poseLandmarks, { runtime: "mediapipe", video });
    for (const [name, value, scale] of [["Hips", pose.Hips.rotation, 0.7], ["Spine", pose.Spine, 0.45], ["Chest", pose.Spine, 0.25]]) {
      rig(name, value, scale, now);
    }
    for (const name of ["LeftUpperArm", "LeftLowerArm", "RightUpperArm", "RightLowerArm"]) rig(name, pose[name], 1, now);
    for (const name of neutralLegs) rig(name, mode === "full" ? pose[name] : { x: 0, y: 0, z: 0 }, 1, now);
    const pairs = visibleFramePairs(result.poseLandmarks, modelFramePoints);
    currentFraming = framing.update(solveScreenFraming(pairs), now);
  } else {
    currentFraming = framing.update(null, now);
  }

  for (const [side, landmarks] of handInputs(result, selfie)) {
    if (!validPalmLandmarks(landmarks)) continue;
    const hand = Kalidokit.Hand.solve(landmarks, side);
    const dt = Math.max(1 / 120, Math.min(0.1, (now - (handTimes.get(side) || now - 33)) / 1000));
    handTimes.set(side, now);
    const joints = [
      ...["Thumb", "Index", "Middle", "Ring", "Little"].flatMap((finger) =>
        ["Proximal", "Intermediate", "Distal"].map((joint) => [`${side}${finger}${joint}`, hand[`${side}${finger}${joint}`]])),
      [`${side}Hand`, hand[`${side}Wrist`]],
    ];
    for (const [name, value] of joints) {
      const next = constrainedHandEuler(name, value, handState.get(name), dt);
      handState.set(name, next);
      rig(name, next, 1, now);
    }
  }
  status.textContent = `Tracking: ${mode === "full" ? "Ganzkörper" : "Oberkörper"} · live`;
}

async function stop() {
  loop?.stop();
  loop = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  video.srcObject = null;
  const oldTracker = tracker;
  tracker = null;
  await oldTracker?.close?.();
}

async function enumerate() {
  const devices = await navigator.mediaDevices.enumerateDevices();
  const old = $("camera").value;
  $("camera").replaceChildren(new Option("Standardkamera", ""));
  for (const device of devices.filter((entry) => entry.kind === "videoinput")) {
    $("camera").add(new Option(device.label || `Kamera ${$("camera").length}`, device.deviceId));
  }
  $("camera").value = old;
}

function start() {
  return lifecycle.run(async (_, live) => {
    await stop();
    if (!live()) return;
    stream = await navigator.mediaDevices.getUserMedia({
      video: { deviceId: $("camera").value || undefined, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30, max: 60 } },
      audio: false,
    });
    if (!live()) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    video.srcObject = stream;
    await video.play();
    await enumerate();
    if (!live()) return;
    tracker = new Holistic({ locateFile: (file) => `./mediapipe/${file}` });
    tracker.setOptions({
      modelComplexity: 1,
      smoothLandmarks: true,
      refineFaceLandmarks: true,
      selfieMode: $("mirror").checked,
      minDetectionConfidence: 0.65,
      minTrackingConfidence: 0.65,
    });
    tracker.onResults(results);
    trackingMeter.reset();
    framing.reset();
    loop = loopController(
      () => tracker?.send({ image: video }),
      (error) => { status.textContent = `Tracking-Frame verworfen: ${error.message}`; },
      video,
    );
    loop.start();
    status.textContent = "Kamera aktiv – nur neue Kameraframes, kein Frame-Backlog.";
  });
}

async function load(url, local = false) {
  const token = ++loadGeneration;
  try {
    const gltf = await new GLTFLoader().loadAsync(url);
    if (token !== loadGeneration) {
      disposeObject(gltf.scene);
      if (local) URL.revokeObjectURL(url);
      return;
    }
    const next = await VRM.from(gltf);
    if (token !== loadGeneration) {
      disposeObject(next.scene);
      if (local) URL.revokeObjectURL(url);
      return;
    }
    if (vrm) {
      scene.remove(vrm.scene);
      disposeObject(vrm.scene);
    }
    vrm = next;
    vrm.scene.rotation.y = Math.PI;
    scene.add(vrm.scene);
    vrm.scene.updateMatrixWorld(true);
    targets.captureRest(TRACKED_BONES, bone);
    targets.resetHands();
    handState.clear();
    handTimes.clear();
    gazeTarget = { x: 0, y: 0 };
    gazeCurrent = { x: 0, y: 0 };
    bodyMode.reset();
    currentFraming = framing.reset();
    vrm.springBoneManager?.setCenter?.(vrm.scene);
    vrm.springBoneManager?.reset?.();
    modelBox = new THREE.Box3().setFromObject(vrm.scene);
    fitBaseCamera();
    if (objectUrl && objectUrl !== url) URL.revokeObjectURL(objectUrl);
    objectUrl = local ? url : undefined;
    status.textContent = "VRM 0.x Ganzkörper-Modell geladen.";
  } catch (error) {
    if (local) URL.revokeObjectURL(url);
    status.textContent = `Modell-Fehler: ${error.message}. VRM 1.0 wird noch nicht unterstützt.`;
  }
}

async function refreshModels() {
  try {
    const current = $("preset").value;
    const data = await fetch("/dawasteh/vrm-model-list", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(response.status)));
    const labels = {
      "amazonas.vrm": "Amazonas",
      "olivia.vrm": "Olivia",
      "lady-koi.vrm": "Lady Koi (nichtmenschliche Fantasyfigur)",
      "panda-bear.vrm": "Panda Bear (CC0-Derivat)",
      "dawasteh-img00031-highrealism-local-v2.vrm": "DaWasteh High-Realism v2 (legacy)",
      "dawasteh-img00031-highrealism-local-v5.vrm": "DaWasteh High-Realism v5 · Source-Face (lokal)",
    };
    $("preset").replaceChildren(...data.models.map((name) => new Option(labels[name] || name, name)));
    if ([...$("preset").options].some((option) => option.value === current)) $("preset").value = current;
  } catch (error) {
    status.textContent = `Modellliste-Fehler: ${error.message}`;
  }
}

$("start").onclick = () => start().catch((error) => { status.textContent = `Kamera-Fehler: ${error.message}`; });
$("tongue").onpointerdown = () => {
  tongueHeld = true;
  $("tongue").setAttribute("aria-pressed", "true");
  tongue(1);
};
for (const event of ["pointerup", "pointerleave", "pointercancel"]) {
  $("tongue").addEventListener(event, () => {
    tongueHeld = false;
    $("tongue").setAttribute("aria-pressed", "false");
    tongue(0);
  });
}
$("preset").onchange = (event) => load(`/dawasteh/vrm-models/${encodeURIComponent(event.target.value)}`);
$("reloadModels").onclick = () => refreshModels();
$("upload").onchange = (event) => {
  const file = event.target.files[0];
  if (file && file.size <= 32 * 1024 * 1024) load(URL.createObjectURL(file), true);
  else if (file) status.textContent = "Upload zu groß (maximal 32 MiB).";
};
$("mirror").onchange = () => {
  video.style.transform = $("mirror").checked ? "scaleX(-1)" : "none";
  if (tracker) start().catch((error) => { status.textContent = `Kamera-Fehler: ${error.message}`; });
};
$("followFraming").onchange = (event) => {
  if (!event.target.checked) currentFraming = framing.reset();
};
$("present").onclick = () => {
  const enabled = document.body.classList.toggle("presentation");
  $("present").setAttribute("aria-pressed", String(enabled));
};
addEventListener("keydown", (event) => {
  if (event.key === "p" && !/input|select/i.test(event.target.tagName)) {
    $("present").click();
    event.preventDefault();
  }
  if (event.key.toLowerCase() === "t" && !event.repeat && !/input|select/i.test(event.target.tagName)) {
    tongueHeld = true;
    $("tongue").setAttribute("aria-pressed", "true");
    tongue(1);
    event.preventDefault();
  }
});
addEventListener("keyup", (event) => {
  if (event.key.toLowerCase() === "t") {
    tongueHeld = false;
    $("tongue").setAttribute("aria-pressed", "false");
    tongue(0);
  }
});
$("tongueHeuristic").onchange = (event) => {
  if (!event.target.checked) {
    tongueFilter.reset();
    if (!tongueHeld) tongue(0);
  }
};
$("chroma").onchange = (event) => renderer.setClearColor(event.target.checked ? 0x00ff00 : 0, event.target.checked ? 1 : 0);
$("calibrate").onclick = () => {
  if (lastFace && performance.now() - lastFaceAt < 500) {
    calibration = { ...lastFace.head };
    targets.resetHands();
    handState.clear();
    currentFraming = framing.reset();
    vrm?.springBoneManager?.reset?.();
    status.textContent = "Neutrale Kopfpose und Vollbild-Basis gespeichert.";
  } else status.textContent = "Kalibrierung benötigt ein aktuell sichtbares Gesicht.";
};

(function draw() {
  requestAnimationFrame(draw);
  const now = performance.now();
  const rawDt = clock.getDelta();
  const dt = Math.min(rawDt, 0.05);
  if (now - lastPoseAt > 350) currentFraming = framing.update(null, now);
  if (vrm) {
    if (rawDt > 0.25) vrm.springBoneManager?.reset?.();
    targets.apply({
      bone,
      expression: (name, value, alpha) => {
        try {
          const proxy = vrm.blendShapeProxy;
          const current = proxy?.getValue?.(name) || 0;
          proxy?.setValue(name, current + (value - current) * alpha);
        } catch {}
      },
      now,
      dt,
      smoothing: +$("smoothing").value,
    });
    if (now - lastFaceAt > 350) {
      lastMouthA = 0;
      gazeTarget = { x: 0, y: 0 };
    }
    const gazeAlpha = 1 - Math.exp(-Math.max(0.001, dt) * 12);
    gazeCurrent.x += (gazeTarget.x - gazeCurrent.x) * gazeAlpha;
    gazeCurrent.y += (gazeTarget.y - gazeCurrent.y) * gazeAlpha;
    vrm.lookAt?.applyer?.lookAt(new THREE.Euler(gazeCurrent.x, gazeCurrent.y, 0));
    if (tongueHeld) tongue(1, now);
    vrm.scene.updateMatrixWorld(true);
    vrm.update(dt);
  }
  applyFraming(currentFraming);
  renderer.render(scene, camera);
  renderMeter.tick(now);
  if (now - lastMetricsUpdate >= 500) {
    const trackerFps = trackingMeter.fps(now);
    const renderFps = renderMeter.fps(now);
    metrics.textContent = `Tracking ${trackerFps.toFixed(1)} FPS · Render ${renderFps.toFixed(1)} FPS · ${renderer.domElement.width}×${renderer.domElement.height} · Scheduler ${loop?.scheduler || "aus"} · doppelte Kamera-Frames ${loop?.duplicates || 0} · ausgelastet ${loop?.dropped || 0}`;
    lastMetricsUpdate = now;
  }
}());

async function initialize() {
  await refreshModels();
  const params = new URLSearchParams(location.search);
  const requested = params.get("model");
  const options = [...$("preset").options];
  const preferred = "dawasteh-img00031-highrealism-local-v5.vrm";
  const selected = options.some((option) => option.value === requested)
    ? requested
    : options.some((option) => option.value === preferred)
      ? preferred
      : options.some((option) => option.value === "amazonas.vrm")
        ? "amazonas.vrm"
        : options[0]?.value;
  if (selected) {
    $("preset").value = selected;
    await load(`/dawasteh/vrm-models/${encodeURIComponent(selected)}`);
  }
  if (params.get("chroma") === "1") {
    $("chroma").checked = true;
    renderer.setClearColor(0x00ff00, 1);
  }
  if (params.get("follow") === "0") $("followFraming").checked = false;
  if (params.get("present") === "1") {
    document.body.classList.add("presentation");
    $("present").setAttribute("aria-pressed", "true");
  }
}
initialize().catch((error) => { status.textContent = `Start-Fehler: ${error.message}`; });
addEventListener("beforeunload", () => {
  lifecycle.invalidate();
  stop();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
});
