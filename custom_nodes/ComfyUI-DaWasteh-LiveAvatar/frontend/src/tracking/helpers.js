export const handInputs = (results, selfie = false) => selfie
  ? [["Left", results.rightHandLandmarks], ["Right", results.leftHandLandmarks]]
  : [["Left", results.leftHandLandmarks], ["Right", results.rightHandLandmarks]];

export const neutralLegs = ["LeftUpperLeg", "LeftLowerLeg", "RightUpperLeg", "RightLowerLeg"];

export class FpsMeter {
  constructor(windowMs = 2000) {
    this.windowMs = windowMs;
    this.samples = [];
  }

  tick(now = performance.now()) {
    this.samples.push(now);
    this.#trim(now);
  }

  fps(now = performance.now()) {
    this.#trim(now);
    if (this.samples.length < 2) return 0;
    return (this.samples.length - 1) * 1000 / (this.samples.at(-1) - this.samples[0]);
  }

  reset() {
    this.samples.length = 0;
  }

  #trim(now) {
    while (this.samples.length > 1 && this.samples[0] < now - this.windowMs) this.samples.shift();
  }
}

export function loopController(step, onError = () => {}, videoSource = null) {
  let id = 0;
  let running = false;
  let busy = false;
  let dropped = 0;
  let duplicates = 0;
  let lastVideoTime;
  const useVideoFrames = typeof videoSource?.requestVideoFrameCallback === "function";
  const request = (callback) => useVideoFrames
    ? videoSource.requestVideoFrameCallback(callback)
    : requestAnimationFrame(callback);
  const cancel = (handle) => {
    if (useVideoFrames && typeof videoSource.cancelVideoFrameCallback === "function") videoSource.cancelVideoFrameCallback(handle);
    else cancelAnimationFrame(handle);
  };
  const tick = async () => {
    if (!running) return;
    id = request(tick);
    if (!useVideoFrames && Number.isFinite(videoSource?.currentTime)) {
      if (videoSource.currentTime === lastVideoTime) {
        duplicates += 1;
        return;
      }
      lastVideoTime = videoSource.currentTime;
    }
    if (busy) {
      dropped += 1;
      return;
    }
    busy = true;
    try {
      await step();
    } catch (error) {
      onError(error);
    } finally {
      busy = false;
    }
  };
  return {
    start() {
      if (running) return;
      running = true;
      id = request(tick);
    },
    stop() {
      running = false;
      cancel(id);
    },
    get busy() { return busy; },
    get dropped() { return dropped; },
    get duplicates() { return duplicates; },
    get scheduler() { return useVideoFrames ? "camera" : "display-deduplicated"; },
  };
}
