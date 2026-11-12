import unittest
from unittest.mock import patch

from scripts import inventory_mac


class InventoryTests(unittest.TestCase):
    def test_unused_pages_are_not_available_memory(self):
        output = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free:  10.\nPages inactive: 999."
        self.assertEqual(inventory_mac.free_memory_bytes(output), 163840)
        self.assertEqual(inventory_mac.free_memory_bytes(output.replace("10.", "0.")), 0)
        self.assertEqual(inventory_mac.free_memory_bytes("unknown"), "unknown")

    def test_network_output_omits_identifiers_and_unknown_labels(self):
        output = "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: PRIVATE_MAC\nHardware Port: PRIVATE_LABEL\nDevice: en9\nIP: PRIVATE_IP"
        self.assertEqual(inventory_mac.network_adapters(output), [
            {"interface": "en0", "kind": "wi-fi"},
            {"interface": "en9", "kind": "unknown"},
        ])
        self.assertEqual(inventory_mac.network_adapters("unknown"), "unknown")

    def test_other_platform_never_runs_mac_commands(self):
        with patch.object(inventory_mac.platform, "system", return_value="Windows"), patch.object(inventory_mac.doctor, "run_command") as run:
            self.assertFalse(inventory_mac.collect_inventory()["supported"])
            run.assert_not_called()

    def test_failed_probes_and_disk_are_unknown(self):
        with patch.object(inventory_mac.platform, "system", return_value="Darwin"), patch.object(inventory_mac.doctor, "collect_report", return_value={}), patch.object(inventory_mac.doctor, "run_command", return_value="unknown"), patch.object(inventory_mac.shutil, "disk_usage", side_effect=OSError):
            report = inventory_mac.collect_inventory()["inventory"]
        self.assertEqual(report["unused_ram_bytes"], "unknown")
        self.assertEqual(report["free_disk_bytes_on_repository_volume"], "unknown")
        self.assertFalse(report["metal_compiler_found"])
