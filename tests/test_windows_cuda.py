import unittest

from scripts.windows_cuda import SmokeError, cuda_devices, smoke_evidence


TIMINGS = """
common_perf_print: prompt eval time = 123.45 ms / 58 tokens (2.13 ms per token)
common_perf_print:    samplers time = 0.25 ms / 66 tokens
"""
CUDA_PLACEMENT = """
llama_prepare_model_devices: using device CUDA0 (NVIDIA GeForce RTX 5070 Ti) (unknown id) - 14712 MiB free
load_tensors: offloaded 32/65 layers to GPU
"""


class WindowsCudaTests(unittest.TestCase):
    def test_device_list_keeps_only_cuda_entries(self):
        output = ("Available devices:\n"
                  "  CUDA0: NVIDIA GeForce RTX 5070 Ti (16303 MiB, 14712 MiB free)\n"
                  "  OTHER0: Other adapter (1024 MiB, 512 MiB free)\n")
        self.assertEqual(cuda_devices(output), [
            {"id": "CUDA0", "name": "NVIDIA GeForce RTX 5070 Ti", "vram_mib": 16303, "free_vram_mib": 14712}
        ])

    def test_cuda_and_cpu_distinguish_discovery_from_offload(self):
        gpu = smoke_evidence("4, 5, 6,", TIMINGS + CUDA_PLACEMENT, "CUDA0", 32)
        cpu = smoke_evidence("4, 5, 6,", TIMINGS + "Device 0: NVIDIA GeForce RTX 5070 Ti\n"
                             "load_tensors: offloaded 0/65 layers to GPU\n", "none", 0)
        self.assertEqual((gpu["device"], gpu["layers_offloaded"], gpu["generated_tokens"]), ("CUDA0", 32, 8))
        self.assertEqual((cpu["device"], cpu["layers_offloaded"]), ("CPU", 0))

    def test_rejects_wrong_placement_or_incomplete_generation(self):
        for log in (TIMINGS, TIMINGS + CUDA_PLACEMENT.replace("CUDA0", "CUDA1"),
                    TIMINGS.replace("66 tokens", "65 tokens") + CUDA_PLACEMENT):
            with self.subTest(log=log), self.assertRaises(SmokeError):
                smoke_evidence("4, 5, 6,", log, "CUDA0", 32)
        with self.assertRaises(SmokeError):
            smoke_evidence("   ", TIMINGS + CUDA_PLACEMENT, "CUDA0", 32)
