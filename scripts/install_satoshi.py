"""Import unmodified OTFs from an individually downloaded Fontshare ZIP."""
import argparse
from pathlib import Path
import zipfile


def install(archive):
    target = Path(__file__).resolve().parents[1] / "nexus_ui/assets/fonts"
    with zipfile.ZipFile(archive) as source:
        # Exact allowlist; never extract arbitrary archive paths.
        fonts = {f"Satoshi-{weight}.otf": source.read(
            f"Satoshi_Complete/Fonts/OTF/Satoshi-{weight}.otf")
            for weight in ("Regular", "Medium", "Bold")}
        if any(len(data) > 2_000_000 or not data.startswith(b"OTTO")
               for data in fonts.values()):
            raise ValueError("Unexpected OTF format or size")
    target.mkdir(parents=True, exist_ok=True)
    for name, data in fonts.items():
        (target / name).write_bytes(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    install(args.archive)
    print("Satoshi Regular/Medium/Bold installed locally; files remain ignored by Git.")
