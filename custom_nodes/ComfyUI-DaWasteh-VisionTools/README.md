# DaWasteh VisionTools

ComfyUI-Nodes (`comfy_api.latest`) für die v1.2.8-Workflows *Qwen Image 2.1 Mask Inpaint* sowie *Pose & Depth*.

- **DaWRequireMask** (`DaW Require Painted Mask`): reicht die Maske unverändert durch und stoppt den Lauf mit einem
  klaren Hinweis, wenn (fast) nichts gemalt ist. Ohne Maske behält eine Latent-Noise-Maske jedes Pixel, das
  Ergebnis wäre stillschweigend das unveränderte Eingabebild. `min_pixels` (Standard 16) zählt Maskenpixel > 0,5.
- **DaWSaveDepth16** (`DaW Save 16-bit Depth PNG`): speichert den ersten Kanal jedes Bildes als 16-Bit-Graustufen-PNG
  (0–65535) unter `ComfyUI/output`, mit Workflow in den PNG-Metadaten. 8-Bit-Tiefenkarten haben nur 256 Stufen und
  zeigen bei Displacement/Parallax Treppen; 16 Bit behält die Float-Genauigkeit des Tiefen-Renders. Pfade außerhalb von
  `output/` werden abgelehnt.

Abhängigkeiten: nur ComfyUI (PyTorch, NumPy, Pillow). Der Bundle-Updater installiert das Paket mit.
Workflows und Messwerte: [docs/POSE_DEPTH_V128.md](../../docs/POSE_DEPTH_V128.md),
[docs/QWEN_IMAGE21_INPAINT_V128.md](../../docs/QWEN_IMAGE21_INPAINT_V128.md).
