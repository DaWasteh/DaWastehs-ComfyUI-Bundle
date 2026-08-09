import test from "node:test";
import assert from "node:assert/strict";
import { ModeController } from "./mode-controller.js";

const names = ["leftHip", "rightHip", "leftKnee", "rightKnee", "leftAnkle", "rightAnkle"];
const full = Object.fromEntries(names.map((name) => [name, { visibility: 0.9 }]));

test("enters full body only after stable frames", () => {
  const controller = new ModeController({ enterFrames: 2, minHoldMs: 0 });
  assert.equal(controller.update(full, 1), "upper");
  assert.equal(controller.update(full, 2), "full");
});

test("hysteresis and reset prevent flicker", () => {
  const controller = new ModeController({ enterFrames: 1, exitFrames: 2, minHoldMs: 0 });
  controller.update(full, 1);
  assert.equal(controller.update({}, 2), "full");
  assert.equal(controller.update({}, 3), "upper");
  controller.reset();
  assert.equal(controller.mode, "upper");
});

test("missing ankles leave the dead band and fall back to upper body", () => {
  const controller = new ModeController({ enterFrames: 1, exitFrames: 2, minHoldMs: 0 });
  controller.update(full, 1);
  const torsoOnly = { ...full, leftAnkle: undefined, rightAnkle: undefined };
  assert.equal(controller.update(torsoOnly, 2), "full");
  assert.equal(controller.update(torsoOnly, 3), "upper");
});

test("landmarks between entry and exit thresholds remain in the hysteresis dead band", () => {
  const controller = new ModeController({ enterFrames: 1, exitFrames: 2, minHoldMs: 0 });
  controller.update(full, 1);
  const marginal = Object.fromEntries(names.map((name) => [name, { visibility: 0.6 }]));
  assert.equal(controller.update(marginal, 2), "full");
  assert.equal(controller.update(marginal, 3), "full");
});

test("manual mode overrides missing landmarks", () => {
  const controller = new ModeController();
  assert.equal(controller.update({}, 1, "full"), "full");
  assert.equal(controller.update({}, 2, "upper"), "upper");
});
