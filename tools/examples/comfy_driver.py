"""Drive the real ComfyUI frontend (headless Edge) for the example gallery.

The driver loads a UI workflow, sets widget values the way a user would, queues it with the frontend's own Run path
(``app.queuePrompt``: subgraphs, Pixaroma prompt state and gate pruning happen exactly as in the browser), waits for
the result through the HTTP API and takes a screenshot of the graph with the outputs shown in their nodes and the
explanation notes removed.

Run with the selenium test venv (selenium, psutil, pillow):
  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/comfy_driver.py <workflow.json> --shot out.png
"""
from __future__ import annotations

import base64
import copy
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait

NOTE_TYPES = ("MarkdownNote", "Note", "PixaromaNote")

JS_BOOT = r"""
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const deadline = Date.now() + 180000;
  while ((!app.graph || !app.canvas) && Date.now() < deadline) await new Promise(r => setTimeout(r, 250));
  await new Promise(r => setTimeout(r, 12000));
  const settings = {
    'LiteGraph.Canvas.LowQualityRenderingZoomThreshold': 0.05,
    'Comfy.Workflow.ShowMissingModelsWarning': false,
    'Comfy.Workflow.ShowMissingNodesWarning': false,
    'Comfy.Validation.Workflows': false,
    'Comfy.Graph.CanvasInfo': false,
    'Comfy.Minimap.Visible': false,
    'Comfy.TutorialCompleted': true,
    'Comfy.Workflow.ConfirmDelete': false,
    'Comfy.PromptFilename': false,
    'Comfy.NodeBadge.NodeIdBadgeMode': 'None',
    'Comfy.NodeBadge.NodeSourceBadgeMode': 'None',
    'Comfy.WidgetControlMode': 'after',
    'Comfy.VueNodes.Enabled': true,
  };
  const errors = [];
  for (const [k, v] of Object.entries(settings)) {
    try { await app.extensionManager.setting.set(k, v); } catch (e) { errors.push(k + ': ' + e); }
  }
  done({ok: true, errors, version: window.__COMFYUI_FRONTEND_VERSION__ || null});
})().catch(e => done({ok: false, error: String(e)}));
"""

JS_LOAD = r"""
const workflow = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const identity = nodes => JSON.stringify(nodes.map(n => [String(n.id), n.type]).sort());
  const expected = identity(workflow.nodes);
  let ready = false;
  let warning = null;
  for (let attempt = 0; attempt < 4 && !ready; attempt++) {
    try {
      await app.loadGraphData(workflow, true, true);
    } catch (e) {
      // Some node extensions put non-cloneable objects into node properties (e.g. KJ Ideogram dock geometry);
      // the graph itself is configured, only the workflow-tab bookkeeping fails.
      warning = String(e).slice(0, 300);
    }
    await new Promise(r => setTimeout(r, 2500));
    ready = identity(app.graph._nodes) === expected;
    if (ready) {
      await new Promise(r => setTimeout(r, 1500));
      ready = identity(app.graph._nodes) === expected;
    }
  }
  // Close dialogs the load may have opened (missing models etc.). Node extensions such as VHS use the legacy
  // ComfyDialog (.comfy-modal, no role="dialog"); it stays open until closed and would end up in later screenshots.
  const legacy = [...document.querySelectorAll('.comfy-modal')].filter(d => d.style.display !== 'none' && d.innerText.trim());
  const dialogs = [...document.querySelectorAll('[role="dialog"]'), ...legacy].map(d => d.innerText.slice(0, 400));
  document.querySelectorAll('[role="dialog"] button[aria-label="Close"], .p-dialog-close-button').forEach(b => b.click());
  try { app.ui.dialog.close(); } catch (e) {}
  legacy.forEach(d => { d.style.display = 'none'; });
  const missing = [];
  for (const node of app.graph._nodes) if (node.has_errors || node.type === undefined) missing.push(String(node.id) + ':' + node.type);
  done({ok: ready, dialogs, missing, warning});
})().catch(e => done({ok: false, error: String(e), stack: e && e.stack}));
"""

