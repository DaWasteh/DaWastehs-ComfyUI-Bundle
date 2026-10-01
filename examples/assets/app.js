/* ComfyUI-Bundle example gallery – plain JS, no build step. Data comes from gallery-data.js (window.GALLERY),
   written by tools/examples/build_gallery.py. Works on GitHub Pages and from a local checkout (file://). */
(() => {
  "use strict";
  const G = window.GALLERY || { workflows: [], categories: [], ideas: [], families: [] };
  const app = document.getElementById("app");
  const byId = new Map(G.workflows.map(w => [w.id, w]));
  // shipped with the page (assets/vendor, Apache-2.0 / MIT): a blocked CDN (tracking prevention, ad blockers) left the
  // 3D outputs without a viewer
  const MODEL_VIEWER = "assets/vendor/model-viewer.min.js";
  const MESHOPT_DECODER = "assets/vendor/meshopt_decoder.js";
  const state = { q: "", cat: "", inp: new Set(), out: new Set(), onlyEx: false, scroll: 0 };

  // ---------------------------------------------------------------- helpers
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const enc = p => String(p).split("/").map(encodeURIComponent).join("/");
  const src = (wf, file) => enc(wf.dir) + "/" + enc(file);
  const nf1 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const gib = v => (v == null ? "–" : nf1.format(v) + " GiB");
  const dur = s => {
    if (s == null) return "–";
    if (s < 60) return Math.round(s) + " s";
    const m = Math.floor(s / 60), r = Math.round(s % 60);
    return m < 60 ? `${m} min ${r ? r + " s" : ""}`.trim() : `${Math.floor(m / 60)} h ${m % 60} min`;
  };
  const KIND_ICON = { image: "🖼️", video: "🎬", audio: "🎵", model: "🧊", text: "📝", none: "⚙️" };
  const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

  function toast(msg) {
    const t = document.getElementById("toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toast.timer); toast.timer = setTimeout(() => t.classList.remove("show"), 1800);
  }
  async function copyText(text, what = "Kopiert") {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); ta.remove();
    }
    toast(what);
  }
  async function copyWorkflow(wf) {
    const url = "workflows/" + enc(wf.file);
    try {
      const r = await fetch(url); if (!r.ok) throw new Error(r.status);
      await copyText(await r.text(), "Workflow-JSON kopiert – in ComfyUI mit Strg+V einfügen");
    } catch {
      window.open(rawUrl(wf), "_blank", "noopener");
      toast("Lokal nicht ladbar – GitHub-Rohdatei geöffnet");
    }
  }
  const rawUrl = wf => `https://raw.githubusercontent.com/${G.repo}/${G.branch}/workflows/${enc(wf.file)}`;
  const ghUrl = wf => `https://github.com/${G.repo}/blob/${G.branch}/workflows/${enc(wf.file)}`;
  let mvRequested = false, mvFailed = false;
  function mvFallback() {  // viewer script missing: say so next to every model instead of an empty box
    document.querySelectorAll("model-viewer").forEach(m => {
      if (m.dataset.fallback) return; m.dataset.fallback = "1";
      m.insertAdjacentHTML("afterend", `<p class="notice">Die 3D-Ansicht konnte nicht geladen werden. Das Modell lässt sich über „GLB herunterladen“ in Blender, Godot oder einem anderen 3D-Programm öffnen.</p>`);
      m.style.display = "none";
    });
  }
  function needModelViewer() {
    if (mvFailed) { setTimeout(mvFallback, 0); return; }
    if (mvRequested) return; mvRequested = true;
    // the GLBs are meshopt-compressed (tools/examples/build_gallery.py): the decoder location has to be known before the
    // element class loads its first model, so it goes into the documented pre-load config object
    self.ModelViewerElement = Object.assign(self.ModelViewerElement || {}, { meshoptDecoderLocation: MESHOPT_DECODER });
    const s = document.createElement("script"); s.type = "module"; s.src = MODEL_VIEWER;
    s.addEventListener("error", () => { mvFailed = true; mvFallback(); });
    document.head.appendChild(s);
  }

  // ---------------------------------------------------------------- theme
  const themeBtn = document.getElementById("theme-toggle");
  try { const t = localStorage.getItem("gallery-theme"); if (t) document.documentElement.dataset.theme = t; } catch { }
  themeBtn.addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const next = cur === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("gallery-theme", next); } catch { }
  });

  // ---------------------------------------------------------------- lightbox (zoom + pan)
  const lb = document.getElementById("lightbox");
  const lbImg = lb.querySelector("img"), lbStage = lb.querySelector(".lb-stage");
  const view = { s: 1, x: 0, y: 0 };
  const applyView = () => { lbImg.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.s})`; };
  function fitView() {
    const W = lbStage.clientWidth, H = lbStage.clientHeight, w = lbImg.naturalWidth || 1, h = lbImg.naturalHeight || 1;
    view.s = Math.min(W / w, H / h, 1); view.x = (W - w * view.s) / 2; view.y = (H - h * view.s) / 2; applyView();
  }
  function openLightbox(url, title, original) {
    lb.hidden = false; document.body.style.overflow = "hidden";
    lb.querySelector(".lb-title").textContent = title || "";
    const open = lb.querySelector(".lb-open"); open.href = original || url;
    lbImg.onload = fitView; lbImg.src = url; if (lbImg.complete) fitView();
  }
  function closeLightbox() { lb.hidden = true; document.body.style.overflow = ""; lbImg.removeAttribute("src"); }
  lb.querySelector(".lb-close").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !lb.hidden) closeLightbox(); });
  lbStage.addEventListener("wheel", e => {
    e.preventDefault();
    const r = lbStage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    const f = Math.exp(-e.deltaY * 0.0015), s = Math.min(8, Math.max(0.05, view.s * f));
    view.x = mx - (mx - view.x) * (s / view.s); view.y = my - (my - view.y) * (s / view.s); view.s = s; applyView();
  }, { passive: false });
  let drag = null;
  lbStage.addEventListener("pointerdown", e => { drag = { x: e.clientX - view.x, y: e.clientY - view.y }; lbStage.setPointerCapture(e.pointerId); lbStage.classList.add("dragging"); });
  lbStage.addEventListener("pointermove", e => { if (!drag) return; view.x = e.clientX - drag.x; view.y = e.clientY - drag.y; applyView(); });
  lbStage.addEventListener("pointerup", () => { drag = null; lbStage.classList.remove("dragging"); });
  lbStage.addEventListener("dblclick", e => {
    const r = lbStage.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (view.s < 0.99) { const s = 1; view.x = mx - (mx - view.x) * (s / view.s); view.y = my - (my - view.y) * (s / view.s); view.s = s; applyView(); }
    else fitView();
  });
  window.addEventListener("resize", () => { if (!lb.hidden) fitView(); });

  // delegated clicks
  document.addEventListener("click", e => {
    const z = e.target.closest("[data-zoom]");
    if (z) { e.preventDefault(); openLightbox(z.dataset.zoom, z.dataset.title, z.dataset.original); return; }
    const c = e.target.closest("[data-copy]");
    if (c) { e.preventDefault(); copyText(c.dataset.copy, c.dataset.msg || "Kopiert"); return; }
    const cw = e.target.closest("[data-copy-wf]");
    if (cw) { e.preventDefault(); copyWorkflow(byId.get(cw.dataset.copyWf)); }
  });

  // ---------------------------------------------------------------- media
  function mediaHtml(wf, o, title) {
    const u = src(wf, o.src);
    const orig = o.original ? src(wf, o.original) : u;
    switch (o.kind) {
      case "image":
        return `<img src="${u}" alt="${esc(title || o.caption || "")}" loading="lazy" data-zoom="${u}" data-original="${orig}" data-title="${esc(title || "")}"${o.w ? ` width="${o.w}" height="${o.h}"` : ""}>`;
      case "video":
        return `<video src="${u}" controls playsinline preload="metadata"${o.poster ? ` poster="${src(wf, o.poster)}"` : ""}></video>`;
      case "audio":
        return `<audio src="${u}" controls preload="none"></audio>`;
      case "model":
        needModelViewer();
        return `${o.compressed ? `<p class="faint" style="font-size:.78rem;margin:0 0 6px">Für die Web-Ansicht komprimiert (Meshopt, WebP-Texturen), Geometrie unverändert.</p>` : ""}<model-viewer src="${u}" camera-controls auto-rotate touch-action="pan-y" shadow-intensity="1" exposure="1.05" environment-image="neutral" alt="${esc(title || "3D-Modell")}"${o.poster ? ` poster="${src(wf, o.poster)}"` : ""}></model-viewer><p class="faint" style="font-size:.78rem;margin:6px 0 0">Ziehen dreht, Mausrad/zwei Finger zoomen · <a href="${u}" download>GLB herunterladen</a></p>`;
      case "text":
        return `<pre class="text-out">${esc(o.text)}</pre>`;
      default:
        return `<a href="${u}">${esc(o.src)}</a>`;
    }
  }
  function thumbOf(wf) {
    if (wf.thumb) return src(wf, wf.thumb);
    if (wf.shot && wf.shot.thumb) return src(wf, wf.shot.thumb);
    return null;
  }
  const ioText = wf => `${(wf.inputs || []).join(" + ") || "–"} → ${(wf.outputs || []).join(" + ") || "–"}`;

  // ---------------------------------------------------------------- home
  function matches(wf) {
    if (state.cat && wf.category !== state.cat) return false;
    if (state.onlyEx && !(wf.examples || []).length) return false;
    for (const i of state.inp) if (!(wf.inputs || []).includes(i)) return false;
    for (const o of state.out) if (!(wf.outputs || []).includes(o)) return false;
    if (state.q) {
      const hay = [wf.name, wf.old_name, wf.title, wf.summary, wf.category, ...(wf.models || []).map(m => m.name), ...(wf.inputs || []), ...(wf.outputs || [])].join(" ").toLowerCase();
      for (const t of state.q.toLowerCase().split(/\s+/).filter(Boolean)) if (!hay.includes(t)) return false;
    }
    return true;
  }
  function card(wf) {
    const t = thumbOf(wf);
    const kind = wf.kind || "none";
    const chips = [
      `<span class="chip io">${esc(ioText(wf))}</span>`,
      wf.quant ? `<span class="chip quant">${esc(wf.quant)}</span>` : "",
      wf.stats && wf.stats.seconds != null ? `<span class="chip time">⏱ ${dur(wf.stats.seconds)}</span>` : "",
      wf.stats && wf.stats.vram_gib != null ? `<span class="chip vram">VRAM ${gib(wf.stats.vram_gib)}</span>` : "",
      !(wf.examples || []).length ? `<span class="chip warn">${wf.shot ? "nur Screenshot" : "ohne Beispiel"}</span>` : "",
    ].join("");
    return `<a class="card" href="#/w/${esc(wf.id)}">
      <div class="thumb">${t ? `<img src="${t}" alt="" loading="lazy">` : `<span class="ph">${KIND_ICON[kind] || "⚙️"}</span>`}
        <span class="chip kind">${KIND_ICON[kind] || ""} ${(wf.examples || []).length} Beispiel${(wf.examples || []).length === 1 ? "" : "e"}</span></div>
      <div class="body"><div class="title">${esc(wf.title)}</div><div class="name">${esc(wf.name)}</div><div class="chips">${chips}</div></div></a>`;
  }
  function renderHome() {
    const cats = G.categories.map(c => c.name);
    const ins = G.io_inputs || [], outs = G.io_outputs || [];
    const nEx = G.workflows.reduce((a, w) => a + (w.examples || []).length, 0);
    const nWith = G.workflows.filter(w => (w.examples || []).length).length;
    app.innerHTML = `
      <section class="hero">
        <div><h1>Was macht welcher Workflow?</h1>
          <p>Zu jedem Workflow des Bundles: ein Screenshot aus ComfyUI mit Eingabe und Ergebnis im Workflow selbst, die Original-Ausgaben, die verwendeten Prompts und Einstellungen zum Kopieren sowie Dauer und RAM/VRAM-Bedarf der jeweiligen Generierung. Bildmodelle zeigen dieselben Ideen in mehreren Auflösungen mit gleichem Seed.</p></div>
        <div class="stats">
          <div class="stat"><b>${G.workflows.length}</b><span>Workflows</span></div>
          <div class="stat"><b>${nWith}</b><span>mit Beispielausgabe</span></div>
          <div class="stat"><b>${nEx}</b><span>Beispiel-Generierungen</span></div>
        </div>
      </section>
      <section class="filters" aria-label="Filter">
        <input type="search" id="q" placeholder="Suchen: Modell, Quant, Aufgabe, alter Name … (z. B. „FLUX2 FP8“, „Video“, „Song“)" value="${esc(state.q)}">
        <div class="filter-row"><span class="label">Kategorie</span>
          <button class="chip" data-cat="" aria-pressed="${!state.cat}">Alle</button>
          ${cats.map(c => `<button class="chip" data-cat="${esc(c)}" aria-pressed="${state.cat === c}">${esc(c)}</button>`).join("")}</div>
        <div class="filter-row"><span class="label">Eingabe</span>
          ${ins.map(i => `<button class="chip" data-inp="${esc(i)}" aria-pressed="${state.inp.has(i)}">${esc(i)}</button>`).join("")}</div>
        <div class="filter-row"><span class="label">Ausgabe</span>
          ${outs.map(o => `<button class="chip" data-out="${esc(o)}" aria-pressed="${state.out.has(o)}">${esc(o)}</button>`).join("")}
          <button class="chip" data-onlyex aria-pressed="${state.onlyEx}">nur mit Beispielausgabe</button>
          <span class="result-count" id="count"></span></div>
      </section>
      <div id="results"></div>`;
    const results = app.querySelector("#results");
    const draw = () => {
      const list = G.workflows.filter(matches);
      app.querySelector("#count").textContent = `${list.length} von ${G.workflows.length}`;
      const groups = new Map();
      for (const wf of list) { if (!groups.has(wf.category)) groups.set(wf.category, []); groups.get(wf.category).push(wf); }
      results.innerHTML = [...groups].map(([c, wfs]) => `
        <div class="cat"><h2>${esc(c)}</h2><span class="faint">${wfs.length}</span></div>
        <div class="grid">${wfs.map(card).join("")}</div>`).join("") || `<p class="notice">Nichts gefunden.</p>`;
    };
    draw();
    const q = app.querySelector("#q");
    q.addEventListener("input", () => { state.q = q.value; draw(); });
    app.querySelector(".filters").addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.hasAttribute("data-cat")) {
        state.cat = b.dataset.cat;
        app.querySelectorAll("[data-cat]").forEach(x => x.setAttribute("aria-pressed", x.dataset.cat === state.cat));
      } else if (b.dataset.inp) {
        state.inp.has(b.dataset.inp) ? state.inp.delete(b.dataset.inp) : state.inp.add(b.dataset.inp);
        b.setAttribute("aria-pressed", state.inp.has(b.dataset.inp));
      } else if (b.dataset.out) {
        state.out.has(b.dataset.out) ? state.out.delete(b.dataset.out) : state.out.add(b.dataset.out);
        b.setAttribute("aria-pressed", state.out.has(b.dataset.out));
      } else if (b.hasAttribute("data-onlyex")) {
        state.onlyEx = !state.onlyEx; b.setAttribute("aria-pressed", state.onlyEx);
      }
      draw();
    });
    requestAnimationFrame(() => window.scrollTo(0, state.scroll));
  }

  // ---------------------------------------------------------------- workflow page
  function paramsTable(ex) {
    const skip = new Set(["prompt", "idea", "negative"]);
    const LABEL = { seed: "Seed", width: "Breite", height: "Höhe", steps: "Schritte", cfg: "CFG", sampler: "Sampler",
      sampler_name: "Sampler", shift: "Shift", guidance: "Guidance",
      scheduler: "Scheduler", seconds: "Länge", duration: "Länge", fps: "FPS", frames: "Frames", denoise: "Denoise",
      target: "Ziel", detail: "Länge", language: "Sprache", tags: "Stil-Tags", voice: "Stimme", lyrics: "Songtext",
      objects: "Objekte", instruction: "Anweisung", model: "Modell", resolution: "Auflösung", strength: "Stärke" };
    const rows = Object.entries(ex.params || {}).filter(([k, v]) => !skip.has(k) && v !== "" && v != null && typeof v !== "object");
    if (ex.params && ex.params.width && ex.params.height) {
      const i = rows.findIndex(([k]) => k === "width"); rows.splice(i, 1, ["Größe", `${ex.params.width} × ${ex.params.height} px`]);
      const j = rows.findIndex(([k]) => k === "height"); if (j >= 0) rows.splice(j, 1);
    }
    if (!rows.length) return "";
    return `<table class="kv">${rows.map(([k, v]) => `<tr><th>${esc(LABEL[k] || k)}</th><td>${esc(v)}</td></tr>`).join("")}</table>`;
  }
  function measureBox(ex) {
    const m = ex.measure || {};
    const gpus = (m.vram || []).filter(g => g.gib > 0.3);
    const rows = [
      ["Dauer (Ausführung)", dur(m.exec_seconds ?? m.seconds)],
      ...gpus.map(g => [`VRAM ${esc(g.gpu)}`, `${gib(g.gib)} belegt${g.alloc_gib != null ? ` <span class="faint">· PyTorch-Spitze ${gib(g.alloc_gib)}</span>` : ""}<div class="meter" title="${nf1.format(g.gib)} von ${g.total} GiB"><i style="width:${Math.min(100, 100 * g.gib / g.total).toFixed(1)}%"></i></div>`]),
      ["RAM (ComfyUI-Prozess)", gib(m.ram_gib)],
    ];
    if (m.llm_vram_gib) rows.splice(1 + gpus.length, 0, ["VRAM llama-server (RX 9070 XT)", gib(m.llm_vram_gib)]);
    return `<div class="box"><h3>Messung <span class="faint" style="font-size:.78rem;font-weight:400">R9700 32 GB · <a href="#/info">Methode</a></span></h3>
      <table class="kv">${rows.map(([k, v]) => `<tr><th>${k}</th><td>${v}</td></tr>`).join("")}</table>
      ${m.note ? `<p class="faint" style="font-size:.8rem;margin:.5em 0 0">${esc(m.note)}</p>` : ""}</div>`;
  }
  function exampleGroups(wf) {
    const groups = [];
    const idx = new Map();
    for (const ex of wf.examples || []) {
      const g = ex.idea || ex.key;
      if (!idx.has(g)) { idx.set(g, groups.length); groups.push({ id: g, title: ex.title, items: [] }); }
      groups[idx.get(g)].items.push(ex);
    }
    return groups;
  }
  function renderWorkflow(id, exKey) {
    const wf = byId.get(id);
    if (!wf) { app.innerHTML = `<p class="notice">Workflow „${esc(id)}“ nicht gefunden. <a href="#/">Zur Übersicht</a></p>`; return; }
    document.title = `${wf.title} · ComfyUI-Bundle Beispiele`;
    const groups = exampleGroups(wf);
    let gi = Math.max(0, groups.findIndex(g => g.items.some(e => e.key === exKey)));
    const fam = (G.families || []).filter(f => f.members.includes(wf.id));
    const models = (wf.models || []).map(m => `<li><span class="faint">${esc(m.role)}:</span> <code>${esc(m.name)}</code>${m.quant ? ` <span class="chip quant">${esc(m.quant)}</span>` : ""}${m.gib ? ` <span class="faint">${gib(m.gib)}</span>` : ""}</li>`).join("");
    app.innerHTML = `
      <div class="crumbs"><a href="#/">Workflows</a> › ${esc(wf.category)}</div>
      <div class="wf-head">
        <div>
          <h1>${esc(wf.title)}</h1>
          <div class="wf-name"><code>${esc(wf.name)}.json</code>
            <button class="btn small" data-copy="${esc(wf.name)}" data-msg="Name kopiert">Name kopieren</button>
            ${wf.old_name && wf.old_name !== wf.name ? `<span class="faint" style="font-size:.82rem">bis v1.3.0: <code>${esc(wf.old_name)}</code></span>` : ""}</div>
          <p class="summary">${esc(wf.summary || "")}</p>
        </div>
        <div class="wf-actions">
          <a class="btn primary" href="workflows/${enc(wf.file)}" download="${esc(wf.name)}.json">Workflow herunterladen</a>
          <button class="btn" data-copy-wf="${esc(wf.id)}">Workflow-JSON kopieren</button>
          <a class="btn" href="${ghUrl(wf)}" rel="noopener">Auf GitHub</a>
        </div>
      </div>
      <div class="facts">
        <div class="fact"><div class="k">Eingabe → Ausgabe</div><div class="v">${esc(ioText(wf))}</div></div>
        <div class="fact"><div class="k">Kategorie / Ordner</div><div class="v">${esc(wf.category)}</div></div>
        ${wf.stats ? `<div class="fact"><div class="k">Typisch (Hauptbeispiel)</div><div class="v">⏱ ${dur(wf.stats.seconds)} · VRAM ${gib(wf.stats.vram_gib)} · RAM ${gib(wf.stats.ram_gib)}</div></div>` : ""}
        ${models ? `<div class="fact" style="grid-column: span 2"><div class="k">Modelle</div><ul class="models">${models}</ul></div>` : ""}
      </div>
      ${wf.note ? `<p class="notice">${esc(wf.note)}</p>` : ""}
      ${fam.length ? `<p>${fam.map(f => `Gleiche Prompts mit anderen Varianten/Quants: <a href="#/quants/${esc(f.id)}">${esc(f.name)}</a>`).join(" · ")}</p>` : ""}
      ${wf.shot ? `<figure class="shot"><img src="${src(wf, wf.shot.preview || wf.shot.src)}" alt="Screenshot des Workflows in ComfyUI" loading="lazy" data-zoom="${src(wf, wf.shot.src)}" data-title="${esc(wf.name)} · Screenshot"><figcaption>Screenshot aus ComfyUI nach dem Hauptbeispiel – Eingaben und Ergebnis direkt im Workflow, Erklärungstafeln ausgeblendet. Klicken zum Zoomen.</figcaption></figure>` : ""}
      ${groups.length ? `<h2>Beispiele</h2><div class="tabs" role="tablist">${groups.map((g, i) => `<button class="tab" role="tab" data-g="${i}" aria-selected="${i === gi}">${esc(g.title)}${g.items.length > 1 ? ` <span class="faint">(${g.items.length})</span>` : ""}</button>`).join("")}</div><div id="exview"></div>` : ""}
    `;
    if (!groups.length) return;
    const exview = app.querySelector("#exview");
    const showGroup = (g, key) => {
      const items = g.items;
      let cur = Math.max(0, items.findIndex(e => e.key === key));
      let outSel = 0;
      const draw = () => {
        const ex = items[cur];
        const outs = ex.outputs || [];
        const o = outs[outSel] || outs[0];
        const multiEx = items.length > 1, multiOut = !multiEx && outs.length > 1;
        const variants = multiEx
          ? items.map((e, i) => { const t = (e.outputs || [])[0]; return `<button class="variant" data-v="${i}" aria-current="${i === cur}">${t && t.thumb ? `<img src="${src(wf, t.thumb)}" alt="">` : ""}<div>${esc(e.variant || e.key)}</div></button>`; }).join("")
          : multiOut ? outs.map((x, i) => `<button class="variant" data-o="${i}" aria-current="${i === outSel}">${x.thumb ? `<img src="${src(wf, x.thumb)}" alt="">` : `<div style="padding:18px 10px">${KIND_ICON[x.kind] || ""}</div>`}<div>${esc(x.caption || x.kind)}</div></button>`).join("") : "";
        const canCompare = (multiEx && items.every(e => (e.outputs || [])[0] && e.outputs[0].kind === "image")) ||
          (multiOut && outs.filter(x => x.kind === "image").length > 1);
        const inputs = (ex.inputs || []).map(i => `<div class="in">${i.kind === "image" ? `<img src="${src(wf, i.src)}" alt="" data-zoom="${src(wf, i.src)}" data-title="${esc(i.caption || "Eingabe")}">` : i.kind === "video" ? `<video src="${src(wf, i.src)}" controls preload="metadata"></video>` : i.kind === "audio" ? `<audio src="${src(wf, i.src)}" controls preload="none"></audio>` : `<pre class="text-out">${esc(i.text || "")}</pre>`}<div class="cap">${esc(i.caption || "")}</div></div>`).join("");
        // Text-only workflows (prompt writers, LLM tools): their texts are the result and go into the stage
        const textStage = !o && (ex.texts || []).length > 0;
        const textBox = t => `<div class="box"><h3>${esc(t.title)} <button class="btn small" data-copy="${esc(t.text)}">Kopieren</button></h3><pre class="text-out">${esc(t.text)}</pre></div>`;
        const texts = textStage ? "" : (ex.texts || []).map(textBox).join("");
        const downloads = outs.filter(x => x.original).map(x => `<a class="btn small" href="${src(wf, x.original)}" download>${esc(x.original_label || "Original")}</a>`).join(" ");
        exview.innerHTML = `
          <div class="example">
            <div class="stage">
              ${inputs ? `<div class="io-strip"><h4>Eingabe</h4><div class="inputs">${inputs}</div></div>` : ""}
              <div class="io-strip"><h4>Ausgabe${o && o.caption ? ` · ${esc(o.caption)}` : ""}</h4>
                <div class="media">${o ? mediaHtml(wf, o, `${wf.title} · ${ex.title}${ex.variant ? " · " + ex.variant : ""}`) : textStage ? `<div class="text-results">${ex.texts.map(textBox).join("")}</div>` : `<p class="faint">Keine Ausgabe.</p>`}</div></div>
              ${variants ? `<div class="variants">${variants}</div>` : ""}
              ${canCompare ? `<div class="row"><button class="btn small" id="cmpbtn">${multiEx ? "Größen" : "Ausgaben"} nebeneinander vergleichen</button></div><div id="cmp"></div>` : ""}
              ${downloads ? `<div class="row">${downloads}</div>` : ""}
            </div>
            <div class="side">
              ${ex.params && ex.params.prompt ? `<div class="box"><h3>Prompt <button class="btn small" data-copy="${esc(ex.params.prompt)}" data-msg="Prompt kopiert">Kopieren</button></h3><pre class="prompt">${esc(ex.params.prompt)}</pre>${ex.params.negative ? `<p class="faint" style="font-size:.8rem;margin:.6em 0 .2em">Negativ</p><pre class="prompt">${esc(ex.params.negative)}</pre>` : ""}</div>` : ""}
              ${paramsTable(ex) ? `<div class="box"><h3>Einstellungen <button class="btn small" data-copy="${esc(JSON.stringify(ex.params, null, 2))}" data-msg="Einstellungen kopiert">Kopieren</button></h3>${paramsTable(ex)}${ex.changes ? `<p class="faint" style="font-size:.8rem;margin:.6em 0 0">${esc(ex.changes)}</p>` : ""}</div>` : ""}
              ${measureBox(ex)}
              ${texts}
            </div>
          </div>`;
        exview.querySelectorAll("[data-v]").forEach(b => b.addEventListener("click", () => { cur = +b.dataset.v; outSel = 0; draw(); }));
        exview.querySelectorAll("[data-o]").forEach(b => b.addEventListener("click", () => { outSel = +b.dataset.o; draw(); }));
        const cb = exview.querySelector("#cmpbtn");
        if (cb) cb.addEventListener("click", () => {
          const imgs = multiEx ? items.map(e => ({ u: src(wf, e.outputs[0].src), l: e.variant || e.key })) : outs.filter(x => x.kind === "image").map(x => ({ u: src(wf, x.src), l: x.caption || "" }));
          compareWidget(exview.querySelector("#cmp"), imgs, 0, imgs.length - 1);
        });
        history.replaceState(null, "", `#/w/${wf.id}/${ex.key}`);
      };
      draw();
    };
    const tabs = app.querySelectorAll(".tab");
    tabs.forEach(t => t.addEventListener("click", () => {
      tabs.forEach(x => x.setAttribute("aria-selected", x === t));
      showGroup(groups[+t.dataset.g]);
    }));
    showGroup(groups[gi], exKey);
  }

  // split compare with two selectors
  function compareWidget(host, imgs, a, b) {
    host.innerHTML = `
      <div class="row" style="margin:8px 0">
        <label>Links <select id="ca">${imgs.map((x, i) => `<option value="${i}" ${i === a ? "selected" : ""}>${esc(x.l)}</option>`).join("")}</select></label>
        <label>Rechts <select id="cb">${imgs.map((x, i) => `<option value="${i}" ${i === b ? "selected" : ""}>${esc(x.l)}</option>`).join("")}</select></label>
        <span class="faint" style="font-size:.8rem">Regler ziehen; beide Bilder werden auf dieselbe Breite skaliert.</span>
      </div>
      <div class="split"><img class="base" alt=""><div class="top"><img alt=""></div><div class="handle"></div><span class="lbl l"></span><span class="lbl r"></span></div>`;
    const split = host.querySelector(".split"), base = split.querySelector(".base"), top = split.querySelector(".top img");
    const topWrap = split.querySelector(".top"), handle = split.querySelector(".handle");
    const set = () => {
      const ia = +host.querySelector("#ca").value, ib = +host.querySelector("#cb").value;
      top.src = imgs[ia].u; base.src = imgs[ib].u;
      split.querySelector(".lbl.l").textContent = imgs[ia].l; split.querySelector(".lbl.r").textContent = imgs[ib].l;
    };
    const move = x => {
      const r = split.getBoundingClientRect(); const p = Math.min(100, Math.max(0, (x - r.left) / r.width * 100));
      topWrap.style.clipPath = `inset(0 ${100 - p}% 0 0)`; handle.style.left = p + "%";
    };
    host.querySelectorAll("select").forEach(s => s.addEventListener("change", set));
    let on = false;
    split.addEventListener("pointerdown", e => { on = true; split.setPointerCapture(e.pointerId); move(e.clientX); });
    split.addEventListener("pointermove", e => { if (on) move(e.clientX); });
    split.addEventListener("pointerup", () => { on = false; });
    set();
  }

  // ---------------------------------------------------------------- model comparison (same idea, all image models)
  function renderCompare(ideaId, size) {
    const ideas = G.ideas || [];
    const idea = ideas.find(i => i.id === ideaId) || ideas[0];
    if (!idea) { app.innerHTML = `<p class="notice">Keine Vergleichsdaten.</p>`; return; }
    const withIdea = G.workflows.filter(w => (w.examples || []).some(e => e.idea === idea.id));
    const sizes = [...new Set(withIdea.flatMap(w => w.examples.filter(e => e.idea === idea.id).map(e => e.variant)))]
      .filter(Boolean).sort((a, b) => parseInt(b) - parseInt(a));
    // largest size first; the default is the largest one (almost) every model rendered
    const covered = s => withIdea.filter(w => w.examples.some(e => e.idea === idea.id && e.variant === s)).length;
    const sz = size && sizes.includes(size) ? size : (sizes.find(s => covered(s) >= 0.8 * withIdea.length) || sizes[0]);
    const tiles = [];
    for (const wf of G.workflows) {
      const ex = (wf.examples || []).find(e => e.idea === idea.id && e.variant === sz);
      if (ex && ex.outputs && ex.outputs[0]) tiles.push({ wf, ex });
    }
    app.innerHTML = `
      <h1>Modellvergleich</h1>
      <p class="summary">Dieselbe Idee mit demselben Seed durch alle Bildmodelle. Jedes Modell nutzt die Standardeinstellungen seines Workflows (Schritte, CFG, Sampler). Anime-Modelle bekommen die Idee als Tag-Liste. Zwei Kacheln anhaken, um sie mit dem Regler zu vergleichen.</p>
      <div class="cmp-controls">
        <div class="tabs">${ideas.map(i => `<a class="tab" href="#/vergleich/${i.id}/${encodeURIComponent(sz || "")}" aria-selected="${i.id === idea.id}">${esc(i.title)}</a>`).join("")}</div>
        <div class="tabs">${sizes.map(s => `<a class="tab" href="#/vergleich/${idea.id}/${encodeURIComponent(s)}" aria-selected="${s === sz}">${esc(s)}</a>`).join("")}</div>
      </div>
      <details class="box"><summary>Prompt dieser Idee</summary><pre class="prompt">${esc(idea.text)}</pre><p class="faint" style="font-size:.8rem">Tag-Variante: ${esc(idea.tags)}</p></details>
      <div id="cmp" style="margin:14px 0"></div>
      <div class="cmp-grid">${tiles.map(({ wf, ex }, i) => {
        const o = ex.outputs[0]; const m = ex.measure || {};
        const v = (m.vram || []).reduce((a, g) => a + g.gib, 0);
        return `<div class="tile" data-i="${i}"><img src="${src(wf, o.thumb || o.src)}" alt="" loading="lazy" data-zoom="${src(wf, o.src)}" data-title="${esc(wf.title)} · ${esc(ex.variant)}">
          <label class="pick chip"><input type="checkbox" data-pick="${i}"> vergleichen</label>
          <div class="cap"><a href="#/w/${wf.id}/${ex.key}">${esc(wf.title)}</a><span class="faint mono" style="font-size:.7rem">${esc(wf.name)}</span>
          <span><span class="chip time">⏱ ${dur(m.exec_seconds ?? m.seconds)}</span> <span class="chip vram">VRAM ${gib(v)}</span></span></div></div>`;
      }).join("")}</div>`;
    const picked = [];
    app.querySelectorAll("[data-pick]").forEach(cb => cb.addEventListener("change", () => {
      const i = +cb.dataset.pick;
      if (cb.checked) { picked.push(i); if (picked.length > 2) { const d = picked.shift(); app.querySelector(`[data-pick="${d}"]`).checked = false; } }
      else picked.splice(picked.indexOf(i), 1);
      app.querySelectorAll(".tile").forEach(t => t.classList.toggle("picked", picked.includes(+t.dataset.i)));
      if (picked.length === 2) {
        const imgs = picked.map(p => ({ u: src(tiles[p].wf, tiles[p].ex.outputs[0].src), l: tiles[p].wf.title }));
        compareWidget(app.querySelector("#cmp"), imgs, 0, 1);
        app.querySelector("#cmp").scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }));
  }

  // ---------------------------------------------------------------- quant / variant families
  function familyTabs(f, members) {
    if (f.keys) return f.keys.map(k => ({ id: k.key, title: k.title }));
    return (G.ideas || []).filter(i => members.every(w => (w.examples || []).some(e => e.idea === i.id && e.variant === f.variant)))
      .map(i => ({ id: i.id, title: i.title }));
  }
  function familyExample(f, w, tab) {
    return (w.examples || []).find(e => f.keys ? e.key === tab : (e.idea === tab && e.variant === f.variant));
  }
  function renderQuants(famId) {
    const fams = G.families || [];
    const blocks = fams.map(f => {
      const members = f.members.map(id => byId.get(id)).filter(Boolean);
      const tabs = familyTabs(f, members);
      const rows = members.map(w => {
        const ex = familyExample(f, w, (tabs[0] || {}).id) || {};
        const m = ex.measure || {}; const v = (m.vram || []).reduce((a, g) => a + g.gib, 0);
        const main = (w.models || [])[0];
        return `<tr><td><a href="#/w/${w.id}">${esc(w.title)}</a></td><td>${esc(w.quant || "")}</td><td class="num">${main ? gib(main.gib) : "–"}</td><td class="num">${dur(m.exec_seconds ?? m.seconds)}</td><td class="num">${gib(v)}</td><td class="num">${gib(m.ram_gib)}</td></tr>`;
      }).join("");
      return `<section class="family" id="fam-${esc(f.id)}"><h2>${esc(f.name)}</h2><p class="summary">${esc(f.note || "")}</p>
        <div class="tabs">${tabs.map((t, k) => `<button class="tab" data-tab="${esc(t.id)}" aria-selected="${k === 0}">${esc(t.title)}</button>`).join("")}</div>
        <div class="fam-cmp"></div><div class="members"></div>
        <table class="data"><thead><tr><th>Workflow</th><th>Quant</th><th style="text-align:right">Modelldatei</th><th style="text-align:right">Dauer${f.variant ? " " + esc(f.variant) : ""}</th><th style="text-align:right">VRAM</th><th style="text-align:right">RAM</th></tr></thead><tbody>${rows}</tbody></table></section>`;
    }).join("");
    app.innerHTML = `<h1>Quant- und Varianten-Vergleich</h1>
      <p class="summary">Workflows desselben Modells in verschiedenen Quantisierungen (BF16, FP16, FP32, FP8, GGUF Q8/Q6_K, INT8) oder Varianten (Turbo-LoRA, Merge, destilliert) mit identischem Prompt, Seed und identischer Größe. Bei Bildern Regler ziehen oder anklicken zum Zoomen, bei Video und Audio nebeneinander abspielen.</p>
      ${blocks || `<p class="notice">Noch keine Vergleichsgruppen.</p>`}`;
    for (const f of fams) {
      const sec = document.getElementById("fam-" + f.id); if (!sec) continue;
      const members = f.members.map(id => byId.get(id)).filter(Boolean);
      const show = tab => {
        const items = members.map(w => ({ w, ex: familyExample(f, w, tab) })).filter(x => x.ex && x.ex.outputs && x.ex.outputs[0]);
        const allImages = items.every(x => x.ex.outputs[0].kind === "image");
        sec.querySelector(".members").innerHTML = items.map(({ w, ex }) => {
          const o = ex.outputs[0];
          const media = o.kind === "image"
            ? `<img src="${src(w, o.thumb || o.src)}" alt="" loading="lazy" data-zoom="${src(w, o.src)}" data-title="${esc(w.title)}">`
            : `<div style="padding:8px">${mediaHtml(w, o, w.title)}</div>`;
          return `<div class="tile">${media}<div class="cap"><a href="#/w/${w.id}/${ex.key}">${esc(w.title)}</a><span class="chip quant">${esc(w.quant || "")}</span></div></div>`;
        }).join("");
        const cmp = sec.querySelector(".fam-cmp");
        if (allImages && items.length > 1) compareWidget(cmp, items.map(({ w, ex }) => ({ u: src(w, ex.outputs[0].src), l: w.quant || w.title })), 0, 1);
        else cmp.innerHTML = "";
      };
      const tabs = sec.querySelectorAll(".tab");
      tabs.forEach(t => t.addEventListener("click", () => { tabs.forEach(x => x.setAttribute("aria-selected", x === t)); show(t.dataset.tab); }));
      if (tabs[0]) show(tabs[0].dataset.tab);
    }
    if (famId) { const s = document.getElementById("fam-" + famId); if (s) s.scrollIntoView(); }
  }

  // ---------------------------------------------------------------- info
  function renderInfo() {
    const sys = G.system || {};
    const none = G.workflows.filter(w => !(w.examples || []).length);
    const renamed = G.workflows.filter(w => w.old_name && w.old_name !== w.name);
    app.innerHTML = `<div class="prose">
      <h1>Messung &amp; Hinweise</h1>
      <h2>So entstanden die Beispiele</h2>
      <p>Jedes Beispiel ist ein normaler Lauf des jeweiligen Workflows über das echte ComfyUI-Frontend (${esc(sys.frontend || "")}), nur Prompt, Seed, Größe und Eingabedateien wurden geändert. Seeds stehen fest (<code>control_after_generate = fixed</code>), damit jedes Ergebnis mit denselben Werten reproduzierbar ist. Bilder liegen in voller Auflösung als WebP vor; beim Hauptbeispiel jedes Workflows steckt der komplette Workflow in der Datei („Volle Auflösung“ herunterladen und in ComfyUI ziehen).</p>
      <h2>System</h2>
      <table class="kv">${Object.entries(sys).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</table>
      <h2>Was die Zahlen bedeuten</h2>
      <ul>
        <li><strong>Dauer</strong>: reine Ausführungszeit laut ComfyUI (vom Start bis zum Ende des Laufs). Beim ersten Beispiel eines Workflows ist das Laden der Modelle von der SSD enthalten, die weiteren Größen laufen mit bereits geladenen Modellen.</li>
        <li><strong>VRAM</strong>: höchster belegter Grafikspeicher des ComfyUI-Prozesses je GPU (Windows-Leistungszähler „GPU Process Memory“, das schließt den HIP-Kontext ein; zusätzlich ist der Spitzenwert des PyTorch-Allokators gespeichert). ComfyUI lädt Modelle komplett in den VRAM, wenn Platz ist – auf Karten mit weniger Speicher lagert es aus und wird langsamer, läuft aber meist trotzdem.</li>
        <li><strong>RAM</strong>: höchster Arbeitsspeicher (Working Set) des ComfyUI-Prozesses einschließlich Kindprozessen. Vor jedem neuen Workflow wurden alle Modelle entladen und der Cache geleert.</li>
        <li>Startprofil: ${esc(sys.profile || "")}</li>
      </ul>
      <h2>Workflows ohne Beispielausgabe (${none.length})</h2>
      <ul>${none.map(w => `<li><a href="#/w/${w.id}">${esc(w.name)}</a> – ${esc(w.note || "")}</li>`).join("")}</ul>
      <h2>Neue Dateinamen seit v1.3.1 (${renamed.length})</h2>
      <p>Schema: <code>Modell[_Variante]_Quant[+Hilfsmodell]-Eingabe-to-Ausgabe[-Zweck]</code>. Werkzeug-Workflows ohne Modell und die nummerierte Live-Avatar-Reihe behalten ihre Namen. Der Updater entfernt die alten Dateien (lokal veränderte bleiben liegen und werden im Log mit dem neuen Namen genannt).</p>
      <table class="data"><thead><tr><th>bis v1.3.0</th><th>ab v1.3.1</th></tr></thead><tbody>${renamed.map(w => `<tr><td class="mono" style="font-size:.78rem">${esc(w.old_name)}</td><td class="mono" style="font-size:.78rem"><a href="#/w/${w.id}">${esc(w.name)}</a></td></tr>`).join("")}</tbody></table>
    </div>`;
  }

  // ---------------------------------------------------------------- router
  function route() {
    const h = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
    const [page, a, b] = h.split("/");
    if (!page) { renderHome(); }
    else if (page === "w") { renderWorkflow(a, b); window.scrollTo(0, 0); }
    else if (page === "vergleich") { renderCompare(a, b); }
    else if (page === "quants") { renderQuants(a); if (!a) window.scrollTo(0, 0); }
    else if (page === "info") { renderInfo(); window.scrollTo(0, 0); }
    else renderHome();
    if (page !== "w") document.title = "ComfyUI-Bundle Beispiele";
    document.querySelectorAll(".mainnav [data-nav]").forEach(n => n.classList.toggle("active", (n.dataset.nav === (page || "home")) || (!page && n.dataset.nav === "home")));
  }
  window.addEventListener("scroll", () => { if (!location.hash || location.hash === "#/") state.scroll = window.scrollY; }, { passive: true });
  window.addEventListener("hashchange", () => { if (!lb.hidden) closeLightbox(); route(); });
  route();
})();
