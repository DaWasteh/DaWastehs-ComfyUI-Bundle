# Pixal3D-Game-Assets für Godot · v0.9.7

v0.9.7 ergänzt zwei lokale Image-to-3D-Workflows mit vollständigem PBR-Material:

- `workflows/Game Development/Pixal3D_INT8-Buildings-and-Environment-PBR-for-Godot.json`
- `workflows/Game Development/Pixal3D_INT8-Humanoids-and-Animals-PBR-for-Godot.json`

Beide verwenden den offiziellen ComfyUI-Core-Pfad für **Pixal3D INT8 ConvRot**,
erzeugen bei 1024³ eine hochaufgelöste Referenzform, vereinfachen sie auf ein
sichtbares Godot-Dreiecksbudget und backen Base Color, Metallic, Roughness,
Normal und Ambient Occlusion in ein GLB. Sie exportieren bewusst **ein**
Quellmesh; Godot erzeugt daraus beim Import bildschirmgrößenabhängige LODs.

## Modellentscheidung

Recherchestand: 29. August 2026. Aussagen zu Qualität stammen teilweise von den
jeweiligen Projekten; es existiert kein unabhängiger, einheitlicher Benchmark
für alle Kategorien und dieselben Eingabebilder.

| Modell | Stärken | Grenze für diesen Rechner/Use Case | Entscheidung |
|---|---|---|---|
| **Pixal3D** | TRELLIS.2-Basis plus pixel- und kamera-ausgerichtete Konditionierung; Form und PBR; sichtbare Vorderseite folgt der Referenz besonders eng; offizieller ComfyUI-Core-Graph | eine Ansicht erfindet Rückseite/Verdecktes; statisches generatives Dreiecksmesh, kein Rig | **gewählt und installiert** |
| **TRELLIS.2 4B** | MIT, PBR, 512³–1536³, offene/nichtmanifold Topologien, offizieller Core-Pfad | gleiche Grundarchitektur, aber ohne Pixal3D-Ausrichtungs-Finetune; zusätzlicher großer DiT-Download ohne klaren Vorteil für die Zielreferenzen | nicht zusätzlich installiert |
| **Hunyuan3D 2.1** | vorhandener und bereits geprüfter Shape-Pfad; niedrigerer Einstieg | lokaler Workflow liefert nur untexturierte Form und deutlich gröbere Details | bleibt als schneller Low-Poly-/LOD-Fallback |
| **Hunyuan3D-Omni** | Pose-, Bounding-Box-, Punktwolken- und Voxel-Kontrolle; interessant für humanoide Pose | Formmodell ohne gleichwertigen PBR-Endpfad; kein gepflegter ComfyUI-Core-/Windows-ROCm-Graph; veröffentlichte Pakete zielen auf Python 3.10/CUDA | nicht installiert |
| **Step1X-3D** | Apache-2.0, getrennte 1,3B-Form und 3,5B-Textur, Trainingscode | offizielles Projekt führt ComfyUI noch als offenen Punkt; CUDA/PyTorch3D/Kaolin-orientierte Umgebung | nicht installiert |
| **TripoSplat** | aktueller ComfyUI-Core-Pfad für 3D Gaussian Splats | Splat statt optimiertem, riggbarem Godot-Dreiecksmesh | nicht für diese Workflows |
| **MeshAnything V2** | explizite Mesh-Topologie, sehr klein | 1.600-Face-Ziel, nichtkommerzielle S-Lab-Lizenz, kein offizieller Windows-ROCm-/Core-Pfad | weiterhin verworfen |

Primärquellen:

