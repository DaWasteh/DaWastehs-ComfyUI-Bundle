# Godot Game-Asset Startworkflows · v0.9.5

Die beiden Workflows unter `workflows/Game Development/` sind funktionsfähige,
lokal geprüfte Nachfolger der Gemini-Testentwürfe aus
`L:/LAB/ComfyUI Testworkflows`. Die Entwürfe wurden nicht unverändert übernommen:
einer war ungültiges JSON, referenzierte ein fehlendes Modell und versprach ein
UV-Atlas ohne UV-Eingabe; der andere verwendete einen nicht existierenden
`MeshDecimate`-Node und ließ den für Hunyuan3D benötigten Sampling-Shift aus.

Für diese beiden Nachfolger wurden **keine neuen Modellgewichte heruntergeladen**.

## 1. FLUX.2 Klein 4B → PS1-Texturkonzept

Workflow:

`workflows/Game Development/FLUX2_Klein_4B-PS1-Texture-Concept.json`

Bereits vorhandene Gewichte:

- `models/diffusion_models/FLUX/flux-2-klein-4b.safetensors`
- `models/text_encoders/Qwen/qwen_3_4b.safetensors`
- `models/vae/FLUX2/flux2-vae.safetensors`

### Bedienung

1. Im grünen `Prompt Pixaroma` Materialien und Stil ändern. Der Startprompt fragt
   eine klar getrennte 3×3-Materialübersicht ab.
2. Normal **Run** drücken. FLUX.2 Klein erzeugt die 1024×1024-Quelle in vier
   Schritten.
3. Der Workflow skaliert per `area` auf echte 128×128 Pixel, begrenzt das Bild
   mit Core-`ImageQuantize` auf 32 Farben und erzeugt zusätzlich eine
   1024×1024-Nearest-Preview.
4. Ergebnisse liegen unter:

   - `output/GameDev/PS1_Texture_Concept/source_1024_*.png`
   - `output/GameDev/PS1_Texture_Concept/game_128_*.png`
   - `output/GameDev/PS1_Texture_Concept/nearest_preview_1024_*.png`

32 Farben und `bayer-4` sind bewusst sichtbare Startwerte. Für ruhigere Flächen
`dither=none`, für mehr Farbabstufungen 64 oder 128 Farben testen.

### Ehrliche Grenze

Das Ergebnis ist ein **Texturkonzeptblatt**, kein automatisch passendes UV-Atlas.
Ohne das echte UV-Layout eines Zielmeshes kann eine Bild-KI keine verlässlich
zugeordneten UV-Inseln erzeugen. Geeignete Kacheln deshalb in Blender, Krita
oder Aseprite auswählen beziehungsweise auf eine echte UV-Vorlage übertragen.

### Godot-Import

- Für Sprite/UI-Pixelart: `Filter` aus, Mipmaps aus, Lossless-Kompression.
- Für Texturen auf 3D-Geometrie: `Filter` für den harten PS1-Look aus;
  Mipmaps meistens anlassen, wenn die Fläche in die Tiefe läuft, damit sie
  weniger flimmert. Das gewünschte Ergebnis im Zielspiel prüfen.
- Die 1024er Preview dient nur der Sichtkontrolle. Im Spiel die echte 128er
  Datei verwenden, nicht die hochskalierte Preview.

## 2. Hunyuan3D 2.1 → Low-Poly-GLB

Workflow:

`workflows/Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json`

Bereits vorhandener Checkpoint:

`models/checkpoints/Hunyuan3D/hunyuan_3d_v2.1.safetensors`

Der Workflow verwendet den gepflegten Hunyuan3D-Core-Pfad mit
`ModelSamplingAuraFlow shift=1`, 40 Schritten, Voxel-Decode und `VoxelToMesh`.
Das frisch installierte ComfyUI 0.34 ergänzt danach den Core-Node
`DecimateMesh`; ein zusätzlicher Mesh-Custom-Node ist nicht nötig.

### Bedienung

1. In `Objekt-Bild` ein einzelnes, zentriertes Objekt mit sauberem oder
   transparentem Hintergrund wählen. Mehrere Gegenstände, abgeschnittene Teile
   und starke Perspektive verschlechtern die Form.
2. Normal **Run** drücken.
3. `LOW-POLY · Ziel maximal 5.000 Faces` verwendet den qualitätsorientierten
   `midpoint`-Modus. 5.000 ist ein Maximalwert: Hat das Eingangsmaterial bereits
   weniger Faces, erfindet der Node keine zusätzliche Geometrie.
4. Das GLB liegt unter:

   `output/GameDev/Hunyuan3D_LowPoly/hunyuan3d_lowpoly_static_*.glb`

800 Faces aus dem Gemini-Entwurf sind höchstens ein aggressives fernes LOD.
Zuerst 5.000, danach 2.500 und erst dann niedrigere Werte vergleichen. Dünne
Teile und Silhouette bei jeder Stufe prüfen.

### Ehrliche Grenze

Das Ergebnis ist ein **statisches, untexturiertes und ungeriggtes
Zwischenmesh**. Es enthält nicht automatisch:

- ein fertiges UV-Layout oder Albedo-/Normal-/Roughness-Texturen,
- Skeleton, Skin-Weights oder Animationen,
- Collision Shapes oder eine geprüfte LOD-Kette,
- garantierte Godot-Maße, Achsen oder saubere Produktions-Topologie.

Vor einem Character-Einsatz in Blender Maßstab/Achsen, Normalen, nichtmanifold
Geometrie, UVs, Material, Rig, Skinning und Deformation prüfen. Als statischer
Prop kann das GLB nach Sichtprüfung direkt als `MeshInstance3D` dienen;
Collision bewusst separat und möglichst vereinfacht erzeugen.

## Empfohlene Demo-Reihenfolge

1. Texturworkflow mit dem Startprompt laufen lassen und die drei PNG-Stufen
   nebeneinander zeigen.
2. Im Prompt nur drei bis neun Materialien des geplanten Spiels einsetzen.
3. Hunyuan-Workflow mit einem klaren Prop-Bild (Kiste, Fels, Fass, Waffe)
   demonstrieren; ein Character verlangt deutlich mehr Nacharbeit.
4. GLB in Godot importieren, Face-/Triangle-Budget und Silhouette zeigen und die
   fehlenden Produktionsstufen ausdrücklich benennen.
