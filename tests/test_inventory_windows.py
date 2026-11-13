import json
import unittest
from unittest.mock import patch

from scripts import inventory_windows as inventory


class WindowsInventoryTests(unittest.TestCase):
    def test_reports_windows_profile_without_private_fields(self):
        cim = {
            "os": {"Caption": "Microsoft Windows 11 Pro", "Version": "10.0.26100",
                   "BuildNumber": "26100", "FreePhysicalMemory": "1048576", "CSName": "PRIVATE_HOST"},
            "ubr": 2345, "cpu": "AMD Ryzen 7 Example", "ram_bytes": 32 * 2**30,
            "gpus": [{"Name": "Example GPU", "DriverVersion": "32.0.15.7632", "PNPDeviceID": "PRIVATE_DEVICE"}],
            "adapters": [
                {"NdisPhysicalMedium": 14, "MediaConnectState": 1, "ReceiveLinkSpeed": "2500000000",
                 "TransmitLinkSpeed": 2500000000, "Name": "PRIVATE_ALIAS", "PermanentAddress": "PRIVATE_MAC"},
                {"NdisPhysicalMedium": 9, "MediaConnectState": 2, "ReceiveLinkSpeed": 1000000, "IP": "PRIVATE_IP"},
                {"NdisPhysicalMedium": 0, "InterfaceType": 6, "MediaConnectState": 1,
                 "ReceiveLinkSpeed": str(2**64 - 1)},
            ],
            "wsl": 1, "virtual_machine_platform": 2,
        }
        paths = {"powershell": "PRIVATE_SHELL_PATH", "nvcc": "PRIVATE_CUDA_PATH", "wsl.exe": "PRIVATE_WSL_PATH"}
        with (
            patch.object(inventory.platform, "system", return_value="Windows"),
            patch.object(inventory.shutil, "which", side_effect=paths.get),
            patch.object(inventory.shutil, "disk_usage") as disk,
            patch.object(inventory.doctor, "read_json", return_value=cim),
            patch.object(inventory.doctor, "nvidia_gpus", return_value=[
                {"name": "NVIDIA Example", "vram_mib": 16384, "driver_version": "576.32"},
            ]),
            patch.object(inventory.doctor, "run_command", return_value="CUDA compilation tools, release 12.9, V12.9.41") as run,
        ):
            disk.return_value.free = 20 * 2**30
            report = inventory.collect_inventory()
        run.assert_called_once_with(["PRIVATE_CUDA_PATH", "--version"])
        self.assertEqual(report["os"]["build"], "26100")
        self.assertEqual(report["os"]["update_build_revision"], 2345)
        self.assertEqual(report["free_physical_ram_bytes"], 2**30)
        self.assertEqual(report["free_disk_bytes_on_repository_volume"], 20 * 2**30)
        self.assertEqual(report["gpu"]["nvidia"][0]["vram_mib"], 16384)
        ethernet, wifi, fallback = report["network_adapters"]
        self.assertEqual((ethernet["kind"], ethernet["receive_link_bps"]), ("ethernet", 2500000000))
        self.assertEqual((wifi["link"], wifi["receive_link_bps"]), ("disconnected", "unknown"))
        self.assertEqual((fallback["kind"], fallback["receive_link_bps"]), ("ethernet", "unknown"))
        self.assertEqual(report["cuda_toolkit_release"], "12.9")
        self.assertEqual(report["wsl"]["subsystem_feature"], "enabled")
        self.assertEqual(report["wsl"]["virtual_machine_platform"], "disabled")
        self.assertFalse(report["wsl"]["wsl2_validated"])
        self.assertFalse(report["inference_validated"])
        self.assertNotIn("PRIVATE_", json.dumps(report))

    def test_failed_probes_leave_unknown_values(self):
        with (
            patch.object(inventory.platform, "system", return_value="Windows"),
            patch.object(inventory.shutil, "which", return_value="powershell"),
            patch.object(inventory.shutil, "disk_usage", side_effect=OSError("PRIVATE_PATH")),
            patch.object(inventory.doctor, "read_json", return_value=None),
            patch.object(inventory.doctor, "run_command", return_value="unknown"),
        ):
            report = inventory.collect_inventory()
        for field in ("cpu", "ram_bytes", "free_physical_ram_bytes", "network_adapters",
                      "cuda_toolkit_release", "free_disk_bytes_on_repository_volume"):
            self.assertEqual(report[field], "unknown")
        self.assertEqual(report["gpu"]["nvidia"], "unknown")
        self.assertEqual(report["wsl"]["subsystem_feature"], "unknown")

    def test_missing_powershell_does_not_prevent_local_disk_inventory(self):
        with (
            patch.object(inventory.platform, "system", return_value="Windows"),
            patch.object(inventory.shutil, "which", return_value=None),
            patch.object(inventory.shutil, "disk_usage") as disk,
            patch.object(inventory.doctor, "read_json") as cim,
        ):
            disk.return_value.free = 0
            report = inventory.collect_inventory()
        cim.assert_not_called()
        self.assertEqual(report["free_disk_bytes_on_repository_volume"], 0)
        self.assertFalse(report["tools_on_path"]["nvcc"])

    def test_non_windows_hosts_skip_probes(self):
        with patch.object(inventory.platform, "system", return_value="Darwin"):
            with patch.object(inventory.shutil, "which") as which:
                self.assertFalse(inventory.collect_inventory()["supported"])
        which.assert_not_called()
