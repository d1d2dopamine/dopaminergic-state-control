from __future__ import annotations

import argparse
import json
from pathlib import Path

from .malecns import build_dopamine_snapshot
from .pipeline import run_pipeline


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
    fetch.add_argument("--min-nt-confidence", type=float, default=0.70)
    fetch.add_argument("--min-synapses", type=int, default=3)
    fetch.add_argument("--include-nontraced", action="store_true")
    fetch.add_argument("--refresh", action="store_true")

    args = parser.parse_args()
    if args.command == "run":
        manifest = run_pipeline(args.snapshot, args.config, args.output, args.site_template)
        print(json.dumps(manifest, indent=2))
    elif args.command == "fetch-malecns":
        lock = build_dopamine_snapshot(
            args.raw_dir,
            args.output,
            min_confidence=args.min_nt_confidence,
            min_synapses=args.min_synapses,
            traced_only=not args.include_nontraced,
            refresh=args.refresh,
        )
        print(json.dumps(lock["selection"], indent=2))


if __name__ == "__main__":
    main()
