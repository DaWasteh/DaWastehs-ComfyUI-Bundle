#!/usr/bin/env python3
"""Deterministically build v1.1.9 native YuE2 NAR-LoRA training + inference graphs."""
from __future__ import annotations

import argparse
import copy
import json
import uuid
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.build_workflows_v118 import Graph
from tools import migrate_workflows_v092 as migration
from tools.generate_dual_gpu_workflows import install_run_timer
from tools.refine_workflows import refine_workflow, build_note_text
from tools.rodent_layout import apply_rodent_layout

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "tools/workflow_templates/yue2-lora/node-schemas.json"
CHECKPOINT = "yue2_3b_bf16.safetensors"
TRAIN_PATH = "LoRA Generation/YuE2_3B_BF16-PRIVATE-Style-LoRA-Training.json"
MUSIC_PATH = "Music Generation/YuE2_3B_BF16-PRIVATE-LoRA-Music-Generation.json"


class LoRAGraph(Graph):
    def finish(self, path):
        install_run_timer(self.w)
        self.w["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "dawasteh-v119:" + path))
        self.w["revision"] = 0
        self.w.setdefault("extra", {})["dawasteh_yue2_lora"] = {
            "version": 1,
            "release": "v1.1.9",
            "branch": "NAR acoustic style/timbre; AR frozen",
            "experimental": True,
            "license": "CC-BY-NC-4.0",
            "validation_report": "performance/rdna4/yue2-lora-v119-validation.json",
        }
        refine_workflow(self.w, self.schemas)
        previous = migration.OBJECT_INFO.copy()
        try:
            migration.OBJECT_INFO.update(self.schemas)
            self.w = migration.migrate_workflow(self.w, path)
        finally:
            migration.OBJECT_INFO.clear()
            migration.OBJECT_INFO.update(previous)
        # Training loads its own models rather than using ModelPatchers. Wire the
        # actual GPU input, not decorative disconnected device selectors.
        control = next(n for n in self.w["nodes"] if n["type"] == "DaWMultiGPUDeviceControl")
        for n in self.w["nodes"]:
            if n["type"] in {"YuE2TrainingDataset", "YuE2LoRATrainer"}:
                self.connect(control, 2 if n["type"] == "YuE2TrainingDataset" else 0, n, "device")
                n["size"] = [560, 430 if n["type"] == "YuE2TrainingDataset" else 860]
        if path == TRAIN_PATH:
            self.w["extra"]["dawasteh_dual_gpu"].update({
                "placement_support": "direct-training-device-inputs",
                "connected_roles": ["model_device", "vae_device"],
                "execution": "VAE encoding then full AR/NAR training on selected GPU; CLIP control unused",
            })
        nodes = {n["id"]: n for n in self.w["nodes"]}
        for n in self.w["nodes"]:
            if n["type"] == "MarkdownNote":
                target = nodes.get(n.get("properties", {}).get("dawasteh_note_for"))
                if target and target["type"] in self.schemas:
                    n["widgets_values"] = [build_note_text(target, self.schemas[target["type"]])]
                text = n.get("widgets_values", [""])[0]
                lines = sum(max(1, (len(line) + 79) // 80) for line in text.splitlines())
                n["size"] = [680, max(420, 160 + lines * 22)]
        migration._normalize_counters(self.w)
        apply_rodent_layout(self.w, path)
        return self.w


def training(schemas):
    g = LoRAGraph(schemas)
    dataset = g.add("YuE2TrainingDataset", "DATENSATZ · eigene Musik + optionale TXT-Captions",
                    checkpoint=CHECKPOINT, audio_folder="yue2_lora/my_style",
                    clip_seconds=6.0, caption_mode="txt_file", cache_folder="",
                    default_caption="", force_reencode=False)
    train = g.add("YuE2LoRATrainer", "TRAINING · BF16 / AdamW / NAR-Stil-LoRA",
                  checkpoint=CHECKPOINT, trigger_word="my_style", steps=100,
                  learning_rate=0.0001, rank=16, alpha=16.0, lora_dropout=0.0,
                  target_preset="nar_attn_mlp", lora_name="yue2_my_style", seed=119,
                  optimizer="adamw", lr_scheduler="cosine", warmup_steps=10,
                  grad_accum=1, caption_dropout=0.1, t_sampling="logit_normal",
                  max_grad_norm=1.0, log_every=10, save_every=0, ema_decay=0.99,
                  live_curve=True)
    g.connect(dataset, 0, train, "dataset")
    for source, slot, title in [(dataset, 1, "DATENSATZ · Clips / Dauer / Captions"),
                                 (train, 0, "ERGEBNIS · gespeicherter LoRA-Pfad"),
                                 (train, 1, "TRAININGSLOG · Loss / LR / Schritte")]:
        out = g.add("PreviewAny", title)
        g.connect(source, slot, out, "source")
    curve = g.add("YuE2TrainingCurve", "LOSS-KURVE · technisch, keine Qualitätsmessung", smooth=3)
    g.connect(train, 1, curve, "training_log")
    save = g.add("SaveImage", "TRAININGSKURVE · PNG speichern", filename_prefix="Music/PRIVATE_YuE2/LoRA/training_curve")
    g.connect(curve, 0, save, "images")
    g.note("START HIER · YuE2 echtes Stil-LoRA-Training / PRIVAT", """**YuE2 / CC-BY-NC-4.0: nur privat/nichtkommerziell, mit Quellenangabe.** Kein Streaming-/ACE-Step-Ersatz. Keine private Musik, Adapter oder Trainingsdaten ins öffentliche Repository laden.

**Was wird gelernt?** Echte LoRA-Gewichte für die akustische NAR-Stufe: Klangstil, Instrumente, Stimmfarbe. AR-Komposition und Textmodell bleiben eingefroren. EXPERIMENTELL, kein verlässliches Voice-Cloning. Ein technischer Smoke-Test beweist keine musikalische Qualität.

**1 · Installation:** tools/install_yue2_lora_node.py installiert den gepinnten Starnodes-Trainer mit RDNA4-Patch. tools/install_yue2_lora_model.py --accept-noncommercial installiert den verifizierten 7,80-GB-BF16-Checkpoint. ComfyUI neu starten. INT8/convrot ist KEINE Trainingsbasis. Beide checkpoint-Felder müssen BF16 wählen.

**2 · Eigene Daten:** input/yue2_lora/my_style/ mit 001.wav + optional 001.txt, 002.flac + 002.txt. TXT enthält Genre/Instrumente/Stimmcharakter, NICHT das exakte Lyrics-Transkript. Nur eigene/freigegebene Aufnahmen. Keine Unterordner-Suche; WAV/FLAC bevorzugt. Relative Ordner beziehen sich auf ComfyUI/input; absolute Pfade funktionieren ebenfalls. 48 kHz Stereo wird automatisch vorbereitet. Dateien mindestens 6s lang; Reststücke unter clip_seconds werden verworfen. Fehlende Captions bleiben leer. Einheitliches Material, später etwa 5–30 geeignete Songs.

**3 · Sicherstart:** 100 Schritte, 6s Clips, Rank/Alpha 16, LR 1e-4, AdamW, Accumulation 1, Warmup 10, Cosine, EMA 0.99. Das ist ein kurzer Funktionsstart, KEIN fertig trainierter Qualitätsadapter. Für einen Mini-Test steps=5, warmup_steps=0, log_every=1. Für echtes Training nach Hörvergleich z.B. 3000 Schritte, 10s, Rank/Alpha 32, Warmup 50, EMA 0.999; Speicherbedarf steigt. Nicht blind auf 5000 erhöhen.

**4 · GPU:** R9700 / gpu:0, SDPA, kein FlashAttention, kein torch.compile, kein bitsandbytes. VAE-GPU steuert Datensatz-Encoding, MODEL-GPU das komplette AR/NAR-Trainingsmodell; CLIP-Auswahl hat hier keine Funktion. Der Patch entlädt bestehende Comfy-Modelle vor GPU-Arbeit. Exklusiv ausführen. Unsichtbare GPUs werden abgewiesen. Bei OOM Clipdauer/Rank senken, dann neu starten.

**5 · Ergebnis:** models/loras/yue2_my_style.safetensors (EMA) und yue2_my_style_raw.safetensors. lora_name enthält KEINE Ordner. Vor jedem neuen Lauf einen neuen Namen wählen: vorhandene Adapter werden ausdrücklich NICHT überschrieben. Zwischenstände sind Adapter, KEIN Optimizer-Resume. Abbruch stoppt an Schritt-/Encoding-Grenzen; ein finaler Adapter entsteht erst nach erfolgreichem Training. Cache liegt standardmäßig unter temp/yue2_latents, nach Modell/Datensatz getrennt; force_reencode verwirft nur diesen Cache.

**6 · Anwenden:** Musik-Workflow öffnen, LoRA-Liste aktualisieren, Adapter wählen, denselben trigger_word an den Anfang des Style-Prompts setzen. Stärke zuerst 1.0; 0 ist Baseline, danach vorsichtig vergleichen. ABC bleibt leer (cot=off). Loss und Kurve sind technische Diagnostik, keine Hörabnahme.

Quellen: github.com/Starnodes2024/ComfyUI-YuE2-Trainer (MIT, Referenzcode Apache-2.0); huggingface.co/Comfy-Org/YuE2; m-a-p/YuE2-3B. RODENT Method: Nerdy Rodent. Details: docs/YUE2_LORA_V119.md.""")
    return g.finish(TRAIN_PATH)


def music(schemas):
    g = LoRAGraph(schemas)
    ck = g.add("CheckpointLoaderSimple", "YuE2 BF16 · dieselbe Basis wie beim Training", ckpt_name=CHECKPOINT)
    lora = g.add("LoraLoaderModelOnly", "STIL-LoRA · 0 = Baseline / 1 = Startwert",
                 lora_name="yue2_my_style.safetensors", strength_model=1.0)
    g.connect(ck, 0, lora, "model")
    style = g.prompt("STYLE · zuerst dein trigger_word", "my_style, instrumental, warm analog synthesizers, steady drums, 96 BPM, cinematic mysterious atmosphere")
    lyrics = g.prompt("LYRICS · optional, eigene singbare Texte", "")
    gen = g.add("YuE2GenerateMusic", "AR · komponiert weiterhin OHNE LoRA", seed=119, abc="", max_duration=30.0)
    for node, slot, name in [(ck, 1, "clip"), (style, 0, "style"), (lyrics, 0, "lyrics")]:
        g.connect(node, slot, gen, name)
    empty = g.add("EmptyYuE2LatentAudio")
    g.connect(gen, 1, empty, "seconds")
    duration = g.add("PreviewAny", "TATSÄCHLICHE DAUER · max_duration ist nur eine Obergrenze")
    g.connect(gen, 1, duration, "source")
    negative = g.add("ConditioningZeroOut")
    g.connect(gen, 0, negative, "conditioning")
    sampler = g.add("KSampler", "NAR · LoRA verändert die Klangerzeugung", seed=119, steps=32, cfg=1.0,
                    sampler_name="dpm_2", scheduler="sgm_uniform", denoise=1.0)
    for node, name in [(lora, "model"), (gen, "positive"), (negative, "negative"), (empty, "latent_image")]:
        g.connect(node, 0, sampler, name)
    decode = g.add("VAEDecodeAudio")
    g.connect(sampler, 0, decode, "samples")
    g.connect(ck, 2, decode, "vae")
    save = g.add("SaveAudioAdvanced", "AUDIO · 48-kHz-Stereo / PRIVATE",
                 filename_prefix="Music/PRIVATE_YuE2/LoRA/song", format="flac")
    g.connect(decode, 0, save, "audio")
    g.note("START HIER · YuE2 mit eigener Stil-LoRA / PRIVAT", """**CC-BY-NC-4.0 · ausschließlich privat/nichtkommerziell.** Experimentelles NAR-Stil-/Stimmfarben-LoRA, KEIN verlässliches Voice-Cloning, kein Echtzeit-Streaming. Für Streaming-Songs weiter ACE-Step.

1. Zuerst den Trainings-Workflow ausführen oder einen kompatiblen nativen YuE2-NAR-Adapter installieren. Nach Training die LoRA-Liste aktualisieren/ComfyUI neu laden. yue2_my_style.safetensors ist der erwartete eigene Adapter, kein mitgeliefertes Qualitätsmodell.

2. BF16-Basis wählen: yue2_3b_bf16.safetensors. LoraLoaderModelOnly wirkt nur auf MODEL/NAR. CLIP/AR und VAE bleiben unverändert. Keine YuE-v1-, ACE-Step-, FL-YuE2-AR- oder beliebigen Bild-LoRAs laden. INT8/convrot ist hier nicht als kompatible Basis freigegeben.

3. trigger_word aus dem Training als ERSTES Wort in STYLE verwenden (Standard my_style). Danach Genre, Sprache, Instrumente, Stimmung. LYRICS leer für Instrumental oder eigene Lyrics mit [Verse]/[Chorus]. ABC bewusst leer lassen: Der Core schaltet automatisch cot=off; die sichtbare mode-Auswahl wird dann ignoriert. Kein ABC-Generator/Audio-Cover, um den Trainingsmodus nicht zusätzlich zu verändern.

4. strength_model zuerst 1.0; für Baseline 0.0. Gleiche AR- und Sampler-Seeds, gleiche Prompts/Dauer benutzen, EMA und _raw vergleichen. Hohe Stärke kann dumpfen Klang/Artefakte erzeugen; 2.0 ist KEIN automatisch geprüfter Qualitätswert.

5. max_duration=30s ist eine Obergrenze, KEINE exakte Länge. Tatsächlich generierte Sekunden sind direkt mit dem Latent verbunden. Nach kurzen Hörtests z.B. 120s einstellen. 32 DPM2/SGM-uniform-Schritte, CFG 1. Vollständige Stereo-FLAC wird erst nach der Queue gespeichert unter output/Music/PRIVATE_YuE2/LoRA/.

6. R9700 gpu:0 für MODEL/CLIP/VAE. Keine zweite GPU erforderlich. SDPA / klassisches hipBLAS / kein torch.compile. Der Trainer braucht den separaten 7,80-GB-BF16-Checkpoint; vorhandenes INT8 bleibt unangetastet.

Keine Audioaufnahmen oder privaten Adapter im öffentlichen Bundle. Nur eigene/freigegebene Daten nutzen. Technische Smoke-Tests mit synthetischem Audio bestätigen Training/Adapterladung/Ausgabe, nicht Stiltreue oder Stimmenähnlichkeit. Quellen und Anleitung: docs/YUE2_LORA_V119.md. RODENT Method: Nerdy Rodent.""")
    return g.finish(MUSIC_PATH)


def build_all(schemas=None):
    schemas = schemas or json.loads(SCHEMAS.read_text(encoding="utf-8"))
    return {TRAIN_PATH: training(copy.deepcopy(schemas)), MUSIC_PATH: music(copy.deepcopy(schemas))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, default=ROOT / "workflows")
    a = p.parse_args()
    for path, w in build_all().items():
        target = a.destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(w, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(target)


if __name__ == "__main__":
    main()
