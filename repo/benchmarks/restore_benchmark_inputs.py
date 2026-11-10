"""Check frozen FITS inputs; optionally restore missing files from their MAST URIs."""
import argparse
from pathlib import Path
import shutil
from vstar.io import read_json, sha256
from vstar.network import ArchiveClient


def records(value):
    if isinstance(value, dict):
        if all(k in value for k in ["path", "uri", "sha256"]) and value["path"].endswith(".fits"):
            yield value
        for child in value.values():
            yield from records(child)
    elif isinstance(value, list):
        for child in value:
            yield from records(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-missing", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifests = [root/"repo/benchmarks/source-9473243-v01/input-manifest.json", root/"repo/benchmarks/mixed-v01/input-manifest.json"]
    inputs = {}
    for manifest in manifests:
        for item in records(read_json(manifest)):
            if item["path"] in inputs and inputs[item["path"]]["sha256"] != item["sha256"]:
                raise ValueError(f"Conflicting expected checksum: {item['path']}")
            inputs[item["path"]] = item
    client = ArchiveClient(root/"repo/data/restore-downloads", offline=not args.download_missing)
    for item in inputs.values():
        path = root/item["path"]
        if not path.exists():
            if not args.download_missing:
                raise FileNotFoundError(f"Missing {item['path']}; use --download-missing to restore")
            downloaded, digest = client.download(item["uri"])
            if digest != item["sha256"]:
                raise ValueError(f"Archive returned different bytes: {item['uri']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix+".restore")
            shutil.copyfile(downloaded, temporary)
            temporary.replace(path)
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Modified existing input (not overwritten): {item['path']}")
    print(f"Verified {len(inputs)} FITS files against frozen manifests")


if __name__ == "__main__":
    main()
