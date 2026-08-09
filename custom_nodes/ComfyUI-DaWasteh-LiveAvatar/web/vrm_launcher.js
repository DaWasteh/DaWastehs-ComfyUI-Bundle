import { app } from "/scripts/app.js";

const enabled = (value, fallback = false) => value === undefined
  ? fallback
  : ![false, 0, "0", "false", "disable"].includes(value);

app.registerExtension({
  name: "DaWasteh.VRMLiveAvatarLauncher",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DaWastehVRMLiveAvatarLauncher") return;
    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function onNodeCreated() {
      original?.apply(this, arguments);
      this.addWidget("button", "VRM Live Avatar öffnen", "", () => {
        const value = (name, fallback) => this.widgets?.find((widget) => widget.name === name)?.value ?? fallback;
        const port = value("port", window.location.port || 8188);
        const model = String(value("model", "")).split(/[\\/]/).at(-1);
        const query = new URLSearchParams({
          follow: enabled(value("follow_framing", true), true) ? "1" : "0",
          chroma: enabled(value("chroma", false)) ? "1" : "0",
          present: enabled(value("presentation", false)) ? "1" : "0",
        });
        if (model) query.set("model", model);
        window.open(
          `http://127.0.0.1:${port}/dawasteh/vrm-live/?${query}`,
          "_blank",
          "noopener,noreferrer",
        );
      });
    };
  },
});
