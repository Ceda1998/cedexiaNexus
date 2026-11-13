"""NX-007: run a fixed, offline Qwen baseline on native Apple Silicon."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import statistics
import subprocess
import sys
import time
from datetime import date

from scripts.verify_model import DEFAULT_MANIFEST, verify


ROOT = DEFAULT_MANIFEST.parents[1]
RUNTIME = Path("local/build/llama-metal/bin/llama-completion")
PROMPT = "Write the numbers 1 through 100 separated by commas. Do not add an introduction."
CONTEXT = 4096
OUTPUT_TOKENS = 64
MEASURED_RUNS = 3
TIMEOUT_SECONDS = 180


class BenchmarkError(Exception):
    """An error safe to publish without raw output or local paths."""


def benchmark_args(filename):
    return [
        "--model", str(Path("models") / filename),
        "--offline", "--device", "MTL0", "--n-gpu-layers", "all", "--fit", "off",
        "--ctx-size", str(CONTEXT), "--batch-size", "128", "--ubatch-size", "128",
        "--threads", "4", "--threads-batch", "4", "--predict", str(OUTPUT_TOKENS),
        "--seed", "42", "--temp", "0", "--jinja", "--conversation", "--single-turn",
        "--reasoning", "off", "--ignore-eos", "--no-context-shift",
        "--no-display-prompt", "--color", "off", "--perf", "--verbosity", "4",
        "--prompt", PROMPT,
    ]


def parse_metrics(log):
    def match(pattern):
        results = re.findall(pattern, log, re.MULTILINE)
        if len(results) != 1:
            raise BenchmarkError("Messwert fehlt oder ist mehrdeutig.")
        return results[0]

    model = match(r"using device MTL0 \((Apple [^)]+)\)")
    layers, total = map(int, match(r"offloaded (\d+)/(\d+) layers to GPU"))
    context, budget = map(int, match(r"generate: n_ctx = (\d+), n_batch = 128, n_predict = (\d+)"))
    prefill_ms, input_tokens, prefill_rate = match(
        r"common_perf_print: prompt eval time =\s+(\d+\.\d+) ms /\s+(\d+) tokens"
        r" \(\s*\d+\.\d+ ms per token,\s*(\d+\.\d+) tokens per second\)"
    )
    decode_ms, decode_steps, decode_rate = match(
        r"common_perf_print:\s+eval time =\s+(\d+\.\d+) ms /\s+(\d+) runs"
        r"\s+\(\s*\d+\.\d+ ms per token,\s*(\d+\.\d+) tokens per second\)"
    )
    samples = int(match(r"common_perf_print:\s+samplers time =\s+\d+\.\d+ ms /\s+(\d+) tokens"))
    peak_rss = int(match(r"^\s*(\d+)\s+maximum resident set size$"))
    metal_mib = int(match(r"common_memory_breakdown_print: \|\s+- MTL0 .*?=\s*\d+ \+ \((\d+) ="))
    if (not 0 < layers == total or context != CONTEXT or budget != OUTPUT_TOKENS
            or samples - int(input_tokens) != OUTPUT_TOKENS
            or int(decode_steps) != OUTPUT_TOKENS - 1
            or min(int(input_tokens), peak_rss, metal_mib) <= 0
            or min(map(float, (prefill_ms, decode_ms, prefill_rate, decode_rate))) <= 0):
        raise BenchmarkError("Runtime hat das feste Messprofil nicht eingehalten.")
    return {
        "device": model, "gpu_layers": layers, "input_tokens": int(input_tokens),
        "output_tokens": OUTPUT_TOKENS, "decode_steps": int(decode_steps),
        "load_ms": float(match(r"common_perf_print:\s+load time =\s+(\d+\.\d+) ms")),
        "prefill_ms": float(prefill_ms), "prefill_tok_s": float(prefill_rate),
        "decode_ms": float(decode_ms), "decode_tok_s": float(decode_rate),
        "peak_rss_bytes": peak_rss, "metal_reported_mib": metal_mib,
        "process_swaps": int(match(r"^\s*(\d+)\s+swaps$")),
    }


def measure(args, env):
    """Observe stdout as it arrives and keep stderr only in bounded memory."""
    stderr = bytearray()
    first_output = None
    start = time.monotonic()
    with subprocess.Popen(
        ["/usr/bin/time", "-l", str(RUNTIME), *args], cwd=ROOT, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    ) as process, selectors.DefaultSelector() as streams:
        try:
            streams.register(process.stdout, selectors.EVENT_READ, "stdout")
            streams.register(process.stderr, selectors.EVENT_READ, "stderr")
            while streams.get_map():
                remaining = start + TIMEOUT_SECONDS - time.monotonic()
                if remaining <= 0:
                    raise BenchmarkError("Messlauf hat das Zeitlimit überschritten.")
                for key, _ in streams.select(remaining):
                    chunk = os.read(key.fd, 8192)
                    if not chunk:
                        streams.unregister(key.fileobj)
                    elif key.data == "stderr":
                        stderr.extend(chunk)
                        if len(stderr) > 1024 * 1024:
                            raise BenchmarkError("Runtime-Diagnose überschreitet die erlaubte Größe.")
                    elif first_output is None and chunk.strip():
                        first_output = time.monotonic()
            if process.wait(timeout=max(0, start + TIMEOUT_SECONDS - time.monotonic())) != 0:
                raise BenchmarkError("Runtime hat den Messlauf mit einem Fehler beendet.")
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise
    if first_output is None:
        raise BenchmarkError("Keine sichtbare Token-Ausgabe empfangen.")
    metrics = parse_metrics(stderr.decode("utf-8", errors="replace"))
    metrics["ttft_visible_ms"] = round((first_output - start) * 1000, 2)
    return metrics


def baseline():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise BenchmarkError("Nativer Apple-Silicon-Mac erforderlich.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("LLAMA_")}
    env.update(LC_ALL="C", LANG="C")
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    artifact = manifest["artifact"]
    filename = artifact["filename"]
    if not re.fullmatch(r"[\w.-]+\.gguf", filename):
        raise BenchmarkError("Manifest enthält keinen gültigen lokalen GGUF-Dateinamen.")
    revision = manifest["runtime"]["candidate_revision"]
    version = subprocess.run(
        [str(RUNTIME), "--version"], cwd=ROOT, env=env, capture_output=True,
        check=True, text=True, timeout=10,
    )
    build = re.search(
        r"^version: ([\w.-]+) \(build (\d+), commit ([0-9a-f]{8,40})\)$",
        version.stdout + version.stderr, re.MULTILINE,
    )
    if not build or not revision.startswith(build[3]):
        raise BenchmarkError("Runtime-Version stimmt nicht mit dem Manifest überein.")
    print("Prüfe das lokale Modell …", file=sys.stderr, flush=True)
    if not verify(ROOT / "models" / filename, manifest)["verified"]:
        raise BenchmarkError("Modellgröße oder SHA-256 stimmt nicht mit dem Manifest überein.")
    args = benchmark_args(filename)
    print("Warm-up (außerhalb der Messreihe) …", file=sys.stderr, flush=True)
    measure(args, env)
    runs = []
    for index in range(1, MEASURED_RUNS + 1):
        print(f"Messlauf {index}/{MEASURED_RUNS} …", file=sys.stderr, flush=True)
        runs.append(measure(args, env))
    for field in ("device", "gpu_layers", "input_tokens"):
        if len({run[field] for run in runs}) != 1:
            raise BenchmarkError("Die Messläufe verwenden unterschiedliche Eingaben oder Geräte.")
    ram_bytes = int(subprocess.check_output(
        ["/usr/sbin/sysctl", "-n", "hw.memsize"], timeout=10, text=True, env=env,
    ).strip())
    return {
        "experiment_id": "NX-007-MAC-METAL",
        "date": date.today().isoformat(),
        "macos_version": platform.mac_ver()[0],
        "macos_build": subprocess.check_output(
            ["/usr/bin/sw_vers", "-buildVersion"], timeout=10, text=True, env=env,
        ).strip(),
        "host_ram_bytes": ram_bytes,
        "runtime_revision": revision,
        "runtime_version": build[1],
        "runtime_build": int(build[2]),
        "artifact": {key: artifact[key] for key in ("repository", "revision", "quantization", "sha256")},
        "context_tokens": CONTEXT,
        "command": ["/usr/bin/time", "-l", str(RUNTIME), *args],
        "excluded_warmup_runs": 1,
        "runs": runs,
        "median": {
            key: statistics.median(run[key] for run in runs)
            for key in ("ttft_visible_ms", "load_ms", "prefill_tok_s", "decode_tok_s", "peak_rss_bytes")
        },
        "max_peak_rss_bytes": max(run["peak_rss_bytes"] for run in runs),
    }


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        print(json.dumps(baseline(), indent=2))
    except BenchmarkError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        print("Messung fehlgeschlagen: Runtime, Modellmanifest oder Systemmessung prüfen.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Messung abgebrochen.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
