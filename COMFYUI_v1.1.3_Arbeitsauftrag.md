# ComfyUI: Workflow-Konsolidierung, MiniMax-H3-Audiofix und Release v1.1.3

Überarbeite mein bestehendes ComfyUI-Projekt und setze die folgenden Änderungen tatsächlich um. Ich möchte nicht nur einen Plan oder Empfehlungen, sondern funktionierende Workflows, nachvollziehbare Testergebnisse und – bei erfüllten Abnahmekriterien – das Release v1.1.3 samt Update-Skript.

Arbeite innerhalb der vorhandenen Projektstruktur. Bewahre die bestehenden Anwendungsfälle und verwende vorhandene Customnodes, Hilfsfunktionen und Skripte, bevor du neue Abhängigkeiten oder parallele Implementierungen einführst. Weniger unnötige Workflows und einfachere Bedienung sind das Ziel, nicht weniger Funktionalität.

## 1. Prioritäten und Arbeitsweise

Arbeite in dieser Reihenfolge:
1. MiniMax-H3-Workflows sichten und die überschneidenden Anwendungsfälle zuordnen. Originale und Vergleichsbasis sichern.
2. Den Audiofehler unserer MiniMax-H3-REF- und FL-Workflows reproduzieren, eingrenzen und beheben. Vorher keine großflächigen Umbauten an diesen Workflows.
3. MiniMax-H3-Workflows auf dieser geprüften Grundlage konsolidieren.
4. Übrige Workflows auf Redundanz prüfen; Videolängen, optionale Eingaben und GPU-Zuweisung vereinheitlichen.
5. Migration/Update-Skript fertigstellen und bei bestandener Abnahme v1.1.3 veröffentlichen.

Beginne nach einer kurzen Bestandsaufnahme mit der Umsetzung. Halte nicht nach der Planung an und warte nicht zwischen jedem Arbeitsschritt auf meine Zustimmung. Ermittle technische Details selbst im Repository und in der Installation. Frage nur bei tatsächlich nicht auflösbaren Entscheidungen mit Datenverlust-, Kosten- oder Veröffentlichungsrisiko nach.

Nutze Parallelisierung für unabhängige Analysen, aber mit klarer Zuständigkeit für Dateien. Keine konkurrierenden Änderungen derselben Dateien. GPU-intensive Testläufe müssen zwischen allen Agenten koordiniert und nacheinander ausgeführt werden, damit Ergebnisse vergleichbar bleiben und sich die Prozesse nicht gegenseitig den Speicher belegen.

Halte einen knappen Arbeitsstand mit Entscheidungen, Testergebnissen, offenen Punkten und nächsten Schritten im Projekt fest. Nutze vorhandene Dokumentation dafür, statt ein unnötiges Berichtssystem aufzubauen. Informiere mich an sinnvollen Meilensteinen. Keine endlosen Review- oder Optimierungsschleifen und keine Ausweitung auf unbestellte Features.

## 2. Installation, Repository und Sicherung

Die Beispielvideos liegen hier:
L:\ComfyUI\ComfyUI\output\video

Ermittle den tatsächlichen ComfyUI-Root, das zuständige Projekt-Repository, Workflow-Quell- und Installationsverzeichnisse, die verwendete Python-Umgebung, Startskripte und vorhandene Update-Skripte. Unterscheide ausdrücklich zwischen Repository und installierter Kopie. Verwende keine alten Installationspfade oder angenommenen GPU-Indizes ungeprüft.

Prüfe Git-Status, Branch, Remotes, vorhandene Versionskonventionen und lokale Änderungen. Sichere die betroffenen Originaldateien einschließlich unversionierter Workflows reversibel. Verwirf, überschreibe oder committe keine fremden Änderungen ungefragt; verschiebe sie auch nicht ungefragt in einen Git-Stash. Kein `reset --hard`, `git clean` oder Force-Push.

Dokumentiere für die Fehlersuche die relevanten ComfyUI-/Customnode-Versionen, Modellvarianten, Quantisierung, Torch-/ROCm-Versionen und Startparameter. Verändere nicht zuerst pauschal die gesamte Umgebung: Die funktionierende Referenz und die Fehlerbedingungen müssen erhalten bleiben.

Modelle, Eingabedateien, Beispielvideos, andere Outputs, Zugangsdaten und private Konfigurationen gehören nicht in den Release-Commit.