JS_PATCH = r"""
const patches = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const log = [];
  const all = [];
  const visit = (graph, path) => {
    for (const n of graph._nodes || graph.nodes || []) {
      all.push({node: n, path});
      if (n.subgraph) visit(n.subgraph, path.concat([String(n.id)]));
    }
  };
  visit(app.graph, []);
  const match = (entry, sel) => {
    const n = entry.node;
    if (sel.id !== undefined && String(n.id) !== String(sel.id)) return false;
    if (sel.path !== undefined && entry.path.join('/') !== sel.path) return false;
    if (sel.type !== undefined && n.type !== sel.type) return false;
    if (sel.title !== undefined && (n.title || '') !== sel.title) return false;
    if (sel.title_re !== undefined && !(new RegExp(sel.title_re)).test(n.title || '')) return false;
    return true;
  };
  for (const p of patches) {
    const hits = all.filter(e => match(e, p.select || {}));
    if (!hits.length) { log.push({patch: p, error: 'no node'}); continue; }
    if (hits.length > 1 && !p.all) { log.push({patch: p, error: 'ambiguous ' + hits.map(h => h.node.id + ':' + h.node.type).join(',')}); continue; }
    for (const {node} of hits) {
      if (p.mode !== undefined) { node.mode = p.mode; log.push({node: node.id, mode: p.mode}); }
      if (p.widget !== undefined) {
        const w = (node.widgets || []).find(w => w.name === p.widget);
        if (!w) { log.push({node: node.id, error: 'no widget ' + p.widget, widgets: (node.widgets || []).map(w => w.name)}); continue; }
        w.value = p.value;
        try { w.callback && w.callback(p.value, app.canvas, node); } catch (e) { log.push({node: node.id, warn: String(e)}); }
        log.push({node: node.id, widget: p.widget, value: typeof p.value === 'string' ? p.value.slice(0, 80) : p.value});
      }
      if (p.props !== undefined) {
        node.properties = node.properties || {};
        for (const [k, v] of Object.entries(p.props)) node.properties[k] = v;
        if (node.onConfigure) { try { node.onConfigure({properties: node.properties, widgets_values: node.widgets_values}); } catch (e) { log.push({node: node.id, warn: 'onConfigure ' + e}); } }
        log.push({node: node.id, props: Object.keys(p.props)});
      }
      if (p.prompt !== undefined) {
        node.properties = node.properties || {};
        const cur = node.properties.promptState || {};
        node.properties.promptState = {...cur, text: p.prompt};
        const ta = node.widgets && node.widgets.map(w => w.element).find(el => el && el.querySelector && el.querySelector('textarea'));
        if (ta) { const t = ta.querySelector('textarea'); t.value = p.prompt; t.dispatchEvent(new Event('input', {bubbles: true})); }
        log.push({node: node.id, prompt: p.prompt.slice(0, 80)});
      }
    }
  }
  // Fixed seeds: the example must show the seed that produced it.
  for (const {node} of all) for (const w of node.widgets || []) {
    if (w.name === 'control_after_generate' || w.name === 'control_before_generate') w.value = 'fixed';
  }
  app.graph.setDirtyCanvas(true, true);
  done({ok: true, log});
})().catch(e => done({ok: false, error: String(e), stack: e && e.stack}));
"""

JS_QUEUE = r"""
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const { api } = await import('/scripts/api.js');
  let captured = null;
  const orig = api.queuePrompt;
  api.queuePrompt = async function (...args) {
    const res = await orig.apply(this, args);
    captured = res;
    return res;
  };
  let ok, err = null;
  try { ok = await app.queuePrompt(0, 1); } catch (e) { err = String(e); }
  api.queuePrompt = orig;
  const dialogs = [...document.querySelectorAll('[role="dialog"]')].map(d => d.innerText.slice(0, 1500));
  done({ok, err, captured, nodeErrors: app.lastNodeErrors || null, dialogs});
})().catch(e => done({ok: false, error: String(e)}));
"""

