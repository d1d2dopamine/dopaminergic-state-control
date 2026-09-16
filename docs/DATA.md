# Data and provenance

## Primary dataset

The real-data workflow targets the public MaleCNS `v1.0` flat-connectome release.

The repository does **not** redistribute the large upstream Feather files. `dsc fetch-malecns` downloads them from the official public Google Storage release path into an ignored local/runner directory, computes SHA-256 for the exact files used, and writes a bounded one-hop snapshot plus `source.lock.json`.

Expected upstream files:

- `body-annotations-male-cns-v1.0-minconf-0.5.feather`
- `body-neurotransmitters-male-cns-v1.0.feather`
- `connectome-weights-male-cns-v1.0-minconf-0.5.feather`

The full weights file is about 1.1 GB, so real snapshot creation is a manual workflow, not a job run on every push.

## Derived snapshot schema

`nodes.csv`

- `body_id`
- `type`
- `side`
- `status`
- `nt`
- `nt_confidence`

`edges.csv`

- `pre`
- `post`
- `weight`

The snapshot is deliberately boring. Keeping a small, documented intermediate format lets the analysis and website stay independent of upstream schema changes.

## License

MaleCNS is distributed by the project under CC-BY. The code in this repository is MIT. Dataset attribution must be preserved in any redistributed derived data/results.
