"""NX-004: verify an explicitly supplied local file; never download weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "config/model-manifest.json"
GGUF_HEADER = struct.Struct("<4sIQQ")
SPLIT_NAME = re.compile(r"(.+)-(\d{5})-of-(\d{5})\.gguf", re.IGNORECASE)
GGUF_SCALAR_SIZES = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


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


def read_metadata(stream, size, fields, *, stop_when_found=False):
    """Read selected GGUF scalar fields without loading tensors or tokenizer arrays."""
    def read(fmt):
        length = struct.calcsize(fmt)
        data = stream.read(length)
        if len(data) != length:
            raise ValueError("truncated GGUF metadata")
        return struct.unpack(fmt, data)

    def skip(length):
        if stream.tell() + length > size:
            raise ValueError("truncated GGUF metadata")
        stream.seek(length, os.SEEK_CUR)

    def skip_values(kind, count):
        if kind == 8:
            if count > (size - stream.tell()) // 8:
                raise ValueError("truncated GGUF string array")
            for _ in range(count):
                skip(read("<Q")[0])
        elif kind in GGUF_SCALAR_SIZES:
            skip(GGUF_SCALAR_SIZES[kind] * count)
        else:
            raise ValueError("unknown GGUF value type")

    _, _, _, count = read("<4sIQQ")
    values = {}
    for _ in range(count):
        key_length, = read("<Q")
        if not 0 < key_length <= 65535:
            raise ValueError("invalid GGUF key")
        key = stream.read(key_length)
        kind, = read("<I")
        if key in fields:
            if kind != fields[key] or key in values:
                raise ValueError("invalid GGUF metadata field")
            if kind == 8:
                length, = read("<Q")
                if length > min(262144, size - stream.tell()):
                    raise ValueError("invalid GGUF metadata text")
                values[key] = stream.read(length)
            else:
                values[key], = read("<H")
            if stop_when_found and len(values) == len(fields):
                break
        elif kind == 9:
            element_kind, elements = read("<IQ")
            skip_values(element_kind, elements)
        else:
            skip_values(kind, 1)
    return values


def split_metadata(stream, size):
    fields = read_metadata(stream, size, {b"split.no": 2, b"split.count": 2})
    return fields.get(b"split.no", 0), fields.get(b"split.count", 1)


def completion_prefills_thinking(path):
    """Recognize Qwen's default generation prefix in the GGUF chat template."""
    try:
        with path.open("rb") as stream:
            fields = read_metadata(stream, os.fstat(stream.fileno()).st_size,
                                   {b"general.architecture": 8, b"tokenizer.chat_template": 8},
                                   stop_when_found=True)
    except (OSError, ValueError):
        return False
    template = fields.get(b"tokenizer.chat_template", b"")
    generation = template.rpartition(b"if add_generation_prompt")[2]
    return (fields.get(b"general.architecture") in (b"qwen35", b"qwen35moe")
            and b"<|im_start|>assistant" in generation
            and re.search(rb"""['"]<think>\\n['"]""", generation) is not None)


def fingerprint_gguf(path):
    """Fingerprint a single GGUF or the ordered parts of a conventionally named split GGUF."""
    if match := SPLIT_NAME.fullmatch(path.name):
        prefix, first, total = match.groups()
        count = int(total)
        if first != "00001" or not 2 <= count <= 999:
            raise ValueError("first split part required")
        paths = [path, *(path.with_name(f"{prefix}-{index:05d}-of-{total}{path.suffix}")
                         for index in range(2, count + 1))]
    else:
        paths = [path]
    size = 0
    hashes = []
    for index, part in enumerate(paths):
        if inspect_gguf(part) is not None:
            raise ValueError("invalid or missing GGUF part")
        with part.open("rb") as stream:
            before = os.fstat(stream.fileno())
            part_index, count = split_metadata(stream, before.st_size)
            if (part_index, max(count, 1)) != (index, len(paths)):
                raise ValueError("GGUF parts do not match their metadata")
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").digest()
        after = part.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("GGUF changed during verification")
        size += before.st_size
        hashes.append(digest)
    digest = (hashes[0] if len(hashes) == 1 else
              hashlib.sha256(b"Nexus split GGUF v1\x00" + b"".join(hashes)).digest())
    return {"sha256": digest.hex(), "size": size, "parts": len(paths)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--gguf", action="store_true", help="check the GGUF header without matching a pinned artifact")
    mode.add_argument("--fingerprint-gguf", action="store_true", help="hash a GGUF and its conventionally named parts")
    parser.add_argument("--chat-format", action="store_true", help="include chat template information with --gguf")
    args = parser.parse_args(argv)
    try:
        if args.fingerprint_gguf:
            result = fingerprint_gguf(args.model)
        elif args.gguf:
            error = inspect_gguf(args.model)
            result = {"header_ok": error is None, "error": error}
            if args.chat_format and error is None:
                result["thinking_prefilled"] = completion_prefills_thinking(args.model)
        else:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            result = verify(args.model, manifest)
    except (OSError, ValueError, KeyError, TypeError):
        # Do not disclose user paths, filenames or raw OS errors in reports.
        if args.fingerprint_gguf:
            result = {"error": "gguf_invalid_or_unreadable"}
        elif args.gguf:
            result = {"header_ok": False, "error": "missing_or_unreadable"}
        else:
            result = {"verified": False, "error": "model_or_manifest_invalid_or_unreadable"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("header_ok", result.get("verified", "sha256" in result)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
