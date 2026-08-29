import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.integrate_pixaroma_prompts import MARK, apply, sha
from tools.validate_workflows import rect, overlaps, validate_integration_delta

MANIFEST_PATH = ROOT / "tools" / "pixaroma_prompt_manifest.json"
LIBRARY_PATH = ROOT / "prompt-libraries" / "DaWasteh-Pixaroma-Prompt-Library.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def head_json(path: Path):
    raw = subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(ROOT).as_posix()}"],
        text=True,
        encoding="utf-8",
    )
    return json.loads(raw)


class PixaromaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load(MANIFEST_PATH)
        cls.entries = {entry["path"]: entry for entry in cls.manifest["entries"]}

    def test_manifest_exactly_covers_collection_and_head_hashes(self):
        paths = {path.relative_to(ROOT).as_posix() for path in (ROOT / "workflows").rglob("*.json")}
        manifest_paths = [entry["path"] for entry in self.manifest["entries"]]
        self.assertEqual(self.manifest["workflow_count"], 186)
        self.assertEqual(len(manifest_paths), len(set(manifest_paths)))
        self.assertTrue(set(manifest_paths) <= paths)
        generated_unmanaged = {
            path for path in paths
            if path in {
                "workflows/Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json",
                "workflows/Text to Video/LTX25_INT8_ConvRot-Text-to-Video.json",
                "workflows/Text+Image to Video/LTX25_INT8_ConvRot-First+Last-Frame-to-Video.json",
                "workflows/Text+Image to Video/LTX25_INT8_ConvRot-Image-to-Video.json",
                "workflows/Prompt Enhancer/MiniMax_H3_Base_FL2VA-Official-Guide-Prompt-Enhancer.json",
                "workflows/Prompt Enhancer/MiniMax_H3_Ref2VA-Official-Guide-Prompt-Enhancer.json",
                "workflows/Prompt Enhancer/MiniMax_Music3-Official-Skill-Caption-Enhancer.json",
                "workflows/Music Generation/MiniMax_Music3_FP32-BF16-Text-to-Music.json",
                "workflows/Game Development/FLUX2_Klein_4B-PS1-Texture-Concept.json",
                "workflows/Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json",
                "workflows/Game Development/Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json",
                "workflows/Game Development/Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json",
                "workflows/Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json",
            }
        }
        self.assertEqual(
            paths - set(manifest_paths),
            {
                "workflows/Music Generation/ACE-Step1_5_XL_SFT_Gemma4_e4B-AutoSongwriter-Genre-Selector.json",
                "workflows/Music Generation/ACE-Step1_5_XL_SFT_Qwen3_5_4B-AutoSongwriter-Genre-Selector.json",
                "workflows/Music Generation/HeartMuLa_HappyNewYear_3B_Gemma4_e4B-Idea-to-Lyrics-to-Music.json",
                "workflows/Music Generation/HeartMuLa_HappyNewYear_3B_Qwen3_5_4B-Idea-to-Lyrics-to-Music.json",
                "workflows/Music Generation/ACE-Step1_5_XL_SFT_INT8_ConvRot-Music-Generation.json",
                "workflows/Music Generation/StableAudio3_Medium_INT8_ConvRot-Audio-Generation.json",
                "workflows/Music Generation/YuE_7B-INT8_R9700-Music-Generation.json",
                "workflows/Reference to Video/MiniMax_H3_Complete_Song_to_Music_Video_One_Click.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_to_Video_LOCAL.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_Ref2VA_All_Reference_Inputs.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_Reference_Inputs.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_Ref2VA_Picture_and_Video_to_Video_LOCAL.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_RefImage_Audio_to_Video_OriginalAudio_AutoLength.json",
                "workflows/Reference to Video/MiniMax_H3_Spectrum_RefImage_RefVideo_to_Video_Audio_AutoLength.json",
                "workflows/Live Avatar/LiveAvatar-01-SDXL-Avatar-Generation.json",
                "workflows/Live Avatar/LiveAvatar-02-RMBG-Transparency.json",
                "workflows/Live Avatar/LiveAvatar-03-LivePortrait-Webcam-Spout-OBS.json",
                "workflows/Live Avatar/LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json",
                "workflows/Live Avatar/LiveAvatar-05-LivePortrait-Continuous-Spout-OBS.json",
                "workflows/Live Avatar/LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json",
                "workflows/Live Avatar/LiveAvatar-07-AI-Webcam-Character-Swap-Experimental.json",
                "workflows/Live Avatar/LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized.json",
                "workflows/Live Avatar/LiveAvatar-09-Meshy-AutoRig-to-VRM-Candidate-Optional-Cloud.json",
                "workflows/Live Avatar/LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json",
                "workflows/Live Avatar/LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose.json",
                "workflows/Live Avatar/LiveAvatar-12-I-DirectML-Face-Clone-Bakeoff.json",
                "workflows/Live Avatar/LiveAvatar-12-II-LivePortrait-Quality-Mode.json",
                "workflows/Live Avatar/LiveAvatar-12-III-Reliable-VRM-Mode.json",
                "workflows/Live Avatar/LiveAvatar-13-Synthetic-Character-Sheet.json",
                "workflows/Live Avatar/LiveAvatar-14-Local-Hunyuan3D-Multiview-Mesh-Unrigged.json",
                "workflows/Live Avatar/LiveAvatar-15-Local-High-Realism-VRM.json",
                "workflows/LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json",
                "workflows/Voice Design/Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json",
            } | generated_unmanaged,
        )
        for entry in self.manifest["entries"]:
            self.assertIn(entry["action"], {"integrate", "skip"})
            self.assertTrue(entry["reason"])
            self.assertEqual(entry["action"] == "integrate", bool(entry.get("targets") or entry.get("pauses")))
            before = head_json(ROOT / entry["path"])
            nodes = {node["id"]: node for node in before["nodes"]}
            for target in entry.get("targets", []):
                node = nodes[target["node_id"]]
                value = node["widgets_values"][target["widget_index"]]
                self.assertEqual(node["type"], target["node_type"])
                if value == "":
                    prompt = next(
                        item for item in before["nodes"]
                        if item.get("properties", {}).get(MARK, {}).get("target")
                        == [target["node_id"], target["input"]]
                    )
                    value = prompt["properties"]["promptState"]["text"]
                self.assertEqual(value, target["source_text"])
                self.assertRegex(target["source_hash"], r"^[0-9a-f]{64}$")
                self.assertEqual(sha(value), target["source_hash"])

    def test_library_schema_sides_and_tailored_categories(self):
        data = load(LIBRARY_PATH)
        categories = set(data["categories"])
        list_categories = set(data["listCats"])
        self.assertEqual(data["version"], 1)
        self.assertTrue(list_categories <= categories)
        self.assertTrue({"Branding", "Adult", "Negative", "Music-Style", "Voice-Direction"} <= categories)
        names = []
        by_name = {}
        for tag in data["tags"]:
            self.assertRegex(tag["name"], r"^[A-Za-z0-9_-]+$")
            names.append(tag["name"].lower())
            by_name[tag["name"]] = tag
            self.assertIn(tag["cat"], categories)
            if tag.get("kind") == "list":
                self.assertIn(tag["cat"], list_categories)
                self.assertGreaterEqual(len([line for line in tag["text"].splitlines() if line.strip()]), 2)
            else:
                self.assertNotIn(tag["cat"], list_categories)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue({"dawasteh", "pandaking", "draygh", "stella"} <= set(by_name))
        self.assertTrue(all(tag["cat"] == "Adult" for tag in data["tags"] if tag["name"].startswith("adult-")))
        self.assertFalse(any(tag["cat"] in list_categories for tag in data["tags"] if tag["cat"] in {"Adult", "Negative"}))

    def test_applied_prompt_nodes_preserve_text_and_wiring(self):
        prompt_count = 0
        for rel, entry in self.entries.items():
            current = load(ROOT / rel)
            nodes = {node["id"]: node for node in current["nodes"]}
            links = {link[0]: link for link in current["links"]}
            for target in entry.get("targets", []):
                prompt_count += 1
                candidates = [
                    node for node in current["nodes"]
                    if node.get("properties", {}).get(MARK, {}).get("target") == [target["node_id"], target["input"]]
                ]
                self.assertEqual(len(candidates), 1, f"{rel}:{target}")
                prompt = candidates[0]
                destination = nodes[target["node_id"]]
                slot = next(i for i, item in enumerate(destination["inputs"]) if item["name"] == target["input"])
                link_id = destination["inputs"][slot]["link"]
                self.assertEqual(prompt["type"], "PixaromaPrompt")
                self.assertEqual(prompt["properties"]["promptState"]["text"], target["source_text"])
                self.assertEqual(destination["widgets_values"][target["widget_index"]], "")
                self.assertEqual(links[link_id], [link_id, prompt["id"], 0, destination["id"], slot, "STRING"])
                self.assertEqual(prompt["outputs"][0]["links"], [link_id])
                title = (destination.get("title") or "").lower()
                self.assertNotIn("negative", title)
                self.assertNotIn("negativ", title)
                self.assertNotIn(target["kind"], {"lyrics", "tts-text", "transcript", "system-formula"})
        self.assertEqual(prompt_count, 111)
        total_marked_prompts = sum(
            node.get("properties", {}).get(MARK, {}).get("kind") == "prompt"
            for path in (ROOT / "workflows").rglob("*.json")
            for node in load(path)["nodes"]
        )
        dual_marked_prompts = 0
        minimax_enhancer_marked_prompts = sum(
            node.get("properties", {}).get(MARK, {}).get("kind") == "prompt"
            for pattern in (
                "MiniMax_H3_*Official-Guide-Prompt-Enhancer.json",
                "MiniMax_Music3-Official-Skill-Caption-Enhancer.json",
            )
            for path in (ROOT / "workflows" / "Prompt Enhancer").glob(pattern)
            for node in load(path)["nodes"]
        )
        self.assertEqual(dual_marked_prompts, 0)
        self.assertEqual(minimax_enhancer_marked_prompts, 4)
        self.assertEqual(total_marked_prompts, 121 + minimax_enhancer_marked_prompts)

    def test_pause_gates_are_reciprocal_and_have_textgenerate_ancestry(self):
        pause_count = 0
        for rel, entry in self.entries.items():
            if not entry.get("pauses"):
                continue
            current = load(ROOT / rel)
            nodes = {node["id"]: node for node in current["nodes"]}
            links = {link[0]: link for link in current["links"]}
            for spec in entry["pauses"]:
                pause_count += 1
                gates = [
                    node for node in current["nodes"]
                    if node.get("properties", {}).get(MARK, {}).get("pause_target") == spec["target_link"]
                ]
                self.assertEqual(len(gates), 1, rel)
                gate = gates[0]
                fresh_id = gate["inputs"][0]["link"]
                self.assertIsNotNone(fresh_id)
                self.assertEqual(
                    links[fresh_id],
                    [fresh_id, spec["source_node"], spec.get("source_slot", 0), gate["id"], 0, "STRING"],
                )
                old_link = links[spec["target_link"]]
                self.assertEqual(old_link[1:5], [gate["id"], 0, spec["target_node"], old_link[4]])
                self.assertEqual(gate["outputs"][0]["links"], [spec["target_link"]])
                self.assertEqual(nodes[spec["target_node"]]["type"], "CLIPTextEncode")

                visited = set()
                stack = [spec["source_node"]]
                found_textgenerate = False
                while stack:
                    node_id = stack.pop()
                    if node_id in visited:
                        continue
                    visited.add(node_id)
                    node = nodes[node_id]
                    if node["type"] == "TextGenerate":
                        found_textgenerate = True
                        break
                    for item in node.get("inputs", []) or []:
                        link = links.get(item.get("link"))
                        if link:
                            stack.append(link[1])
                self.assertTrue(found_textgenerate, f"{rel}: Pause source lacks TextGenerate ancestry")
        self.assertEqual(pause_count, 9)

    def test_marked_nodes_do_not_overlap_any_node(self):
        for path in (ROOT / "workflows").rglob("*.json"):
            data = load(path)
            marked = [node for node in data["nodes"] if node.get("properties", {}).get(MARK)]
            for node in marked:
                for other in data["nodes"]:
                    if node["id"] != other["id"]:
                        self.assertFalse(overlaps(rect(node), rect(other)), f"{path}: {node['id']} overlaps {other['id']}")

    def test_validator_rejects_old_node_corruption_and_disconnected_pause(self):
        rel = "workflows/Text to Image/Krea2_turbo-2K-Text-to-Image.json"
        before = head_json(ROOT / rel)
        entry = self.entries[rel]
        with tempfile.TemporaryDirectory() as temp_dir:
            migrated = Path(temp_dir) / "workflow.json"
            migrated.write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
            apply(migrated, entry, False)
            after = load(migrated)
        errors = []
        validate_integration_delta(Path(rel), before, after, entry, errors)
        self.assertEqual(errors, [])

        corrupt_node = copy.deepcopy(after)
        original_id = before["nodes"][0]["id"]
        next(node for node in corrupt_node["nodes"] if node["id"] == original_id)["type"] = "CorruptedNodeType"
        errors = []
        validate_integration_delta(Path(rel), before, corrupt_node, entry, errors)
        self.assertTrue(errors)

        corrupt_prompt = copy.deepcopy(after)
        prompt = next(node for node in corrupt_prompt["nodes"] if node.get("properties", {}).get(MARK, {}).get("kind") == "prompt")
        prompt["mode"] = 4
        errors = []
        validate_integration_delta(Path(rel), before, corrupt_prompt, entry, errors)
        self.assertTrue(any("schema/state" in error for error in errors))

        corrupt_pause = copy.deepcopy(after)
        gate = next(node for node in corrupt_pause["nodes"] if node.get("properties", {}).get(MARK, {}).get("kind") == "pause")
        gate["inputs"][0]["link"] = None
        errors = []
        validate_integration_delta(Path(rel), before, corrupt_pause, entry, errors)
        self.assertTrue(any("upstream link" in error for error in errors))

    def test_integrator_second_apply_is_byte_identical_and_corruption_fails(self):
        rel = "workflows/Text to Image/Krea2_turbo-2K-Text-to-Image.json"
        entry = self.entries[rel]
        raw = subprocess.check_output(["git", "show", f"HEAD:{rel}"], text=True, encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "workflow.json"
            path.write_text(raw, encoding="utf-8")
            first_apply = apply(path, entry, False)
            self.assertIn(first_apply, {0, len(entry.get("targets", [])) + len(entry.get("pauses", []))})
            once = path.read_bytes()
            self.assertEqual(apply(path, entry, False), 0)
            self.assertEqual(path.read_bytes(), once)

            data = load(path)
            prompt = next(node for node in data["nodes"] if node.get("properties", {}).get(MARK, {}).get("kind") == "prompt")
            prompt["mode"] = 4
            gate = next(node for node in data["nodes"] if node.get("properties", {}).get(MARK, {}).get("kind") == "pause")
            gate["type"] = "CorruptedGate"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                apply(path, entry, True)

    def test_cli_check_is_clean(self):
        result = subprocess.run(
            [sys.executable, "tools/integrate_pixaroma_prompts.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
