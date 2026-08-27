# Godot Game-Asset Startworkflows · v0.9.6

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

## 2. Hunyuan3D 2.1 → 2000er-Low-Poly-LOD-Set

Workflow:

`workflows/Game Development/Hunyuan3D_v2_1-Low-Poly-Static-Mesh-for-Godot.json`

Bereits vorhandener Checkpoint:

`models/checkpoints/Hunyuan3D/hunyuan_3d_v2.1.safetensors`

### Warum kein neues Modell heruntergeladen wurde

Hunyuan3D 2.1 bleibt die lokale Bild→Form-Stufe. Ein zusätzliches
MeshAnything-V2-Modell würde das Problem auf diesem Rechner nicht zuverlässig
lösen: Es ist eine nachgeschaltete Retopologie-Stufe mit höchstens 1.600 Faces,
hat keinen offiziell unterstützten ComfyUI-/Windows-ROCm-Pfad und seine
S-Lab-Lizenz erlaubt die veröffentlichte Nutzung nur nichtkommerziell. Der
vorhandene Hunyuan-/ComfyUI-Core-Pfad ist dagegen bereits lokal lauffähig.

Der frühere einzelne 5.000-Face-Decimator war trotzdem nicht ausreichend:
Unterhalb von ungefähr 500 Faces verlor eine komplexe Figur wichtige
Silhouettenmerkmale; 50 Faces konnten prinzipbedingt nur noch eine grobe Form
tragen. Der neue Graph erzeugt deshalb vier **unabhängige** Mesh-Pfade aus dem
gleichen Hunyuan-Voxel. So mutieren parallele `DecimateMesh`-Nodes nicht
unbeabsichtigt dasselbe Mesh-Objekt.

### LOD-Profile

| Ausgabe | Voxel-Schwelle | Face-Maximum | Zweck |
|---|---:|---:|---|
| `lod0_hero_5000_*.glb` | 0,60 | 5.000 | komplexer Prop/Character nah an der Kamera |
| `lod1_game_2500_*.glb` | 0,58 | 2.500 | normales Spielmodell |
| `lod2_distant_1200_*.glb` | 0,55 | 1.200 | mittlere Entfernung |
| `lod3_ultra_0600_*.glb` | 0,52 | 600 | aggressive Fernsilhouette |

Die niedrigere Voxel-Schwelle macht dünne Teile bei den kleineren LODs vor der
Reduktion kontrolliert kräftiger. Alle vier Pfade verwenden den auf dieser
Windows-ROCm-Installation live geprüften `midpoint`-Modus. Der alternative
Core-`qem`-Modus läuft hier in einen `torch.linalg.solve`-/HIP-Fehler und ist
bewusst nicht Teil des ausgelieferten Workflows.

Danach erzeugt `UnwrapMesh` ein echtes 256px-UV-Layout mit zwei Pixeln Padding;
`MeshSmoothNormals` setzt 60°-Crease-Normalen. Die GLBs enthalten damit
Dreiecke, UV0 und Normalen und lassen sich direkt in Blender/Godot importieren.
Sie bleiben absichtlich untexturiert.

### Bedienung

1. In `Objekt-Bild` genau ein zentriertes Objekt mit transparentem oder ruhigem
   Hintergrund wählen. Für Figuren eine klare Ganzkörper-/Bust-Silhouette und
   getrennte Gliedmaßen bevorzugen.
2. Normal **Run** drücken. Hunyuan läuft nur einmal; die vier LOD-Pfade folgen
   aus demselben dekodierten Voxel.
3. Ergebnisse unter `output/GameDev/Hunyuan3D_LowPoly/` vergleichen. Nicht nur
   die Zahl, sondern Silhouette und tatsächliche Bildschirmgröße beurteilen.
4. Für ein nah sichtbares Modell LOD0 oder LOD1 verwenden. LOD3 ist kein
   Ersatz für ein Nahmodell.

