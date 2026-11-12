"""NX-004: verify an explicitly supplied local file; never download weights."""
import argparse
import hashlib
import json
from pathlib import Path
import re

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/model-manifest.json"


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
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        result = verify(args.model, manifest)
    except (OSError, ValueError, KeyError, TypeError):
        # Do not disclose user paths, filenames or raw OS errors in reports.
        result = {"verified": False, "error": "model_or_manifest_invalid_or_unreadable"}
    print(json.dumps(result, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
