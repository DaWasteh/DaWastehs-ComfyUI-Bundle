import test from "node:test";
import assert from "node:assert/strict";
import {
  FramingController,
  frameProjectionElements,
  solveScreenFraming,
  visibleFramePairs,
} from "./framing-controller.js";

const model = new Map([
  ["LeftUpperArm", { x: 0.4, y: 0.3 }],
  ["RightUpperArm", { x: 0.6, y: 0.3 }],
  ["LeftUpperLeg", { x: 0.45, y: 0.55 }],
  ["RightUpperLeg", { x: 0.55, y: 0.55 }],
]);

function landmarks(points) {
  const values = Array.from({ length: 33 }, () => undefined);
  for (const [index, x, y, visibility = 1] of points) values[index] = { x, y, visibility };
  return values;
}

test("visible anchors reject occluded and incomplete points", () => {
  const pairs = visibleFramePairs(landmarks([
    [11, 0.2, 0.1, 0.9],
    [12, 0.8, 0.1, 0.9],
    [23, 0.3, 0.8, 0.9],
    [24, 0.7, 0.8, 0.2],
  ]), model);
  assert.equal(pairs.length, 3);
});

test("screen framing zooms and translates a close torso so the head can leave frame", () => {
  const pairs = visibleFramePairs(landmarks([
    [11, 0.25, 0.02],
    [12, 0.75, 0.02],
    [23, 0.35, 0.72],
    [24, 0.65, 0.72],
  ]), model);
  const framing = solveScreenFraming(pairs);
  assert.ok(framing.scale > 2);
  const transformedShoulderY = 0.5 + (0.3 - 0.5) * framing.scale + framing.offsetY;
  assert.ok(transformedShoulderY < 0.1);
  assert.equal(framing.matchedAnchors, 4);
});

test("framing holds briefly after loss then follows a frame-rate-independent return", () => {
  const controller = new FramingController({ smoothing: 0, lostHoldMs: 100, returnMs: 900 });
  controller.update({ scale: 2, offsetX: 0.1, offsetY: -0.2, matchedAnchors: 4 }, 10);
  assert.equal(controller.update(null, 80).scale, 2);
  let returning = controller.update(null, 210);
  for (let now = 226; now <= 610; now += 16) returning = controller.update(null, now);
  assert.ok(returning.scale > 1.5 && returning.scale < 2);
  assert.ok(returning.offsetY < 0);
});

test("projection framing scales NDC rows and applies screen translation", () => {
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const framed = frameProjectionElements(identity, { scale: 2, offsetX: 0.25, offsetY: -0.25 });
  assert.equal(framed[0], 2);
  assert.equal(framed[5], 2);
  assert.equal(framed[12], 0.5);
  assert.equal(framed[13], 0.5);
});
