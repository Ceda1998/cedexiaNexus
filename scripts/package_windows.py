"""Build the portable Windows x64 app using pinned upstream CUDA archives."""

import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "local/windows-package"
APP = ROOT / "dist/CedexiaNexus"
RELEASE = "https://github.com/ggml-org/llama.cpp/releases/download/b12347/"
REVISION = "8ca5a8008b57aa39f2601546c0d07912045080a5"
ARCHIVES = {
    "llama-b12347-bin-win-cuda-13.5-x64.zip": "c8a95d61f7aa171fd2bf0879595c47a88535f9e0d0405e69fe50ca3ca739784b",
    "cudart-llama-bin-win-cuda-13.5-x64.zip": "c2bf4cc202bfbaaa7a0b75f5082457c3811326947bb216059b72839d844e9cba",
}
RUNTIME_FILE = re.compile(
    r"llama-completion\.exe|llama(?:-common|-completion-impl)?\.dll|"
    r"ggml(?:-base|-cuda|-cpu(?:-[\w-]+)?)?\.dll|"
    r"(?:cudart|cublas|cublasLt)64_\d+\.dll", re.IGNORECASE,
)


def download(url, path, sha256=None):
    if not path.exists():
        temporary = path.with_suffix(".part")
        try:
            with urlopen(url, timeout=90) as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if sha256:
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != sha256:
            path.unlink()
            raise ValueError(f"SHA-256 mismatch for {path.name}")
    return path


def stage_runtime(runtime):
    runtime.mkdir()
    for name, digest in ARCHIVES.items():
        print(f"Preparing {name} …", flush=True)
        archive = download(RELEASE + name, WORK / name, digest)
        with ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                filename = Path(entry.filename).name
                if entry.is_dir() or not RUNTIME_FILE.fullmatch(filename):
                    continue
                with bundle.open(entry) as source, (runtime / filename).open("xb") as target:
                    shutil.copyfileobj(source, target)
    required = ("llama-completion.exe", "llama.dll", "ggml.dll", "ggml-base.dll", "ggml-cuda.dll")
    if any(not (runtime / name).is_file() for name in required):
        raise ValueError("The release is missing a required llama.cpp file.")
    for prefix in ("ggml-cpu", "cudart64_", "cublas64_", "cublasLt64_"):
        if not list(runtime.glob(f"{prefix}*.dll")):
            raise ValueError(f"The release is missing {prefix} libraries.")
    launcher = runtime / "llama-completion.exe"
    version = subprocess.run(
        [str(launcher), "--version"], cwd=runtime, capture_output=True, text=True, check=True, timeout=30,
    )
    commit = re.search(r"\bcommit ([0-9a-f]{8,40})\)", version.stdout + version.stderr)
    if not commit or not REVISION.startswith(commit[1]):
        raise ValueError("The runtime does not report the pinned llama.cpp revision.")
    subprocess.run([str(launcher), "--offline", "--list-devices"], cwd=runtime, check=True, timeout=30)


def smoke_package():
    exe = str(APP / "CedexiaNexus.exe")
    subprocess.run([exe, "--smoke-test"], cwd=WORK, check=True, timeout=30)
    # Exercise the frozen verifier with spaces and Unicode in the model path.
    with TemporaryDirectory(dir=WORK) as directory:
        model = Path(directory) / "Prüfung lokal.gguf"
        data = b"NX-052 verifier test data"
        model.write_bytes(data)
        manifest = model.with_suffix(".json")
        manifest.write_text(json.dumps({
            "artifact": {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        }), encoding="utf-8")
        proof = subprocess.run(
            [exe, "--verify-local-model", str(model), "--manifest", str(manifest)],
            cwd=WORK, check=True, capture_output=True, timeout=30,
        )
        if json.loads(proof.stdout).get("verified") is not True:
            raise ValueError("The packaged model verifier did not verify the test file.")
        model.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 1) + bytes(128))
        proof = subprocess.run(
            [exe, "--verify-local-model", str(model), "--gguf"],
            cwd=WORK, check=True, capture_output=True, timeout=30,
        )
        if json.loads(proof.stdout).get("header_ok") is not True:
            raise ValueError("The packaged model verifier did not accept a standalone GGUF header.")
        data = struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + bytes(128)
        model.write_bytes(data)
        proof = subprocess.run(
            [exe, "--verify-local-model", str(model), "--fingerprint-gguf"],
            cwd=WORK, check=True, capture_output=True, timeout=30,
        )
        expected = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "parts": 1}
        if json.loads(proof.stdout) != expected:
            raise ValueError("The packaged verifier did not fingerprint the GGUF.")


