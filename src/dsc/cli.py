from __future__ import annotations

import argparse
import json

from .geometry import build_geometry_manifest
from .malecns import build_dopamine_snapshot
from .pipeline import run_pipeline
from .synapses import build_synapse_site_manifest
from .state_model import run_scenario_file


def main() -> None:
    parser = argparse.ArgumentParser(prog="dsc", description="Dopaminergic State Control discovery engine")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run discovery and build the static research site")
    run.add_argument("--snapshot", required=True)
    run.add_argument("--config", default="configs/discovery.yml")
    run.add_argument("--output", default="results/current")
    run.add_argument("--site-template", default="site")
    run.add_argument("--min-synapses", type=int, help="Override dataset.min_synapses for this analysis run")

    fetch = sub.add_parser("fetch-malecns", help="Build a one-hop dopamine snapshot from official MaleCNS v1.0 flat files")
    fetch.add_argument("--raw-dir", default="data/raw/male-cns-v1.0")
    fetch.add_argument("--output", default="data/derived/male-cns-v1.0-dopamine")
    fetch.add_argument("--min-synapses", type=int, default=3, help="Primary analysis threshold used for whole-connectome controls")
    fetch.add_argument("--snapshot-floor", type=int, default=1, help="Lowest edge weight retained so robustness tests can re-threshold without re-downloading")
    fetch.add_argument("--include-nontraced", action="store_true")
    fetch.add_argument("--refresh", action="store_true")
    fetch.add_argument("--roi-cache", help="Optional .json.gz cache for compact neuPrint inputRois/outputRois metadata")

    geometry = sub.add_parser("geometry-manifest", help="Build/vend official MaleCNS shell/ROI geometry and selected skeletons")
    geometry.add_argument("--output", required=True)
    geometry.add_argument("--vendor-dir")
    geometry.add_argument("--findings")
    geometry.add_argument("--max-vendored-skeletons", type=int, default=128)
    geometry.add_argument("--region-lod-divisions", type=int, default=20)
    geometry.add_argument("--shell-lod-divisions", type=int, default=46)
    geometry.add_argument("--source-cache-dir")

    syn = sub.add_parser("synapse-sites", help="Best-effort fetch of real synapse positions for direct-connectivity findings")
    syn.add_argument("--findings", required=True)
    syn.add_argument("--output", required=True)
    syn.add_argument("--max-sources", type=int, default=24)
    syn.add_argument("--max-points", type=int, default=4000)
    syn.add_argument("--spatial-permutations", type=int, default=400)

    sim = sub.add_parser("pam04-simulate", help="Reproduce a committed Experiment 001 State Lab scenario")
    sim.add_argument("--experiment", required=True, help="Generated experiment_001_pam04.json")
    sim.add_argument("--scenario", required=True, help="Scenario JSON exported from State Lab or written by hand")
    sim.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "run":
        manifest = run_pipeline(args.snapshot, args.config, args.output, args.site_template, min_synapses_override=args.min_synapses)
        print(json.dumps(manifest, indent=2))
    elif args.command == "fetch-malecns":
        lock = build_dopamine_snapshot(
            args.raw_dir,
            args.output,
            min_synapses=args.min_synapses,
            traced_only=not args.include_nontraced,
            refresh=args.refresh,
            snapshot_floor=args.snapshot_floor,
            roi_cache=args.roi_cache,
        )
        print(json.dumps(lock["selection"], indent=2))
    elif args.command == "geometry-manifest":
        payload = build_geometry_manifest(
            args.output,
            vendor_dir=args.vendor_dir,
            findings_path=args.findings,
            max_vendored_skeletons=args.max_vendored_skeletons,
            region_lod_divisions=args.region_lod_divisions,
            shell_lod_divisions=args.shell_lod_divisions,
            source_cache_dir=args.source_cache_dir,
        )
        print(json.dumps({
            "geometry_mode": payload.get("geometry_mode"),
            "regions": len(payload.get("regions", [])),
            "vendored_skeletons": len(payload.get("vendored_skeleton_ids", [])),
            "dataset": payload["dataset"],
            "source_triangles": payload.get("region_lod", {}).get("source_triangles_total", 0),
            "display_triangles": payload.get("region_lod", {}).get("display_triangles_total", 0),
            "display_bytes": payload.get("region_lod", {}).get("display_bytes_total", 0),
        }, indent=2))
    elif args.command == "synapse-sites":
        payload = build_synapse_site_manifest(
            args.findings,
            args.output,
            max_sources=args.max_sources,
            max_points_per_finding=args.max_points,
            spatial_permutations=args.spatial_permutations,
        )
        print(json.dumps({
            "dataset": payload["dataset"],
            "total_points": payload["total_points"],
            "findings": len(payload["findings"]),
        }, indent=2))
    elif args.command == "pam04-simulate":
        payload = run_scenario_file(args.experiment, args.scenario, args.output)
        print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