## 3. MiniMax-H3-Audiofehler: höchste technische Priorität

Meine Beobachtung:
- Der offizielle Template-Workflow erzeugt guten Ton.
- Unsere REF- und FL-Workflows erzeugen blechernen, artefaktbehafteten Ton; nach meinen bisherigen Versuchen mit unterschiedlichen Modellen.

Beispieldateien im oben genannten Videoverzeichnis:
- Offizielle Referenz: `MiniMax_H3_00003_.mp4`
- Unser REF-Workflow: `MiniMax_H3_Spectrum_Ref2VA_MAXIMUM_All_References_00001_.mp4`
- Unser FL-Workflow: `MiniMax_H3_Spectrum_FL2VA_First_Last_Frame_00001_.mp4`

Behandle meine Beobachtung als Fehlerbeschreibung, nicht als bereits bewiesene Ursachenanalyse.

### Vergleichsbasis und Eingrenzung

Ordne die Dateien ihren tatsächlichen Workflow-JSONs und Einstellungen zu. Nutze vorhandene Metadaten und Begleitdateien; erfinde keine fehlenden Parameter. Sichere den funktionierenden offiziellen Workflow unverändert. Wenn die damalige Konfiguration nicht rekonstruierbar ist, dokumentiere das und erzeuge eine neue kontrollierte Referenz.

Vergleiche die Ausführungspfade semantisch: Welche Nodes, Parameter, Modellkomponenten und Patches beeinflussen die Audioerzeugung und Ausgabe? Dateinamen, Node-Anzahl und grafische Positionen reichen dafür nicht.

Führe kontrollierte Vergleichstests mit gleichem Modell, gleicher Quantisierung, gleichen relevanten Eingaben, Prompt, Seed, Auflösung, Dauer und Sampler-Einstellungen durch, soweit der untersuchte Unterschied das zulässt. Dokumentiere unvermeidbare Unterschiede. Die vorhandenen drei Videos allein sind noch kein kontrollierter A/B-Test.

Isoliere insbesondere:
- Offizieller nativer Pfad gegenüber unserem entsprechenden Pfad ohne zusätzliche Beschleunigungspatches.
- Unser Pfad ohne Spectrum gegenüber demselben Pfad mit Spectrum.
- Weitere tatsächlich vorhandene Patches, Cache-Verfahren, LoRAs, Sampler- oder Decoder-Abweichungen jeweils einzeln.

Prüfe die zur installierten Spectrum-Version passenden Upstream-Hinweise zu Audioqualität und Sampler-Kompatibilität:
https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3
 Leite daraus Hypothesen ab, aber übernimm Einstellungen nicht blind und erkläre Spectrum nicht allein aufgrund des Dateinamens zur Ursache.

Stelle bei Patch-Wechseln sicher, dass deaktivierte Patches wirklich entfernt sind. Nutze bei Bedarf frisch geladene Modelle oder einen separaten Testprozess, damit persistenter Modellzustand und Caches die Vergleiche nicht verfälschen.

### Erzeugung oder Export?

Untersuche, wo der Fehler erstmals entsteht: im generierten Audio/Latent, beim Decoding, bei einer Weiterverarbeitung oder erst beim Encodieren/Zusammenführen mit dem Video.

Prüfe nach Befund unter anderem Audio-Decoder/VAE, Präzision und Gerätewechsel, Conditioning und Referenz-Audio, Kanal-/Tensoranordnung, Sample-Rate, tatsächliches Resampling, Pegel/Clipping, Chunk-Übergänge sowie Export-Codec und zeitliche Synchronität. Nutze nur Architekturannahmen, die du im tatsächlichen Code bestätigt hast.

Sichere bei Bedarf das Audio direkt vor dem Videoexport verlustfrei und vergleiche es mit der aus dem fertigen Video extrahierten Tonspur. Nutze vorhandenes FFmpeg/ffprobe oder geeignete lokale Werkzeuge. Metadaten, Spektren und Pegelwerte können eine Ursache stützen, beweisen aber allein keine gute Klangqualität.

Behebe die Ursache möglichst lokal und nachvollziehbar. Kein pauschaler Equalizer, Denoiser, Lautstärke-Trick oder geänderter Prompt als Ersatz für einen Pipeline-Fix. Falls eine Beschleunigung nachweislich die Qualität verschlechtert, darf sie als dokumentierter Qualitäts-/Geschwindigkeitsmodus optional werden; der zuverlässige Standardpfad hat Vorrang.