def stage_notices():
    notices = APP / "licenses"
    notices.mkdir()
    shutil.copyfile(ROOT / "nexus_ui/assets/icons/LICENSE", notices / "Tabler-MIT.txt")
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", notices / "Python.txt")
    for name in ("LGPL-3.0-only.txt", "GPL-3.0-only.txt"):
        download("https://raw.githubusercontent.com/qt/qtbase/v6.8.3/LICENSES/" + name, notices / name)
    download(
        f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{REVISION}/LICENSE",
        notices / "llama.cpp-MIT.txt",
        "94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d",
    )
    for file in distribution("pyinstaller").files or ():
        if file.name in ("COPYING.txt", "LICENSE.txt") and ".dist-info" in str(file):
            shutil.copyfile(file.locate(), notices / f"PyInstaller-{file.name}")
    for package in ("pyOpenSSL", "cryptography", "cffi", "pycparser"):
        for file in distribution(package).files or ():
            if file.parent.name == "licenses" and file.name.startswith("LICENSE"):
                shutil.copyfile(file.locate(), notices / f"{package}-{file.name}.txt")
    shutil.copyfile(ROOT / "docs/windows-app.md", APP / "START.md")
    (notices / "Sources.txt").write_text(
        "Qt 6.8.3, PySide6 and Shiboken6 6.8.3 (LGPLv3), unmodified shared libraries.\n"
        "Qt source: https://download.qt.io/archive/qt/6.8/6.8.3/single/\n"
        "Qt for Python source: https://download.qt.io/official_releases/QtForPython/pyside6/\n"
        "The LGPL libraries in _internal may be replaced with compatible versions.\n"
        "LAN TLS libraries: https://pypi.org/project/pyOpenSSL/ and https://pypi.org/project/cryptography/\n"
        f"llama.cpp (MIT): https://github.com/ggml-org/llama.cpp/tree/{REVISION}\n"
        "NVIDIA CUDA 13.5 runtime and cuBLAS: https://docs.nvidia.com/cuda/eula/index.html\n"
        "CUDA archives and SHA-256:\n"
        + "".join(f"{RELEASE}{name}  {digest}\n" for name, digest in ARCHIVES.items()),
        encoding="utf-8",
    )


def main():
    if platform.system() != "Windows" or platform.machine().upper() not in ("AMD64", "X86_64"):
        raise SystemExit("Build this package on Windows x64.")
    manifest = json.loads((ROOT / "config/model-manifest.json").read_text(encoding="utf-8"))
    if manifest["runtime"]["candidate_revision"] != REVISION:
        raise SystemExit("Update the Windows release pins to match the model manifest.")
    WORK.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--onedir", "--console", "--hide-console", "hide-early",
        "--noupx", "--noconfirm", "--name", "CedexiaNexus", "--paths", str(ROOT),
        "--distpath", str(APP.parent), "--workpath", str(WORK / "build"), "--specpath", str(WORK),
        "--add-data", f"{ROOT / 'nexus_ui/assets/icons'}:nexus_ui/assets/icons",
        "--add-data", f"{ROOT / 'config/model-manifest.json'}:config",
        str(ROOT / "scripts/windows_desktop_entry.py"),
    ], cwd=ROOT, check=True)
    stage_runtime(APP / "_internal/runtime")
    stage_notices()
    smoke_package()


if __name__ == "__main__":
    main()
