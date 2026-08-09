import * as THREE from "three";

const BODY_LIMITS = {
  Neck: [0.45, 0.65, 0.45],
  Hips: [0.55, 0.55, 0.45],
  Spine: [0.40, 0.45, 0.38],
  Chest: [0.30, 0.35, 0.30],
  UpperArm: [1.45, 1.10, 1.55],
  LowerArm: [2.15, 0.90, 0.85],
  UpperLeg: [1.15, 0.55, 0.65],
  LowerLeg: [1.75, 0.32, 0.32],
  Foot: [0.60, 0.38, 0.38],
};

const limitFor = (name) => Object.entries(BODY_LIMITS).find(([suffix]) => name.endsWith(suffix))?.[1];
const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
const shortestDelta = (from, to) => Math.atan2(Math.sin(to - from), Math.cos(to - from));

export function poseTargets({ handTimeoutMs = 250, bodyTimeoutMs = 350, expressionTimeoutMs = 250 } = {}) {
  const rotations = new Map();
  const rotationTimes = new Map();
  const inputEulers = new Map();
  const inputTimes = new Map();
  const expressions = new Map();
  const expressionTimes = new Map();
  const hands = new Map();
  const rests = new Map();
  const restFor = (name) => rests.get(name) || new THREE.Quaternion();
  return {
    captureRest(names, bone) {
      rests.clear();
      for (const name of names) {
        const node = bone(name);
        if (node) rests.set(name, node.quaternion.clone());
      }
    },
    rest(name) { return restFor(name).clone(); },
    rotation(name, euler = {}, scale = 1, now = performance.now()) {
      const limit = limitFor(name);
      const raw = [euler.x || 0, euler.y || 0, euler.z || 0].map((value, axis) => {
        const scaled = value * scale;
        return limit ? clamp(scaled, limit[axis]) : scaled;
      });
      const isHand = /Hand|Thumb|Index|Middle|Ring|Little/.test(name);
      const previous = inputEulers.get(name) || [0, 0, 0];
      const elapsed = Math.max(1 / 120, Math.min(0.05, (now - (inputTimes.get(name) ?? now - 16)) / 1000));
      const radiansPerSecond = /UpperLeg|LowerLeg|Foot/.test(name) ? 4.2 : 6.5;
      const next = isHand ? raw : raw.map((value, axis) => {
        const step = clamp(shortestDelta(previous[axis], value), radiansPerSecond * elapsed);
        return previous[axis] + step;
      });
      inputEulers.set(name, next);
      inputTimes.set(name, now);
      const delta = new THREE.Quaternion().setFromEuler(new THREE.Euler(...next));
      rotations.set(name, restFor(name).clone().multiply(delta));
      rotationTimes.set(name, now);
    },
    expression(name, value, now = performance.now()) {
      expressions.set(name, Math.max(0, Math.min(1, value)));
      expressionTimes.set(name, now);
    },
    hand(name, now = performance.now()) { hands.set(name, now); },
    resetHands() {
      for (const name of hands.keys()) {
        rotations.set(name, restFor(name).clone());
        inputEulers.delete(name);
        inputTimes.delete(name);
      }
      hands.clear();
    },
    apply({ bone, expression, now = performance.now(), dt = 1 / 60, smoothing = 0.3 }) {
      const alpha = 1 - Math.exp(-Math.max(0.001, dt) * Math.max(0.1, smoothing) * 18);
      for (const [name, target] of rotations) {
        const targetBone = bone(name);
        if (!targetBone) continue;
        const timeout = hands.has(name) ? handTimeoutMs : bodyTimeoutMs;
        const updatedAt = hands.get(name) ?? rotationTimes.get(name) ?? now;
        const age = now - updatedAt;
        if (age > timeout) {
          targetBone.quaternion.slerp(restFor(name), Math.min(1, alpha * (age / timeout)));
          continue;
        }
        targetBone.quaternion.slerp(target, alpha);
      }
      for (const [name, value] of expressions) {
        const age = now - (expressionTimes.get(name) ?? now);
        expression(name, age > expressionTimeoutMs ? 0 : value, alpha);
      }
    },
  };
}
