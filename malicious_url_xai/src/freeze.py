"""Checksum manifests that pin a released model version (results/<version>/freeze.json)."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FREEZE_TOOL_VERSION = "1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def freeze_path(version: str, root: Path = ROOT) -> Path:
    return root / "results" / version / "freeze.json"


def write_freeze(version: str, files, root: Path = ROOT, **meta) -> dict:
    """Hash files (paths relative to root) into results/<version>/freeze.json; never overwrites."""
    path = freeze_path(version, root)
    if path.exists():
        raise SystemExit(f"{path} exists: {version} is already frozen.")
    rels = sorted({Path(f).as_posix() for f in files})
    manifest = {
        "version": version,
        "frozen_at": datetime.now().isoformat(timespec="seconds"),
        "freeze_tool_version": FREEZE_TOOL_VERSION,
        **meta,
        "sha256": {rel: sha256_file(root / rel) for rel in rels},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def check_frozen(version: str, root: Path = ROOT) -> dict:
    """Stop with an error if any frozen file is missing or its bytes changed."""
    path = freeze_path(version, root)
    if not path.exists():
        raise SystemExit(f"{path} missing: {version} has not been frozen.")
    manifest = json.loads(path.read_text())
    for rel, digest in manifest["sha256"].items():
        target = root / rel
        if not target.exists():
            raise SystemExit(f"{rel} is missing since {version} was frozen.")
        if sha256_file(target) != digest:
            raise SystemExit(f"{rel} changed since {version} was frozen.")
    return manifest
