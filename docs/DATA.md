# Data and provenance

## MaleCNS v1.0

MaleCNS remains the primary discovery dataset. The pipeline uses the pinned public annotation/connectivity sources and the public `male-cns:v1.0` neuPrint dataset.

Large raw MaleCNS tables stay in CI cache. Derived snapshots retain source URLs, hashes, thresholds and metadata provenance in `source.lock.json`, `snapshot_meta.json` and `run_manifest.json`.

### Compact ROI metadata

v0.5 queries `bodyId`, `inputRois`, `outputRois`, and `roiInfo`.

Some MaleCNS neuPrint neurons expose useful neuropil counts through `roiInfo` even when the explicit ROI arrays are empty. The loader therefore derives input ROIs from entries with positive `post` counts and output ROIs from entries with positive `pre` counts. Empty legacy ROI caches are rejected and replaced.

ROI overlap is only an availability control. It is not a physical contact model.

### Compact identity metadata

A separate small neuPrint cache stores:

- `flywireType`
- `hemibrainType`
- `supertype`
- `itoleeHl`
- `dimorphism`
- `synonyms`

These fields are used to resolve known PAM04 subtypes and cross-dataset identity. They are annotation evidence, not a new clustering result from this project.

## BANC v888

Experiment 001 can download/cache the published BANC v888 per-neuron metadata and neuron-to-neuron v2 edge list.

The metadata provide BANC `cell_type`, side, hemilineage, proofreading status and cross-dataset match fields, including Hemibrain and MaleCNS/FlyWire-related identities.

The v2 neuron edge list records `pre`, `post`, raw synapse `count`, normalized target input fraction, and source/target totals. v0.5 uses the raw count and applies `count >= 5`.

For connectivity-sensitive replication the analysis uses the strict `proofread == TRUE` PAM04 population. Raw BANC files remain in cache and are not copied into the research artifact/site.

## FlyWire v783

Experiment 001 can download/cache the public v783 annotation table and proofread neuron-neuron connectivity feather.

The annotation table supplies `root_id`, `cell_type`, `hemibrain_type`, side and hemilineage fields.

The connectivity file can contain separate rows for a neuron pair in different neuropils. v0.5 groups those rows by pre/post neuron before applying the connection threshold, then computes the same input-concentration metric used for BANC.

Raw FlyWire files remain in cache and are not repackaged in release artifacts.

## Cross-connectome comparability

MaleCNS, BANC and FlyWire are different specimens, sexes/data releases, annotation systems and synapse-detection pipelines. Therefore v0.5 does **not** compare root IDs or treat raw synapse counts as identical physiological units.

The replication target is a structural rule: whether an unusually concentrated PAM04 input profile persists within an explicitly known subtype and whether an outlier motif recurs bilaterally in independent adult connectomes.

## Geometry and synapses

MaleCNS State Lab continues to use official centerline skeletons and the official brain-shell geometry. Best-effort neuPrint synapse queries provide real candidate synapse coordinates. Simulated pulses/event ticks are never stored as measured physiology.
