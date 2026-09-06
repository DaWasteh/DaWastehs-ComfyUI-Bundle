# Copyright 2026 DaWasteh contributors
# SPDX-License-Identifier: Apache-2.0
"""Qwen3-TTS LoRA training and inference nodes.

The loss, PEFT target modules, speaker-embedding handling, and inference scaling
follow the Apache-2.0 Qwen3-TTS LoRA companion implementation by cheeweijie:
https://github.com/cheeweijie/qwen3-tts-lora-finetuning
"""

from __future__ import annotations

import gc
import hashlib
import json
import re
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
import torch
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from peft.tuners.lora import LoraLayer
from safetensors.torch import load_file, save_file
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import AutoConfig

from .peft_compat import disable_incompatible_torchao_dispatcher
from .adapter_utils import (
    accumulation_group_size,
    adapter_signature,
    find_audio_transcript_pairs,
    normalize_lora_rank,
    publish_directory,
)

import folder_paths
from comfy import model_management
from comfy.utils import ProgressBar

_BASE_MODELS = {
    "0.6B": "Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen3-TTS-12Hz-1.7B-Base",
}
_TOKENIZER_DIR = "Qwen3-TTS-Tokenizer-12Hz"
_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
_LANGUAGES = [
    "Auto",
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "French",
    "German",
    "Spanish",
    "Portuguese",
    "Russian",
    "Italian",
]
_SPEAKER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
_MODEL_CACHE: dict[tuple[Any, ...], Any] = {}


def _ensure_qwen_imports():
    try:
        from qwen_tts import Qwen3TTSModel, Qwen3TTSTokenizer
        from qwen_tts.finetuning.dataset import TTSDataset
        return Qwen3TTSModel, Qwen3TTSTokenizer, TTSDataset
    except ImportError:
        custom_nodes = Path(folder_paths.__file__).resolve().parent / "custom_nodes"
        candidates = [
            custom_nodes / "qwen3-tts-comfyui",
            custom_nodes / "ComfyUI-Qwen-TTS",
        ]
        for candidate in candidates:
            if (candidate / "qwen_tts").is_dir() and str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
        from qwen_tts import Qwen3TTSModel, Qwen3TTSTokenizer
        from qwen_tts.finetuning.dataset import TTSDataset
        return Qwen3TTSModel, Qwen3TTSTokenizer, TTSDataset


def _models_root() -> Path:
    return Path(folder_paths.models_dir).resolve() / "qwen-tts"


def _base_model_path(model_size: str) -> Path:
    path = _models_root() / _BASE_MODELS[model_size]
    if not (path / "config.json").is_file():
        raise FileNotFoundError(
            f"Missing Qwen3-TTS {model_size} Base model: {path}. "
            "Download the matching Qwen/Qwen3-TTS-12Hz-*-Base repository first."
        )
    return path


def _tokenizer_path() -> Path:
    path = _models_root() / _TOKENIZER_DIR
    if not (path / "config.json").is_file():
        raise FileNotFoundError(
            f"Missing Qwen3-TTS tokenizer: {path}. "
            "Download Qwen/Qwen3-TTS-Tokenizer-12Hz first."
        )
    return path


def _lora_root() -> Path:
    return _models_root() / "loras"


def _available_adapters() -> list[str]:
    root = _lora_root()
    if not root.is_dir():
        return ["speaker/checkpoint-epoch-1"]
    adapters = [
        str(path.parent.relative_to(root)).replace("\\", "/")
        for path in root.rglob("adapter_config.json")
        if (path.parent / "adapter_model.safetensors").is_file()
        and (path.parent / "speaker_embedding.safetensors").is_file()
    ]
    return sorted(adapters, key=str.casefold) or ["speaker/checkpoint-epoch-1"]


