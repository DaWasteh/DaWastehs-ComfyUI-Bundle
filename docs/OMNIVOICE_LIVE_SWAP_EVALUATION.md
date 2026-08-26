# OmniVoice-Prüfung für Live-Voice-Swapping · v0.9.5

**Entscheidung:** OmniVoice wird **nicht** als Live-Mikrofon-Voice-Swap in das
Bundle eingebaut. Es ist ein schnelles Zero-shot-**Text-to-Speech**-Modell, aber
kein kontinuierlicher Speech-to-Speech-Voice-Converter. Für den separaten
Live-Workflow wird deshalb der bereits installierte DirectML-RVC-Pfad genutzt.

Stand der Prüfung: 26. August 2026.

## Was OmniVoice tatsächlich macht

Das offizielle Projekt `k2-fsa/OmniVoice` beschreibt eine
nichtautoregressive, maskierte Diffusions-TTS. Die API erhält Text und optional
eine Referenzstimme:

```python
audio = model.generate(
    text="...",
    ref_audio="ref.wav",
    ref_text="Transkript der Referenz",
)
```

Die offizielle Empfehlung sind **3–10 Sekunden** Referenzaudio. Das passt gut
für kurze Zero-shot-Stimmenklone in geskripteter TTS beziehungsweise Dubbing,
ändert aber nicht die Aufgabenart: Mikrofoneingang, Timing, Prosodie und
laufender Inhalt einer sprechenden Person werden nicht als Stream konvertiert.

Quellen:

- Offizielles Repository/README: <https://github.com/k2-fsa/OmniVoice>
- Paper: <https://arxiv.org/abs/2604.00688>
- Modellkarte: <https://huggingface.co/k2-fsa/OmniVoice>

## Warum „40× schneller als Echtzeit“ kein Live-Swap bedeutet

Die RTF-Angabe misst, wie schnell ein vollständiger TTS-Clip nach bekanntem
Text berechnet wird. Sie ist keine Zusage für Time-to-first-audio,
Mikrofon-Streaming oder kausale Speech-to-Speech-Konvertierung. Das Modell
verwendet einen bidirektionalen Transformer und maskierte Diffusion.

In der offiziellen Issue #77 erklärt ein Contributor, diese NAR-Architektur
widerspreche echtem Streaming. Ein Collaborator empfiehlt höchstens
satzweises Erzeugen und schreibt ausdrücklich: **„This is not true
streaming.“**

Quelle: <https://github.com/k2-fsa/OmniVoice/issues/77>

Eine ASR→Text→OmniVoice-Kette wäre deshalb ein gepufferter Sprachassistent:
Sie verliert oder verändert Timing/Prosodie, wartet auf erkannte Textsegmente
und kann an Satzgrenzen hörbare Artefakte erzeugen. Das ist nicht der gewünschte
Live-Voice-Swap.

## Lizenzgrenze

Die Lizenz ist zweigeteilt und für ein öffentliches Bundle wichtig:

- **Code:** Apache-2.0.
- **Offiziell vortrainierte Gewichte:** laut Projekt-Collaborator nur
  **CC-BY-NC**, weil Teile der Trainingsdaten dies erfordern.
- Der Higgs-Audio-Tokenizer bringt zusätzliche Lizenzbedingungen mit.

Quelle und Maintainer-Klarstellung vom 9. Juli 2026:
<https://github.com/k2-fsa/OmniVoice/issues/60#issuecomment-4921003794>

Das Bundle lädt oder verteilt diese Gewichte daher nicht für den
Live-Showcase. Ein Viewer müsste für eine mögliche Offline-TTS-Nutzung
Nichtkommerzialität, Attribution und Tokenizer-Bedingungen selbst passend zum
Projekt prüfen.

## AMD-/ComfyUI-Risiko

Das offizielle README dokumentiert NVIDIA/CUDA, Apple MPS und Intel XPU.
Community-Berichte zeigen experimentelle ROCm-Läufe, aber keinen gepflegten,
für diese Windows-RDNA4-ComfyUI-Installation validierten Pfad. Die verfügbaren
Community-ComfyUI-Nodes sind TTS-/Clone-Nodes und keine Live-Converter. Einige
Installer bringen eigene Torch-Pins oder CUDA-Beschleuniger mit; sie dürfen die
bestehende Windows-ROCm-Umgebung nicht ungeprüft überschreiben.

Deshalb wurde weder ein OmniVoice-Custom-Node noch ein neues Gewichtspaket
installiert.

## Gewählter Live-Pfad

Für tatsächlichen Mikrofoneingang bleibt RVC/w-okada-artige Voice Conversion
die passende Modellklasse. Im lokalen Bundle ist bereits der gepinnte
DirectML-Runtime `deiteris/voice-changer b2332` vorhanden und bytegenau
verifiziert. Frühere lokale Messungen auf der RX 9070 XT lagen warm bei etwa
36–41 ms Modellrechenzeit pro 100-ms-Chunk. Dieser Pfad erhält laufendes
Sprachtiming deutlich direkter als ASR→TTS.

Er benötigt weiterhin ein eigenes oder ausdrücklich lizenziertes kompatibles
RVC-Modell und manuelle Audiowege über ein virtuelles Kabel. Ohne autorisiertes
RVC-Modell wird kein fremder Stimmenklon mitgeliefert.

Details und Messgrenzen:
[`live-avatar-v072-voice-backend-evaluation.md`](live-avatar-v072-voice-backend-evaluation.md)