JS_PREPARE_SHOT = r"""
const opts = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const g = app.graph;
  const removeTypes = new Set(opts.remove_types);
  const keep = new Set((opts.keep_ids || []).map(String));
  for (const n of [...g._nodes]) if (removeTypes.has(n.type) && !keep.has(String(n.id))) g.remove(n);
  for (const id of opts.remove_ids || []) { const n = g.getNodeById(id); if (n) g.remove(n); }
  // Drop groups that became empty, then shrink the others around what is left.
  // from pos/size, not boundingRect: that one is cached until the next draw and would ignore the moves below
  const TITLE_H = 30;
  const rect = n => [n.pos[0], n.pos[1] - TITLE_H, n.size[0], n.size[1] + TITLE_H];
  // membership by the node's centre, like the frontend's own group drag: a node drawn a little wider than saved (long
  // combo values) sticks out of its group and stayed behind while the rest of the group moved up over it
  const inside = (r, gr) => { const cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2;
    return cx >= gr[0] && cy >= gr[1] && cx <= gr[0] + gr[2] && cy <= gr[1] + gr[3]; };
  const groups = g._groups || g.groups || [];
  const gbox = grp => { const b = grp._bounding || [grp.pos[0], grp.pos[1], grp.size[0], grp.size[1]]; return [b[0], b[1], b[2], b[3]]; };
  const setBox = (grp, b) => {  // groups keep their bounds in the layout store; setBounds writes both
    if (grp.setBounds) grp.setBounds(b[0], b[1], b[2], b[3]); else { grp.pos = [b[0], b[1]]; grp.size = [b[2], b[3]]; }
  };
  const moveNode = (n, dx, dy) => { n.pos = [n.pos[0] + dx, n.pos[1] + dy]; };
  // Close empty bands along one axis: items = [{lo, hi, move(d)}]; gaps wider than keep shrink to keep.
  const closeGaps = (items, keep) => {
    const sorted = [...items].sort((a, b) => a.lo - b.lo);
    let reach = -Infinity, shift = 0;
    for (const it of sorted) {
      if (reach > -Infinity && it.lo - reach > keep) shift += it.lo - reach - keep;
      reach = Math.max(reach, it.hi);
      if (shift) it.move(-shift);
    }
  };
  const members = new Map();
  for (const grp of [...groups]) {
    const gb = gbox(grp);
    const inner = g._nodes.filter(n => inside(rect(n), gb));
    if (!inner.length) { if (g.remove) g.remove(grp); else groups.splice(groups.indexOf(grp), 1); continue; }
    members.set(grp, inner);
  }
  const TITLE = 44, PAD = 20, GAP = 40;
  if (opts.compact !== false) {
    const grouped = new Set();
    for (const [grp, inner] of members) {
      inner.forEach(n => grouped.add(n));
      const gb = gbox(grp);
      // inside the group: pull nodes up to the title bar and left to the border, then close inner gaps
      const nodeItems = axis => inner.map(n => { const r = rect(n); return {lo: r[axis], hi: r[axis] + r[axis + 2],
        move: d => moveNode(n, axis === 0 ? d : 0, axis === 1 ? d : 0)}; });
      closeGaps(nodeItems(1), GAP);
      closeGaps(nodeItems(0), GAP);
      let top = Infinity, left = Infinity;
      for (const n of inner) { const r = rect(n); top = Math.min(top, r[1]); left = Math.min(left, r[0]); }
      const dy = gb[1] + TITLE - top, dx = gb[0] + PAD - left;
      for (const n of inner) moveNode(n, dx, dy);
      let right = -Infinity, bottom = -Infinity;
      for (const n of inner) { const r = rect(n); right = Math.max(right, r[0] + r[2]); bottom = Math.max(bottom, r[1] + r[3]); }
      setBox(grp, [gb[0], gb[1], right - gb[0] + PAD, bottom - gb[1] + PAD]);
    }
    // between groups (and loose nodes): close the empty columns and rows the shrinking left behind
    const blocks = [...members.keys()].map(grp => ({grp, nodes: members.get(grp)}));
    for (const n of g._nodes) if (!grouped.has(n)) blocks.push({grp: null, nodes: [n]});
    const blockBox = b => b.grp ? gbox(b.grp) : rect(b.nodes[0]);
    const blockMove = (b, dx, dy) => {
      if (b.grp) { const r = gbox(b.grp); setBox(b.grp, [r[0] + dx, r[1] + dy, r[2], r[3]]); }
      b.nodes.forEach(n => moveNode(n, dx, dy));
    };
    for (const axis of [0, 1]) {
      closeGaps(blocks.map(b => { const r = blockBox(b); return {lo: r[axis], hi: r[axis] + r[axis + 2],
        move: d => blockMove(b, axis === 0 ? d : 0, axis === 1 ? d : 0)}; }), 2 * GAP);
    }
  }
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  const add = r => { minx = Math.min(minx, r[0]); miny = Math.min(miny, r[1]); maxx = Math.max(maxx, r[0] + r[2]); maxy = Math.max(maxy, r[1] + r[3]); };
  for (const n of g._nodes) add(rect(n));
  for (const grp of (g._groups || g.groups || [])) add(grp._bounding || [grp.pos[0], grp.pos[1], grp.size[0], grp.size[1]]);
  done({ok: true, bounds: [minx, miny, maxx - minx, maxy - miny], nodes: g._nodes.length});
})().catch(e => done({ok: false, error: String(e), stack: e && e.stack}));
"""

