# DirectML-RVC Live-Voice-Swap · v0.9.5

Workflow:

`workflows/Voice Design/RVC_DirectML-Live-Microphone-Voice-Swap.json`

Der Workflow ist ein sicheres ComfyUI-Kontrollpanel für einen echten
Mikrofon→RVC→Audioausgang-Pfad. Die kontinuierliche Audiokonvertierung läuft
bewusst im spezialisierten lokalen Voice-Changer und nicht in der
request-basierten ComfyUI-Queue.

## Warum RVC statt OmniVoice

OmniVoice ist Zero-shot-TTS aus Text plus kurzer Referenz und unterstützt laut
Projektteam kein echtes inkrementelles Streaming. Es ist deshalb für Dubbing
interessant, aber nicht für die laufende Stimme eines Sprechers. Hinzu kommen
CC-BY-NC-Gewichte und ein ungeprüfter Windows-RDNA4-Pfad. Vollständige Prüfung:
[`OMNIVOICE_LIVE_SWAP_EVALUATION.md`](OMNIVOICE_LIVE_SWAP_EVALUATION.md).

RVC verarbeitet dagegen laufende Sprachchunks und behält das Timing der
Eingangssprache deutlich direkter bei.

## Kontrollnode

`DaWastehLiveVoiceSwapLauncher` bietet genau drei Aktionen:

- `start / open UI`: prüft alle 3.400 Dateien des gepinnten b2332-Runtime per
  Größe und SHA-256, startet nur `MMVCServerSIO.exe` und öffnet
  `http://127.0.0.1:18888/`.
- `status / open UI`: akzeptiert den Port nur, wenn der Listener exakt diese EXE
  aus dem gewählten Installationsordner ist.
- `stop verified service`: beendet nur den identitätsgeprüften Listener. b2332
  besitzt keinen authentifizierten Graceful-Shutdown-Endpunkt.

Beliebige Kommandos, andere Ports, fremde Listener und nicht verifizierte
Runtime-Bäume werden abgelehnt. Das Stimmenmodell wird weder automatisch
geladen noch im Repository verteilt.

Einmalige Runtime-Installation, falls sie fehlt:

```powershell
python tools/install_live_voice_converter.py --destination L:/ComfyUI/voice-changer-dml-b2332
```

## Lokales Demomodell auf diesem Rechner

Für die Vorführung wurde lokal und **außerhalb des Git-Repositories** das
offizielle Modell **Amitaro Hakihaki v1.0** importiert:

- Offizielle Seite/Regeln: <https://amitaro.net/synth/rvc/>
- Direkter Download stammt von derselben Urheberseite.
- Lokaler ZIP-Download: 421.620.163 Bytes.
- Lokal berechnete SHA-256 des Downloads:
  `54392cc8939d22a1d21def09de8e2fac457dffa243860aa3023f383aad00583b`
- RVC v2, 40 kHz, F0, mit Index; der Runtime hat daraus eigene Safetensors- und
  ONNX-Dateien erzeugt.

Pflichtcredit:

`RVC Model: Amitaro's Voice Material Studio (https://amitaro.net/)`

Die Modellregeln erlauben unter Credit unter anderem Stream, Video, Spiel und
kommerzielle Nutzung, verbieten aber insbesondere Weiterverkauf/-verteilung,
fehlenden Credit, Vortäuschen der echten Stimme, Täuschung/Scams sowie die auf
der Modellseite genannten Adult-, Gewalt-, Politik-/Religion-, Hass-, NFT-,
Glücksspiel-, Drogen- und Waffenwerbe-Kontexte. Die Modelldateien bleiben daher
rein lokal und sind kein Releasebestandteil.

## Empfohlener Start

1. Workflow laden, Aktion `start / open UI`, einmal normal **Run**.
2. In der lokalen RVC-UI Slot 0 wählen. Das Amitaro-Modell ist auf diesem
   Rechner bereits importiert; bei einem anderen Modell dessen Rechte zuerst
   prüfen.
3. DirectML-Gerät `0: AMD Radeon RX 9070 XT` wählen.
4. `rmvpe_onnx`, 48-kHz-Ein-/Ausgabe, zunächst ungefähr 100-ms-Chunk,
   Index-Ratio `0.5` und Protect `0.33` verwenden.
5. Bei ähnlicher Stimmhöhe Transpose `0`; bei männlicher Quelle für diese
   weibliche Zielstimme vorsichtig `+12` testen und anschließend nach Gehör
   reduzieren.
6. Für eine reine Vorführung Mikrofon als Eingang und **Kopfhörer** als Ausgang
   wählen. Lautsprecher erzeugen schnell Feedback.
7. Für OBS ein virtuelles Audiokabel separat und bewusst installieren; auf
   diesem Rechner wurde bei der v0.9.5-Prüfung keines erkannt. Danach nur den
   Kabelausgang in OBS aufnehmen und das Originalmikrofon stummschalten.
8. Am Ende im Workflow `stop verified service` wählen und erneut **Run**.

## Gemessener Smoke-Test

Lokale Testkette am 26. August 2026:

- Windows-System-TTS als klar künstliche Testquelle,
- 6,4495 Sekunden, 48-kHz-Mono-PCM,
- 65 aufeinanderfolgende 100-ms-REST-Chunks,
- RX 9070 XT über DirectML, `rmvpe_onnx`, app-eigenes ONNX,
- 0 Fehler,
- warmes Request-Roundtrip: Median 92,96 ms, p95 100,69 ms,
- warme Modellstufe: Median 70,24 ms, p95 78,74 ms,
- nichtleere 48-kHz-Ausgabe: RMS 0,00930, Peak 0,0669.

Das beweist Modellimport, ONNX-Erzeugung, DirectML-Inferenz und fortlaufende
Chunk-Konvertierung. Es ersetzt nicht die manuelle Abnahme von Mikrofon,
Kopfhörer/Kabel, Zielstimmenqualität, Feedbackfreiheit und mindestens zehn
Minuten Stabilität. Die tatsächliche hörbare Qualität hängt stark von
Eingangsstimme, Raum, Pegel, Transpose, Chunkgröße und Modell ab.
