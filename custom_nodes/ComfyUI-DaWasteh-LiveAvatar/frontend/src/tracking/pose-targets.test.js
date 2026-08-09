import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { poseTargets } from "./pose-targets.js";

test("10fps targets interpolate over render frames", () => {
  const targets = poseTargets();
  const bone = new THREE.Object3D();
  targets.rotation("Hand", { z: 1 }, 1, 0);
  targets.apply({ bone: (name) => name === "Hand" ? bone : null, expression() {}, now: 100, dt: 1 / 60, smoothing: 0.3 });
  const first = bone.rotation.z;
  targets.apply({ bone: (name) => name === "Hand" ? bone : null, expression() {}, now: 116, dt: 1 / 60, smoothing: 0.3 });
  assert.ok(first > 0 && bone.rotation.z > first && bone.rotation.z < 1);
});

test("body targets clamp implausible angles and slew sudden leg jumps", () => {
  const targets = poseTargets();
  const bone = new THREE.Object3D();
  const lookup = (name) => name === "LeftUpperLeg" ? bone : null;
  targets.captureRest(["LeftUpperLeg"], lookup);
  targets.rotation("LeftUpperLeg", { x: 10 }, 1, 0);
  targets.apply({ bone: lookup, expression() {}, now: 0, dt: 1, smoothing: 0.8 });
  assert.ok(Math.abs(bone.rotation.x) < 0.1);
  for (let now = 50; now <= 500; now += 50) {
    targets.rotation("LeftUpperLeg", { x: 10 }, 1, now);
    targets.apply({ bone: lookup, expression() {}, now, dt: 1, smoothing: 0.8 });
  }
  assert.ok(Math.abs(bone.rotation.x) <= 1.16);
});

test("stale hands decay toward captured model rest instead of identity", () => {
  const targets = poseTargets({ handTimeoutMs: 20 });
  const bone = new THREE.Object3D();
  bone.rotation.z = 0.25;
  targets.captureRest(["leftHand"], (name) => name === "leftHand" ? bone : null);
  targets.rotation("leftHand", { z: 1 }, 1, 0);
  targets.hand("leftHand", 0);
  targets.apply({ bone: (name) => name === "leftHand" ? bone : null, expression() {}, now: 0, dt: 0.1, smoothing: 0.4 });
  const before = bone.rotation.z;
  targets.apply({ bone: (name) => name === "leftHand" ? bone : null, expression() {}, now: 100, dt: 0.01, smoothing: 0.4 });
  assert.ok(bone.rotation.z < before && bone.rotation.z > 0.25);
  assert.ok(Math.abs(targets.rest("leftHand").angleTo(new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, 0.25)))) < 1e-6);
});

test("stale body targets and facial expressions decay after occlusion", () => {
  const targets = poseTargets({ bodyTimeoutMs: 20, expressionTimeoutMs: 20 });
  const bone = new THREE.Object3D();
  targets.captureRest(["Neck"], (name) => name === "Neck" ? bone : null);
  targets.rotation("Neck", { z: 1 }, 1, 0);
  targets.expression("Blink", 1, 0);
  targets.apply({ bone: (name) => name === "Neck" ? bone : null, expression() {}, now: 0, dt: 0.1, smoothing: 0.4 });
  const before = bone.rotation.z;
  let expressionValue = 1;
  targets.apply({ bone: (name) => name === "Neck" ? bone : null, expression: (_name, value) => { expressionValue = value; }, now: 100, dt: 0.01, smoothing: 0.4 });
  assert.ok(bone.rotation.z < before);
  assert.equal(expressionValue, 0);
});

test("expression callback receives a frame damping factor", () => {
  const targets = poseTargets();
  let call;
  targets.expression("TongueOut", 1);
  targets.apply({ bone: () => null, expression: (name, value, alpha) => { call = { name, value, alpha }; }, dt: 1 / 60, smoothing: 0.3 });
  assert.equal(call.name, "TongueOut");
  assert.equal(call.value, 1);
  assert.ok(call.alpha > 0 && call.alpha < 1);
});