Belege den Fix für REF und FL mit kurzen, geeigneten A/B-Ausgaben; bestätige ihn nach Möglichkeit mit einem weiteren Seed. Halte Ursache, Änderung, Testeinstellungen und Ergebnis fest. Behaupte keinen Hörtest, den du nicht tatsächlich durchführen konntest. Ist eine Hörabnahme nötig, aber mit deinen Werkzeugen nicht möglich, stelle die Vergleichsdateien bereit und kennzeichne die offene Abnahme ausdrücklich.

## 4. Workflows konsolidieren, Funktionen erhalten

Erstelle zuerst für MiniMax H3 und anschließend für die übrigen Workflows eine kompakte Bestandsliste: Zweck, Eingaben, Ausgaben, Modelle/Loader, Besonderheiten, Redundanzen und Entscheidung „behalten“, „zusammenführen“ oder „archivieren“.

Fasse echte funktionale Doppelungen zusammen. Bewahre Unterschiede wie REF, First/Last Frame, Continuation, Audio-Steuerung und andere tatsächlich vorhandene Betriebsarten. Erzwinge keinen einzigen überladenen Universalworkflow, wenn wenige klar getrennte Workflows verständlicher und technisch zuverlässiger sind.

Für General Prompt Enhancer sollen Modellauswahl, Presets oder wiederverwendbare Bausteine separate nahezu identische Workflows ersetzen, soweit Loader, Prompt-Templates, Ein-/Ausgabeformate und Fähigkeiten kompatibel sind. Erhalte die nötigen modellspezifischen Einstellungen. „Anderes LLM“ allein ist weder ein zwingender Grund für einen eigenen Workflow noch ein Beweis für Austauschbarkeit.

Entferne abgelöste Workflows erst aus der aktiven Auswahl, wenn der Ersatz ihre Anwendungsfälle abdeckt. Sichere Altstände außerhalb der aktiven Auswahl und dokumentiere die Zuordnung „alter Workflow → neuer Workflow/Modus“. Aktualisiere README, Verweise und Installationslogik. Prüfe auch Abhängigkeiten, die außerhalb der sichtbaren Node-Verbindungen bestehen.

## 5. Videolängen einheitlich in Sekunden

Alle Video-Workflows sollen eine klar benannte, zentrale Eingabe `Dauer (Sekunden)` erhalten. Eine reine Umbenennung eines Frame-Feldes genügt nicht.

Leite die benötigte Frame-Anzahl aus Dauer, tatsächlicher FPS und den Beschränkungen des jeweiligen Modells ab. Prüfe Mindest-/Maximallängen und zulässige zeitliche Raster im vorhandenen Code bzw. in der passenden offiziellen Dokumentation. Keine universelle, ungeprüfte Rundungsformel für alle Modelle.

Zeige oder dokumentiere gewünschte Dauer, berechnete Frames und tatsächlich resultierende Dauer. Übergib konsistente Werte an Generierung, Decoding, Audioverarbeitung und Export. Ändere nicht nur die Export-FPS, um eine gewünschte Dauer vorzutäuschen.

Bei vorhandenen Continuation-/Mehrsegment-Workflows müssen Gesamtdauer, Segmentdauer und Übergangsüberlappungen korrekt zusammenpassen. Erhalte vorhandene Modi wie „Länge von Referenz-Audio/-Video übernehmen“ mit klarer Auswahl und Vorrangregel gegenüber manueller Sekundenangabe.

Teste kurze, typische und relevante Grenzwerte sowie eine nicht ganzzahlige Sekundenangabe. Prüfe die tatsächlichen Medienlaufzeiten und A/V-Synchronität. Nicht unterstützte Dauern müssen verständlich behandelt werden, statt stillschweigend falsche Ergebnisse zu erzeugen. Baue dafür keine neue, unbestellte Langvideo-Engine.

## 6. Optionale Inputs einfach und vollständig deaktivieren

Bei Workflows mit vielen Eingaben soll jeder optionale Funktionszweig zentral und verständlich ein-/ausschaltbar sein. Fasse zusammengehörige Loader, Vorverarbeitung und Conditioning-Nodes sinnvoll zusammen und verwende vorhandene Gruppen-/Schaltmechanismen, soweit sie zuverlässig funktionieren.

