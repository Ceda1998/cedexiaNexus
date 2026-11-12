# NX-004 · Festgelegtes Text-Modellartefakt

Stand 12.11.2026. Maschinenlesbare Quelle: [model-manifest.json](../config/model-manifest.json).
Die Metadatenabfrage selbst lädt keine Modellgewichte. Der erwartete Hash
stammt aus den veröffentlichten LFS-Metadaten. Am 12.11.2026 wurde die Datei
auf ausdrücklichen Nutzerauftrag lokal heruntergeladen und erfolgreich gegen
Größe und SHA-256 geprüft. Native Metal-Textgenerierung wurde anschließend in
[NX-005](mac-metal.md) auf dem M5-Mac nachgewiesen.

| Feld | Festlegung |
| --- | --- |
| Original | `Qwen/Qwen3.8-27B` |
| Originalrevision | `37561816e66b5b9153b1b64c10968c18c1e6f4a0` |
| GGUF-Repository | `ggml-org/Qwen3.8-27B-GGUF` |
| GGUF-Revision | `c1869413dece09109e55b7dcc2c77ef382b0d0bd` |
| Datei / Quantisierung | `Qwen3.8-27B-Q4_K_M.gguf` / Q4_K_M |
| Größe | 19.403.684.480 Byte, etwa 18,07 GiB |
| SHA-256 | `d15d4b6de55f662ac40e867702d31afe738d032fa06b829b2b1a21a49d4a48ee` |
| Lizenzangabe beider Modellkarten | Apache-2.0; unabhängig von der offenen Projektlizenz |

Herkunft: [Originalmodell](https://huggingface.co/Qwen/Qwen3.8-27B/tree/37561816e66b5b9153b1b64c10968c18c1e6f4a0),
[GGUF-Datei und LFS-Metadaten](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/blob/c1869413dece09109e55b7dcc2c77ef382b0d0bd/Qwen3.8-27B-Q4_K_M.gguf).
Die [Konvertierungsreferenz `.src_sha`](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF/raw/c1869413dece09109e55b7dcc2c77ef382b0d0bd/.src_sha)
nennt diese Originalrevision als PRIMARY. Zusätzliche DFlash- und
Projektor-Artefakte gehören nicht zur ersten Text-Baseline.

## Tokenizer, Chat-Template und Runtime

Original-Tokenizer: Qwen2Tokenizer, EOS `<|im_end|>`, Padding `<|endoftext|>`.
Die revisionsgebundenen Dateien
[tokenizer_config.json](https://huggingface.co/Qwen/Qwen3.8-27B/raw/37561816e66b5b9153b1b64c10968c18c1e6f4a0/tokenizer_config.json)
und [chat_template.jinja](https://huggingface.co/Qwen/Qwen3.8-27B/raw/37561816e66b5b9153b1b64c10968c18c1e6f4a0/chat_template.jinja)
wurden abgerufen und gehasht; ihre SHA-256 stehen im Manifest. Für GGUF gilt
der eingebettete Tokenizer samt Chat-Template. Dessen Übereinstimmung und
Thinking-Verhalten beim Rendern müssen die späteren Ladetests bestätigen;
kein selbst erfundenes Promptformat einsetzen.

Runtime-Kandidat: llama.cpp-Commit
[`8ca5a8008b57aa39f2601546c0d07912045080a5`](https://github.com/ggml-org/llama.cpp/commit/8ca5a8008b57aa39f2601546c0d07912045080a5).
Erforderlich sind GGUF-Architektur `qwen35`, Q4_K_M, eingebetteter Tokenizer,
Jinja-Verarbeitung und funktionierende native Metal-/CUDA-Backends. Dieser
Commit ist für einen kurzen Metal-Textlauf in NX-005 validiert. CUDA muss
NX-006 mit demselben Commit praktisch prüfen; nötige Revisionänderungen im
Manifest begründen. Eine plattformübergreifende Kompatibilitätszusage fehlt.
Cross-Backend-RPC bleibt separat in NX-009 zu prüfen.

19,4 GB Dateigröße sind kein Laufzeit-Speicherbedarf. Runtime, KV-Cache und OS
benötigen zusätzliche Reserve. Die Metadaten nennen 262.144 Kontexttokens;
das ist kein getestetes Speicherbudget. Für erste Baselines zunächst 4.096
Kontexttokens planen und unter tatsächlichen Speichergrenzen prüfen.

## Lokale Integritätsprüfung nach einem separat beauftragten Download

```sh
python3 -m scripts.verify_model /pfad/zur/Qwen3.8-27B-Q4_K_M.gguf
```

Unter Windows `py -3` statt `python3`. Die Prüfung liest in 1-MiB-Blöcken,
vergleicht Größe und SHA-256 und schreibt JSON ohne lokale Dateipfade. Exit 0
bedeutet identische Bytes, Exit 1 Abweichung oder ungültige/unlesbare Eingaben.
Sie lädt nichts herunter, startet keine Runtime und bestätigt keine Inferenz.
Vier Tests decken mehrere Blöcke, gleich große Beschädigung, abgeschnittene
Dateien, ungültige Eingaben und CLI-Exitcodes ohne Pfadpreisgabe ab.

## NX-005: lokale Modellbereitstellung vom 12.11.2026

Die oben gepinnte Q4_K_M-Datei wurde über HTTPS aus der festgelegten Revision
in `models/Qwen3.8-27B-Q4_K_M.gguf.part` geladen. Vor Umbenennung in
`models/Qwen3.8-27B-Q4_K_M.gguf` prüfte `scripts.verify_model` die gesamte Datei:
19.403.684.480 Byte, SHA-256 identisch zum Manifest, Exit 0, `verified: true`.
Der Ordner und die Gewichte bleiben Git-ignoriert und werden nicht verteilt.

Die Modelldatei wurde anschließend mit dem lokalen Metal-Build ausgeführt.
CMake liegt in `.venv`, die Runtime unter `local/build/llama-metal`.
Die 32 GiB Unified Memory sind keine Garantie für ein bestimmtes Kontext- oder
Leistungsbudget; tatsächlichen Speicherverbrauch beim Laden prüfen. Die
Demo-Seiten bleiben simuliert; die getrennte [lokale UI-Ansicht](desktop.md)
aus NX-042 verwendet dieselbe verifizierte Datei.
