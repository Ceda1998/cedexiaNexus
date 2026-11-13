import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from scripts import verify_model


class ModelVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private-model.gguf"
        self.data = b"GGUF" + b"test" * 300000  # More than one streaming chunk.
        self.path.write_bytes(self.data)
        self.manifest = {"artifact": {
            "size_bytes": len(self.data),
            "sha256": hashlib.sha256(self.data).hexdigest(),
        }}

    def test_matching_file_does_not_claim_inference(self):
        result = verify_model.verify(self.path, self.manifest)
        self.assertTrue(result["verified"])
        self.assertFalse(result["inference_validated"])

    def test_same_size_corruption_and_truncation_are_rejected(self):
        self.path.write_bytes(b"X" + self.data[1:])
        result = verify_model.verify(self.path, self.manifest)
        self.assertTrue(result["size_matches"])
        self.assertFalse(result["verified"])
        self.path.write_bytes(self.data[:-1])
        result = verify_model.verify(self.path, self.manifest)
        self.assertFalse(result["size_matches"])
        self.assertFalse(result["sha256_matches"])

    def test_cli_exit_status_and_private_path_redaction(self):
        manifest_path = self.path.with_suffix(".json")
        manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        for present, expected in ((True, 0), (False, 1)):
            if not present:
                self.path.unlink()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = verify_model.main([str(self.path), "--manifest", str(manifest_path)])
            self.assertEqual(status, expected)
            self.assertNotIn(str(self.path), output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["verified"], present)

    def test_invalid_manifest_and_directory_are_rejected(self):
        for artifact in ({"size_bytes": -1, "sha256": "0" * 64},
                         {"size_bytes": 1, "sha256": "invalid"}):
            with self.assertRaises(ValueError):
                verify_model.verify(self.path, {"artifact": artifact})
        with self.assertRaises(ValueError):
            verify_model.verify(Path(self.directory.name), self.manifest)

    def test_gguf_header_cli_checks_format_without_matching_manifest_size(self):
        header = struct.Struct("<4sIQQ")
        payload = bytes(128)
        cases = (
            (header.pack(b"GGUF", 3, 1, 1) + payload, None),
            (header.pack(b"GGUF", 2, 1, 1) + payload * 2, None),
            (header.pack(b"GGUF", 3, 1, 1), "truncated"),
            (b"GGUF", "truncated"),
            (header.pack(b"JSON", 3, 1, 1) + payload, "not_gguf"),
            (header.pack(b"GGUF", 1, 1, 1) + payload, "unsupported_version"),
            (header.pack(b"GGUF", 3, 0, 1) + payload, "no_tensors"),
        )
        for data, error in cases:
            with self.subTest(error=error, size=len(data)):
                self.path.write_bytes(data)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = verify_model.main([str(self.path), "--gguf"])
                self.assertEqual(status, int(error is not None))
                self.assertEqual(json.loads(output.getvalue()), {"header_ok": error is None, "error": error})
