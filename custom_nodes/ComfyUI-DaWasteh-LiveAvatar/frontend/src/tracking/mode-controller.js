export class ModeController {
  constructor({ enterFrames = 15, exitFrames = 30, enterVisibility = 0.65, exitVisibility = 0.45, minHoldMs = 2000 } = {}) {
    Object.assign(this, { enterFrames, exitFrames, enterVisibility, exitVisibility, minHoldMs });
    this.reset();
  }

  reset() {
    this.mode = "upper";
    this.good = 0;
    this.bad = 0;
    this.changedAt = 0;
  }

  update(landmarks, now = performance.now(), override = "auto") {
    if (override === "upper" || override === "full") {
      this.mode = override;
      this.good = this.bad = 0;
      return this.mode;
    }
    const legs = ["leftHip", "rightHip", "leftKnee", "rightKnee", "leftAnkle", "rightAnkle"];
    const values = legs.map((key) => landmarks?.[key]?.visibility ?? 0);
    const average = values.reduce((sum, value) => sum + value, 0) / values.length;
    const enterCount = values.filter((value) => value >= this.enterVisibility).length;
    const exitCount = values.filter((value) => value >= this.exitVisibility).length;
    const enoughForFullBody = average >= this.enterVisibility && enterCount >= 5;
    const legsAreLost = average < this.exitVisibility || exitCount < 5;
    if (enoughForFullBody) {
      this.good += 1;
      this.bad = 0;
    } else if (legsAreLost) {
      this.bad += 1;
      this.good = 0;
    } else {
      this.good = this.bad = 0;
    }
    if (this.mode === "upper" && this.good >= this.enterFrames && now - this.changedAt >= this.minHoldMs) {
      this.mode = "full";
      this.changedAt = now;
      this.good = 0;
    }
    if (this.mode === "full" && this.bad >= this.exitFrames && now - this.changedAt >= this.minHoldMs) {
      this.mode = "upper";
      this.changedAt = now;
      this.bad = 0;
    }
    return this.mode;
  }
}
