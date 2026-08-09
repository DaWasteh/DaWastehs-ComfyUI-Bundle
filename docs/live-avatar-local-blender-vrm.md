# Lokaler Blender-VRM-Kandidat

`tools/build_local_blender_vrm_avatar.py` erzeugt lokal einen VRM0-Kandidaten aus der hash-geprüften CC0-Datei `olivia.vrm`. Blender 4.5.9 Portable und die VRM-Erweiterung 4.5.0 sind über `tools/install_live_avatar_blender.py` pinbar und prüfbar. Weder Referenzbild noch Kamera verlassen den Rechner.

Die Datei `02_Avatar_Transparent_00001_.png` ist nur ein frontales Oberkörperporträt. Der Kandidat ist daher **eine Olivia-abgeleitete Stilannäherung, kein Klon**: Körper, Hände, Finger, Seiten- und Rückansicht bleiben vom CC0-Original geerbt. Die Builder-Textur ändert nur konservativ lokale UV-Farbbereiche und projiziert das Porträt nicht über unbekannte Flächen.

Der Kandidat enthält eine reale rosa Zungengeometrie mit einem VRM0-Custom-Blendshape `TongueOut`. Im Browser: Zunge über den Button oder `T` gedrückt halten. Die manuelle Aktion öffnet zusätzlich A teilweise. MediaPipe Holistic meldet keinen zuverlässigen Zungenwert. `T`/Button bleibt deshalb der unterstützte Pfad. Eine standardmäßig ausgeschaltete Webcam-Farbheuristik kann im geöffneten Mund pink-rote Zungenpixel erkennen, ist aber wegen Lippenstift, Licht und Schatten ausdrücklich experimentell und nicht zugesichert.

Prüfen: Browsermodell laden, `T` halten, danach Kopf/Mund/Hand/Finger in einer sichtbaren Webcam-Session testen. Die GLB/VRM-Datei und das Zwischen-`.blend` enthalten abgeleitete lokale Daten und dürfen nicht in Git aufgenommen werden.

## High-Realism-Hunyuan-Pfad (Workflow 15)

`LiveAvatar-15-Local-High-Realism-VRM.json` ist der lokale Geometrieschritt für eine **manuell vorbereitete, realistische A-Pose-Frontansicht**. Vor dem Run muss die Figur mit RMBG isoliert sein: level camera, Kopf bis Fuß, getrennte Arme und Beine, vollständige sichtbare Hände/Finger und keine abgeschnittenen Ränder. Der Workflow verwendet bewusst **nur diese eine Ansicht**. Der getestete lokale Multiview-Hunyuan-Pfad fragmentiert Geometrie und ist deshalb kein Geometriepfad von Workflow 15.

Er nutzt ausschließlich native ComfyUI-Hunyuan3D-v2.1-Knoten mit latent resolution `4096`, `VAEDecodeHunyuan3D` octree resolution `512`, `surface net` und anschließendem `SaveGLB`. Das Ergebnis ist ein hochaufgelöstes, aber weiterhin untexturiertes und ungeriggtes GLB. `tools/build_high_realism_local_vrm.py` ruft die wiederverwendbaren Blender-Tools unter `tools/blender/` auf: Rig/Weighting, vier separate Erscheinungsprojektionen, PBR-Roughness, 2048er Texture-Limit und konservative Blink-/Vokal-Expressions.

Der Pfad ist vollständig lokal, benötigt aber explizite lokale Dateien und Blender/VRM-Addon. Auf Windows-ROCm **nicht** Hunyuan Paint, nvdiffrast oder CUDA-Rasterizer installieren/verwenden; sie sind hier kein unterstützter Weg. Auch mit 512er Octree bleibt dies keine photorealistische oder automatische Produktionspipeline: Gesicht, einzelne Finger, Haare, Seiten/Rücken, Mundhöhle und Gelenkdeformation müssen visuell geprüft und bei Bedarf manuell in Blender nachbearbeitet werden.

## Source-Face-v5-Veredelung

Für den lokal geprüften img00031-Avatar war die separate Hunyuan-Kopfgeometrie texturseitig schlechter als das stabile v2-Rig und wurde verworfen. `tools/blender/add_face_decal_vrm.py` ergänzt stattdessen ein alpha-gefedertes, an den humanoiden Kopfknochen gebundenes Gesichtsdetail. Das Detail besitzt eigene `Blink`, `Blink_L`, `Blink_R` sowie `A/I/U/E/O`-Morphs. Dadurch bleibt die Frontalansicht nah an der lokalen Originalreferenz, ohne eine vollständige volumetrische Rekonstruktion zu behaupten.

Beispielaufruf mit lokalen, nicht zu commitenden Eingaben:

```powershell
L:/ComfyUI/tools/blender-4.5.9-windows-x64/blender.exe --background `
  --python tools/blender/add_face_decal_vrm.py -- `
  L:/ComfyUI/logs/live-avatar-image-00031/highrealism-orchestrator-v2/final.blend `
  L:/ComfyUI/tmp/liveavatar-v085-audit/face-decal.png `
  L:/ComfyUI/logs/live-avatar-image-00031/highrealism-orchestrator-v5/final.blend `
  L:/ComfyUI/ComfyUI/models/live-avatar-vrm/dawasteh-img00031-highrealism-local-v5.vrm `
  L:/ComfyUI/logs/live-avatar-image-00031/highrealism-orchestrator-v5/decal-report.json
```

Die RGBA-Textur muss aus einer lizenzierten/autorisierten Referenz lokal erzeugt und an den Rändern transparent ausgeblendet werden. Das erzeugte `.blend`, `.vrm`, die Gesichtsreferenz und Zwischenbilder bleiben aus Git ausgeschlossen. Frontal ist v5 deutlich quelltreuer; extreme Profile und die darunterliegende Körpertextur bleiben durch das v2-Ausgangsrig begrenzt.
