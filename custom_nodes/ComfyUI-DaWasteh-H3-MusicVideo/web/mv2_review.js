// v1.2.5 · MV 5b · Szene prüfen
// The node holds the running workflow after every new scene. This widget shows the scene with the original
// song audio and sends the decision to the waiting node: Weiter (accept the shown take), Neu rendern (new seed,
// same scene, same run) or Rest ohne Prüfung. Earlier takes of the scene stay selectable.
import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

const CLASS = "DaWMV2ReviewScene";
const EVENT = "dawasteh-mv2-review";
const EVENT_DONE = "dawasteh-mv2-review-done";
const ROUTE = "/dawasteh/mv2/review";
const MIN_H = 380;

function injectCSS() {
  if (document.getElementById("daw-mv2-review-css")) return;
  const style = document.createElement("style");
  style.id = "daw-mv2-review-css";
  style.textContent = `
    .daw-rv { display:flex; flex-direction:column; gap:6px; height:100%; box-sizing:border-box; padding:4px;
      font:12px sans-serif; color:var(--fg-color,#ddd); overflow:hidden; }
    .daw-rv-status { flex:0 0 auto; padding:5px 7px; border-radius:5px; background:rgba(0,0,0,0.25); line-height:1.35; }
    .daw-rv.pending .daw-rv-status { background:#7a4b00; color:#fff; font-weight:600; }
    .daw-rv-takes { flex:0 0 auto; display:flex; flex-wrap:wrap; gap:4px; }
    .daw-rv-take { padding:3px 9px; border-radius:4px; cursor:pointer; user-select:none;
      border:1px solid rgba(255,255,255,0.2); background:rgba(255,255,255,0.05); }
    .daw-rv-take.active { background:#2f6fb3; border-color:#2f6fb3; color:#fff; }
    .daw-rv-video { flex:1 1 0; min-height:120px; width:100%; background:#111; border-radius:4px; object-fit:contain; }
    .daw-rv-empty { flex:1 1 0; min-height:120px; display:flex; align-items:center; justify-content:center; text-align:center;
      color:#888; background:#161616; border-radius:4px; padding:10px; box-sizing:border-box; }
    .daw-rv-row { flex:0 0 auto; display:flex; gap:6px; }
    .daw-rv-btn { flex:1 1 0; min-width:0; height:30px; border-radius:5px; cursor:pointer; font:600 12px sans-serif;
      border:1px solid rgba(255,255,255,0.22); background:rgba(255,255,255,0.07); color:#eee;
      white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .daw-rv-btn:hover:not(:disabled) { border-color:#fff; }
    .daw-rv-btn.go:not(:disabled) { background:#2e7d32; border-color:#2e7d32; color:#fff; }
    .daw-rv-btn.redo:not(:disabled) { background:#b3541e; border-color:#b3541e; color:#fff; }
    .daw-rv-btn:disabled { opacity:0.4; cursor:default; }
    .daw-rv-shots { flex:0 0 auto; max-height:88px; overflow:auto; color:#aaa; font-size:11px; }
    .daw-rv-shots summary { cursor:pointer; color:#ccc; }
    .daw-rv-toast { position:fixed; right:18px; bottom:18px; z-index:10000; display:flex; gap:10px; align-items:center;
      padding:10px 12px; border-radius:8px; background:#7a4b00; color:#fff; font:600 13px sans-serif;
      box-shadow:0 4px 18px rgba(0,0,0,0.5); }
    .daw-rv-toast button { font:600 12px sans-serif; padding:5px 10px; border-radius:5px; border:0; cursor:pointer; }
  `;
  document.head.appendChild(style);
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function viewUrl(ref, bust) {
  const params = new URLSearchParams({ filename: ref.filename, subfolder: ref.subfolder || "", type: ref.type || "output",
                                       t: String(bust || Date.now()) });
  return api.apiURL(`/view?${params.toString()}`);
}

function findNode(id) {
  const graph = app.graph;
  if (!graph) return null;
  return graph.getNodeById?.(Number(id)) ?? graph.getNodeById?.(id) ?? null;
}

function reviewNodes() {
  return (app.graph?._nodes || app.graph?.nodes || []).filter((n) => n.comfyClass === CLASS || n.type === CLASS);
}

// ---------------------------------------------------------------------------------------------------------
// Widget
// ---------------------------------------------------------------------------------------------------------

function buildWidget(node) {
  injectCSS();
  const root = el("div", "daw-rv");
  const status = el("div", "daw-rv-status", "Wartet auf die erste gerenderte Szene.");
  const takes = el("div", "daw-rv-takes");
  const video = el("video", "daw-rv-video");
  video.controls = true;
  video.preload = "auto";
  video.playsInline = true;
  video.style.display = "none";
  const empty = el("div", "daw-rv-empty", "Nach jeder Szene erscheint sie hier mit Originalton.\nWeiter rendert die nächste, Neu rendern würfelt diese Szene neu.");
  const row = el("div", "daw-rv-row");
  const redo = el("button", "daw-rv-btn redo", "↻ Neu rendern");
  redo.title = "Diese Szene mit neuem Seed noch einmal rendern. Der gezeigte Take bleibt wählbar.";
  const go = el("button", "daw-rv-btn go", "✓ Weiter");
  go.title = "Den gezeigten Take übernehmen und die nächste Szene rendern.";
  row.append(redo, go);
  const row2 = el("div", "daw-rv-row");
  const all = el("button", "daw-rv-btn", "⏩ Rest ohne Prüfung");
  all.title = "Gezeigten Take übernehmen und alle weiteren Szenen dieses Laufs ohne Halt rendern.";
  row2.append(all);
  const shots = el("details", "daw-rv-shots");
  shots.style.display = "none";
  root.append(status, takes, video, empty, row, row2, shots);

  for (const button of [redo, go, all]) {
    button.addEventListener("pointerdown", (e) => e.stopPropagation());
  }
  go.addEventListener("click", (e) => { e.stopPropagation(); decide(node, "continue"); });
  redo.addEventListener("click", (e) => { e.stopPropagation(); decide(node, "redo"); });
  all.addEventListener("click", (e) => { e.stopPropagation(); decide(node, "continue_all"); });

  node._dawRv = { root, status, takes, video, empty, go, redo, all, shots, pending: null, selected: null, last: null, busy: null };
  return root;
}

function showVideo(state, ref, bust) {
  if (!ref) {
    state.video.style.display = "none";
    state.empty.style.display = "flex";
    return;
  }
  const url = viewUrl(ref, bust);
  if (state.video.dataset.src !== url) {
    state.video.dataset.src = url;
    state.video.src = url;
  }
  state.video.style.display = "block";
  state.empty.style.display = "none";
}

function render(node) {
  const state = node._dawRv;
  if (!state) return;
  const p = state.pending;
  state.root.classList.toggle("pending", !!p && !state.busy);
  state.takes.replaceChildren();
  if (p) {
    const selected = p.takes.find((t) => t.take === state.selected) || p.takes.find((t) => t.current) || p.takes[0];
    state.status.textContent = state.busy ||
      `Szene ${p.scene}/${p.total} prüfen · ${p.start}–${p.end} · ${p.section} · Take ${selected.take + 1}` +
      (p.takes.length > 1 ? ` von ${p.takes.length}` : "");
    if (p.takes.length > 1) {
      for (const t of p.takes) {
        const tab = el("div", "daw-rv-take" + (t.take === selected.take ? " active" : ""),
                       `Take ${t.take + 1}${t.current ? " (neu)" : ""}`);
        tab.title = `Seed ${t.seed}`;
        tab.addEventListener("pointerdown", (e) => e.stopPropagation());
        tab.addEventListener("click", (e) => {
          e.stopPropagation();
          state.selected = t.take;
          render(node);
          state.video.play().catch(() => {});
        });
        state.takes.appendChild(tab);
      }
    }
    showVideo(state, selected.video, p.id);
    state.go.textContent = selected.current ? "✓ Weiter" : `✓ Take ${selected.take + 1} nehmen + weiter`;
    state.shots.replaceChildren(el("summary", "", "Shots dieser Szene"),
                                ...p.shots.map((s, i) => el("div", "", `${i + 1}. ${s}`)));
    state.shots.style.display = p.shots.length ? "block" : "none";
  } else {
    state.status.textContent = state.busy || state.last?.text || "Wartet auf die erste gerenderte Szene.";
    state.go.textContent = "✓ Weiter";
    if (state.last?.video) showVideo(state, state.last.video, state.last.bust);
  }
  const open = !!p && !state.busy;
  state.go.disabled = !open;
  state.redo.disabled = !open;
  state.all.disabled = !open;
  node.setDirtyCanvas?.(true, true);
}

async function decide(node, action) {
  const state = node._dawRv;
  const p = state?.pending;
  if (!p || state.busy) return;
  const body = { id: p.id, action };
  if (action !== "redo") body.take = state.selected ?? p.take;
  state.busy = action === "redo" ? `Szene ${p.scene} wird neu gerendert …`
    : `Szene ${p.scene} übernommen${action === "continue_all" ? ", Rest läuft ohne Halt" : ""} …`;
  render(node);
  try {
    const response = await api.fetchApi(ROUTE, { method: "POST", headers: { "Content-Type": "application/json" },
                                                 body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    state.video.pause();
    hideToast();
  } catch (err) {
    state.busy = null;
    render(node);
    state.status.textContent = `Entscheidung nicht angekommen: ${err.message}`;
  }
}

// ---------------------------------------------------------------------------------------------------------
// Server events
// ---------------------------------------------------------------------------------------------------------

let toast = null;
function hideToast() {
  toast?.remove();
  toast = null;
}

function showToast(payload, node) {
  hideToast();
  toast = el("div", "daw-rv-toast", `Szene ${payload.scene}/${payload.total} wartet auf deine Prüfung`);
  const show = el("button", "", "Anzeigen");
  show.addEventListener("click", () => {
    if (node) {
      app.canvas?.centerOnNode?.(node);
      app.canvas?.selectNode?.(node);
      app.canvas?.setDirty?.(true, true);
    }
  });
  const close = el("button", "", "×");
  close.addEventListener("click", hideToast);
  toast.append(show, close);
  document.body.appendChild(toast);
}

function onPending(payload) {
  if (!payload?.id) return;
  const node = findNode(payload.node) || reviewNodes()[0];
  if (node?._dawRv) {
    const state = node._dawRv;
    if (state.pending?.id !== payload.id) state.selected = payload.take;
    state.pending = payload;
    state.busy = null;
    render(node);
    state.video.play().catch(() => {});
  }
  showToast(payload, node);
}

function onDone(id) {
  for (const node of reviewNodes()) {
    const state = node._dawRv;
    if (state?.pending && (!id || state.pending.id === id)) {
      state.pending = null;
      render(node);
    }
  }
  hideToast();
}

async function fetchPending() {
  try {
    const response = await api.fetchApi(ROUTE);
    if (response.ok) onPending(await response.json());
  } catch (err) {
    console.warn("[DaWasteh MV2 review] pending review not loaded", err);
  }
}

// a page reload or a freshly loaded workflow while a scene waits: ask the server once the nodes exist
let fetchTimer = null;
function scheduleFetch() {
  clearTimeout(fetchTimer);
  fetchTimer = setTimeout(fetchPending, 800);
}

app.registerExtension({
  name: "DaWasteh.MV2.ReviewScene",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== CLASS) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = created?.apply(this, arguments);
      this.addDOMWidget("review_ui", "dawmv2_review", buildWidget(this), {
        serialize: false, hideOnZoom: false, getMinHeight: () => MIN_H,
      });
      this.setSize([Math.max(this.size[0], 480), Math.max(this.size[1], MIN_H + 90)]);
      scheduleFetch();
      return result;
    };
    const executed = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      executed?.apply(this, arguments);
      const shown = message?.dawmv2_review?.[0];
      if (!shown || !this._dawRv) return;
      this._dawRv.last = { ...shown, bust: Date.now() };
      this._dawRv.pending = null;
      this._dawRv.busy = null;
      render(this);
    };
  },
  async setup() {
    api.addEventListener(EVENT, (e) => onPending(e.detail));
    api.addEventListener(EVENT_DONE, (e) => onDone(e.detail?.id));
    for (const name of ["execution_interrupted", "execution_error"]) {
      api.addEventListener(name, () => onDone(null));
    }
    api.addEventListener("reconnected", scheduleFetch);
    scheduleFetch();
  },
});
