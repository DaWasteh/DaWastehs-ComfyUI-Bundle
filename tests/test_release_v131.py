"""v1.3.1: workflow names, repairs found by the example gallery, environment pins and the gallery itself."""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from tools import workflow_fixes_v131 as fixes
from tools.workflow_names_v131 import new_key, old_key, renames

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT / "workflows"
EXAMPLES = ROOT / "examples"
GALLERY_DATA = EXAMPLES / "assets" / "gallery-data.js"
SCHEME = re.compile(r"^[A-Za-z0-9_.+&-]+$")


def git_json(ref: str, key: str) -> dict:
    return json.loads(subprocess.check_output(["git", "show", f"{ref}:workflows/{key}"], cwd=ROOT, encoding="utf-8"))


class RenameTests(unittest.TestCase):
    def test_every_renamed_file_exists_under_its_new_name_only(self):
        for old, new in renames().items():
            self.assertTrue((WF / new).is_file(), new)
            if old.lower() != new.lower():  # case-only renames share one file on Windows
                self.assertFalse((WF / old).exists(), old)

    def test_names_are_unique_stay_in_their_folder_and_follow_the_character_set(self):
        targets = list(renames().values())
        self.assertEqual(len(targets), len(set(targets)))
        for old, new in renames().items():
            self.assertEqual(Path(old).parent, Path(new).parent, new)
            self.assertRegex(Path(new).stem, SCHEME)
        self.assertEqual(old_key(new_key("Text to Image/ZImage_turbo-Text-to-Image.json")),
                         "Text to Image/ZImage_turbo-Text-to-Image.json")

    def test_model_workflows_name_an_input_and_an_output(self):
        for new in renames().values():
            stem = Path(new).stem
            if new.startswith("Live Avatar/") or "-to-" not in stem and "_" not in stem.split("-")[0]:
                continue  # tools without a model and the numbered Live Avatar series keep their names
            self.assertTrue("-to-" in stem or stem.endswith(("-Inpaint", "-Upscale", "-Edit", "-Remover",
                                                              "-Separation", "-Outpaint", "-Tiled-Upscale")) or
                            re.search(r"-(Image|Video|Audio|Mesh|Layers|Prompt|Song|Speech|Text)(-|$)", stem), stem)

    def test_updater_maps_every_old_name_to_its_new_name(self):
        updater = (ROOT / "tools" / "update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        block = updater[updater.index("$WorkflowMigrationMap = [ordered]@{"):]
        block = block[:block.index("\n}")]
        for old, new in renames().items():
            self.assertRegex(block, re.escape(f'"{old}"') + r"\s+= " + re.escape(f'"{new}"'), old)


class RepairTests(unittest.TestCase):
    CHANGED = {
        "Text+Image to Video/WAN22_5B-Text+Image-to-Video.json",
        "Controlled Video/WAN22_5B_Fun-Control-to-Video.json",
        "Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json",
        "Pose & Depth/SDPose-Pose-from-Video.json",
        "Pose & Depth/DepthAnything3-Depth-from-Video.json",
        "Video to Audio/MMAudio_Video-to-Audio.json",
        "Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json",
        "Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json",
        "Text to Image/Ideogram4-Text-to-Image.json",
        "Image Editing/Bernini_R-Image-Edit.json",
        "Image Editing/Multi-Character-Angles-One-Click.json",
        "Image Upscaling/ZImage_Turbo-Tiled-Upscale.json",
        "Character & Consistency/FLUX1_Kontext-Character-Keep.json",
        "Text to Image/SDXL_moodyRealMix_zitV4DPO-Text-to-Image.json",
        "Text to Image/SDXL_ultrarealFineTune_v4-Text-to-Image.json",
        "Text+Image to Video/LTX23_Director-Prompt-Replay.json",
        "Text+Image to Video/LTX23_Director_Q8_GGUF-Tiled-Video-Generation.json",
        "Text+Image to Video/LTX23_Director_fp8-2-Stage.json",
        "Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json",
        "Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json",
        "Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json",
        "Prompt Tools/Ideogram4_Qwen3_5-JSON-Prompt-Builder.json",
        "Character & Consistency/SDXL_IPAdapter-Character-Keep.json",
        "NSFW/SDXL_Illustrious_v2-Text-to-Image.json",
        "NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json",
    }

    def test_repaired_workflows_are_the_deterministic_v131_form_of_v130(self):
        for key in sorted(self.CHANGED):
            with self.subTest(workflow=key):
                current = json.loads((WF / new_key(key)).read_text(encoding="utf-8"))
                expected = fixes.expected(key, git_json("v1.3.0", key), lambda k: git_json("v1.3.0", k))
                self.assertIsNotNone(expected)
                self.assertEqual(expected, current)

    def test_wan22_5b_decodes_in_tiles_and_zimage_upscale_uses_qwen3_4b(self):
        for key in ("Text+Image to Video/WAN22_5B-Text+Image-to-Video.json",
                    "Controlled Video/WAN22_5B_Fun-Control-to-Video.json"):
            wf = json.loads((WF / new_key(key)).read_text(encoding="utf-8"))
            decode = next(n for n in wf["nodes"] if n["id"] == 8)
            self.assertEqual((decode["type"], decode["widgets_values"]), ("VAEDecodeTiled", [512, 64, 64, 8]))
        wf = json.loads((WF / new_key("Text+Image to Video/Kandinsky5_Lite-Text+Image-to-Video.json"))
                        .read_text(encoding="utf-8"))
        decode = next(n for n in wf["nodes"] if n["id"] == 85)
        self.assertEqual((decode["type"], decode["widgets_values"]), ("VAEDecodeTiled", [256, 64, 32, 8]))

    def test_eight_camera_angles_share_one_model_chain(self):
        wf = json.loads((WF / new_key("Image Editing/Multi-Character-Angles-One-Click.json")).read_text(encoding="utf-8"))
        graphs = [wf, *wf["definitions"]["subgraphs"]]
        count = lambda kind: sum(n["type"] == kind for g in graphs for n in g["nodes"])
        for kind in ("UNETLoader", "CLIPLoader", "VAELoader", "SelectModelDevice", "SelectCLIPDevice", "SelectVAEDevice"):
            self.assertEqual(count(kind), 1, kind)
        self.assertEqual(count("LoraLoaderModelOnly"), 2)
        self.assertEqual(count("KSampler"), 8)
        outer = next(g for g in graphs[1:] if g["name"] == "Qwen-Image 2511: Batch Angle Generation")
        links = {l["id"]: l for l in outer["links"]}
        angles = [n for n in outer["nodes"] if any(g["id"] == n["type"] for g in graphs[1:])]
        self.assertEqual(len(angles), 8)
        sources = {(links[i["link"]]["origin_id"], i["name"]) for n in angles for i in n["inputs"]
                   if i["name"] in ("model", "clip", "vae")}
        self.assertEqual(len(sources), 3)  # one MODEL, one CLIP and one VAE source for all eight angles

    def test_mmaudio_takes_fps_and_duration_from_the_loaded_video(self):
        wf = json.loads((WF / new_key("Video to Audio/MMAudio_Video-to-Audio.json")).read_text(encoding="utf-8"))
        info = next(n for n in wf["nodes"] if n["type"] == "VHS_VideoInfoLoaded")
        links = {l[0]: l for l in wf["links"]}
        nodes = {n["id"]: n for n in wf["nodes"]}
        source = lambda node_id, name: links[next(i["link"] for i in nodes[node_id]["inputs"] if i["name"] == name)][1:3]
        self.assertEqual(source(info["id"], "video_info"), [3, 3])
        self.assertEqual(source(6, "frame_rate"), [info["id"], 0])
        self.assertEqual(source(4, "duration"), [info["id"], 2])
        wf = json.loads((WF / new_key("Image Upscaling/ZImage_Turbo-Tiled-Upscale.json")).read_text(encoding="utf-8"))
        loader = next(n for n in wf["nodes"] if n["id"] == 201)
        self.assertEqual(loader["widgets_values"][:2], ["Qwen\\qwen_3_4b.safetensors", "lumina2"])

    def test_audio_react_keeps_the_models_out_of_system_ram(self):
        # unloading moved ~14 GiB of weights into RAM, where the Pixaroma engine keeps every rendered frame
        wf = json.loads((WF / new_key("Audio to Video/FLUX2_Klein_4B_Gemma4-Audio-Context-to-AudioReact-Video.json"))
                        .read_text(encoding="utf-8"))
        debug = next(n for n in wf["nodes"] if n["id"] == 34)
        self.assertEqual((debug["type"], debug["widgets_values"]), ("VRAM_Debug", [True, True, False]))

    def test_ideogram4_samples_with_the_official_schedule(self):
        # karras / res_2m / shift 5 left a hatched pattern over every picture
        for key, size_linked in (("Text to Image/Ideogram4-Text-to-Image.json", False),
                                 ("Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json", True)):
            with self.subTest(workflow=key):
                wf = json.loads((WF / new_key(key)).read_text(encoding="utf-8"))
                kinds = {n["type"]: n for n in wf["nodes"]}
                self.assertNotIn("BasicScheduler", kinds)
                scheduler = kinds["Ideogram4Scheduler"]
                self.assertEqual(scheduler["widgets_values"], [20, 1024, 1024, 0.0, 1.75])
                self.assertEqual(scheduler["inputs"][1]["link"] is not None, size_linked)
                self.assertEqual(kinds["KSamplerSelect"]["widgets_values"], ["euler"])
                self.assertEqual(kinds["CFGOverride"]["widgets_values"], [3, 0.7, 1])
                self.assertEqual(kinds["ModelSamplingAuraFlow"]["widgets_values"], [1.0])

    def test_klein_base_uses_real_cfg_with_an_empty_negative(self):
        # the undistilled base model sampled at CFG 1 with a zeroed negative gave soft, washed-out pictures
        wf = json.loads((WF / new_key("Text to Image/FLUX2_Klein_base_4b-Text-to-Image.json")).read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in wf["nodes"]}
        links = {l[0]: l for l in wf["links"]}
        self.assertEqual(nodes[6]["widgets_values"][3], 5.0)
        self.assertEqual((nodes[4]["type"], nodes[4]["widgets_values"]), ("CLIPTextEncode", [""]))
        self.assertEqual(links[nodes[4]["inputs"][0]["link"]][1], 26)  # same text encoder as the positive prompt
        self.assertEqual(links[nodes[6]["inputs"][2]["link"]][1], 4)

    def test_kontext_negative_is_connected_and_the_default_prompt_is_neutral(self):
        wf = json.loads((WF / new_key("Character & Consistency/FLUX1_Kontext-Character-Keep.json"))
                        .read_text(encoding="utf-8"))
        zero = next(n for n in wf["nodes"] if n["id"] == 10)
        link = next(l for l in wf["links"] if l[0] == zero["inputs"][0]["link"])
        self.assertEqual(link[1:5], [7, 0, 10, 0])
        text = json.dumps(wf, ensure_ascii=False).lower()
        self.assertNotIn("nude", text)
        self.assertNotIn("clothing so they", text)


    def load(self, key: str) -> tuple[dict, dict]:
        wf = json.loads((WF / new_key(key)).read_text(encoding="utf-8"))
        return wf, {n["id"]: n for n in wf["nodes"]}

    def test_wan22_text_to_video_uses_the_text_to_video_models(self):
        _, nodes = self.load("Text to Video/WAN22_14B_fp8_lightx2v-Text-to-Video.json")
        files = [nodes[i]["widgets_values"][0] for i in (164, 165, 166, 167)]
        self.assertTrue(all("t2v" in f and "i2v" not in f for f in files), files)

    def test_ideogram_sketch_loaders_are_muted_and_the_json_reaches_the_builder(self):
        for key, loader in (("Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json", 213),
                            ("Prompt Tools/Ideogram4_Qwen3_5-Field-Text-Builder.json", 3),
                            ("Prompt Tools/Ideogram4_Qwen3_5-JSON-Prompt-Builder.json", 3)):
            _, nodes = self.load(key)
            self.assertEqual(nodes[loader]["mode"], 2, key)
        wf, nodes = self.load("Prompt Enhancer/Ideogram4_Qwen3_5-Auto-Prompt-to-Image.json")
        slot = next(i for i in nodes[185]["inputs"] if i["name"] == "import_json")
        link = next(l for l in wf["links"] if l[0] == slot["link"])
        self.assertEqual(link[1], 210)

    def test_sdxl_samplers_and_chain(self):
        _, nodes = self.load("Character & Consistency/SDXL_IPAdapter-Character-Keep.json")
        self.assertEqual(nodes[8]["widgets_values"][4:6], ["dpmpp_2m", "karras"])
        self.assertEqual(nodes[11]["widgets_values"][7:9], ["dpmpp_2m", "karras"])
        _, nodes = self.load("NSFW/SDXL_Illustrious_v2-Text-to-Image.json")
        self.assertEqual(nodes[3]["widgets_values"][2:4], [30, 6.5])
        wf, nodes = self.load("NSFW/SDXL_Multi-Checkpoint_v1-Text-to-Image.json")
        slot = next(i for i in nodes[19]["inputs"] if i["name"] == "latent_image")
        self.assertEqual(next(l for l in wf["links"] if l[0] == slot["link"])[1], 18)


class EnvironmentTests(unittest.TestCase):
    def test_updater_pins_protobuf_and_insightface_last_without_deps(self):
        updater = (ROOT / "tools" / "update-comfyui-rdna4.ps1").read_text(encoding="utf-8-sig")
        dml = updater.index('"onnxruntime-directml>=1.24.4"')
        pin = updater.index('"protobuf==5.29.6" "ml_dtypes==0.6.0" "insightface==1.0.1"')
        self.assertLess(dml, pin)
        self.assertIn('"--no-deps" "protobuf==5.29.6"', updater)
        self.assertLess(pin, updater.index('Write-Host "Validierung"'))

    def test_yue_long_genre_patch_shortens_the_file_name(self):
        patch = (ROOT / "tools" / "patches" / "ComfyUI_YuE-Windows-long-genre-filenames.patch").read_text(
            encoding="utf-8")
        self.assertIn("+import re", patch)
        self.assertIn('[:60]', patch)
        self.assertEqual(patch.count('f"{genre_slug}_tp'), 2)
        self.assertIn("ComfyUI_YuE-Windows-long-genre-filenames.patch", (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_launcher_names_the_release(self):
        script = (ROOT / "tools" / "start-MultiGPU.ps1").read_text(encoding="utf-8-sig")
        self.assertRegex(script, r"Launcher v1\.3\.\d+")  # the banner names the current release (v1.3.1 or later)


class PagesTests(unittest.TestCase):
    def test_pages_workflow_publishes_examples_and_workflows(self):
        yml = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        for token in ("cp -r examples/. _site/", "cp -r workflows/. _site/workflows/", "actions/upload-pages-artifact",
                      "actions/deploy-pages", "pages: write", "id-token: write"):
            self.assertIn(token, yml)
        self.assertIn("dawasteh.github.io/DaWastehs-ComfyUI-Bundle", (ROOT / "README.md").read_text(encoding="utf-8"))


@unittest.skipUnless(GALLERY_DATA.is_file(), "the gallery is built by tools/examples/build_gallery.py")
class GalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = GALLERY_DATA.read_text(encoding="utf-8")
        cls.data = json.loads(text[text.index("=") + 1:].strip().rstrip(";"))

    def test_every_workflow_has_an_entry_with_its_current_file(self):
        files = {w["file"] for w in self.data["workflows"]}
        current = {p.relative_to(WF).as_posix() for p in WF.rglob("*.json")}
        self.assertEqual(files, current)
        self.assertEqual(len({w["id"] for w in self.data["workflows"]}), len(self.data["workflows"]))

    def test_every_referenced_media_file_exists(self):
        missing = []
        for w in self.data["workflows"]:
            base = EXAMPLES / w["dir"]
            refs = [w.get("shot", {}).get(k) for k in ("src", "thumb")] if isinstance(w.get("shot"), dict) else []
            for ex in w["examples"]:
                for item in (ex.get("outputs") or []) + (ex.get("inputs") or []):
                    refs += [item.get("src"), item.get("thumb"), item.get("poster"), item.get("original")]
            missing += [f"{w['dir']}/{r}" for r in refs if r and not (base / r).is_file()]
        self.assertEqual(missing, [])

    def test_no_private_inputs_are_published(self):
        blob = json.dumps(self.data, ensure_ascii=False)
        for token in ("Nutzi", "Basti_Ref_Audio", "TaylorSwift_Ref_Audio", "I Knew You Were Trouble", "Opalite"):
            self.assertNotIn(token, blob)
        published = [p.name for p in EXAMPLES.rglob("*") if p.is_file()]
        self.assertFalse([n for n in published if n.lower().endswith((".pth", ".safetensors", ".ckpt"))])


if __name__ == "__main__":
    unittest.main()
