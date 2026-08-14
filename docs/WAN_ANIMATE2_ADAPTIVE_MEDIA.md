# Wan Animate 2 · Adaptive Media · Speicherwarnung

## Adaptive Load Image / Load Video

`custom_nodes/ComfyUI-DaWasteh-MultiGPU-Control/` enthält zusätzlich zwei adaptive Medien-Nodes:

- `Adaptive Load Image · Model Resolution`
- `Adaptive Load Video · Model Resolution`

`Auto (connected model)` verfolgt die ausgehenden Graphverbindungen und zeigt das erkannte Profil im Node-Titel. Bei mehrdeutigen Graphen kann `model_profile` manuell gesetzt werden. `quality` bietet Modell-Nativqualität, 75 %, 50 % und 35 % Kantenauflösung.

Die Nodes croppen nicht. Sie skalieren das vollständige Bild beziehungsweise jeden vollständigen Videoframe bei beibehaltenem Seitenverhältnis und runden Breite/Höhe auf das erforderliche Modellraster. Der Video-Node bleibt bis zum tatsächlichen Frame-Abruf lazy und erhält Audio, FPS, Dauer und Bit-Tiefe.

## Wan Animate 2: Sekunden statt fester 81 Frames

Im Workflow `workflows/Character Animation/WanAnimate2_INT8_ConvRot-Motion-Transfer.json` steuert `OUTPUT DURATION · SECONDS` die aktive Motion-Transfer-Stufe:

```text
Sekunden × echte Pose-Video-FPS → nächster gültiger 4n+1-Framewert
```

Die Ausgabe verwendet weiterhin die FPS des geladenen Pose-Videos. Deshalb entspricht die sichtbare Sekundenangabe der gespeicherten Laufzeit, abgesehen von höchstens der kleinen `4n+1`-Rundung. Context Windows sind im aktiven Subgraph eingeschaltet, damit längere Werte nicht mehr an der früheren 81-Frame-Vorgabe hängen. Der zweite, standardmäßig bypassed Subgraph bleibt als manuelle Segment-Alternative erhalten.

Sehr lange Clips bleiben rechen- und speicherintensiv. Für schnelle Tests zuerst 35 % oder 50 % Qualität und wenige Sekunden verwenden.

## `WanTEModel`-Memory-Leak-Warnung

Die Meldung stammt aus ComfyUIs `cleanup_models_gc()` in `comfy/model_management.py`. Sie ist **keine Messung**, dass RAM oder VRAM mit jeder Warnung gewachsen ist. ComfyUI meldet damit folgenden Objektzustand:

- der verwaltete `ModelPatcher` ist über seine Weak Reference nicht mehr erreichbar,
- das zugrunde liegende PyTorch-Modell lebt aber noch,
- ein vollständiges `gc.collect()` plus `soft_empty_cache()` hat diesen Zustand nicht aufgelöst.

`WanTEModel` ist der Klassenname des Wan-UMT5-Textencoders, nicht des 14B-Wan-Video-DiT. Der für v0.9.4 geprüfte ComfyUI-Stand `0.33.0` (`7fe8a613`) enthält bereits die Finalizer-Bereinigung aus ComfyUI PR `#9979`; ein zusätzlicher „Clear VRAM“-Node im Workflow wäre trotzdem kein sauberer Fix. ComfyUI führt GC und Cache-Leerung vor der Warnung bereits selbst aus, und ein Workflow-Node kann eine fremde starke Python-Referenz nicht zuverlässig entfernen.

### Wann kann die Warnung beobachtet werden?

Wenn alle Läufe korrekt enden und sich RAM/VRAM nach mehreren identischen Durchläufen auf einem Plateau stabilisieren, ist die Meldung primär ein Diagnose-/Performancehinweis. Für lange Batches kann ein ComfyUI-Neustart zwischen Serien vorsorglich sinnvoll sein.

### Wann muss weiter untersucht werden?

Nicht ignorieren, wenn mindestens eines davon reproduzierbar auftritt:

- Prozess-RAM oder VRAM steigt nach jedem identischen Lauf weiter,
- Modellwechsel werden zunehmend langsamer,
- Out-of-Memory-Fehler oder Abstürze folgen,
- derselbe Ablauf war ohne Drittanbieter-Nodes stabil.

Dann:

1. ComfyUI und alle Custom Nodes gemeinsam aktualisieren.
2. Nach einem frischen Neustart denselben kurzen Workflow mehrfach ausführen und RAM/VRAM messen.
3. Mit dem aktuellen Core-Wan-Workflow und möglichst ohne Drittanbieter-Nodes gegenprüfen.
4. Custom Nodes anschließend in Hälften wieder aktivieren, bis der Referenzhalter eingegrenzt ist.
5. Für einen Fehlerbericht ComfyUI-Commit, Python-/Torch-Version, Workflow, vollständigen Log und Messwerte angeben.

`--cache-none` kann als Diagnose helfen, verursacht aber zusätzliche Modell-Neuladungen und repariert keine lebende Python-Referenz.

## Primärquellen

- [ComfyUI model management · geprüfter Commit 7fe8a613](https://github.com/Comfy-Org/ComfyUI/blob/7fe8a613/comfy/model_management.py)
- [ComfyUI Wan text encoder · geprüfter Commit 7fe8a613](https://github.com/Comfy-Org/ComfyUI/blob/7fe8a613/comfy/text_encoders/wan.py)
- [ComfyUI issue #6390](https://github.com/Comfy-Org/ComfyUI/issues/6390)
- [ComfyUI PR #9979](https://github.com/Comfy-Org/ComfyUI/pull/9979)
