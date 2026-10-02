"""Apply a camera in AnyAngle Studio T8 the way a user does and keep the applied scene for the gallery example.

The studio node only runs after a scene was applied in its editor (the ``snapshot`` widget holds a token, the scene and
its guide image live under ``input/anyangle_studio/``). This script drives the real editor in headless Edge: load the
bundle workflow, open the studio from the node's button, wait for the reference, click "reconstruct 3D from photo"
(TripoSplat runs on the test server), set the camera, apply to the node and write the token to the staging assets. The
gallery catalog then runs the workflow with that token like any other example.

  L:/ComfyUI/tmp/minimax-test-venv/Scripts/python.exe tools/examples/anyangle_studio_scene.py [--azimuth 45] [--dump]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from comfy_driver import ComfyDriver, load_workflow  # noqa: E402
from runner import INPUT_DIR, ROOT, WORK  # noqa: E402

WORKFLOW = "Image Editing/Qwen_Image_2_1_BF16+AnyAngle_Studio_T8-Image-to-Camera-Angle.json"
TOKEN = WORK / "assets" / "anyangle_studio_fox.json"
IMAGE = "character_fox.png"

JS_OPEN = r"""
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const node = app.graph._nodes.find(n => n.type === 'AnyAngleStudioT8');
  if (!node) { done({ok: false, error: 'no studio node'}); return; }
  const button = node.widgets.find(w => w.type === 'button');
  if (!button) { done({ok: false, error: 'no studio button', widgets: node.widgets.map(w => [w.name, w.type])}); return; }
  button.callback();
  await new Promise(r => setTimeout(r, 1500));
  done({ok: !!document.querySelector('dialog iframe'), node: node.id});
})().catch(e => done({ok: false, error: String(e)}));
"""

JS_TOKEN = r"""
const done = arguments[arguments.length - 1];
(async () => {
  const { app } = await import('/scripts/app.js');
  const node = app.graph._nodes.find(n => n.type === 'AnyAngleStudioT8');
  done({value: node.widgets.find(w => w.name === 'snapshot').value, dialog: !!document.querySelector('dialog iframe')});
})().catch(e => done({error: String(e)}));
"""

JS_STATE = r"""
const q = s => document.querySelector(s);
const text = s => (q(s)?.textContent || '').trim().slice(0, 300);
return {
  reconstruct_disabled: q('#reconstruct')?.disabled, apply_disabled: q('#apply')?.disabled,
  loading_hidden: q('#loading')?.hidden, loading: text('#loading-text'), status: text('#status'), toast: text('#toast'),
  badge: text('#source-badge'), recon: text('#reconstruction-state'), guide_state: text('#guide-state'),
  coarse: text('#coarse-status'), prompt: text('#prompt-preview'), model: text('#model-badge'),
};
"""


def wait_for(driver, predicate, timeout: float, what: str, poll: float = 1.0) -> dict:
    deadline = time.time() + timeout
    state = {}
    while time.time() < deadline:
        state = driver.execute_script(JS_STATE)
        if predicate(state):
            return state
        time.sleep(poll)
    raise TimeoutError(f"{what}: {json.dumps(state, ensure_ascii=False)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--azimuth", type=float, default=45.0)
    ap.add_argument("--elevation", type=float, default=10.0)
    ap.add_argument("--shot", default="", help="save a screenshot of the editor before applying")
    ap.add_argument("--dump", action="store_true", help="print the camera controls of the editor and stop before applying")
    args = ap.parse_args()

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(WORK / "assets" / IMAGE, INPUT_DIR / ("ex_" + IMAGE))
    workflow = load_workflow(ROOT / "workflows" / WORKFLOW)
    load_id = next(n["id"] for n in workflow["nodes"] if n["type"] == "LoadImage")
    d = ComfyDriver()
    try:
        d.open()
        d.load(workflow)
        d.patch([{"select": {"id": load_id, "path": ""}, "widget": "image", "value": "ex_" + IMAGE}])
        opened = d.driver.execute_async_script(JS_OPEN)
        if not opened.get("ok"):
            raise RuntimeError(f"studio did not open: {opened}")
        frame = d.driver.find_element("css selector", "dialog iframe")
        d.driver.switch_to.frame(frame)
        # the editor reads the connected reference image through a small prompt of the upstream nodes
        wait_for(d.driver, lambda s: s["reconstruct_disabled"] is False and s["loading_hidden"] is not False, 300,
                 "reference image never arrived")
        d.driver.execute_script("document.querySelector('#reconstruct').click()")
        time.sleep(2)
        state = wait_for(d.driver, lambda s: s["loading_hidden"] is True and "TripoSplat" in (s["badge"] + s["recon"] + s["status"]) or
                         (s["loading_hidden"] is True and s["apply_disabled"] is False), 900, "reconstruction did not finish", poll=2.0)
        print("reconstructed:", json.dumps(state, ensure_ascii=False))
        if args.dump:
            print(d.driver.execute_script("return document.querySelector('#camera-sliders').outerHTML.slice(0, 6000)"))
            print(d.driver.execute_script("return document.querySelector('#view-presets').outerHTML.slice(0, 3000)"))
            print(d.driver.execute_script("return document.querySelector('#coarse-inputs').outerHTML.slice(0, 2000)"))
            return 0
        moved = d.driver.execute_script(r"""
            const set = (key, value) => {
              const inputs = [...document.querySelectorAll('#camera-sliders input')].filter(i => (i.dataset.key || i.name || i.id || '').includes(key));
              for (const input of inputs) { input.value = String(value); input.dispatchEvent(new Event('input', {bubbles: true}));
                                            input.dispatchEvent(new Event('change', {bubbles: true})); }
              return inputs.length;
            };
            return {azimuth: set('azimuth', arguments[0]), elevation: set('elevation', arguments[1])};
        """, args.azimuth, args.elevation)
        print("camera controls set:", moved)
        # the splat viewer needs a few frames for the new camera; the applied guide is the image shown in the preview
        time.sleep(6)
        d.driver.execute_script("document.querySelector('#preview-coarse')?.click()")
        wait_for(d.driver, lambda s: s["apply_disabled"] is False, 300, "guide never became ready")
        time.sleep(12)
        if args.shot:
            d.driver.save_screenshot(args.shot)
        d.driver.execute_script("document.querySelector('#apply').click()")
        d.driver.switch_to.default_content()
        token = None
        for _ in range(120):
            value = d.driver.execute_async_script(JS_TOKEN)
            if value.get("value") and not value.get("dialog"):
                token = value["value"]
                break
            time.sleep(1)
        if not token:
            d.driver.switch_to.frame(d.driver.find_element("css selector", "dialog iframe"))
            raise RuntimeError("apply failed: " + json.dumps(d.driver.execute_script(JS_STATE), ensure_ascii=False))
        TOKEN.write_text(json.dumps({"snapshot": token, "azimuth": args.azimuth, "elevation": args.elevation,
                                     "image": IMAGE}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("applied:", token, "->", TOKEN)
        return 0
    finally:
        d.close()


if __name__ == "__main__":
    raise SystemExit(main())