JS_FIT = r"""
const b = arguments[0], scale = arguments[1], margin = arguments[2];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const c = app.canvas;
  c.ds.scale = scale;
  c.ds.offset[0] = -b[0] + margin / scale;
  c.ds.offset[1] = -b[1] + margin / scale;
  c.setDirty(true, true);
  c.draw(true, true);
  await new Promise(r => setTimeout(r, 1500));
  c.draw(true, true);
  const el = c.canvas;
  done({ok: true, canvas: [el.width, el.height], client: [el.clientWidth, el.clientHeight]});
})().catch(e => done({ok: false, error: String(e)}));
"""

JS_CONTINUE = r"""
const gateId = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const { api } = await import('/scripts/api.js');
  const all = app.graph._nodes || [];
  const gates = all.filter(n => n.type === 'PixaromaPauseImage' || n.type === 'PixaromaPauseText');
  const node = gateId == null ? gates[0] : gates.find(n => String(n.id) === String(gateId));
  if (!node) { done({ok: false, error: 'no gate', gates: gates.map(g => g.id)}); return; }
  // Pause Image reads _pixPauseSubmitMode, Pause Text reads _pixPtSubmitMode (one-shot submit mode of that gate only)
  const prop = node.type === 'PixaromaPauseText' ? '_pixPtSubmitMode' : '_pixPauseSubmitMode';
  for (const n of all) if (n !== node) { n._pixPauseSubmitMode = null; n._pixPtSubmitMode = null; }
  let captured = null;
  const orig = api.queuePrompt;
  api.queuePrompt = async function (...args) { const r = await orig.apply(this, args); captured = r; return r; };
  node[prop] = 'continue';
  let err = null;
  try { await app.queuePrompt(0, 1); } catch (e) { err = String(e); }
  node[prop] = null;
  api.queuePrompt = orig;
  done({ok: !err, err, captured, gate: node.id});
})().catch(e => done({ok: false, error: String(e)}));
"""

CSS_FOCUS = r"""
const style = document.createElement('style');
style.id = 'dawasteh-shot';
style.textContent = `
  .comfyui-menu, .comfy-menu, .side-tool-bar-container, .workflow-tabs-container, .p-toast, .graph-canvas-menu,
  .comfyui-body-top, .comfyui-body-left, .comfyui-body-right, .comfyui-body-bottom, .actionbar, .comfy-menu-button-wrapper,
  .splitter-overlay-root > .p-splitter-gutter, .bottom-panel, .selection-toolbox, .zoom-controls, nav, header,
  [data-testid="graph-canvas-toolbar"], .p-dialog-mask, .comfy-modal, .p-buttongroup.absolute, button:has(> .pi-bars), .pi-bars
  { display: none !important; }
`;
document.head.appendChild(style);
return true;
"""