def _resolve_adapter(adapter_name: str, custom_adapter_path: str) -> Path:
    if custom_adapter_path.strip():
        return Path(custom_adapter_path).expanduser().resolve()
    relative = Path(adapter_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("adapter_name must be a safe path relative to models/qwen-tts/loras.")
    return (_lora_root() / relative).resolve()


def _speaker_name(value: str) -> str:
    speaker = value.strip().lower()
    if not _SPEAKER_RE.fullmatch(speaker):
        raise ValueError("speaker_name must use 1-64 lowercase letters, digits, '_' or '-'.")
    return speaker


def _clear_gpu_cache() -> None:
    gc.collect()
    model_management.soft_empty_cache()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _disable_incompatible_torchao_dispatcher() -> None:
    """Delegate to peft_compat (process-wide, idempotent); kept as the historical call site."""
    disable_incompatible_torchao_dispatcher()


def _prepare_entries(audio_folder: Path, prepared_dir: Path, language: str, tokenizer: Any) -> list[dict[str, Any]]:
    pairs = find_audio_transcript_pairs(audio_folder, _AUDIO_EXTENSIONS)
    if not pairs:
        raise ValueError(
            f"No audio/transcript pairs found in {audio_folder}. "
            "Use <name>.wav + <name>.txt or <name>.wav + <name>_Text.txt "
            "with a UTF-8 transcript."
        )

    prepared_dir.mkdir(parents=True, exist_ok=True)
    prepared: list[tuple[Path, str]] = []
    for source, transcript in pairs:
        text = transcript.read_text(encoding="utf-8-sig").strip()
        if not text:
            continue
        digest = hashlib.sha256(f"{source.resolve()}:{source.stat().st_mtime_ns}:{source.stat().st_size}".encode()).hexdigest()[:12]
        target = prepared_dir / f"{source.stem}-{digest}.wav"
        if not target.is_file():
            waveform, _ = librosa.load(source, sr=24000, mono=True)
            if waveform.size == 0 or not np.isfinite(waveform).all():
                raise ValueError(f"Invalid or empty audio: {source}")
            sf.write(target, waveform.astype(np.float32), 24000, subtype="PCM_16")
        prepared.append((target, text))

    if not prepared:
        raise ValueError("All matching transcripts were empty.")

    reference = str(prepared[0][0])
    entries: list[dict[str, Any]] = []
    for audio_path, text in prepared:
        encoded = tokenizer.encode([str(audio_path)])
        codes = encoded.audio_codes[0].detach().cpu().tolist()
        entries.append(
            {
                "audio": str(audio_path),
                "text": text,
                "language": language,
                "ref_audio": reference,
                "audio_codes": codes,
            }
        )
    return entries


def _compute_loss(model: Any, batch: dict[str, torch.Tensor], target_embedding: torch.Tensor | None):
    device = next(model.parameters()).device
    dtype = next(model.parameters()).dtype
    input_ids = batch["input_ids"].to(device)
    codec_ids = batch["codec_ids"].to(device)
    ref_mels = batch["ref_mels"].to(device=device, dtype=dtype)
    text_mask = batch["text_embedding_mask"].to(device=device, dtype=dtype)
    codec_embedding_mask = batch["codec_embedding_mask"].to(device=device, dtype=dtype)
    attention_mask = batch["attention_mask"].to(device)
    labels = batch["codec_0_labels"].to(device)
    codec_mask = batch["codec_mask"].to(device=device, dtype=torch.bool)

    with torch.no_grad():
        speaker_embedding = model.speaker_encoder(ref_mels).detach()
    if target_embedding is None:
        target_embedding = speaker_embedding[0].detach().cpu()

    input_text_ids = input_ids[:, :, 0]
    input_codec_ids = input_ids[:, :, 1]
    text_embedding = model.talker.model.text_embedding(input_text_ids)
    if hasattr(model.talker, "text_projection"):
        text_embedding = model.talker.text_projection(text_embedding)
    text_embedding = text_embedding * text_mask
    codec_embedding = model.talker.model.codec_embedding(input_codec_ids) * codec_embedding_mask
    codec_embedding[:, 6, :] = speaker_embedding
    input_embeddings = text_embedding + codec_embedding

    for index in range(1, 16):
        layer_embedding = model.talker.code_predictor.get_input_embeddings()[index - 1](codec_ids[:, :, index])
        input_embeddings = input_embeddings + layer_embedding * codec_mask.unsqueeze(-1)

    outputs = model.talker(
        inputs_embeds=input_embeddings[:, :-1, :],
        attention_mask=attention_mask[:, :-1],
        labels=None,
        output_hidden_states=True,
    )
    logits = outputs.logits
    targets = labels[:, 1:]
    codec_loss = torch.nn.functional.cross_entropy(
        logits.reshape(-1, logits.size(-1)),
        targets.reshape(-1),
        ignore_index=-100,
    )
    hidden_states = outputs.hidden_states[0][-1]
    talker_hidden_states = hidden_states[codec_mask[:, 1:]]
    talker_codec_ids = codec_ids[codec_mask]
    _, sub_talker_loss = model.talker.forward_sub_talker_finetune(talker_codec_ids, talker_hidden_states)
    return codec_loss + sub_talker_loss, target_embedding


def _resolve_core_model(model: Any) -> Any:
    if hasattr(model, "talker"):
        return model
    if hasattr(model, "model") and hasattr(model.model, "talker"):
        return model.model
    if hasattr(model, "base_model"):
        return _resolve_core_model(model.base_model)
    raise TypeError("Could not resolve the Qwen3-TTS core model from the PEFT wrapper.")


def _set_lora_scale(model: Any, scale: float) -> None:
    active = getattr(model, "active_adapter", None)
    for module in model.modules():
        if not isinstance(module, LoraLayer):
            continue
        if isinstance(active, (list, tuple)):
            for name in active:
                module.set_scale(name, scale)
        elif active is not None:
            module.set_scale(active, scale)
        else:
            module.scale_layer(scale)


class Qwen3TTSLoRATrain:
    @classmethod
    def INPUT_TYPES(cls):
        default_dataset = str(Path(folder_paths.get_input_directory()) / "qwen3tts_lora" / "speaker")
        default_output = str(_models_root() / "loras" / "speaker")
        return {
            "required": {
                "model_size": (["0.6B", "1.7B"], {"default": "0.6B"}),
                "audio_folder": ("STRING", {"default": default_dataset}),
                "output_dir": ("STRING", {"default": default_output}),
                "speaker_name": ("STRING", {"default": "my_voice"}),
                "language": (_LANGUAGES, {"default": "German"}),
                "learning_rate": ("FLOAT", {"default": 0.000002, "min": 0.0000001, "max": 0.0001, "step": 0.0000001}),
                "num_epochs": ("INT", {"default": 1, "min": 1, "max": 100}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 8}),
                "gradient_accumulation_steps": ("INT", {"default": 4, "min": 1, "max": 64}),
                "lora_rank": (["8", "16", "32", "64"], {"default": "16"}),
                "lora_alpha": ("INT", {"default": 32, "min": 1, "max": 256}),
                "lora_dropout": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 0.5, "step": 0.01}),
                "attention": (["sdpa", "eager"], {"default": "sdpa"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("adapter_path",)
    FUNCTION = "train"
    CATEGORY = "DaWasteh/Audio/Qwen3-TTS LoRA"
    OUTPUT_NODE = True
    DESCRIPTION = "Train a PEFT LoRA adapter plus its Qwen3-TTS speaker embedding."

    @torch.inference_mode(False)
    def train(
        self,
        model_size: str,
        audio_folder: str,
        output_dir: str,
        speaker_name: str,
        language: str,
        learning_rate: float,
        num_epochs: int,
        batch_size: int,
        gradient_accumulation_steps: int,
        lora_rank: str,
        lora_alpha: int,
        lora_dropout: float,
        attention: str,
    ):
        speaker = _speaker_name(speaker_name)
        rank = normalize_lora_rank(lora_rank)
        dataset_dir = Path(audio_folder).expanduser().resolve()
        if not dataset_dir.is_dir():
            raise FileNotFoundError(f"Training folder not found: {dataset_dir}")
        adapter_root = Path(output_dir).expanduser().resolve()
        adapter_root.mkdir(parents=True, exist_ok=True)
        base_path = _base_model_path(model_size)
        tokenizer_path = _tokenizer_path()
        Qwen3TTSModel, Qwen3TTSTokenizer, TTSDataset = _ensure_qwen_imports()

        _MODEL_CACHE.clear()
        model_management.unload_all_models()
        _clear_gpu_cache()
        if not torch.cuda.is_available():
            raise RuntimeError("Qwen3-TTS LoRA training requires a PyTorch CUDA/HIP device; CPU training is disabled.")

        tokenizer = None
        tts = None
        peft_model = None
        try:
            tokenizer = Qwen3TTSTokenizer.from_pretrained(str(tokenizer_path))
            if hasattr(tokenizer, "model"):
                tokenizer.model.to("cuda")
                tokenizer.device = torch.device("cuda")
            entries = _prepare_entries(dataset_dir, adapter_root / "prepared_24khz", language, tokenizer)
            del tokenizer
            tokenizer = None
            _clear_gpu_cache()

            tts = Qwen3TTSModel.from_pretrained(
                str(base_path),
                device_map="cuda",
                dtype=torch.bfloat16,
                attn_implementation=attention,
            )
            config = AutoConfig.from_pretrained(str(base_path))
            dataset = TTSDataset(entries, tts.processor, config)
            dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=dataset.collate_fn)

            _disable_incompatible_torchao_dispatcher()
            peft_model = get_peft_model(
                tts.model,
                LoraConfig(
                    r=rank,
                    lora_alpha=lora_alpha,
                    lora_dropout=lora_dropout,
                    bias="none",
                    target_modules=_TARGET_MODULES,
                    task_type=TaskType.CAUSAL_LM,
                ),
            )
            peft_model.train()
            optimizer = AdamW((p for p in peft_model.parameters() if p.requires_grad), lr=learning_rate, weight_decay=0.01)
            optimizer.zero_grad(set_to_none=True)
            progress = ProgressBar(num_epochs * len(dataloader))
            target_embedding = None
            final_path: Path | None = None

            for epoch in range(num_epochs):
                for step, batch in enumerate(dataloader):
                    raw_loss, target_embedding = _compute_loss(peft_model, batch, target_embedding)
                    divisor = accumulation_group_size(step, len(dataloader), gradient_accumulation_steps)
                    (raw_loss / divisor).backward()
                    should_step = (step + 1) % gradient_accumulation_steps == 0 or step + 1 == len(dataloader)
                    if should_step:
                        torch.nn.utils.clip_grad_norm_(
                            (parameter for parameter in peft_model.parameters() if parameter.requires_grad), 1.0
                        )
                        optimizer.step()
                        optimizer.zero_grad(set_to_none=True)
                    progress.update(1)

                final_path = adapter_root / f"checkpoint-epoch-{epoch + 1}"
                if target_embedding is None:
                    raise RuntimeError("Training produced no speaker embedding.")
                staging_path = adapter_root / f".{final_path.name}.staging-{uuid.uuid4().hex}"
                staging_path.mkdir(parents=True, exist_ok=False)
                metadata = {
                    "format": "qwen3-tts-lora-v1",
                    "base_model": str(base_path),
                    "model_size": model_size,
                    "speaker_name": speaker,
                    "speaker_id": 3000,
                    "sample_rate": 24000,
                    "recommended_lora_scale": 0.3,
                    "language": language,
                    "lora_rank": rank,
                    "lora_alpha": lora_alpha,
                    "lora_dropout": lora_dropout,
                    "learning_rate": learning_rate,
                    "epoch": epoch + 1,
                }
                try:
                    peft_model.save_pretrained(str(staging_path), safe_serialization=True)
                    save_file(
                        {"target_speaker_embedding": target_embedding},
                        str(staging_path / "speaker_embedding.safetensors"),
                    )
                    (staging_path / "qwen3_tts_speaker.json").write_text(
                        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                    publish_directory(staging_path, final_path)
                finally:
                    if staging_path.exists():
                        shutil.rmtree(staging_path)
                _MODEL_CACHE.clear()

            if final_path is None:
                raise RuntimeError("Training did not create a checkpoint.")
            return (str(final_path),)
        finally:
            _MODEL_CACHE.clear()
            del peft_model, tts, tokenizer
            _clear_gpu_cache()


class Qwen3TTSLoRAInference:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"multiline": True, "default": "Hallo! Das ist meine lokal trainierte Avatar-Stimme."}),
                "adapter_name": (_available_adapters(),),
                "speaker_name": ("STRING", {"default": "my_voice"}),
                "model_size": (["0.6B", "1.7B"], {"default": "0.6B"}),
                "language": (_LANGUAGES, {"default": "German"}),
                "lora_scale": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.5, "step": 0.05}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "max_new_tokens": ("INT", {"default": 2048, "min": 128, "max": 4096, "step": 128}),
                "top_p": ("FLOAT", {"default": 0.8, "min": 0.05, "max": 1.0, "step": 0.05}),
                "top_k": ("INT", {"default": 20, "min": 1, "max": 100}),
                "temperature": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 2.0, "step": 0.1}),
                "repetition_penalty": ("FLOAT", {"default": 1.05, "min": 1.0, "max": 2.0, "step": 0.05}),
                "attention": (["sdpa", "eager"], {"default": "sdpa"}),
                "unload_model_after_generate": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "custom_adapter_path": ("STRING", {"default": "", "placeholder": "Optional absolute adapter directory"}),
            },
        }

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "generate"
    CATEGORY = "DaWasteh/Audio/Qwen3-TTS LoRA"
    DESCRIPTION = "Generate a complete audio clip with a switchable Qwen3-TTS PEFT LoRA adapter."

    @classmethod
    def IS_CHANGED(cls, adapter_name: str, custom_adapter_path: str = "", **_: Any):
        adapter = _resolve_adapter(adapter_name, custom_adapter_path)
        return adapter_signature(adapter)

    def generate(
        self,
        text: str,
        adapter_name: str,
        speaker_name: str,
        model_size: str,
        language: str,
        lora_scale: float,
        seed: int,
        max_new_tokens: int,
        top_p: float,
        top_k: int,
        temperature: float,
        repetition_penalty: float,
        attention: str,
        unload_model_after_generate: bool,
        custom_adapter_path: str = "",
    ):
        if not text.strip():
            raise ValueError("text must not be empty.")
        speaker = _speaker_name(speaker_name)
        adapter = _resolve_adapter(adapter_name, custom_adapter_path)
        required = [adapter / "adapter_config.json", adapter / "adapter_model.safetensors", adapter / "speaker_embedding.safetensors"]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("Incomplete Qwen3-TTS LoRA adapter; missing: " + ", ".join(missing))
        metadata_path = adapter / "qwen3_tts_speaker.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
        trained_size = metadata.get("model_size")
        if trained_size and trained_size != model_size:
            raise ValueError(f"Adapter was trained for {trained_size}, but model_size is {model_size}.")
        speaker_id = int(metadata.get("speaker_id", 3000))
        base_path = _base_model_path(model_size)
        signature = adapter_signature(adapter)
        cache_key = (str(base_path), str(adapter), signature, round(lora_scale, 6), attention, speaker)
        Qwen3TTSModel, _, _ = _ensure_qwen_imports()

        if cache_key not in _MODEL_CACHE:
            _MODEL_CACHE.clear()
            _clear_gpu_cache()
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.bfloat16 if device == "cuda" else torch.float32
            tts = Qwen3TTSModel.from_pretrained(
                str(base_path),
                device_map=device,
                dtype=dtype,
                attn_implementation=attention,
            )
            _disable_incompatible_torchao_dispatcher()
            peft_model = PeftModel.from_pretrained(tts.model, str(adapter), local_files_only=True)
            _set_lora_scale(peft_model, lora_scale)
            tts.model = peft_model.merge_and_unload()
            core = _resolve_core_model(tts.model)

            core.config.tts_model_type = "custom_voice"
            core.tts_model_type = "custom_voice"
            core.config.talker_config.spk_id[speaker] = speaker_id
            core.config.talker_config.spk_is_dialect[speaker] = False
            core.supported_speakers = core.config.talker_config.spk_id.keys()
            embedding = load_file(str(adapter / "speaker_embedding.safetensors"))["target_speaker_embedding"]
            weight = core.talker.model.codec_embedding.weight
            weight.data[speaker_id] = embedding.to(device=weight.device, dtype=weight.dtype)
            _MODEL_CACHE[cache_key] = tts

        tts = _MODEL_CACHE[cache_key]
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        np.random.seed(seed % (2**32))
        wavs, sample_rate = tts.generate_custom_voice(
            text=text,
            speaker=speaker,
            language=language.lower(),
            max_new_tokens=max_new_tokens,
            top_p=top_p,
            top_k=top_k,
            temperature=temperature,
            repetition_penalty=repetition_penalty,
        )
        if not wavs:
            raise RuntimeError("Qwen3-TTS LoRA inference returned no audio.")
        waveform = torch.from_numpy(np.asarray(wavs[0], dtype=np.float32))
        if waveform.ndim == 1:
            waveform = waveform.unsqueeze(0).unsqueeze(0)
        elif waveform.ndim == 2:
            waveform = waveform.unsqueeze(0)
        audio = {"waveform": waveform, "sample_rate": int(sample_rate)}
        if unload_model_after_generate:
            _MODEL_CACHE.clear()
            _clear_gpu_cache()
        return (audio,)