- [Pixal3D Repository](https://github.com/TencentARC/Pixal3D)
- [Pixal3D in ComfyUI](https://docs.comfy.org/tutorials/3d/pixal3d)
- [TRELLIS.2 Repository](https://github.com/microsoft/TRELLIS.2)
- [TRELLIS.2 Model Card](https://huggingface.co/microsoft/TRELLIS.2-4B)
- [Hunyuan3D-Omni](https://github.com/Tencent-Hunyuan/Hunyuan3D-Omni)
- [Step1X-3D](https://github.com/stepfun-ai/Step1X-3D)

## Installierte Dateien

Der Installer lädt nur den ausgewählten Pixal3D-Pfad, nicht zusätzlich
TRELLIS.2. Gesamtgröße: **9.950.408.908 Byte (9,27 GiB)**.

| Ziel unter `ComfyUI/models/` | Byte | SHA-256 |
|---|---:|---|
| `diffusion_models/pixal3d_int8_convrot.safetensors` | 5.584.555.824 | `4621eac3b715484f79303c7152af641fe0b2b14f4d0e3d394fd6922d00f955ec` |
| `clip_vision/dino_v3_L_naf_fp32.safetensors` | 1.215.214.176 | `4ad2ec4e0879a5b5b04cd97325cc37da954a7b6edca5170b86510f17f2b2290f` |
| `vae/trellis_2_shape_vae_bf16.safetensors` | 1.095.844.024 | `de0cb4949a76c59ee5c091a995a69bcc8c51d5aeda939f0c641a50d2a72341f4` |
| `vae/trellis_2_texture_vae_bf16.safetensors` | 948.461.364 | `714e5ebf094a610e12a8e3b5175c18a62f37f6ea4218acb6073644456b73ab0e` |
| `geometry_estimation/moge_2_vitl_normal_fp16.safetensors` | 661.859.924 | `cb1a692d03235671e959e81360d7b4d9f44aefadb1f852d6ca6aa17799d5e31f` |
| `background_removal/birefnet.safetensors` | 444.473.596 | `9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154` |

Reproduzierbare Installation mit dem vorhandenen ComfyUI-Python:

```powershell
L:/ComfyUI/.venv/Scripts/python.exe tools/install_pixal3d_game_models.py `
  --comfy-root L:/ComfyUI/ComfyUI
```

Nur vorhandene Dateien erneut vollständig prüfen:

```powershell
L:/ComfyUI/.venv/Scripts/python.exe tools/install_pixal3d_game_models.py `
  --comfy-root L:/ComfyUI/ComfyUI --verify-only
```

## Lizenzhinweis

Die offiziellen Pixal3D-Code-/Gewichts-Repositories und die Comfy-Org-Repackages
sind als MIT markiert. MoGe und BiRefNet sind ebenfalls MIT-markiert. Der in der
kombinierten CLIP-Vision-Datei enthaltene **DINOv3**-Encoder unterliegt dagegen
Metas eigener DINOv3-Lizenz. Sie gewährt eine weltweite, gebührenfreie Nutzung
und enthält kein allgemeines Nichtkommerziell- oder EU-Verbot, verpflichtet aber
unter anderem zu ihren Weitergabe-, Trade-Control- und Nutzungsbedingungen.
Vor Veröffentlichung immer die aktuellen Originaltexte prüfen; dies ist keine
Rechtsberatung:

- [Pixal3D LICENSE/NOTICE](https://github.com/TencentARC/Pixal3D)
- [DINOv3 License](https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md)

## Gemeinsamer Ablauf

1. `LoadImage`: genau **ein** vollständig sichtbares Asset laden.
2. BiRefNet erzeugt eine Maske. Bei bereits sauberem Alpha den grünen
   Background-Switch deaktivieren.
3. `ImageCropToMask`: 1024×1024, Pixal3D-Padding 1,1.
4. MoGe 2 schätzt den horizontalen Kamera-FOV.
5. Pixal3D führt Sparse-Structure-, Shape-, Upsample- und PBR-Texture-Stufe aus.
6. `VaeDecodeShapeTrellis` liefert das dichte Referenzmesh.
7. `RemeshMesh` normalisiert die fragmentierte Pixal-Rohgeometrie mit dem auf
   der R9700 geprüften Profil: 256³, UDF, QEF aus, zwei beziehungsweise drei
   Glättungsdurchläufe. Ein direkter Raw-Mesh→Decimate-Versuch erzeugte zwar ein
   syntaktisch gültiges, visuell aber in Scherben zerfallenes Mesh und wurde
   deshalb verworfen.
8. `DecimateMesh` reduziert mit `midpoint`. Das Budget ist eine Obergrenze; der
   anschließende `FINAL GAME MESH INFO` zeigt die tatsächlich erreichte
   Face-Zahl. SDF/QEF und QEM-optimale Vertexplatzierung bleiben wegen lokaler
   HIP-Fehler aus.
9. PEC-UVs sowie Base Color, Metallic, Roughness, Normal und AO werden gebacken
   und als ein PBR-GLB gespeichert.

Die offiziellen CFG-Override-/Rescale-Werte und Sampling-Schritte bleiben
unverändert. Auflösung, Schritte und Dreiecksbudget nicht gleichzeitig ändern,
sonst ist ein Qualitätsvergleich nicht aussagekräftig.

### Host-RAM bei mehreren Assets

Ein vollständiger 1024³-Lauf hält zeitweise ein Rohmesh mit mehreren Millionen
Faces. Unter dem lokalen Launcher mit `--cache-classic` gelangten drei große
Assets nacheinander zum gültigen GLB; beim vierten anderen Eingabebild war der
Host-RAM bereits fast erschöpft und der Server wurde ohne Python-Traceback
beendet. Das ist kein GPU-OOM und ein VRAM-Cleanup leert nicht automatisch den
Execution-Cache im Host-RAM. Für verlässliche Produktion zunächst **ein Asset
pro Server-Session** verarbeiten und ComfyUI vor einem anderen Eingabebild neu
starten. Ein dedizierter Batch-Launcher sollte `--cache-none` statt
`--cache-classic` verwenden.

## Gebäude und Umgebung

Standard:

- 1024³ Formauflösung
- **12.000 Dreiecke maximal**
- **1024px PBR-Atlas**, vier Pixel UV-Padding
- 45° Crease-Normalen
- Ausgabe: `output/GameDev/Pixal3D_Environment/`

Geeignete Eingabe:

- einzelnes Gebäudemodul, Fels, Baum, Kiste, Laterne, Waffe oder vergleichbarer
  Prop; keine komplette Straße und keine Gruppe;
- vollständige Silhouette, ruhiger Hintergrund, gleichmäßiges Licht;
- Dreiviertelansicht, damit Front, Seite und bei Gebäuden etwas Dach sichtbar
  sind;
- bei Vegetation breite Blattgruppen statt tausender einzelner Blätter.

Startbudgets:

| Asset | Dreiecke |
|---|---:|
| kleines/repetitives Prop | 4.000–8.000 |
| normales Gebäudemodul/naher Environment-Prop | 8.000–16.000 |
| einzigartiges nahes Gebäude | 16.000–30.000 |

Ein generiertes Gebäude ist keine fertige modulare Level-Geometrie. Maßstab,
Sockel, Innenraum, begehbare Flächen, Grid-Snapping und Collision in Blender
beziehungsweise Godot prüfen.

## Humanoide und Tiere

Standard:

- 1024³ Formauflösung
- **24.000 Dreiecke maximal**
- **2048px PBR-Atlas**, acht Pixel UV-Padding
- vollständig weiche 180°-Normalen vor/für den organischen Grundkörper
- Ausgabe: `output/GameDev/Pixal3D_Creatures/`

Geeignete Eingabe:

- Humanoid vollständig in neutraler A-/T-Pose, Hände und Füße sichtbar, Arme
  und Beine klar voneinander getrennt;
- Tier neutral stehend in seitlicher Dreiviertelansicht, alle Beine und Schwanz
  sichtbar;
- keine dramatische Perspektive, keine überkreuzten Gliedmaßen, kein enger
  Crop, keine harte Bodenschatten- oder Hintergrundkante.

Startbudgets:

| Asset | Dreiecke |
|---|---:|
| einfacher NPC/einfaches Tier | 12.000–18.000 |
| normal nah sichtbar | 18.000–28.000 |
| einzelner Hero | 28.000–40.000 |

**Die Ausgabe ist statisch und ungeriggt.** Sie enthält weder Skeleton noch
Skin-Weights oder Animationen. Automatische Decimation erzeugt keine
zuverlässigen Gelenkloops. Vor Animation in Blender retopologisieren, Gesicht,
Hände/Pfoten und Gelenke prüfen, riggen und gewichten. Erst dieses Ergebnis nach
Godot exportieren.

## Godot-Import

- Das GLB als Szene importieren und `meshes/generate_lods=true` aktiviert lassen.
- Das Workflow-Budget ist das LOD0-Quellmesh, nicht die Summe aller von Godot
  erzeugten internen LODs.
- Collision separat und wesentlich gröber aufbauen. Sichtmesh nicht blind als
  Trimesh-Collision für bewegte Figuren verwenden.
- Wiederholte Environment-Props über `MultiMeshInstance3D` instanzieren.
- Materialanzahl, Alpha-Overdraw, Schatten, Skinning und Texturspeicher gemeinsam
  mit den Dreiecken messen.
- Vor Produktion Achsen, Maßstab, Bounds, offene/nichtmanifold Bereiche,
  Tangenten, UV-Nähte und die erfundene Rückseite kontrollieren.

## Lokaler R9700-, Blender- und Godot-Nachweis

Die ausgelieferten Graphen wurden am 29. August 2026 über den echten
ComfyUI-Browsergraphen in API-Prompts expandiert und auf der Radeon AI Pro R9700
mit PyTorch `2.13.0+rocm10.1.0a20260822` ausgeführt. Das Environment-Profil lief
sowohl mit dem offiziellen freigestellten Axt-Prop als auch mit einem komplexen
Schlossfoto; das Creature-Profil lief mit dem vollständigen anthropomorphen
Panda. Alle drei sichtbaren Blender-Renderings waren nach dem 256³-UDF-Remesh
kohärent. Der zuvor getestete direkte Raw-Mesh-Pfad war fragmentiert und gehört
nicht zu den ausgelieferten Graphen.

| Referenz | Tatsächliche Dreiecke | GLB-Vertices nach UV-/Tangent-Splits | GLB-Byte | SHA-256 |
|---|---:|---:|---:|---|
| Wolf-Runen-Axt, Environment-Standard | 11.984 | 11.168 | 4.161.044 | `b9a7438cdd14df2d1144293be6a9efbc632d7a99355ed877574ae2884b19f0f6` |
| Schloss, Environment-Override | 11.974 | 12.872 | 4.052.464 | `51001b309d654c48f6cf99ab1e028c68949e0aae9fcb3e8d0944a61317cbb588` |
| Panda-Humanoid, Creature-Standard | 23.524 | 19.395 | 7.825.604 | `c35142d26f4333cc8eb1fe35939e23110659ff1b2939b338b20caa532f6393d3` |

Der vollständige neue Environment-Lauf benötigte warm geladen 501 Sekunden,
der Schlosslauf 526 Sekunden. Beim Creature-Profil benötigte die erste komplette
neuronale Generierung einschließlich des damaligen Diagnose-Postprocessings
1.364 Sekunden; die korrigierte Remesh-/2k-PBR-/Export-Wiederholung aus dem
Cache 185 Sekunden. Laufzeiten hängen stark von Cache, Eingabe und Systemlast ab.
Es trat bei diesen drei abgeschlossenen Assets kein GPU-OOM auf.

Blender 5.2.1 LTS importierte die beiden Standard-GLBs mit je einem Mesh, einer
UV-Schicht, endlichen Bounds und null degenerierten Dreiecken. Die eingebetteten
PBR-Daten bestehen aus Base Color, kombiniertem Metallic/Roughness/AO und Normal:
je drei 1024²- beziehungsweise 2048²-PNGs an einem Principled-BSDF-Material.

Godot 4.7.2 importierte beide als `PackedScene` mit genau einem
`MeshInstance3D`, einer Surface und `StandardMaterial3D`. Triangle-Zahlen blieben
exakt 11.984 und 23.524; UV0, Normalen, Tangenten, Albedo-, Metallic-, Roughness-,
AO- und Normal-Texturen waren vorhanden. Der Creature-Import hatte null
Skeletons und null AnimationPlayer. Beide `.glb.import`-Dateien bestätigen
`meshes/generate_lods=true`.
