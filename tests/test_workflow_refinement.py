import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from tools.refine_workflows import _effect, _fallback_purpose, build_note_text, map_widget_values
from tools.validate_workflows import compare_head

class WidgetMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = ROOT / "assets/live-avatar-v072/object-info.json"
        cls.info = json.loads(fixture.read_text(encoding="utf-8"))

    def names_values(self, node_type, values):
        mapped, ignored = map_widget_values({"widgets_values": values}, self.info[node_type])
        return [(x["name"], x["value"]) for x in mapped], ignored

    def test_ksampler_control_after_generate(self):
        mapped, ignored = self.names_values(
            "KSampler", [123, "randomize", 20, 7.0, "euler", "simple", 1.0]
        )
        self.assertEqual(
            [name for name, _ in mapped],
            ["seed", "seed_control_after_generate", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
        )
        self.assertEqual(mapped[1][1], "randomize")
        self.assertEqual(ignored, [])

    def test_textgenerate_dynamic_combo(self):
        values = ["Prompt", 1024, "on", 0.45, 48, 0.9, 0.05, 1.05, 7, 0.1, False, True]
        mapped, ignored = self.names_values("TextGenerate", values)
        self.assertEqual(
            [name for name, _ in mapped],
            ["prompt", "max_length", "sampling_mode", "temperature", "top_k", "top_p", "min_p",
             "repetition_penalty", "seed", "presence_penalty", "thinking", "use_default_template"],
        )
        self.assertEqual(ignored, [])

    def test_loadaudio_ignores_trailing_ui_state(self):
        mapped, ignored = self.names_values("LoadAudio", ["sample.wav", None, None])
        self.assertEqual(mapped, [("audio", "sample.wav")])
        self.assertEqual(ignored, [None, None])

    def test_vhs_dict_style(self):
        values = {
            "video": "clip.mp4", "force_rate": 24, "custom_width": 0, "custom_height": 0,
            "frame_load_cap": 81, "skip_first_frames": 2, "select_every_nth": 1, "format": "None",
            "videopreview": {"paused": False},
        }
        mapped, ignored = self.names_values("VHS_LoadVideo", values)
        names = [name for name, _ in mapped]
        for expected in ("video", "force_rate", "custom_width", "custom_height", "frame_load_cap",
                         "skip_first_frames", "select_every_nth", "format"):
            self.assertIn(expected, names)
        self.assertEqual(ignored, [{"videopreview": {"paused": False}}])

        combine_values = {
            "frame_rate": 24, "loop_count": 0, "filename_prefix": "out", "format": "video/h264-mp4",
            "pix_fmt": "yuv420p", "crf": 19, "save_metadata": True, "trim_to_audio": False,
            "pingpong": False, "save_output": True, "videopreview": {},
        }
        combine, combine_ignored = self.names_values("VHS_VideoCombine", combine_values)
        combine_names = [name for name, _ in combine]
        self.assertIn("pix_fmt", combine_names)
        self.assertIn("crf", combine_names)
        self.assertIn("trim_to_audio", combine_names)
        self.assertEqual(combine_ignored, [{"videopreview": {}}])

    def test_primitive_ui_state_dict_is_ignored(self):
        mapped, ignored = map_widget_values(
            {"widgets_values": [None, {"project_json": "{}"}]},
            {},
        )
        self.assertEqual([(item["name"], item["value"]) for item in mapped], [("value", None)])
        self.assertEqual(ignored, [{"project_json": "{}"}])

    def test_visible_widget_subset_overrides_optional_schema(self):
        node = {
            "inputs": [
                {"name": "positive", "type": "CONDITIONING", "link": 1},
                {"name": "scale_by", "type": "FLOAT", "link": None, "widget": {"name": "scale_by"}},
                {"name": "upscale_method", "type": "COMBO", "link": None, "widget": {"name": "upscale_method"}},
            ],
            "widgets_values": [0.5, "bicubic"],
        }
        mapped, ignored = map_widget_values(node, self.info["LTXDirectorGuide"])
        self.assertEqual([(item["name"], item["value"]) for item in mapped], [("scale_by", 0.5), ("upscale_method", "bicubic")])
        self.assertEqual(ignored, [])

    def test_acestep_config_seed_control(self):
        values = [16, 32, 0.1, 0.0001, 100, 1, 4, 10, "./output", 42, "randomize", 100, 0.01, 1.0,
                  "q_proj,k_proj,v_proj,o_proj"]
        mapped, ignored = self.names_values("FL_AceStep_TrainingConfig", values)
        names = [name for name, _ in mapped]
        self.assertIn("lora_rank", names)
        self.assertIn("seed_control_after_generate", names)
        self.assertIn("target_modules", names)
        self.assertEqual(ignored, [])

    def test_unetloader_fallback_purpose(self):
        node = {"id": 7, "type": "UNETLoader", "widgets_values": []}
        text = build_note_text(node, {})
        self.assertIn("Lädt die angegebene Ressource", text)
        self.assertNotIn("Verarbeitet seine Eingaben als Node-Typ", text)

    def test_model_combo_has_specific_effect(self):
        schema = {
            "input": {"required": {"model_name": [["a.safetensors", "b.safetensors"], {}]}},
            "input_order": {"required": ["model_name"]},
        }
        node = {"id": 8, "type": "ModelLoader", "widgets_values": ["a.safetensors"]}
        text = build_note_text(node, schema)
        self.assertIn("wechselt die geladene Ressource", text)
        self.assertIn("VRAM-Bedarf, Qualität und Kompatibilität", text)

    def test_boolean_memory_effects_are_specific(self):
        self.assertIn("VRAM", _effect("offloading", "BOOLEAN", {}, True))
        self.assertIn("nächsten Lauf", _effect("unload_model_after_generate", "BOOLEAN", {}, True))
        self.assertIn("Trainings-VRAM", _effect("gradient_checkpointing", "BOOLEAN", {}, True))
        self.assertIn("Auflösungs-Buckets", _effect("bucket_mode", "BOOLEAN", {}, True))

    def test_common_numeric_effects_are_parameter_specific(self):
        cases = {
            "repetition_penalty": "Wiederholungen",
            "scale_by": "proportional",
            "bit_depth": "Farb-/Dynamikabstufungen",
            "tile_overlap": "Nähte",
            "opacity": "deckender",
            "insert_frame_1": "Frame-Timeline",
            "batch_index": "Batch",
            "max_new_tokens": "Text-/Sprachausgaben",
        }
        for name, expected in cases.items():
            self.assertIn(expected, _effect(name, "FLOAT", {}, 1.0), name)
        self.assertIn("Bild-, Farb- oder Detailkorrektur", _fallback_purpose("LayerFilter: FilmV2"))
        self.assertIn("Konditionierungen", _fallback_purpose("ConditioningZeroOut"))
        self.assertIn("Text bzw. die Anweisung", _effect("prefix_text", "STRING", {}, "transcript"))

    def test_generated_train_lora_widgets_follow_live_schema(self):
        expected_names = [
            "batch_size", "grad_accumulation_steps", "steps", "learning_rate", "rank",
            "optimizer", "loss_function", "seed", "training_dtype", "lora_dtype",
            "quantized_backward", "algorithm", "gradient_checkpointing", "checkpoint_depth",
            "offloading", "existing_lora", "bucket_mode", "bypass_mode",
        ]
        paths = sorted((Path("workflows") / "LoRA Generation").glob("*-LoRA-Training.json"))
        generated = [
            path for path in paths
            if path.name not in {
                "ACE-Step1_5_XL-Voice-LoRA-Training.json",
                "Qwen3-TTS_0.6B-Voice-LoRA-Training.json",
            }
        ]
        self.assertEqual(len(generated), 5)
        for path in generated:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            train = next(node for node in workflow["nodes"] if node["type"] == "TrainLoraNode")
            mapped, ignored = map_widget_values(train, self.info["TrainLoraNode"])
            self.assertEqual([item["name"] for item in mapped], expected_names, path.name)
            self.assertEqual(ignored, [], path.name)
            values = {item["name"]: item["value"] for item in mapped}
            self.assertIn(values["training_dtype"], {"bf16", "fp32", "none"}, path.name)
            self.assertIn(values["lora_dtype"], {"bf16", "fp32"}, path.name)
            self.assertEqual(values["algorithm"], "LoRA", path.name)
            self.assertIs(values["bucket_mode"], True, path.name)

    def test_song_idea_workflows_route_generated_lyrics(self):
        paths = sorted((Path("workflows") / "Music Generation").glob("*Idea-to-Lyrics-to-Music.json"))
        self.assertEqual(len(paths), 4)
        for path in paths:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in workflow["nodes"]}
            timers = [node for node in nodes.values() if node["type"] == "PixaromaRunTimer"]
            prompts = [node for node in nodes.values() if node["type"] == "PixaromaPrompt"]
            self.assertEqual(len(timers), 1, path.name)
            self.assertEqual(len(prompts), 2, path.name)

            concat = next(node for node in nodes.values() if node["type"] == "StringConcatenate")
            textgen = next(node for node in nodes.values() if node["type"] == "TextGenerate")
            cleaner = next(node for node in nodes.values() if node["type"] == "RegexReplace")
            show = next(node for node in nodes.values() if node["type"] == "PixaromaShowText")
            music = next(
                node for node in nodes.values()
                if node["type"] in {"TextEncodeAceStepAudio1.5", "HeartMuLaMusicGenerator"}
            )
            self.assertIn("professional songwriter", concat["widgets_values"][0], path.name)
            self.assertEqual(textgen["widgets_values"][1], 1536, path.name)
            clean_values = cleaner["widgets_values"]
            if "Gemma" in path.name:
                self.assertIn("</think>", clean_values[1], path.name)
                raw_lyrics = "Internal analysis with [Intro] inline.\n</think>\n[Instrumental Intro]\nSynths rise.\n[Verse 1]\nText"
            else:
                self.assertNotIn("</think>", clean_values[1], path.name)
                raw_lyrics = "Optional preamble\n[Hook]\nSing this hook.\n[Verse 1]\nText"
            flags = (re.IGNORECASE if clean_values[3] else 0) | (re.MULTILINE if clean_values[4] else 0) | (re.DOTALL if clean_values[5] else 0)
            cleaned = re.sub(clean_values[1], clean_values[2], raw_lyrics, count=clean_values[6], flags=flags)
            expected_opening = "[Instrumental Intro]" if "Gemma" in path.name else "[Hook]"
            self.assertTrue(cleaned.startswith(expected_opening), path.name)
            clean_input_link = cleaner["inputs"][0]["link"]
            clean_input = next(item for item in workflow["links"] if item[0] == clean_input_link)
            self.assertEqual(clean_input[1:5], [textgen["id"], 0, cleaner["id"], 0], path.name)
            show_input_link = show["inputs"][0]["link"]
            show_input = next(item for item in workflow["links"] if item[0] == show_input_link)
            self.assertEqual(show_input[1:5], [cleaner["id"], 0, show["id"], 0], path.name)

            lyric_slot = next(i for i, item in enumerate(music["inputs"]) if item["name"] == "lyrics")
            lyric_link = music["inputs"][lyric_slot]["link"]
            self.assertIsNotNone(lyric_link, path.name)
            link = next(item for item in workflow["links"] if item[0] == lyric_link)
            self.assertEqual(link[1:5], [show["id"], 0, music["id"], lyric_slot], path.name)
            self.assertEqual(link[5], "STRING", path.name)

            if music["type"] == "TextEncodeAceStepAudio1.5":
                duration = next(node for node in nodes.values() if node.get("title") == "Song Duration")
                self.assertEqual(duration["widgets_values"][0], 210, path.name)
            else:
                self.assertEqual(music["widgets_values"][2], 210, path.name)

    def test_live_avatar_workflows_use_rdna4_safe_stack(self):
        paths = sorted((Path("workflows") / "Live Avatar").glob("*.json"))
        self.assertEqual(
            [path.name for path in paths],
            [
                "LiveAvatar-01-SDXL-Avatar-Generation.json",
                "LiveAvatar-02-RMBG-Transparency.json",
                "LiveAvatar-03-LivePortrait-Webcam-Spout-OBS.json",
                "LiveAvatar-04-LivePortrait-Webcam-Spout-OBS+Qwen3TTS-Voice-LoRA.json",
                "LiveAvatar-05-LivePortrait-Continuous-Spout-OBS.json",
                "LiveAvatar-06-VRM-Full-Body-Hand-Face+Live-Mic.json",
                "LiveAvatar-07-AI-Webcam-Character-Swap-Experimental.json",
                "LiveAvatar-08-Local-VRM-Texture-Creator-Realistic+Stylized.json",
                "LiveAvatar-09-Meshy-AutoRig-to-VRM-Candidate-Optional-Cloud.json",
                "LiveAvatar-10-Realistic-Adult-Character-Reference-Prompt+Image.json",
                "LiveAvatar-11-AI-Webcam-Character-Swap-Cached-OpenPose.json",
                "LiveAvatar-12-I-DirectML-Face-Clone-Bakeoff.json",
                "LiveAvatar-12-II-LivePortrait-Quality-Mode.json",
                "LiveAvatar-12-III-Reliable-VRM-Mode.json",
                "LiveAvatar-13-Synthetic-Character-Sheet.json",
                "LiveAvatar-14-Local-Hunyuan3D-Multiview-Mesh-Unrigged.json",
                "LiveAvatar-15-Local-High-Realism-VRM.json",
            ],
        )
        workflows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        for path, workflow in zip(paths, workflows):
            self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 0, path.name)
            nodes_by_id = {node["id"]: node for node in workflow["nodes"]}
            links_by_id = {link[0]: link for link in workflow["links"]}
            for link_id, source_id, source_slot, target_id, target_slot, link_type in workflow["links"]:
                source = nodes_by_id[source_id]["outputs"][source_slot]
                target = nodes_by_id[target_id]["inputs"][target_slot]
                self.assertIn(link_id, source.get("links") or [], path.name)
                self.assertEqual(target.get("link"), link_id, path.name)
                self.assertTrue(source["type"] == "*" or source["type"] == link_type, path.name)
                accepted_types = target["type"].split(",")
                self.assertTrue("*" in accepted_types or link_type in accepted_types, path.name)
            for node in workflow["nodes"]:
                for input_slot, item in enumerate(node.get("inputs", [])):
                    link_id = item.get("link")
                    if link_id is not None:
                        self.assertEqual(links_by_id[link_id][3:5], [node["id"], input_slot], path.name)
                for output_slot, item in enumerate(node.get("outputs", [])):
                    for link_id in item.get("links") or []:
                        self.assertEqual(links_by_id[link_id][1:3], [node["id"], output_slot], path.name)

        generation = {node["type"]: node for node in workflows[0]["nodes"]}
        self.assertEqual(generation["CheckpointLoaderSimple"]["widgets_values"], ["SDXL\\RealVisXL_V4.0.safetensors"])
        self.assertEqual(generation["EmptyLatentImage"]["widgets_values"], [1024, 1024, 1])

        transparency = {node["type"]: node for node in workflows[1]["nodes"]}
        self.assertEqual(transparency["RMBG"]["widgets_values"][0], "RMBG-2.0")
        self.assertEqual(transparency["RMBG"]["widgets_values"][7], "Alpha")

        live_workflow = workflows[2]
        live = {node["type"]: node for node in live_workflow["nodes"]}
        required_types = {
            "DownloadAndLoadLivePortraitModels", "LivePortraitLoadFaceAlignmentCropper",
            "LivePortraitCropper", "WebcamCaptureCV2", "LivePortraitProcess",
            "LivePortraitComposite", "JoinImageWithAlpha", "DaWastehPersistentSpout",
        }
        self.assertTrue(required_types.issubset(self.info), required_types - set(self.info))
        self.assertEqual(live["DownloadAndLoadLivePortraitModels"]["widgets_values"], ["fp16", "human"])
        self.assertEqual(
            live["LivePortraitLoadFaceAlignmentCropper"]["widgets_values"],
            ["blazeface_back_camera", "torch_gpu", "cpu", "fp32", True],
        )
        self.assertEqual(live["LivePortraitCropper"]["widgets_values"][1], 2.3)
        self.assertEqual(live["WebcamCaptureCV2"]["widgets_values"][4], 1)
        self.assertIn("single_frame", live["LivePortraitProcess"]["widgets_values"])
        self.assertEqual(live["DaWastehPersistentSpout"]["widgets_values"], ["ComfyLiveAvatar", 30])
        self.assertIn("Run (Instant)", json.dumps(live_workflow, ensure_ascii=False))

        load_image = live["LoadImage"]
        join_alpha = live["JoinImageWithAlpha"]
        alpha_link_id = join_alpha["inputs"][1]["link"]
        alpha_link = next(link for link in live_workflow["links"] if link[0] == alpha_link_id)
        self.assertEqual(alpha_link[1:5], [load_image["id"], 1, join_alpha["id"], 1])
        self.assertNotIn("cudaexecutionprovider", json.dumps(live_workflow).lower())

        continuous = workflows[4]
        continuous_nodes = {node["type"]: node for node in continuous["nodes"]}
        self.assertIn("DaWastehContinuousLiveAvatar", continuous_nodes)
        for legacy_type in ("WebcamCaptureCV2", "LivePortraitProcess", "LivePortraitComposite", "PreviewImage"):
            self.assertNotIn(legacy_type, continuous_nodes)
        self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in continuous["nodes"]), 0)
        self.assertEqual(continuous["last_link_id"], max(link[0] for link in continuous["links"]))
        self.assertEqual(continuous_nodes["DaWastehContinuousLiveAvatar"]["widgets_values"][:5], [
            "ComfyLiveAvatarFast", 30, 1, 960, 540,
        ])

        vrm_workflow = workflows[5]
        vrm_nodes = {node["type"]: node for node in vrm_workflow["nodes"]}
        self.assertIn("DaWastehVRMLiveAvatarLauncher", vrm_nodes)
        self.assertEqual(vrm_nodes["DaWastehVRMLiveAvatarLauncher"]["widgets_values"], [
            8188, "dawasteh-img00031-highrealism-local-v5.vrm", True, False, False,
        ])
        self.assertIn("nicht</em> Qwen-TTS/Voice-LoRA", json.dumps(vrm_workflow))

        ai = workflows[6]
        ai_nodes = {node["type"]: node for node in ai["nodes"]}
        required_ai = {"WebcamCaptureCV2", "OpenposePreprocessor", "CheckpointLoaderSimple", "LoraLoader", "ControlNetLoader", "ControlNetApplyAdvanced", "VAEEncode", "IPAdapterModelLoader", "IPAdapterAdvanced", "CLIPVisionLoader", "KSampler", "VAEDecode", "DaWastehPersistentSpout"}
        self.assertTrue(required_ai.issubset(ai_nodes), required_ai - set(ai_nodes))
        self.assertNotIn("PreviewImage", ai_nodes)
        self.assertEqual(ai_nodes["WebcamCaptureCV2"]["widgets_values"], [0, 0, 512, 512, 2, False, "DirectShow"])
        self.assertEqual(ai_nodes["OpenposePreprocessor"]["widgets_values"][:4], ["enable", "enable", "enable", 512])
        self.assertEqual(ai_nodes["LoraLoader"]["widgets_values"][0], "LiveAvatar\\lcm-lora-sdv1-5.safetensors")
        self.assertEqual(ai_nodes["KSampler"]["widgets_values"][2:7], [4, 1.5, "lcm", "sgm_uniform", 0.5])
        self.assertEqual(ai_nodes["ControlNetApplyAdvanced"]["widgets_values"][0], 0.8)
        self.assertEqual(ai_nodes["IPAdapterAdvanced"]["widgets_values"][0], 0.55)
        self.assertEqual(ai_nodes["DaWastehPersistentSpout"]["widgets_values"], [
            "ComfyAICharacterSwapExperimental", 30, "live-avatar-07/metrics.json",
        ])
        prompt_text = json.dumps(ai, ensure_ascii=False).lower()
        for token in ("user interface", "malformed hands", "fused fingers", "brand mark", "keine</b> zusage"):
            self.assertIn(token, prompt_text)

        optimized_ai = workflows[10]
        optimized_nodes = {node["type"]: node for node in optimized_ai["nodes"]}
        self.assertIn("DaWastehCachedOpenPose", optimized_nodes)
        self.assertNotIn("OpenposePreprocessor", optimized_nodes)
        self.assertEqual(
            optimized_nodes["WebcamCaptureCV2"]["widgets_values"],
            [0, 0, 384, 384, 2, False, "DirectShow"],
        )
        self.assertEqual(
            optimized_nodes["DaWastehCachedOpenPose"]["widgets_values"],
            ["disable", "enable", "enable", 384, "disable", "disable"],
        )
        self.assertEqual(
            optimized_nodes["DaWastehPersistentSpout"]["widgets_values"],
            ["ComfyAICharacterSwapExperimental", 30, "live-avatar-11/metrics.json"],
        )
        self.assertEqual(optimized_ai["links"], ai["links"])
        optimized_text = json.dumps(optimized_ai, ensure_ascii=False).lower()
        for token in ("cached openpose", "0,21 s", "directshow", "384×384"):
            self.assertIn(token, optimized_text)

        combined_workflow = workflows[3]
        combined = {node["type"]: node for node in combined_workflow["nodes"]}
        self.assertTrue(required_types.issubset(combined), required_types - set(combined))
        self.assertIn("DaWastehQwen3TTSLoRAInference", combined)
        self.assertIn("PlaySoundKJ", combined)
        self.assertEqual(combined["DaWastehQwen3TTSLoRAInference"]["widgets_values"][1:6], [
            "my_voice/checkpoint-epoch-1", "my_voice", "0.6B", "German", 0.3,
        ])
        self.assertEqual(combined["PlaySoundKJ"]["widgets_values"][1], "on_change")
        audio_link_id = next(
            item["link"] for item in combined["PlaySoundKJ"]["inputs"] if item["name"] == "audio"
        )
        audio_link = next(link for link in combined_workflow["links"] if link[0] == audio_link_id)
        self.assertEqual(
            audio_link[1:5],
            [combined["DaWastehQwen3TTSLoRAInference"]["id"], 0, combined["PlaySoundKJ"]["id"], 5],
        )

    def test_qwen3_tts_lora_workflows_use_real_peft_adapters(self):
        training_path = Path("workflows/LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json")
        inference_path = Path("workflows/Voice Design/Qwen3-TTS_LoRA-Low-Latency-Live-Voice.json")
        training = json.loads(training_path.read_text(encoding="utf-8"))
        inference = json.loads(inference_path.read_text(encoding="utf-8"))
        for path, workflow in ((training_path, training), (inference_path, inference)):
            self.assertEqual(sum(node["type"] == "PixaromaRunTimer" for node in workflow["nodes"]), 1, path.name)

        train = next(node for node in training["nodes"] if node["type"] == "DaWastehQwen3TTSLoRATrain")
        self.assertEqual(train["widgets_values"][0], "0.6B")
        self.assertEqual(train["widgets_values"][5], 0.000002)
        self.assertEqual(train["widgets_values"][9:13], ["16", 32, 0.05, "sdpa"])
        self.assertIn("qwen3tts_lora", train["widgets_values"][1])
        self.assertIn("qwen-tts\\loras", train["widgets_values"][2])

        nodes = {node["type"]: node for node in inference["nodes"]}
        self.assertIn("DaWastehQwen3TTSLoRAInference", nodes)
        self.assertIn("PlaySoundKJ", nodes)
        self.assertIn("SaveAudio", nodes)
        self.assertEqual(nodes["DaWastehQwen3TTSLoRAInference"]["widgets_values"][1:6], [
            "my_voice/checkpoint-epoch-1", "my_voice", "0.6B", "German", 0.3,
        ])
        self.assertEqual(nodes["PlaySoundKJ"]["widgets_values"][1], "on_change")
        self.assertEqual(nodes["SaveAudio"]["widgets_values"], ["audio/avatar-voice/qwen3tts-lora"])

    def test_qwen3_tts_v092_migration_rejects_unexpected_rank(self):
        path = Path("workflows/LoRA Generation/Qwen3-TTS_0.6B-Voice-LoRA-Training.json")
        workflow = json.loads(path.read_text(encoding="utf-8"))
        corrupted = copy.deepcopy(workflow)
        train = next(node for node in corrupted["nodes"] if node["type"] == "DaWastehQwen3TTSLoRATrain")
        note = next(node for node in corrupted["nodes"] if node["id"] == 1)
        train["widgets_values"][9] = "not-a-rank"
        note["widgets_values"][0] = "unexpected note"
        errors: list[str] = []
        compare_head(path, corrupted, errors)
        self.assertTrue(any("differs from deterministic v0.9.2 collection migration" in error for error in errors), errors)

    def test_qwen3_tts_lora_node_uses_safe_adapter_files(self):
        source = Path("custom_nodes/ComfyUI-DaWasteh-Qwen3TTS-LoRA/nodes.py").read_text(encoding="utf-8")
        self.assertIn("get_peft_model", source)
        self.assertIn("PeftModel.from_pretrained", source)
        self.assertIn("adapter_model.safetensors", source)
        self.assertIn("speaker_embedding.safetensors", source)
        self.assertNotIn("torch.load(", source)
        self.assertNotIn("pickle", source.lower())
        self.assertIn("attn_implementation=attention", source)

    def test_subgraph_instance_note(self):
        schema = {
            "display_name": "Test Subgraph",
            "description": "Führt einen Test-Subgraph aus.",
            "input": {"required": {"image": ["IMAGE", {"forceInput": True}]}},
            "input_order": {"required": ["image"]},
            "output_name": ["result"],
            "output_tooltips": ["Subgraph result"],
        }
        node = {
            "id": 99, "type": "uuid", "title": "Subgraph Instance", "widgets_values": [],
            "inputs": [{"name": "image", "type": "IMAGE", "link": 7}],
            "outputs": [{"name": "result", "type": "IMAGE", "links": [8]}],
        }
        text = build_note_text(node, schema, "Test Subgraph")
        self.assertIn("Node 99", text)
        self.assertIn("Führt einen Test-Subgraph", text)
        self.assertIn("`image`", text)
        self.assertIn("`result`", text)


if __name__ == "__main__":
    unittest.main()
