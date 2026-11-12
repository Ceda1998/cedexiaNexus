"""Deterministic probe tests; no actual GPU, shell or network is required."""

import io
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts import doctor


class CommandTests(unittest.TestCase):
    def test_missing_failed_and_timed_out_commands_are_unknown(self):
        cases = [
            FileNotFoundError("private path"),
            PermissionError("private path"),
            subprocess.TimeoutExpired("probe", 10),
            subprocess.CompletedProcess([], 1, "private stdout", "private stderr"),
            subprocess.CompletedProcess([], 0, "", "private stderr"),
        ]
        for case in cases:
            with self.subTest(case=type(case).__name__):
                with patch.object(doctor.subprocess, "run") as run:
                    if isinstance(case, Exception):
                        run.side_effect = case
                    else:
                        run.return_value = case
                    self.assertEqual(doctor.run_command(["probe"]), "unknown")

    def test_probe_uses_argument_list_and_timeout_without_shell(self):
        with patch.object(doctor.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "  value\n")) as run:
            self.assertEqual(doctor.run_command(["probe", "argument"]), "value")
        args, kwargs = run.call_args
        self.assertEqual(args[0], ["probe", "argument"])
        self.assertEqual(kwargs["timeout"], 10)
        self.assertFalse(kwargs.get("shell", False))

    def test_invalid_json_is_ignored(self):
        for value in ("unknown", "", "{broken"):
            with self.subTest(value=value), patch.object(doctor, "run_command", return_value=value):
                self.assertIsNone(doctor.read_json(["probe"]))

    def test_invalid_ram_is_never_reported_as_measured(self):
        for value in (None, "unknown", "", "1.5", -1, 0, True):
            with self.subTest(value=value):
                self.assertEqual(doctor.positive_int(value), "unknown")
        self.assertEqual(doctor.positive_int("34359738368"), 34359738368)


