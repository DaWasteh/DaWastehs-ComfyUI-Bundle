import { app } from "/scripts/app.js";

const NODE_TYPES = new Set(["DaWAdaptiveLoadImage", "DaWAdaptiveLoadVideo"]);
const AUTO = "Auto (connected model)";
const NOT_DETECTED = "Not detected";
const AMBIGUOUS = "Ambiguous (select manually)";

// Ordered from specific to broad. The text includes node class/title, subgraph
// title, loader filenames, and S&R metadata encountered downstream.
const SIGNATURES = [
  ["Wan 2.x / Animate 2 (480p)", /wan[ _-]*animate[ _-]*2|wananimate2/i],
  ["SCAIL 2 (480p)", /scail[ _-]*2|scail2/i],
  ["MiniMax H3 (768)", /minimax[ _-]*h3|h3.*(?:video|latent|director)/i],
  ["LTX Video (768x512)", /\bltx(?:v|2|23|25|video)?\b|ltxvideo/i],
  ["Hunyuan Video (720p)", /hunyuan.*video|hunyuanvideo/i],
  ["Wan 2.x (720p)", /wan.*720p/i],
  ["Wan 2.x / Animate 2 (480p)", /\bwan(?:image|video|vace|fun|camera|phantom|control|2)/i],
  ["Qwen Image (1328)", /qwen.*image|qwenimage/i],
  ["SDXL / FLUX (1024)", /\bflux\b|flux\.|sdxl|stable.?diffusion.?xl/i],
  ["SD 1.5 (512)", /sd.?1[._ -]?5|stable.?diffusion.?1[._ -]?5/i],
];

function widget(node, name) {
  return node?.widgets?.find((item) => item.name === name);
}

function linkById(graph, id) {
  const links = graph?.links;
  if (!links) return null;
  if (typeof links.get === "function") return links.get(id) || links.get(String(id)) || null;
  return links[id] || links[String(id)] || null;
}

function targetId(link) {
  if (Array.isArray(link)) return link[3];
  return link?.target_id ?? link?.targetId;
}

function originId(link) {
  if (Array.isArray(link)) return link[1];
  return link?.origin_id ?? link?.originId;
}

function nodeText(node) {
  if (!node) return "";
  if (node.comfyClass === "MarkdownNote" || node.type === "MarkdownNote") return "";
  const values = (node.widgets || [])
    .map((item) => (typeof item.value === "string" ? item.value : ""))
    .filter(Boolean)
    .join(" ");
  return [
    node.comfyClass,
    node.type,
    node.title,
    node.constructor?.title,
    node.properties?.["Node name for S&R"],
    values,
  ].filter(Boolean).join(" ");
}

function directTargets(node) {
  const graph = node?.graph;
  if (!graph) return [];
  const result = [];
  for (const output of node.outputs || []) {
    for (const linkId of output?.links || []) {
      const link = linkById(graph, linkId);
      const id = targetId(link);
      const target = id == null ? null : graph.getNodeById?.(id);
      if (target) result.push(target);
    }
  }
  return result;
}

function incomingSources(node) {
  const graph = node?.graph;
  if (!graph) return [];
  const result = [];
  for (const input of node.inputs || []) {
    if (input?.link == null) continue;
    const link = linkById(graph, input.link);
    const id = originId(link);
    const source = id == null ? null : graph.getNodeById?.(id);
    if (source) result.push(source);
  }
  return result;
}

function adjacentNodes(node) {
  return [...directTargets(node), ...incomingSources(node)];
}

function detectDownstreamProfile(start) {
  // Begin downstream so an unrelated model elsewhere in the canvas cannot win.
  // Once the media branch is reached, walk the connected component in both
  // directions: standard Comfy graphs feed IMAGE and MODEL/VAE from sibling
  // branches into nodes such as VAEEncode or samplers.
  const queue = directTargets(start).map((node) => [node, 1]);
  const seen = new Set([start.id]);
  const matches = new Set();
  let hasMediaPath = false;
  while (queue.length) {
    const [node, depth] = queue.shift();
    if (!node || seen.has(node.id) || depth > 48 || seen.size > 256) continue;
    seen.add(node.id);
    const text = nodeText(node);
    for (const [profile, pattern] of SIGNATURES) {
      if (pattern.test(text)) matches.add(profile);
    }
    if (/image|video|latent|conditioning|vae|sampler/i.test(text)) hasMediaPath = true;
    for (const next of adjacentNodes(node)) queue.push([next, depth + 1]);
  }
  if (matches.size === 1) return [...matches][0];
  if (matches.size > 1) return AMBIGUOUS;
  return hasMediaPath ? "General image/video (1024)" : NOT_DETECTED;
}

function updateDetection(node) {
  if (!NODE_TYPES.has(node?.comfyClass)) return;
  const profileWidget = widget(node, "model_profile");
  const detectedWidget = widget(node, "detected_profile");
  if (!profileWidget || !detectedWidget) return;

  const detected = detectDownstreamProfile(node);
  if (detectedWidget.value !== detected) {
    detectedWidget.value = detected;
    detectedWidget.callback?.(detected);
  }
  const unresolved = detected === NOT_DETECTED || detected === AMBIGUOUS;
  const effective = profileWidget.value === AUTO
    ? (unresolved ? `${detected} · 1024 fallback` : `${detected} · auto`)
    : `${profileWidget.value} · manual`;
  node.title = `${node.comfyClass === "DaWAdaptiveLoadVideo" ? "Adaptive Load Video" : "Adaptive Load Image"} · ${effective}`;
  node.setDirtyCanvas?.(true, true);
}

function updateAll() {
  for (const node of app.graph?._nodes || []) updateDetection(node);
}

app.registerExtension({
  name: "DaWasteh.AdaptiveMedia",

  beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_TYPES.has(nodeData.name)) return;

    const originalConnections = nodeType.prototype.onConnectionsChange;
    nodeType.prototype.onConnectionsChange = function () {
      const result = originalConnections?.apply(this, arguments);
      queueMicrotask(() => updateDetection(this));
      return result;
    };

    const originalConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = originalConfigure?.apply(this, arguments);
      queueMicrotask(() => updateDetection(this));
      return result;
    };
  },

  nodeCreated(node) {
    if (!NODE_TYPES.has(node.comfyClass)) return;
    const profileWidget = widget(node, "model_profile");
    if (profileWidget) {
      const original = profileWidget.callback;
      profileWidget.callback = function () {
        const result = original?.apply(this, arguments);
        updateDetection(node);
        return result;
      };
    }
    queueMicrotask(() => updateDetection(node));
  },
});

// Refresh immediately before serialization so links changed by scripts or
// subgraph operations cannot leave a stale automatic profile in the prompt.
const originalGraphToPrompt = app.graphToPrompt.bind(app);
app.graphToPrompt = async function (...args) {
  try {
    updateAll();
  } catch (error) {
    console.warn("[DaWasteh Adaptive Media] model detection failed; keeping the saved profile", error);
  }
  return originalGraphToPrompt(...args);
};
