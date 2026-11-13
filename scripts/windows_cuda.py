"""NX-006: build and validate pinned llama.cpp on Windows x64."""

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

from scripts import doctor
from scripts.verify_model import DEFAULT_MANIFEST, verify


ROOT = DEFAULT_MANIFEST.parents[1]
SOURCE = ROOT / "local/vendor/llama.cpp"
BUILD = ROOT / "local/build/llama-cuda"
RUNTIME = BUILD / "bin/llama-completion.exe"
FLAGS = {
    "CMAKE_BUILD_TYPE": "Release",
    "CMAKE_CUDA_ARCHITECTURES": "120a-real",
    "BUILD_SHARED_LIBS": "OFF",
    "GGML_CPU": "ON",
    "GGML_CUDA": "ON",
    "GGML_CUDA_NCCL": "OFF",
    "GGML_CUDA_CCCL_VERSION": "",
    "GGML_CCACHE": "OFF",
    "GGML_RPC": "OFF",
    "LLAMA_BUILD_SERVER": "OFF",
    "LLAMA_BUILD_APP": "OFF",
    "LLAMA_BUILD_EXAMPLES": "OFF",
    "LLAMA_BUILD_TESTS": "OFF",
    "LLAMA_OPENSSL": "OFF",
    "LLAMA_SUBPROCESS": "OFF",
}
PROMPT = "Continue the number sequence: 1, 2, 3,"


class SmokeError(Exception):
    """Message that can be printed without paths or raw runtime logs."""


def capture(argv, timeout=15, env=None, cwd=ROOT):
    return subprocess.run(
        argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=timeout, check=True,
    )


def build(revision):
    missing = [tool for tool in ("git", "cmake", "ninja", "cl", "nvcc") if not shutil.which(tool)]
    if missing:
        raise SmokeError("Missing from PATH: " + ", ".join(missing) + ". Use the x64 developer shell and see docs/windows-cuda.md.")
    cmake_output = capture(["cmake", "--version"]).stdout
    cmake = re.search(r"^cmake version (\d+)\.(\d+)\.(\d+)", cmake_output, re.MULTILINE)
    if not cmake or (v := tuple(map(int, cmake.groups()))) < (3, 31, 8) or (4, 0, 0) <= v < (4, 0, 2):
        raise SmokeError("Use CMake 3.31.8+ in the 3.x series or CMake 4.0.2+ for 120a-real.")
    if not (SOURCE / ".git").exists():
        raise SmokeError("Pinned llama.cpp checkout missing. See docs/windows-cuda.md.")
    head = capture(["git", "rev-parse", "HEAD"], cwd=SOURCE).stdout.strip()
    dirty = capture(["git", "status", "--porcelain"], cwd=SOURCE).stdout.strip()
    if head != revision or dirty:
        raise SmokeError("Use a clean llama.cpp checkout at the manifest revision.")
    nvcc = Path(shutil.which("nvcc")).resolve()
    cl = Path(shutil.which("cl")).resolve()
    codes = capture([str(nvcc), "--list-gpu-code"]).stdout
    if "sm_120a" not in codes.split():
        raise SmokeError("This nvcc cannot target sm_120a. See docs/windows-cuda.md.")
    env = os.environ.copy()
    # CMake's CUDAHOSTCXX environment variable can override the compiler flag.
    env.pop("CUDAHOSTCXX", None)
    subprocess.run([
        "cmake", "-S", str(SOURCE), "-B", str(BUILD), "-G", "Ninja",
        "-DCUDAToolkit_ROOT:PATH=" + nvcc.parent.parent.as_posix(),
        "-DCMAKE_CUDA_COMPILER:FILEPATH=" + nvcc.as_posix(),
        "-DCMAKE_CUDA_HOST_COMPILER:FILEPATH=" + cl.as_posix(),
        *(f"-D{key}={value}" for key, value in FLAGS.items()),
    ], cwd=ROOT, env=env, check=True)
    subprocess.run([
        "cmake", "--build", str(BUILD), "--target", "llama-completion", "--parallel", "4",
    ], cwd=ROOT, check=True)
    if not RUNTIME.is_file():
        raise SmokeError("The build did not produce llama-completion.exe.")


def verified_cache():
    cache = {}
    for line in (BUILD / "CMakeCache.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([A-Za-z0-9_]+):[A-Z]+=(.*)", line)
        if match:
            cache[match[1]] = match[2]
    if cache.get("CMAKE_GENERATOR") != "Ninja" or any(cache.get(k) != v for k, v in FLAGS.items()):
        raise SmokeError("CMake settings differ from the NX-006 build profile. Rebuild first.")
    return cache


def run_args(model, device, layers):
    return [
        str(RUNTIME), "--model", str(model), "--offline", "--device", device,
        "--n-gpu-layers", str(layers), "--fit", "off",
        "--ctx-size", "1024", "--batch-size", "128", "--ubatch-size", "128",
        "--threads", "4", "--threads-batch", "4", "--predict", "8",
        "--seed", "42", "--temp", "0", "--jinja", "--conversation", "--single-turn",
        "--reasoning", "off", "--ignore-eos", "--no-context-shift",
        "--no-display-prompt", "--color", "off", "--verbosity", "4", "--perf",
        "--prompt", PROMPT,
    ]


def cuda_devices(listing):
    return [
        {"id": m[1], "name": m[2], "vram_mib": int(m[3]), "free_vram_mib": int(m[4])}
        for m in re.finditer(
            r"^[ \t]*(CUDA\d+): (NVIDIA [\w ()-]+) \((\d+) MiB, (\d+) MiB free\)$",
            listing, re.MULTILINE,
        )
    ]


