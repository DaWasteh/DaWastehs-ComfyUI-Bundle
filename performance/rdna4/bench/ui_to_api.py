"""Convert a ComfyUI UI workflow JSON into the executable API prompt.

Uses the real frontend (`app.graphToPrompt()`) served by a running ComfyUI
instance in headless Edge, so subgraphs, converted widgets, primitives and
bypassed nodes are expanded exactly as a browser would do it.

Run with the selenium test venv:
  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe ui_to_api.py <workflow.json> <out.json> --url http://127.0.0.1:8190

Output file: {"output": <api prompt>, "workflow": <ui workflow>}  (same shape as the frontend's payload).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait

JS = r"""
const workflow = arguments[0];
const done = arguments[arguments.length - 1];
(async () => {
  try {
    const { app } = await import('/scripts/app.js');
    const deadline = Date.now() + 120000;
    while ((!app.graph || !app.canvas) && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    if (!app.graph || !app.canvas) throw new Error('Comfy app did not initialize');
    // app.canvas can exist before the Vue canvas store is mounted (1.53.6:
    // "getCanvas: canvas is null"). Let first-tab initialization settle too.
    await new Promise(resolve => setTimeout(resolve, 15000));
    // Recent frontends restore their initial tab asynchronously. That restore
    // can overwrite loadGraphData and silently serialize the default graph.
    // Require stable identity after loading; never submit an unrelated graph.
    const identity = nodes => JSON.stringify(nodes.map(n => [String(n.id), n.type]).sort());
    const expected = identity(workflow.nodes);
    let ready = false;
    for (let attempt = 0; attempt < 4 && !ready; attempt++) {
      await app.loadGraphData(workflow, true, true);
      await new Promise(resolve => setTimeout(resolve, 3000));
      ready = identity(app.graph._nodes) === expected;
      if (ready) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        ready = identity(app.graph._nodes) === expected;
      }
    }
    if (!ready) throw new Error('Requested workflow did not become the stable active graph');
    const dialogs = [...document.querySelectorAll('[role="dialog"]')].map(d => d.innerText).join('\n');
    if (/Loading aborted|error reloading workflow|Missing Node Types/i.test(dialogs)) {
      throw new Error('Frontend load error: ' + dialogs);
    }
    const missing = [];
    for (const node of app.graph._nodes) {
      if (node.has_errors || node.type === undefined) missing.push(String(node.id) + ':' + node.type);
    }
    const result = await app.graphToPrompt();
    if (identity(result.workflow.nodes) !== expected || identity(app.graph._nodes) !== expected) {
      throw new Error('Active graph changed during serialization');
    }
    if (missing.length) throw new Error('Missing/error nodes: ' + missing.join(', '));
    done({ok: true, result, missing});
  } catch (error) {
    done({ok: false, error: String(error), stack: error && error.stack});
  }
})();
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workflow", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8190")
    args = parser.parse_args()

    workflow = json.loads(args.workflow.read_text(encoding="utf-8"))
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-extensions")
    options.add_argument("--window-size=1600,1000")
    driver = webdriver.Edge(options=options)
    try:
        driver.set_script_timeout(240)
        driver.get(args.url)
        WebDriverWait(driver, 120).until(lambda d: d.execute_script("return document.readyState") == "complete")
        WebDriverWait(driver, 180).until(
            lambda d: d.execute_script("return Boolean(window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app)")
        )
        payload = driver.execute_async_script(JS, workflow)
        if not payload.get("ok"):
            raise RuntimeError(json.dumps(payload, indent=2))
        result = payload["result"]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        classes = sorted({v.get("class_type") for v in result.get("output", {}).values()})
        print(json.dumps({"output": str(args.output), "api_nodes": len(result.get("output", {})),
                          "missing": payload.get("missing"), "classes": classes}, ensure_ascii=False, indent=1))
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
