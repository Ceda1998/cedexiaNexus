"""NX-001: read-only Windows inventory. Run with py -3 -m scripts.inventory_windows."""

import json
from pathlib import Path
import platform
import re
import shutil

from scripts import doctor

UNKNOWN = doctor.UNKNOWN
ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("git", "cmake", "ninja", "cl", "nvcc", "nvidia-smi", "wsl.exe")

# Only selected properties are converted to JSON. Adapter names and addresses,
# device IDs, serial numbers and WSL distribution names are not collected.
CIM_QUERY = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$data = @{}
try {
    $data.os = Get-CimInstance Win32_OperatingSystem -Property Caption,Version,BuildNumber,FreePhysicalMemory |
        Select-Object Caption,Version,BuildNumber,FreePhysicalMemory
} catch {}
try {
    $data.ubr = Get-ItemPropertyValue 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name UBR
} catch {}
try {
    $data.cpu = Get-CimInstance Win32_Processor -Property Name |
        Select-Object -First 1 -ExpandProperty Name
} catch {}
try {
    $data.ram_bytes = Get-CimInstance Win32_ComputerSystem -Property TotalPhysicalMemory |
        Select-Object -ExpandProperty TotalPhysicalMemory
} catch {}
try {
    $data.gpus = @(Get-CimInstance Win32_VideoController -Property Name,DriverVersion |
        Select-Object Name,DriverVersion)
} catch {}
try {
    $data.adapters = @(Get-CimInstance -Namespace 'root\StandardCimv2' -ClassName MSFT_NetAdapter -Filter 'HardwareInterface = TRUE' -Property NdisPhysicalMedium,InterfaceType,MediaConnectState,ReceiveLinkSpeed,TransmitLinkSpeed |
        Select-Object NdisPhysicalMedium,InterfaceType,MediaConnectState,ReceiveLinkSpeed,TransmitLinkSpeed)
} catch {}
try {
    $features = Get-CimInstance Win32_OptionalFeature -Filter "Name = 'Microsoft-Windows-Subsystem-Linux' OR Name = 'VirtualMachinePlatform'" -Property Name,InstallState
    foreach ($feature in $features) {
        if ($feature.Name -eq 'Microsoft-Windows-Subsystem-Linux') {
            $data.wsl = $feature.InstallState
        } elseif ($feature.Name -eq 'VirtualMachinePlatform') {
            $data.virtual_machine_platform = $feature.InstallState
        }
    }
} catch {}
$data | ConvertTo-Json -Depth 4 -Compress
"""


def nonnegative_int(value):
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        return int(value)
    return UNKNOWN


def label(value):
    if isinstance(value, str) and value.isprintable() and 0 < len(value.strip()) <= 160:
        return value.strip()
    return UNKNOWN


def version(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+){0,4}", value) else UNKNOWN


def object_rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def adapters(value):
    if not isinstance(value, list):
        return UNKNOWN
    result = []
    for row in object_rows(value):
        medium = nonnegative_int(row.get("NdisPhysicalMedium"))
        kind = {1: "wi-fi", 9: "wi-fi", 14: "ethernet"}.get(medium, UNKNOWN)
        if medium in (0, UNKNOWN):
            kind = {6: "ethernet", 71: "wi-fi"}.get(nonnegative_int(row.get("InterfaceType")), UNKNOWN)
        state = {1: "connected", 2: "disconnected"}.get(nonnegative_int(row.get("MediaConnectState")), UNKNOWN)
        result.append({
            "kind": kind, "link": state,
            "receive_link_bps": link_speed(row.get("ReceiveLinkSpeed"), state),
            "transmit_link_bps": link_speed(row.get("TransmitLinkSpeed"), state),
        })
    return result


def link_speed(value, state):
    speed = nonnegative_int(value)
    # A disconnected adapter's last-known rate is not a current link.
    return speed if state == "connected" and isinstance(speed, int) and 0 < speed < 2**64 - 1 else UNKNOWN


def hardware(data):
    os_info = data.get("os")
    if not isinstance(os_info, dict):
        os_info = {}
    ram = doctor.positive_int(data.get("ram_bytes"))
    free_kib = nonnegative_int(os_info.get("FreePhysicalMemory"))
    free = free_kib * 1024 if isinstance(free_kib, int) else UNKNOWN
    if isinstance(free, int) and isinstance(ram, int) and free > ram:
        free = UNKNOWN
    gpus = [
        {"name": name, "driver_version": version(row.get("DriverVersion"))}
        for row in object_rows(data.get("gpus")) if (name := label(row.get("Name"))) != UNKNOWN
    ]
    nvidia = [
        {"name": label(row["name"]), "driver_version": version(row["driver_version"]), "vram_mib": row["vram_mib"]}
        for row in object_rows(doctor.nvidia_gpus())
    ]
    return {
        "os": {
            "caption": label(os_info.get("Caption")),
            "version": version(os_info.get("Version")),
            "build": version(os_info.get("BuildNumber")),
            "update_build_revision": nonnegative_int(data.get("ubr")),
            "architecture": platform.machine() or UNKNOWN,
        },
        "cpu": label(data.get("cpu")),
        "ram_bytes": ram,
        "free_physical_ram_bytes": free,
        "gpu": {"cim_devices": gpus or UNKNOWN, "nvidia": nvidia or UNKNOWN},
        "network_adapters": adapters(data.get("adapters")),
    }


def collect_inventory():
    if platform.system() != "Windows":
        return {"schema_version": 1, "supported": False, "reason": "Windows required"}
    shell = shutil.which("powershell") or shutil.which("pwsh")
    data = doctor.read_json([shell, "-NoProfile", "-NonInteractive", "-Command", CIM_QUERY]) if shell else None
    if not isinstance(data, dict):
        data = {}
    try:
        disk = shutil.disk_usage(ROOT).free
    except OSError:
        disk = UNKNOWN
    paths = {tool: shutil.which(tool) for tool in TOOLS}
    nvcc = paths["nvcc"]
    cuda_output = doctor.run_command([nvcc, "--version"]) if nvcc else ""
    cuda = re.search(r"\brelease (\d+\.\d+)\b", cuda_output)
    features = {1: "enabled", 2: "disabled", 3: "absent"}
    return {
        "schema_version": 1,
        "supported": True,
        **hardware(data),
        "free_disk_bytes_on_repository_volume": disk,
        "tools_on_path": {tool: path is not None for tool, path in paths.items()},
        "cuda_toolkit_release": cuda[1] if cuda else UNKNOWN,
        "wsl": {
            "subsystem_feature": features.get(nonnegative_int(data.get("wsl")), UNKNOWN),
            "virtual_machine_platform": features.get(nonnegative_int(data.get("virtual_machine_platform")), UNKNOWN),
            "wsl2_validated": False,
        },
        "inference_validated": False,
    }


def main():
    report = collect_inventory()
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
