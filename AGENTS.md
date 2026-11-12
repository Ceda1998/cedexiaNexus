# Arbeitsanweisungen für Cedexia Nexus

## Ziel und aktueller Fokus
Cedexia Nexus untersucht sichere verteilte LLM-Inferenz. Der erste Prototyp
soll Qwen3.8-27B für Text gemeinsam auf Windows/CUDA und macOS/Metal ausführen;
beide Hosts müssen an derselben Modellberechnung beteiligt sein. Ein Remote-
Chat ist kein Nachweis. Backend-Kompatibilität und Leistung sind noch offen.

Fokus: kleine, reproduzierbare Änderungen. Inferenzfunktionen gehören in
separate Tickets. Einstieg: README.md; Messplan und Abnahme: docs/prototype.md.

NX-037 ergänzt auf Nutzerauftrag eine frühe Offline-Desktop-Demo. UI-Code liegt
in nexus_ui/, Start und Lizenzhinweise in docs/desktop.md. Simulierte Daten
stets markieren; keine Live-Funktionen aus einer Demo ableiten. Satoshi-Dateien
nur lokal installieren und nicht über Git verteilen. Tabler-SVGs samt MIT-Lizenz
und Versionsmanifest ausliefern.

## Arbeitsablauf und Commits
- Notion-Dokumentation stets aktuell halten; nach jeder Implementierung die
  zugehörigen Tickets mit Status, Änderungen und Testnachweisen aktualisieren.
- Existiert kein passendes Ticket, vor der Implementierung im Development Board
  ein Ticket mit konkreten To Dos und Abnahmekriterien anlegen.
- Commitformat: `CN - Ticketnummer - kurze Beschreibung`, zum Beispiel
  `CN - NX-041 - Arbeitsregeln ergänzen`.

## Sicherheitsregeln und Grenzen
- Keine Modellgewichte automatisch herunterladen, großen Binärdateien oder
  fremden Installer ungeprüft einbinden. Quellen, Revisionen und Hashes prüfen.
- Keine Ports freigeben oder RPC-Server starten, sofern der konkrete Auftrag
  dies nicht ausdrücklich umfasst. Experimentelles llama.cpp RPC niemals
  ungeschützt öffentlich oder mit sensiblen Daten betreiben.
- Keine Secrets, privaten IPs, Hostnamen, Schlüssel, Tokens oder unbereinigten
  Rohlogs in Dateien, Commits oder CI-Artefakten speichern. Lokale Daten gehören
  in ignorierte Verzeichnisse; .gitignore ersetzt keine Inhaltsprüfung.
- Keine Remote-Shells, privilegierten Container oder administrativen Freigaben.
  Vertrauensgrenzen und bekannte Risiken stehen in docs/security.md.
- Kein produktives Sicherheitsniveau, keine GPU-Unterstützung und keine
  Performance behaupten, die nicht praktisch nachgewiesen wurden.
- Remotes und Pushes nur im ausdrücklich autorisierten Auftragsumfang ändern.
  Vorhandene Änderungen prüfen und erhalten; niemals ungefragt force-pushen.

## Repository-Orientierung
- scripts/doctor.py: lokale Diagnose mit Python-Standardbibliothek; schreibt
  JSON auf stdout, keine Dateien. Fehlende Messwerte sind unknown.
- tests/test_doctor.py: Unit-Tests mit isolierten Hardware-/Prozessantworten.
- .github/workflows/ci.yml: Tests ohne GPU, Modelle oder zusätzliche Pakete.
- docs/architecture.md: technische Richtung und offene Entscheidungen.
- docs/prototype.md: Hardwareannahmen, Testreihenfolge und Testnachweis.
- docs/mac-metal.md: geprüfter lokaler Metal-Build und Grenzen aus NX-005;
  `sh scripts/run_mac_model.sh` startet einen begrenzten Offline-Terminaltest.

## Ausführen und prüfen
Voraussetzung: Python >= 3.11 und Git. Keine Paketinstallation erforderlich.
Dies gilt für die Bootstrap-Diagnose. Für UI-Arbeit requirements-ui.txt in einer
lokalen virtuellen Umgebung installieren und Qt-Interaktionstests mit ausführen.
Im Repository-Root unter macOS:

```sh
python3 scripts/doctor.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests nexus_ui
git diff --check
```

In Windows PowerShell dieselben Python-Befehle mit `py -3` statt `python3`
ausführen; CI verwendet `python`. Für diesen Bootstrap gibt es kein separates
Build. Ein Diagnosebericht bestätigt keine funktionsfähige Inferenz.

## Definition of Done
Tests ausführen; Plattform und Grenzen dokumentieren. Änderungen auf Secrets,
große Dateien und unbelegte Aussagen prüfen; Git-Status und Diff kontrollieren.
Tickets erst nach erfüllten Abnahmekriterien abschließen. Keine Skills oder
Platzhalter ohne konkreten Bedarf. Details in Skripten oder vorhandenen Docs
pflegen. Die Projektlizenz bleibt offen; keine Lizenz eigenmächtig festlegen.

Postman CLI (optional): /Users/cedric.daunke/.local/bin/postman.
