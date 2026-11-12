"""NX-002: selected local inventory fields, never raw profiler/network output.

Run from the repository root: python3 -m scripts.inventory_mac
"""
import json
import platform
import re
import shutil

from scripts import doctor


def free_memory_bytes(output):
    """Report unused pages only, not reclaimable/available application capacity."""
    page = re.search(r"page size of (\d+) bytes", output)
    free = re.search(r"^Pages free:\s+(\d+)\.", output, re.MULTILINE)
    if not page or not free or int(page[1]) <= 0:
        return doctor.UNKNOWN
    return int(page[1]) * int(free[1])


def network_adapters(output):
    """Allow only OS interface IDs and fixed hardware categories; omit addresses."""
    result = []
    category = doctor.UNKNOWN
    for line in output.splitlines():
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip().lower()
            category = next((name for name in ("wi-fi", "ethernet", "thunderbolt")
                             if name in port), doctor.UNKNOWN)
        elif re.fullmatch(r"Device: (?:en|bridge|bond)\d+", line):
            result.append({"interface": line.split(": ", 1)[1], "kind": category})
    return result or doctor.UNKNOWN


def collect_inventory():
    if platform.system() != "Darwin":
        return {"supported": False, "reason": "macOS required"}
    report = doctor.collect_report()
    probe = doctor.run_command
    try:
        disk_free = shutil.disk_usage(".").free
    except OSError:
        disk_free = doctor.UNKNOWN
    report["inventory"] = {
        "model_identifier": probe(["/usr/sbin/sysctl", "-n", "hw.model"]),
        "macos_version": probe(["/usr/bin/sw_vers", "-productVersion"]),
        "macos_build": probe(["/usr/bin/sw_vers", "-buildVersion"]),
        "unused_ram_bytes": free_memory_bytes(probe(["/usr/bin/vm_stat"])),
        "free_disk_bytes_on_repository_volume": disk_free,
        "network_adapters": network_adapters(probe(["/usr/sbin/networksetup", "-listallhardwareports"])),
        "macos_sdk_version": probe(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"]),
        "metal_compiler_found": probe(["/usr/bin/xcrun", "--find", "metal"]) != doctor.UNKNOWN,
    }
    return report


if __name__ == "__main__":
    print(json.dumps(collect_inventory(), indent=2))
