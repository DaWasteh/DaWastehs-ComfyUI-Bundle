const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));

export const BODY_FRAME_ANCHORS = [
  [11, "LeftUpperArm"],
  [12, "RightUpperArm"],
  [23, "LeftUpperLeg"],
  [24, "RightUpperLeg"],
  [25, "LeftLowerLeg"],
  [26, "RightLowerLeg"],
  [27, "LeftFoot"],
  [28, "RightFoot"],
];

export function visibleFramePairs(landmarks, modelPoints, minimumVisibility = 0.5) {
  if (!Array.isArray(landmarks) || !(modelPoints instanceof Map)) return [];
  const pairs = [];
  for (const [index, bone] of BODY_FRAME_ANCHORS) {
    const target = landmarks[index];
    const model = modelPoints.get(bone);
    const visibility = target?.visibility ?? 0;
    if (!model || !Number.isFinite(target?.x) || !Number.isFinite(target?.y) || visibility < minimumVisibility) continue;
    pairs.push({ model, target: { x: target.x, y: target.y }, weight: visibility });
  }
  return pairs;
}

export function solveScreenFraming(pairs, { minimumScale = 0.55, maximumScale = 4 } = {}) {
  if (!Array.isArray(pairs) || pairs.length < 3) return null;
  const totalWeight = pairs.reduce((sum, pair) => sum + Math.max(0, pair.weight ?? 1), 0);
  if (totalWeight <= 0) return null;
  const center = (side) => pairs.reduce(
    (sum, pair) => {
      const weight = Math.max(0, pair.weight ?? 1);
      sum.x += pair[side].x * weight;
      sum.y += pair[side].y * weight;
      return sum;
    },
    { x: 0, y: 0 },
  );
  const modelCenter = center("model");
  const targetCenter = center("target");
  modelCenter.x /= totalWeight;
  modelCenter.y /= totalWeight;
  targetCenter.x /= totalWeight;
  targetCenter.y /= totalWeight;
  let modelSpread = 0;
  let targetSpread = 0;
  for (const pair of pairs) {
    const weight = Math.max(0, pair.weight ?? 1);
    modelSpread += weight * ((pair.model.x - modelCenter.x) ** 2 + (pair.model.y - modelCenter.y) ** 2);
    targetSpread += weight * ((pair.target.x - targetCenter.x) ** 2 + (pair.target.y - targetCenter.y) ** 2);
  }
  if (modelSpread < 1e-5 || targetSpread < 1e-5) return null;
  const scale = clamp(Math.sqrt(targetSpread / modelSpread), minimumScale, maximumScale);
  const scaledCenter = {
    x: 0.5 + (modelCenter.x - 0.5) * scale,
    y: 0.5 + (modelCenter.y - 0.5) * scale,
  };
  return {
    scale,
    offsetX: targetCenter.x - scaledCenter.x,
    offsetY: targetCenter.y - scaledCenter.y,
    matchedAnchors: pairs.length,
  };
}

export class FramingController {
  constructor({ smoothing = 0.82, lostHoldMs = 350, returnMs = 900 } = {}) {
    Object.assign(this, { smoothing, lostHoldMs, returnMs });
    this.reset();
  }

  reset() {
    this.value = { scale: 1, offsetX: 0, offsetY: 0, matchedAnchors: 0 };
    this.lastSeenAt = 0;
    this.lastUpdateAt = 0;
    return this.value;
  }

  update(solution, now = performance.now()) {
    let target = solution;
    let keep;
    if (solution) {
      this.lastSeenAt = now;
      keep = clamp(this.smoothing, 0, 0.98);
    } else if (now - this.lastSeenAt <= this.lostHoldMs) {
      this.lastUpdateAt = now;
      return this.value;
    } else {
      target = { scale: 1, offsetX: 0, offsetY: 0, matchedAnchors: 0 };
      const returnStartedAt = this.lastSeenAt + this.lostHoldMs;
      const previousAt = Math.max(returnStartedAt, this.lastUpdateAt || returnStartedAt);
      keep = Math.exp(-Math.max(0, now - previousAt) / Math.max(1, this.returnMs));
    }
    this.value = {
      scale: keep * this.value.scale + (1 - keep) * target.scale,
      offsetX: keep * this.value.offsetX + (1 - keep) * target.offsetX,
      offsetY: keep * this.value.offsetY + (1 - keep) * target.offsetY,
      matchedAnchors: target.matchedAnchors,
    };
    this.lastUpdateAt = now;
    return this.value;
  }
}

export function frameProjectionElements(baseElements, { scale = 1, offsetX = 0, offsetY = 0 }) {
  if (!baseElements || baseElements.length !== 16) throw new TypeError("projection matrix must contain 16 elements");
  const framed = Array.from(baseElements);
  const translateX = offsetX * 2;
  const translateY = -offsetY * 2;
  for (let column = 0; column < 4; column += 1) {
    const row0 = column * 4;
    const row1 = row0 + 1;
    const row3 = row0 + 3;
    framed[row0] = scale * baseElements[row0] + translateX * baseElements[row3];
    framed[row1] = scale * baseElements[row1] + translateY * baseElements[row3];
  }
  return framed;
}
