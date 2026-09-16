from __future__ import annotations

import copy
from pathlib import Path

from .discovery import discover
from .io import load_config, load_snapshot, load_snapshot_meta, write_json
from .provenance import make_manifest
from .site import build_site


def run_pipeline(
    snapshot: str | Path,
    config_path: str | Path,
    output: str | Path,
    site_template: str | Path,
    min_synapses_override: int | None = None,
) -> dict:
    config = copy.deepcopy(load_config(config_path))
    if min_synapses_override is not None:
        config.setdefault("dataset", {})["min_synapses"] = int(min_synapses_override)
    nodes, edges = load_snapshot(snapshot)
    snapshot_meta = load_snapshot_meta(snapshot)
    result = discover(nodes, edges, config, snapshot_meta)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result.features.to_csv(output / "features.csv", index=False)
    write_json(output / "findings.json", result.findings)
    review_queue = [f for f in result.findings if f.get("status") in {"survived_controls", "survived_thresholds"}]
    write_json(output / "review_queue.json", review_queue)
    manifest = make_manifest(
        snapshot,
        config_path,
        config["dataset"]["name"],
        {
            "snapshot_nodes": int(len(nodes)),
            "snapshot_edges": int(len(edges)),
            "dopamine_core_nodes": int(len(result.core_ids)),
            "candidate_findings": int(len(result.findings)),
            "survived_controls": int(sum(f.get("status") == "survived_controls" for f in result.findings)),
            "survived_thresholds": int(sum(f.get("status") == "survived_thresholds" for f in result.findings)),
            "threshold_sensitive": int(sum(f.get("status") == "threshold_sensitive" for f in result.findings)),
            "global_only": int(sum(f.get("status") == "global_only" for f in result.findings)),
            "review_queue": int(len(review_queue)),
        },
    )
    manifest["snapshot_meta"] = snapshot_meta
    manifest["effective_analysis"] = {
        "min_synapses": int(config["dataset"].get("min_synapses", 1)),
        "robustness_thresholds": [int(x) for x in config.get("discovery", {}).get("robustness_thresholds", [])],
        "anatomical_null": "source outputRois intersect target inputRois when source metadata are available",
    }
    write_json(output / "run_manifest.json", manifest)
    build_site(site_template, output / "site", nodes, edges, result.findings, result.features, result.core_ids, manifest)
    return manifest
