# Technische Ausgangsbasis

## Entscheidung für NX-040

Der Bootstrap enthält ausschließlich Diagnose, Tests und Dokumentation.
Python >= 3.11 mit Standardbibliothek hält die lokale Prüfung ohne Abhängigkeiten
ausführbar. `scripts/doctor.py` fragt ausgewählte lokale Systeminformationen mit
Zeitlimits ab und gibt einen kleinen JSON-Bericht aus. Fehlende Werkzeuge oder
Probe-Fehler werden zu `unknown`; Rohfehler und Werkzeugpfade werden verworfen.
Unit-Tests simulieren auch fehlende Programme und unvollständige Antworten.

Die Offline-UI aus NX-037 verwendet Python/PySide6 als ersten Desktop-Spike.
Sie hält ausschließlich Demo-Zustand im Arbeitsspeicher und verwendet einen
Qt-Timer für fest vorgegebene Beispielausgabe. Es gibt keine Netzwerk- oder
Inferenzanbindung. `scripts/doctor.py` bleibt unabhängig; ein späterer Adapter
muss echte Diagnose asynchron ausführen. Start, Assets und Lizenzgrenzen:
[desktop.md](desktop.md). Windows-/Mac-Abnahme des Toolkit-Spikes bleibt offen.

Es existieren noch keine Inferenz-Laufzeitkomponenten. Die folgende Richtung ist ein
Versuchsplan, keine implementierte Architektur:

| Rolle | Verantwortung im späteren Versuch | Status |
| --- | --- | --- |
| Koordinator auf einem Host | Modell laden, lokale Berechnung und Remote-Offload steuern | Hostwahl offen |
| Zweiter Host als Worker | Teile derselben Modellberechnung auf CUDA oder Metal ausführen | Ungeprüft |
| Abgeschottetes LAN | Nur definierte Test-Peers verbinden | Bandbreite und Schutzmaßnahmen offen |

Native Windows/CUDA- und macOS/Metal-Builds haben Vorrang. Ein bestehendes
Backend wie llama.cpp RPC soll zunächst als begrenzter Spike untersucht werden,
bevor eine eigene Engine erwogen wird. Laut [Upstream-RPC-Dokumentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/rpc/README.md)
ist dieser Pfad experimentell und unsicher. Das ist keine Freigabe zum Starten
eines Servers; Sicherheitsgrenzen stehen in [security.md](security.md).

## Offene Entscheidungen

- Gemeinsamen llama.cpp-Commit sowie unterstützte Modell-/GGUF-Version pinnen.
- Windows-Treiber, CUDA-Toolchain und Apple-Metal-Pfad praktisch prüfen.
- Koordinator, lokale/entfernte Device-Zuweisung und Layer-Verteilung bestimmen.
- KV-Cache, Kontext, RAM-/VRAM-Reserve und Abbruch-/Timeout-Verhalten messen.
- Nachweisen, dass beide Hosts rechnen; aggregierter RAM ist kein gemeinsamer
  transparenter Speicher und keine Kapazitätsgarantie.
- RPC-Kompatibilität zwischen CUDA und Metal sowie nötige Absicherung bewerten.
- Projektlizenz separat entscheiden; bisher wurde keine Lizenz erteilt.

Die frühe GUI-Demo ist die ausdrücklich beauftragte Ausnahme zum Bootstrap.
Datenbank, Scheduler, öffentlicher P2P-Betrieb, produktiver API-Server,
Docker-Orchestrierung und eigene Distributed-Inference-Engine sind außerhalb
dieses Bootstraps. Messabfolge und Exit-Kriterien: [prototype.md](prototype.md).
