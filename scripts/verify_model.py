"""NX-004: verify an explicitly supplied local file; never download weights."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/model-manifest.json"
GGUF_HEADER = struct.Struct("<4sIQQ")


def inspect_gguf(path):
    """Check a local GGUF header. llama.cpp validates the rest when loading."""
    path = Path(path)
    if path.suffix.lower() != ".gguf":
        return "not_gguf"
    if not path.is_file():
        return "missing_or_unreadable"
    with path.open("rb") as stream:
        header = stream.read(GGUF_HEADER.size)
    if len(header) != GGUF_HEADER.size:
        return "truncated"
    magic, version, tensors, metadata = GGUF_HEADER.unpack(header)
    if magic != b"GGUF":
        return "not_gguf"
    if version not in (2, 3):
        return "unsupported_version"
    if not tensors:
        return "no_tensors"
    # Even without strings, dimensions or payload, each descriptor needs
    # a name length, dimension count, type and offset.
    if path.stat().st_size <= GGUF_HEADER.size + 24 * tensors + 12 * metadata:
        return "truncated"
    return None


def verify(path, manifest):
    """Stream the file once, checking size and digest on the same byte stream."""
    artifact = manifest["artifact"]
    size = artifact["size_bytes"]
    digest = artifact["sha256"]
    if type(size) is not int or size <= 0 or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid artifact metadata")
    if not Path(path).is_file():
        raise ValueError("regular model file required")
    actual_size = 0
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            actual_size += len(chunk)
            hasher.update(chunk)
    actual_digest = hasher.hexdigest()
    return {
        "verified": actual_size == size and actual_digest == digest,
        "size_matches": actual_size == size,
        "sha256_matches": actual_digest == digest,
        "actual_size_bytes": actual_size,
        "actual_sha256": actual_digest,
        "inference_validated": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--gguf", action="store_true", help="check the GGUF header without matching a pinned artifact")
    args = parser.parse_args(argv)
    try:
        if args.gguf:
            error = inspect_gguf(args.model)
            result = {"header_ok": error is None, "error": error}
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = verify(args.model, manifest)
    except (OSError, ValueError, KeyError, TypeError):
        # Do not disclose user paths, filenames or raw OS errors in reports.
        if args.gguf:
            result = {"header_ok": False, "error": "missing_or_unreadable"}
        else:
            result = {"verified": False, "error": "model_or_manifest_invalid_or_unreadable"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("header_ok", result.get("verified")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
