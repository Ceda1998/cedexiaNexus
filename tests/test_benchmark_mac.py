import unittest

from scripts.benchmark_mac import BenchmarkError, parse_metrics


LOG = """
0.00.200.589 I llama_prepare_model_devices: using device MTL0 (Apple M5) (unknown id) - 25558 MiB free
0.01.771.655 I load_tensors: offloaded 65/65 layers to GPU
0.02.400.352 I generate: n_ctx = 4096, n_batch = 128, n_predict = 64, n_keep = 0
0.13.400.352 I common_perf_print:    samplers time =       0.24 ms /   136 tokens
0.13.400.352 I common_perf_print:        load time =    2200.00 ms
0.13.400.353 I common_perf_print: prompt eval time =     720.00 ms /    72 tokens (   10.00 ms per token,   100.00 tokens per second)
0.13.400.354 I common_perf_print:        eval time =   10500.00 ms /    63 runs   (  166.67 ms per token,     6.00 tokens per second)
0.13.400.392 I common_memory_breakdown_print: |   - MTL0 (Apple M5)    | 25559 = 6811 + (18746 = 17812 +     405 +     529) +           0 |
         19740753920  maximum resident set size
                   0  swaps
"""


class BenchmarkMetricsTests(unittest.TestCase):
    def test_runtime_counters_distinguish_output_tokens_and_decode_steps(self):
        result = parse_metrics(LOG + "\nignored diagnostic: /Users/private/model\n")
        self.assertEqual(result["input_tokens"], 72)
        self.assertEqual(result["output_tokens"], 64)
        self.assertEqual(result["decode_steps"], 63)
        self.assertEqual(result["prefill_tok_s"], 100.0)
        self.assertEqual(result["decode_tok_s"], 6.0)
        self.assertEqual(result["peak_rss_bytes"], 19740753920)
        self.assertEqual(result["metal_reported_mib"], 18746)
        self.assertNotIn("/Users", str(result))

    def test_rejects_incomplete_run_or_unverified_gpu_offload(self):
        for old, new in (("136 tokens", "135 tokens"), ("65/65", "64/65"),
                         ("n_ctx = 4096", "n_ctx = 1024"), ("maximum resident set size", "")):
            with self.subTest(counter=old), self.assertRaises(BenchmarkError):
                parse_metrics(LOG.replace(old, new))

    def test_rejects_ambiguous_measurements(self):
        with self.assertRaises(BenchmarkError):
            parse_metrics(LOG + LOG)
