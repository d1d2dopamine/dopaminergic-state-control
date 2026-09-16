from __future__ import annotations

import argparse
import json

from .geometry import build_geometry_manifest
from .malecns import build_dopamine_snapshot
from .pipeline import run_pipeline
from .synapses import build_synapse_site_manifest


def main() -> None:
    parser = argparse.ArgumentParser(prog="dsc", description="Dopaminergic State Control discovery engine")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run discovery and build the static research site")
    run.add_argument("--snapshot", required=True)
    run.add_argument("--config", default="configs/discovery.yml")
    run.add_argument("--output", default="results/current")
    run.add_argument("--site-template", default="site")

    fetch = sub.add_parser("fetch-malecns", help="Build a one-hop dopamine snapshot from official MaleCNS v1.0 flat files")
    fetch.add_argument("--raw-dir", default="data/raw/male-cns-v1.0")
    fetch.add_argument("--output", default="data/derived/male-cns-v1.0-dopamine")
    fetch.add_argument("--min-synapses", type=int, default=3)
    fetch.add_argument("--include-nontraced", action="store_true")
    fetch.add_argument("--refresh", action="store_true")

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
    syn.add_argument("--max-sources", type=int, default=8)
    syn.add_argument("--max-points", type=int, default=2500)

    args = parser.parse_args()
    if args.command == "run":
        manifest = run_pipeline(args.snapshot, args.config, args.output, args.site_template)
        print(json.dumps(manifest, indent=2))
    elif args.command == "fetch-malecns":
        lock = build_dopamine_snapshot(
            args.raw_dir,
            args.output,
            min_synapses=args.min_synapses,
            traced_only=not args.include_nontraced,
            refresh=args.refresh,
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
        )
        print(json.dumps({
            "dataset": payload["dataset"],
            "total_points": payload["total_points"],
            "findings": len(payload["findings"]),
        }, indent=2))


if __name__ == "__main__":
    main()
