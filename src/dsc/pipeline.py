from __future__ import annotations

from pathlib import Path

from .discovery import discover
from .io import load_config, load_snapshot, write_json
from .provenance import make_manifest
from .site import build_site


def run_pipeline(snapshot: str | Path, config_path: str | Path, output: str | Path, site_template: str | Path) -> dict:
    config = load_config(config_path)
    nodes, edges = load_snapshot(snapshot)
    result = discover(nodes, edges, config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result.features.to_csv(output / "features.csv", index=False)
    write_json(output / "findings.json", result.findings)
    manifest = make_manifest(
        snapshot,
        config_path,
        config["dataset"]["name"],
        {
            "snapshot_nodes": int(len(nodes)),
            "snapshot_edges": int(len(edges)),
            "dopamine_core_nodes": int(len(result.core_ids)),
            "candidate_findings": int(len(result.findings)),
        },
    )
    write_json(output / "run_manifest.json", manifest)
    build_site(site_template, output / "site", nodes, edges, result.findings, result.features, result.core_ids, manifest)
    return manifest
