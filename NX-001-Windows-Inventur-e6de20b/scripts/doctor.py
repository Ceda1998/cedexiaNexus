#!/usr/bin/env python3
"""Read-only local inventory. No dependencies, network calls or persistent logs."""

import csv
import json
import os
import platform
import shutil
import subprocess
import sys

UNKNOWN = "unknown"
TIMEOUT_SECONDS = 10
TOOLS = (
    "git", "cmake", "ninja", "clang", "cl", "nvcc", "nvidia-smi", "xcrun",
    "powershell", "pwsh",
)


def run_command(args):
    """Never expose stderr, exceptions or local executable paths in the report."""
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else UNKNOWN


def positive_int(value):
    try:
        number = int(str(value).strip())
        return number if number > 0 else UNKNOWN
    except (ValueError, TypeError):
        return UNKNOWN


def read_json(args):
    try:
        return json.loads(run_command(args).lstrip("\ufeff"))
    except (ValueError, TypeError):
        return None


def mac_hardware():
    cpu = run_command(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"])
    ram = positive_int(run_command(["/usr/sbin/sysctl", "-n", "hw.memsize"]))
    data = read_json(["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"])
    gpus = []
    if isinstance(data, dict) and isinstance(data.get("SPDisplaysDataType"), list):
        for item in data["SPDisplaysDataType"]:
            if not isinstance(item, dict):
                continue
            gpus.append({
                "name": item.get("sppci_model") or UNKNOWN,
                "metal_indication": item.get("spdisplays_metal")
                or item.get("spdisplays_metal_featureset")
                or item.get("spdisplays_mtlgpufamilysupport") or UNKNOWN,
            })
    return cpu, ram, gpus or UNKNOWN


def windows_hardware():
    # Query selected properties only; never serialize the entire ComputerSystem.
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        return UNKNOWN, UNKNOWN, UNKNOWN
    query = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
        "[pscustomobject]@{"
        "cpu=(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name);"
        "ram_bytes=(Get-CimInstance Win32_ComputerSystem | Select-Object -ExpandProperty TotalPhysicalMemory);"
        "gpu_names=@(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name)"
        "} | ConvertTo-Json -Compress"
    )
    data = read_json([shell, "-NoProfile", "-NonInteractive", "-Command", query])
    if not isinstance(data, dict):
        return UNKNOWN, UNKNOWN, UNKNOWN
    names = data.get("gpu_names")
    if isinstance(names, str):
        names = [names]
    gpus = [{"name": name} for name in names if isinstance(name, str) and name] if isinstance(names, list) else []
    cpu = data.get("cpu")
    return (
        cpu if isinstance(cpu, str) and cpu else UNKNOWN,
        positive_int(data.get("ram_bytes")),
        gpus or UNKNOWN,
    )


def posix_hardware():
    cpu = platform.processor() or UNKNOWN
    try:
        pages = positive_int(os.sysconf("SC_PHYS_PAGES"))
        page_size = positive_int(os.sysconf("SC_PAGE_SIZE"))
        ram = pages * page_size if isinstance(pages, int) and isinstance(page_size, int) else UNKNOWN
    except (OSError, ValueError, AttributeError):
        ram = UNKNOWN
    return cpu, ram, UNKNOWN


def nvidia_gpus():
    executable = shutil.which("nvidia-smi")
    if not executable:
        return UNKNOWN
    output = run_command([
        executable, "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    gpus = []
    for row in csv.reader(output.splitlines()):
        if len(row) != 3:
            continue
        name, memory, driver = (value.strip() for value in row)
        gpus.append({
            "name": name or UNKNOWN,
            "vram_mib": positive_int(memory),
            "driver_version": driver or UNKNOWN,
        })
    return gpus or UNKNOWN


def collect_report():
    system = platform.system() or UNKNOWN
    machine = platform.machine() or UNKNOWN
    if system == "Darwin":
        cpu, ram, gpus = mac_hardware()
    elif system == "Windows":
        cpu, ram, gpus = windows_hardware()
    elif system == "Linux":
        cpu, ram, gpus = posix_hardware()
    else:
        cpu, ram, gpus = UNKNOWN, UNKNOWN, UNKNOWN

    nvidia = nvidia_gpus()
    apple_silicon = UNKNOWN
    if system == "Darwin":
        # Also recognize Apple CPUs when Python itself runs through Rosetta.
        if machine.lower() in ("arm64", "aarch64") or cpu.startswith("Apple "):
            apple_silicon = True
        elif "Intel" in cpu:
            apple_silicon = False
    return {
        "schema_version": 1,
        "os": {"system": system, "release": platform.release() or UNKNOWN, "architecture": machine},
        "cpu": cpu,
        "ram_bytes": ram,
        "gpu": {"devices": gpus, "nvidia": nvidia},
        "indications": {
            "apple_silicon": apple_silicon,
            "cuda_toolkit_on_path": shutil.which("nvcc") is not None,
            "nvidia_driver_responding": nvidia != UNKNOWN,
        },
        "tools": {"python_version": platform.python_version(), **{name: shutil.which(name) is not None for name in TOOLS}},
        "inference_validated": False,
    }


def main():
    json.dump(collect_report(), sys.stdout, indent=2, ensure_ascii=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