Entscheidend ist das Verhalten, nicht nur die Optik:
- Ein Schalter deaktiviert den vollständigen optionalen Zweig; keine versteckten zusätzlichen Bypass-Schritte.
- Deaktivierte Eingaben dürfen keine Dateien voraussetzen, unnötig Modelle laden oder weiter GPU-Arbeit auslösen.
- Nachgeschaltete Nodes erhalten einen gültigen, beabsichtigten Ersatzpfad. Keine falschen Datentypen, übrig gebliebenen Referenzen oder alten gecachten Ergebnisse.

Unterscheide Bypass, Mute und tatsächlich bedingte/lazy Ausführung. Technische Referenz:
https://docs.comfy.org/custom-nodes/backend/lazy_evaluation
 Prüfe auch die Prompt-Validierung: Ein unbenutzter Loader mit fehlender Datei darf nicht schon vor der Ausführung den gesamten Workflow blockieren.

Nutze bevorzugt native oder bereits installierte, geeignete Mechanismen. Eine kleine zusätzliche Hilfsnode ist erlaubt, wenn die vorhandenen Mittel das benötigte Verhalten nicht sauber leisten; vermeide dafür umfangreiche neue Abhängigkeiten.

Teste je optionalem Zweig „ein“, „aus“, „aus mit fehlender Eingabedatei“ sowie wichtige Kombinationen und erneutes Umschalten. Die normale Workflow-Ausführung darf keine versteckten Sondergriffe erfordern.

## 7. GPU-Zuweisung mit meiner vorhandenen Customnode

Meine GPUs:
- AMD Radeon AI PRO R9700 mit 32 GB VRAM.
- AMD Radeon RX 9070 XT mit 16 GB VRAM.

Ermittle meine vorhandene GPU-Zuweisungs-Customnode, ihre Schnittstelle und ihre tatsächliche Wirkung. Integriere sie konsistent in jeden Workflow mit GPU-relevanten Komponenten. Baue keine konkurrierende Geräteverwaltung ohne belegte Notwendigkeit.

Ermittle die Gerätezuordnung zur Laufzeit anhand von Gerätename und Speicher, unter Berücksichtigung der Sichtbarkeits-/Startkonfiguration. Nicht blind annehmen, dass GPU 0 oder GPU 1 einer bestimmten Karte entspricht.

Prüfe als Ausgangskonfiguration das große Hauptmodell auf der R9700 und geeignete Komponenten wie Textencoder/CLIP, Video-VAE oder Audio-VAE auf der RX 9070 XT, soweit Backend und Nodes das unterstützen und die Messungen dafür sprechen. Berücksichtige Lastspitzen bei Encoding/Decoding, Aktivierungen, temporäre Buffer und Gerätetransfers – nicht nur die Größe der Gewichte.

Behandle die 32 GB und 16 GB nicht als einen gemeinsamen 48-GB-Speicher. Unterscheide Komponentenverteilung, echtes Modell-Splitting und CPU-Offloading. Behaupte keine Funktion, die der vorhandene Backend-/Node-Pfad nicht unterstützt.

Prüfe, ob die gewählte Zuordnung beim tatsächlichen Laden und Ausführen erhalten bleibt oder von ComfyUI/anderen Nodes überschrieben wird. Miss den Spitzenbedarf je GPU und den zusätzlichen RAM-Bedarf. Vermeide unnötige Duplikate und Transfers. Eine sinnvoll gewählte Single-GPU-Konfiguration darf besser sein als künstlich erzwungene Dual-GPU-Nutzung.

Falls Komponenten nicht passen, nutze nur unterstützte und dokumentierte Alternativen. Keine stillen Präzisions-/Qualitätsänderungen und kein unkontrolliertes Swapping als angebliche Lösung. Teste nach Geräte- oder Präzisionsänderungen insbesondere den reparierten Audiopfad erneut.

## 8. Abnahme und Update-Skript

Für geänderte Workflows müssen JSON-Struktur, Node-Typen, Links, Pflichtinputs und die Ausführung in der installierten ComfyUI-Version geprüft sein. Ein erfolgreiches JSON-Parsing allein ist kein Funktionstest.

