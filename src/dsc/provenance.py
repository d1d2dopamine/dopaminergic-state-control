from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .util import sha256_file


def git_sha() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def make_manifest(snapshot_dir: str | Path, config_path: str | Path, dataset_name: str, counts: dict) -> dict:
    root = Path(snapshot_dir)
    inputs = {}
    for name in ("nodes.csv", "edges.csv"):
        path = root / name
        inputs[name] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "software_version": __version__,
        "git_sha": git_sha(),
        "dataset": dataset_name,
        "config": {"path": str(config_path), "sha256": sha256_file(config_path)},
        "inputs": inputs,
        "counts": counts,
    }