def smoke_evidence(output, log, device, layers):
    prefill = re.search(r"common_perf_print: prompt eval time =\s*[0-9.]+ ms /\s*(\d+) tokens", log)
    samples = re.search(r"common_perf_print:\s*samplers time =\s*[0-9.]+ ms /\s*(\d+) tokens", log)
    if not output.strip() or not prefill or not samples or int(samples[1]) - int(prefill[1]) != 8:
        raise SmokeError("The run did not produce the expected eight smoke-test tokens.")
    offload = re.search(r"offloaded (\d+)/(\d+) layers to GPU", log)
    count = int(offload[1]) if offload else 0
    # Device discovery can appear in either run. Check the model's placement.
    placement = re.findall(r"llama_prepare_model_devices: using device (CUDA\d+) \(", log)
    expected_placement = [device] if layers else []
    if count != layers or placement != expected_placement:
        raise SmokeError("Runtime placement differs from the requested CPU/CUDA profile.")
    return {
        "status": "passed",
        "device": device if layers else "CPU",
        "layers_offloaded": count,
        "total_layers": int(offload[2]) if offload else doctor.UNKNOWN,
        "input_tokens": int(prefill[1]),
        "generated_tokens": 8,
    }


def smoke(manifest, mode, layers, device, model):
    cache = verified_cache()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LLAMA_", "GGML_"))}
    version = capture([str(RUNTIME), "--version"], env=env)
    build_id = re.search(
        r"^version: ([\w.-]+) \(build (\d+), commit ([0-9a-f]{8,40})\)$",
        version.stdout + version.stderr, re.MULTILINE,
    )
    revision = manifest["runtime"]["candidate_revision"]
    if not build_id or not revision.startswith(build_id[3]):
        raise SmokeError("Runtime revision does not match the manifest. Rebuild first.")
    listing = capture([str(RUNTIME), "--offline", "--list-devices"], env=env)
    devices = cuda_devices(listing.stdout)
    if mode == "cuda" and not any(d["id"] == device for d in devices):
        raise SmokeError(f"{device} is unavailable. Check the CUDA build and GPU driver.")
    nvcc = cache.get("CMAKE_CUDA_COMPILER") or shutil.which("nvcc")
    nvcc_output = doctor.run_command([nvcc, "--version"]) if nvcc else ""
    cuda = re.search(r"\brelease \d+\.\d+, V(\d+\.\d+\.\d+)\b", nvcc_output)
    nvidia = doctor.nvidia_gpus()
    drivers = sorted({
        gpu["driver_version"] for gpu in nvidia if re.fullmatch(r"\d+(?:\.\d+)+", gpu["driver_version"])
    }) if isinstance(nvidia, list) else []
    print("Verifying local GGUF size and SHA-256 …", file=sys.stderr, flush=True)
    if not verify(model, manifest)["verified"]:
        raise SmokeError("Model size or SHA-256 does not match the manifest.")
    print(f"Running {mode.upper()} smoke test …", file=sys.stderr, flush=True)
    run_device, run_layers = (device, layers) if mode == "cuda" else ("none", 0)
    args = run_args(model, run_device, run_layers)
    result = capture(args, timeout=180, env=env)
    metrics = smoke_evidence(result.stdout, result.stderr, run_device, run_layers)
    return {
        "experiment_id": "NX-006-WINDOWS",
        "os": platform.version(),
        "runtime_revision": revision,
        "runtime_version": build_id[1],
        "runtime_build": int(build_id[2]),
        "generator": "Ninja",
        "build_flags": FLAGS,
        "cuda_toolkit": cuda[1] if cuda else doctor.UNKNOWN,
        "nvidia_driver_versions": drivers or doctor.UNKNOWN,
        "cuda_devices": devices,
        "model_sha256": manifest["artifact"]["sha256"],
        "mode": mode,
        "context_tokens": 1024,
        "runtime_args": ["--model", manifest["artifact"]["filename"], *args[3:]],
        **metrics,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("build", help="build the pinned source with Ninja and MSVC")
    runner = commands.add_parser("smoke", help="verify model and produce a sanitized JSON report")
    runner.add_argument("mode", choices=("cuda", "cpu"))
    runner.add_argument("--layers", type=int, choices=range(1, 65), metavar="1-64", default=32)
    runner.add_argument("--device", default="CUDA0", help="CUDA device ID from --list-devices")
    runner.add_argument("--model", type=Path, help="local copy of the GGUF pinned in the manifest")
    args = parser.parse_args(argv)
    if platform.system() != "Windows" or platform.machine().upper() not in ("AMD64", "X86_64"):
        parser.exit(2, "NX-006 requires native Windows x64.\n")
    if args.action == "smoke" and not re.fullmatch(r"CUDA\d+", args.device):
        parser.error("--device must be a CUDA device ID, such as CUDA0")
    try:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        if args.action == "build":
            build(manifest["runtime"]["candidate_revision"])
        else:
            model = (args.model or ROOT / "models" / manifest["artifact"]["filename"]).resolve()
            print(json.dumps(smoke(manifest, args.mode, args.layers, args.device, model), indent=2))
    except SmokeError as exc:
        parser.exit(1, f"{exc}\n")
    except subprocess.TimeoutExpired:
        parser.exit(1, "A tool or runtime exceeded its time limit.\n")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        parser.exit(1, "Build or smoke test failed. Check the local prerequisites in docs/windows-cuda.md.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