**50 Dreiecke sind kein allgemeines 3D-Asset-Budget.** Dafür ein bewusst
modelliertes Primitiv, Billboard oder Impostor einsetzen. Godot 4.7 erzeugt beim
Import von GLB-Szenen standardmäßig zusätzliche bildschirmgrößenabhängige
Mesh-LODs; außerdem sind Draw Calls, Materialanzahl, Overdraw, Shader,
Skinning, Collision und Instancing oft wichtiger als die letzten hundert
Dreiecke.

### Ehrliche Grenze

Das Ergebnis ist ein **statisches, UV-entfaltetes, aber untexturiertes und
ungeriggtes Zwischenmesh**. Es enthält nicht automatisch:

- Albedo-/Normal-/Roughness-Texturen,
- Skeleton, Skin-Weights oder Animationen,
- Collision Shapes oder manuell künstlerisch retopologisierte Deformationsloops,
- garantierte Zielmaße oder einen zum konkreten Spiel passenden LOD-Abstand.

Vor Produktion in Blender Maßstab/Achsen, offene beziehungsweise nichtmanifold
Bereiche, Material, Rig/Deformation und Collision prüfen. UV-Nähte benötigen
für GPU-Attribute duplizierte Vertices; deshalb Render-Mesh und vereinfachtes
Physics-Mesh bewusst trennen. Für viele identische Props in Godot
`MultiMeshInstance3D` verwenden.

### Lokaler Importnachweis

Der Live-Test mit `13_three_quarter_left_00001_.png`, Seed 42 und der R9700
erzeugte folgende echte GLBs:

| LOD | Dreiecke | Vertices nach UV-/Normal-Splits | Blender 5.2.1 | Godot 4.7.2 |
|---|---:|---:|---|---|
| LOD0 | 2.970 | 3.340 | importiert, UV0, Normalen, 0 degenerierte Dreiecke | `PackedScene`, 1 `MeshInstance3D`, 1 Surface |
| LOD1 | 1.367 | 1.688 | importiert, UV0, Normalen, 0 degenerierte Dreiecke | `PackedScene`, 1 `MeshInstance3D`, 1 Surface |
| LOD2 | 879 | 1.155 | importiert, UV0, Normalen, 0 degenerierte Dreiecke | `PackedScene`, 1 `MeshInstance3D`, 1 Surface |
| LOD3 | 405 | 603 | importiert, UV0, Normalen, 0 degenerierte Dreiecke | `PackedScene`, 1 `MeshInstance3D`, 1 Surface |

Godot behielt für alle vier Assets exakt dieselben Triangle-Zahlen, gültige
Bounds, UV0 und Normalen. Die erzeugten `.glb.import`-Dateien bestätigen
`importer="scene"` und `meshes/generate_lods=true`.

Primärquellen: [Blender Decimate](https://docs.blender.org/manual/en/5.2/modeling/modifiers/generate/decimate.html),
[Godot Mesh-LOD](https://docs.godotengine.org/en/4.7/tutorials/3d/mesh_lod.html),
[Godot GPU-Optimierung](https://docs.godotengine.org/en/4.7/tutorials/performance/gpu_optimization.html)
und [MeshAnything V2 samt Lizenz](https://github.com/buaacyw/MeshAnythingV2).

## Empfohlene Demo-Reihenfolge

1. Texturworkflow mit dem Startprompt laufen lassen und die drei PNG-Stufen
   nebeneinander zeigen.
2. Im Prompt nur drei bis neun Materialien des geplanten Spiels einsetzen.
3. Hunyuan-Workflow mit einem klaren Prop-Bild (Kiste, Fels, Fass, Waffe)
   demonstrieren; ein Character verlangt deutlich mehr Nacharbeit.
4. Alle vier GLBs in Blender oder Godot nebeneinander zeigen: LOD0/1 als
   Spielmodelle, LOD2/3 nur auf Distanz. Danach Godots automatische Mesh-LODs
   und die weiterhin fehlenden Textur-/Rig-/Collision-Stufen benennen.