class ComfyDriver:
    def __init__(self, url: str = "http://127.0.0.1:8192", headless: bool = True):
        self.url = url.rstrip("/")
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-extensions")
        options.add_argument("--force-device-scale-factor=1")
        options.add_argument("--window-size=1920,1200")
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        options.add_argument("--mute-audio")
        self.driver = webdriver.Edge(options=options)
        self.driver.set_script_timeout(600)
        self.frontend = None

    # -- lifecycle --------------------------------------------------------------------------------------------------
    def open(self) -> dict:
        self.driver.get(self.url)
        WebDriverWait(self.driver, 120).until(lambda d: d.execute_script("return document.readyState") == "complete")
        WebDriverWait(self.driver, 180).until(
            lambda d: d.execute_script("return Boolean(window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app)"))
        res = self.driver.execute_async_script(JS_BOOT)
        self.frontend = res.get("version")
        # Focus mode hides the menus, sidebars, queue popover and the right-hand properties panel.
        self.driver.execute_script(
            "window.comfyAPI.app.app.extensionManager.command.execute('Workspace.ToggleFocusMode')")
        time.sleep(1.0)
        return res

    def close(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass

    # -- HTTP -------------------------------------------------------------------------------------------------------
    def get_json(self, path: str, timeout: float = 30):
        with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
            return json.load(r)

    def post_json(self, path: str, payload: dict | None = None, timeout: float = 60):
        data = json.dumps(payload or {}).encode()
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return json.loads(body) if body else {}

    def upload(self, local: Path, subfolder: str = "", kind: str = "image", overwrite: bool = True) -> dict:
        """Upload an input file through /upload/image (images, audio and video all land in input/)."""
        boundary = "----dawasteh" + str(time.time_ns())
        parts = []
        def field(name, value):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        field("type", "input")
        field("subfolder", subfolder)
        field("overwrite", "true" if overwrite else "false")
        data = Path(local).read_bytes()
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{Path(local).name}\"\r\n"
                      f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(self.url + "/upload/image", data=b"".join(parts),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)

    def free(self) -> None:
        self.post_json("/free", {"unload_models": True, "free_memory": True})

    # -- workflow ---------------------------------------------------------------------------------------------------
    def load(self, workflow: dict) -> dict:
        res = self.driver.execute_async_script(JS_LOAD, workflow)
        if not res.get("ok"):
            raise RuntimeError("load failed: " + json.dumps(res)[:2000])
        return res

    def patch(self, patches: list[dict]) -> dict:
        res = self.driver.execute_async_script(JS_PATCH, patches)
        if not res.get("ok"):
            raise RuntimeError("patch failed: " + json.dumps(res)[:2000])
        bad = [entry for entry in res["log"] if "error" in entry]
        if bad:
            raise RuntimeError("patch errors: " + json.dumps(bad, ensure_ascii=False)[:3000])
        return res

    def queue(self) -> str:
        before = set(self.get_json("/history?max_items=10000").keys())
        res = self.driver.execute_async_script(JS_QUEUE)
        captured = res.get("captured") or {}
        prompt_id = captured.get("prompt_id")
        if not prompt_id:
            # Fall back to the queue: this test server has no other client.
            deadline = time.time() + 20
            while time.time() < deadline and not prompt_id:
                q = self.get_json("/queue")
                ids = [item[1] for item in q["queue_running"] + q["queue_pending"]]
                hist = set(self.get_json("/history?max_items=10000").keys()) - before
                ids = [i for i in ids if i not in before] + list(hist)
                prompt_id = ids[0] if ids else None
                time.sleep(0.5)
        if not prompt_id:
            raise RuntimeError("queue failed: " + json.dumps(res, ensure_ascii=False)[:4000])
        return prompt_id

    def wait(self, prompt_id: str, timeout: float = 7200, poll: float = 1.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            hist = self.get_json(f"/history/{prompt_id}")
            entry = hist.get(prompt_id)
            if entry and entry.get("status", {}).get("completed") is not None and (
                    entry["status"].get("completed") or entry["status"].get("status_str") == "error"):
                return entry
            if entry and entry.get("status", {}).get("status_str") in ("error", "success"):
                return entry
            time.sleep(poll)
        raise TimeoutError(f"prompt {prompt_id} did not finish in {timeout} s")

    # -- Pixaroma pause gates ---------------------------------------------------------------------------------------
    def continue_gate(self, gate: int | None = None) -> str:
        """Press Continue on a Pixaroma pause gate (by node id, default: the first gate) like the node's button."""
        before = set(self.get_json("/history?max_items=10000").keys())
        res = self.driver.execute_async_script(JS_CONTINUE, gate)
        captured = (res or {}).get("captured") or {}
        prompt_id = captured.get("prompt_id")
        if not prompt_id:
            deadline = time.time() + 20
            while time.time() < deadline and not prompt_id:
                q = self.get_json("/queue")
                ids = [item[1] for item in q["queue_running"] + q["queue_pending"]]
                hist = set(self.get_json("/history?max_items=10000").keys()) - before
                ids = [i for i in ids if i not in before] + list(hist)
                prompt_id = ids[0] if ids else None
                time.sleep(0.5)
        if not prompt_id:
            raise RuntimeError("continue failed: " + json.dumps(res, ensure_ascii=False)[:3000])
        return prompt_id

    # -- screenshot -------------------------------------------------------------------------------------------------
    def screenshot(self, path: Path, remove_types=NOTE_TYPES, remove_ids=(), keep_ids=(), max_width: int = 3600,
                   max_height: int = 2600, min_scale: float = 0.55, max_scale: float = 1.0, margin: int = 40,
                   compact: bool = True) -> dict:
        prep = self.driver.execute_async_script(JS_PREPARE_SHOT, {"remove_types": list(remove_types),
                                                                  "remove_ids": list(remove_ids),
                                                                  "keep_ids": list(keep_ids), "compact": compact})
        if not prep.get("ok"):
            raise RuntimeError("prepare shot failed: " + json.dumps(prep))
        bx, by, bw, bh = prep["bounds"]
        scale = min(max_scale, (max_width - 2 * margin) / bw, (max_height - 2 * margin) / bh)
        scale = max(scale, min_scale)
        width = int(bw * scale + 2 * margin)
        height = int(bh * scale + 2 * margin)
        self.driver.execute_script(CSS_FOCUS)
        self.driver.set_window_size(width, height)
        time.sleep(1.5)
        inner = self.driver.execute_script("return [window.innerWidth, window.innerHeight]")
        # Headless windows can report a slightly smaller viewport; grow once to compensate.
        if inner[0] < width or inner[1] < height:
            self.driver.set_window_size(width + (width - inner[0]), height + (height - inner[1]))
            time.sleep(1.0)
        fit = self.driver.execute_async_script(JS_FIT, [bx, by, bw, bh], scale, margin)
        png = self.driver.execute_cdp_cmd("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": False,
            "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1}})
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(png["data"]))
        self.driver.set_window_size(1920, 1200)
        self.driver.execute_script("const s = document.getElementById('dawasteh-shot'); if (s) s.remove();")
        return {"scale": round(scale, 3), "size": [width, height], "nodes": prep["nodes"], "fit": fit}


def history_files(entry: dict) -> list[dict]:
    """Every output file of a history entry: {node, kind, filename, subfolder, type}."""
    files = []
    for node_id, out in (entry.get("outputs") or {}).items():
        for kind, items in out.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    files.append({"node": node_id, "kind": kind, "filename": item["filename"],
                                  "subfolder": item.get("subfolder", ""), "type": item.get("type", "output")})
    return files


def history_texts(entry: dict) -> dict:
    texts = {}
    for node_id, out in (entry.get("outputs") or {}).items():
        for kind in ("text", "string", "texts"):
            items = out.get(kind)
            if isinstance(items, list) and items and all(isinstance(t, str) for t in items):
                texts[node_id] = "\n".join(items)
            elif isinstance(items, str):
                texts[node_id] = items
    return texts


def history_error(entry: dict) -> str | None:
    for msg in entry.get("status", {}).get("messages", []):
        if msg and msg[0] == "execution_error":
            data = msg[1]
            return f"{data.get('node_type')} #{data.get('node_id')}: {data.get('exception_type')}: {data.get('exception_message')}"[:3000]
    if entry.get("status", {}).get("status_str") == "error":
        return "error (no message)"
    return None


def load_workflow(path: Path, props: dict | None = None) -> dict:
    wf = json.loads(Path(path).read_text(encoding="utf-8"))
    return copy.deepcopy(wf)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("workflow", type=Path)
    ap.add_argument("--patch", default="[]", help="JSON list of patches")
    ap.add_argument("--shot", type=Path)
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--url", default="http://127.0.0.1:8192")
    args = ap.parse_args()
    d = ComfyDriver(args.url)
    try:
        print(d.open())
        print(d.load(load_workflow(args.workflow)))
        print(d.patch(json.loads(args.patch)))
        if not args.no_run:
            pid = d.queue()
            t0 = time.time()
            entry = d.wait(pid)
            print("done", round(time.time() - t0, 1), "s", history_error(entry), history_files(entry))
        if args.shot:
            print(d.screenshot(args.shot))
    finally:
        d.close()
