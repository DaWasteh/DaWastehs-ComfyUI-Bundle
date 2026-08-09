import test from "node:test";
import assert from "node:assert/strict";
import { FpsMeter, handInputs, loopController } from "./helpers.js";

test("non-selfie Holistic maps matching hands", () => {
  const results = { leftHandLandmarks: "L", rightHandLandmarks: "R" };
  assert.deepEqual(handInputs(results), [["Left", "L"], ["Right", "R"]]);
  assert.deepEqual(handInputs(results, true), [["Left", "R"], ["Right", "L"]]);
});

test("tracking loop reports a rejected step and schedules another frame", async () => {
  const callbacks = [];
  let errors = 0;
  const oldRequest = globalThis.requestAnimationFrame;
  const oldCancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callbacks.push(callback); return callbacks.length; };
  globalThis.cancelAnimationFrame = () => {};
  const loop = loopController(() => Promise.reject(new Error("bad")), () => { errors += 1; });
  loop.start();
  await callbacks.shift()();
  loop.stop();
  globalThis.requestAnimationFrame = oldRequest;
  globalThis.cancelAnimationFrame = oldCancel;
  assert.equal(errors, 1);
  assert.equal(callbacks.length, 1);
});

test("tracking loop uses unique camera frames when supported", async () => {
  const callbacks = new Map();
  let nextId = 0;
  const video = {
    requestVideoFrameCallback(callback) { callbacks.set(++nextId, callback); return nextId; },
    cancelVideoFrameCallback(id) { callbacks.delete(id); },
  };
  let runs = 0;
  const loop = loopController(async () => { runs += 1; }, undefined, video);
  loop.start();
  assert.equal(loop.scheduler, "camera");
  const callback = callbacks.values().next().value;
  await callback();
  loop.stop();
  assert.equal(runs, 1);
});

test("display fallback deduplicates unchanged camera media time", async () => {
  const callbacks = [];
  const oldRequest = globalThis.requestAnimationFrame;
  const oldCancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callbacks.push(callback); return callbacks.length; };
  globalThis.cancelAnimationFrame = () => {};
  const video = { currentTime: 1 };
  let runs = 0;
  const loop = loopController(async () => { runs += 1; }, undefined, video);
  loop.start();
  await callbacks.shift()();
  await callbacks.shift()();
  video.currentTime = 1.04;
  await callbacks.shift()();
  loop.stop();
  globalThis.requestAnimationFrame = oldRequest;
  globalThis.cancelAnimationFrame = oldCancel;
  assert.equal(runs, 2);
  assert.equal(loop.duplicates, 1);
  assert.equal(loop.scheduler, "display-deduplicated");
});

test("FPS meter reports unique event cadence over its rolling window", () => {
  const meter = new FpsMeter(1000);
  meter.tick(0);
  meter.tick(500);
  meter.tick(1000);
  assert.equal(meter.fps(1000), 2);
  meter.tick(2000);
  assert.equal(meter.fps(2000), 1);
});