Führe geeignete kurze Laufzeittests je verändertem Ausführungspfad durch. Gemeinsame Bausteine können gezielt getestet werden; starte nicht ohne Erkenntnisgewinn dieselben teuren Renderläufe für jede kosmetische Variante. Ungetestete Bereiche ausdrücklich benennen.

Erweitere bevorzugt das vorhandene Windows-/PowerShell-Update-Skript. Es soll die Änderungen dieses Projekts reproduzierbar in meine tatsächliche ComfyUI-Installation übernehmen, nicht ungefragt sämtliche Upstream-Repositories aktualisieren.

Das Skript benötigt:
- Konfigurierbaren ComfyUI-Zielpfad und eine eindeutig gewählte Release-Version, für diesen Auftrag v1.1.3.
- Vorprüfungen, Trockenlauf, verständliche Logs, Fehlerbehandlung und Sicherung/Wiederherstellung der betroffenen Dateien.
- Wiederholbare Ausführung ohne neue Duplikate oder beschädigten Zustand.
- Gezielte Migration abgelöster projektverwalteter Workflows anhand der Alt→Neu-Zuordnung; persönlich veränderte Dateien nicht ungefragt überschreiben oder löschen.
- Schutz für Modelle, Inputs, Outputs, Zugangsdaten, private Einstellungen und unabhängige Customnodes.

Erhalte die funktionierende Python-/Torch-/ROCm-Umgebung. Ändere Abhängigkeiten nur bei belegter Notwendigkeit, mit reproduzierbarer Versionsbindung und Rückweg. Keine pauschalen `pip install --upgrade`-Aktionen oder globalen Treiberänderungen.

Teste den Update- und Rückweg zunächst isoliert bzw. mit dem lokalen Release-Kandidaten, bevor ein veröffentlichter Tag existiert. Prüfe, dass alle erforderlichen Customnode-Änderungen mit ausgeliefert werden. Keine Lösung, die nur durch unversionierte Änderungen in meiner lokalen Installation funktioniert.

Unterbrich keine laufenden ComfyUI-Jobs. Synchronisiere die freigegebenen Projektdateien über den geprüften Update-Weg, soweit dies ohne Konflikte möglich ist. Dokumentiere andernfalls den konkreten noch erforderlichen Schritt einschließlich Aufruf des Skripts und nötigem Neustart.

## 9. Release v1.1.3 und Abschluss

Aktualisiere Versionsangaben, Changelog und relevante Bedienhinweise konsistent. Committe ausschließlich zu diesem Auftrag gehörende Änderungen.

Wenn die Kernanforderungen tatsächlich erfüllt sind, führe den üblichen Release-Prozess dieses Repositories aus und pushe den zugehörigen Branch/Commit und den Tag v1.1.3 an das bereits konfigurierte, eindeutig zuständige Remote. Prüfe vorher, ob der Tag schon existiert. Keine bestehenden Tags überschreiben, keine History umschreiben und keine fremden Repositories verändern.

Ein nicht reproduzierter oder nicht ausreichend verifizierter Audiofix, defekte Kernworkflows oder eine ungeprüfte Migration sind Release-Blocker. Arbeite unabhängige Aufgaben trotzdem weiter ab, aber veröffentliche in diesem Zustand kein angeblich fertiges v1.1.3. Halte nötigenfalls einen klar bezeichneten Release-Kandidaten und die offenen Punkte fest. Respektiere vorhandene Branch-Schutz- und Freigaberegeln.

Berichte am Ende knapp und konkret:
- Welche Workflows bleiben, zusammengeführt oder archiviert wurden und wo ich die bisherigen Funktionen finde.
- Welche Audio-Ursache belegt wurde, was geändert wurde und welche Vergleichstests vorliegen.
- Wie Sekundensteuerung, optionale Inputs und GPU-Zuweisung bedient werden.
- Welche Prüfungen bestanden sind und welche Einschränkungen/Abnahmen offen bleiben.
- Wo das Update-Skript liegt, wie ich es ausführe und zurückrolle.
- Welcher Commit/Tag tatsächlich gepusht und welcher Stand lokal installiert wurde.

Kennzeichne eindeutig: implementiert, ausgeführt/getestet, nur statisch geprüft oder blockiert. Keine erfundenen Messwerte, Hörtests, erfolgreichen Installationen oder Push-Ergebnisse.