class HardwareTests(unittest.TestCase):
    def test_mac_selects_gpu_fields_without_serials(self):
        raw = {"SPDisplaysDataType": [{
            "sppci_model": "Apple Test", "spdisplays_metal": "Metal 4",
            "serial_number": "PRIVATE_SERIAL", "hostname": "PRIVATE_HOST",
        }]}
        with patch.object(doctor, "run_command", side_effect=["Apple Test", "34359738368"]), patch.object(doctor, "read_json", return_value=raw):
            cpu, ram, gpus = doctor.mac_hardware()
        self.assertEqual((cpu, ram), ("Apple Test", 34359738368))
        self.assertEqual(gpus, [{"name": "Apple Test", "metal_indication": "Metal 4"}])
        self.assertNotIn("PRIVATE", json.dumps(gpus))

    def test_mac_probe_failures_and_unexpected_json_are_unknown(self):
        for data in (None, [], {"SPDisplaysDataType": None}, {"SPDisplaysDataType": [None]}):
            with self.subTest(data=data), patch.object(doctor, "run_command", return_value="unknown"), patch.object(doctor, "read_json", return_value=data):
                self.assertEqual(doctor.mac_hardware(), ("unknown", "unknown", "unknown"))

    def test_mac_gpu_family_field_is_recognized(self):
        raw = {"SPDisplaysDataType": [{"sppci_model": "Apple Test", "spdisplays_mtlgpufamilysupport": "spdisplays_metal4"}]}
        with patch.object(doctor, "run_command", return_value="unknown"), patch.object(doctor, "read_json", return_value=raw):
            self.assertEqual(doctor.mac_hardware()[2][0]["metal_indication"], "spdisplays_metal4")

    def test_windows_cim_values_and_utf8_bom(self):
        data = {"cpu": "AMD Test", "ram_bytes": 34359738368, "gpu_names": ["NVIDIA Test"], "Name": "PRIVATE_HOST"}
        with patch.object(doctor.shutil, "which", return_value="powershell"), patch.object(doctor, "run_command", return_value="\ufeff" + json.dumps(data)):
            cpu, ram, gpus = doctor.windows_hardware()
        self.assertEqual((cpu, ram), ("AMD Test", 34359738368))
        self.assertEqual(gpus, [{"name": "NVIDIA Test"}])
        self.assertNotIn("PRIVATE_HOST", json.dumps((cpu, ram, gpus)))

    def test_windows_missing_powershell_and_cim_failures(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            self.assertEqual(doctor.windows_hardware(), ("unknown", "unknown", "unknown"))
        for data in (None, [], {}):
            with self.subTest(data=data), patch.object(doctor.shutil, "which", return_value="pwsh"), patch.object(doctor, "read_json", return_value=data):
                self.assertEqual(doctor.windows_hardware(), ("unknown", "unknown", "unknown"))

    def test_linux_ram_uses_physical_pages(self):
        with patch.object(doctor.os, "sysconf", side_effect=[8388608, 4096]), patch.object(doctor.platform, "processor", return_value=""):
            self.assertEqual(doctor.posix_hardware(), ("unknown", 34359738368, "unknown"))

    def test_linux_ram_failure_is_unknown(self):
        for result in (ValueError("unsupported"), -1):
            with self.subTest(result=result), patch.object(doctor.os, "sysconf") as sysconf:
                if isinstance(result, Exception):
                    sysconf.side_effect = result
                else:
                    sysconf.return_value = result
                self.assertEqual(doctor.posix_hardware()[1], "unknown")

    def test_nvidia_csv_multiple_gpus_and_unknown_memory(self):
        with patch.object(doctor.shutil, "which", return_value="nvidia-smi"), patch.object(doctor, "run_command", return_value="NVIDIA A, 16384, 999.0\nNVIDIA B, [N/A], 999.0"):
            gpus = doctor.nvidia_gpus()
        self.assertEqual(gpus[0], {"name": "NVIDIA A", "vram_mib": 16384, "driver_version": "999.0"})
        self.assertEqual(gpus[1]["vram_mib"], "unknown")

    def test_nvidia_missing_or_broken_is_unknown(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            self.assertEqual(doctor.nvidia_gpus(), "unknown")
        with patch.object(doctor.shutil, "which", return_value="nvidia-smi"), patch.object(doctor, "run_command", return_value="unknown"):
            self.assertEqual(doctor.nvidia_gpus(), "unknown")


class ReportTests(unittest.TestCase):
    def test_platform_dispatch_and_no_inference_claim(self):
        for system, probe in (("Darwin", "mac_hardware"), ("Windows", "windows_hardware"), ("Linux", "posix_hardware")):
            with self.subTest(system=system), patch.object(doctor.platform, "system", return_value=system), patch.object(doctor.platform, "machine", return_value="arm64"), patch.object(doctor, probe, return_value=("Test CPU", 1024, "unknown")) as hardware, patch.object(doctor, "nvidia_gpus", return_value="unknown"), patch.object(doctor.shutil, "which", return_value=None):
                report = doctor.collect_report()
            hardware.assert_called_once_with()
            self.assertEqual(report["ram_bytes"], 1024)
            self.assertFalse(report["inference_validated"])
            self.assertFalse(report["tools"]["git"])
            self.assertEqual(report["indications"]["apple_silicon"], True if system == "Darwin" else "unknown")

    def test_unknown_platform_does_not_invent_hardware(self):
        with patch.object(doctor.platform, "system", return_value="OtherOS"), patch.object(doctor, "nvidia_gpus", return_value="unknown"), patch.object(doctor.shutil, "which", return_value=None):
            report = doctor.collect_report()
        self.assertEqual(report["cpu"], "unknown")
        self.assertEqual(report["ram_bytes"], "unknown")

    def test_apple_silicon_under_rosetta_and_missing_cpu(self):
        for cpu, expected in (("Apple Test", True), ("Intel(R) Test", False), ("unknown", "unknown")):
            with self.subTest(cpu=cpu), patch.object(doctor.platform, "system", return_value="Darwin"), patch.object(doctor.platform, "machine", return_value="x86_64"), patch.object(doctor, "mac_hardware", return_value=(cpu, "unknown", "unknown")), patch.object(doctor, "nvidia_gpus", return_value="unknown"), patch.object(doctor.shutil, "which", return_value=None):
                self.assertEqual(doctor.collect_report()["indications"]["apple_silicon"], expected)

    def test_cli_emits_only_json(self):
        with patch.object(doctor, "collect_report", return_value={"cpu": "unknown"}), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(doctor.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), {"cpu": "unknown"})


if __name__ == "__main__":
    unittest.main()
