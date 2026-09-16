# Data and provenance

## Connectome

Pinned dataset: `male-cns:v1.0`.

The heavy GitHub Action downloads the official flat files for annotations, consensus neurotransmitters and neuron-to-neuron weights. Raw upstream files remain in the Actions cache and are not committed.

v0.4 keeps every weight >= 1 edge touching a consensus-dopamine neuron in the bounded snapshot. The primary analysis threshold remains configurable (default 3). During the same full-connectome scan the builder records target in-degree/in-strength at thresholds 1, 3, 5 and 10, allowing threshold robustness without another download.

`snapshot_meta.json` records the edge floor, primary threshold, robustness thresholds, traced universe and anatomical-null coverage. `source.lock.json` records upstream URLs, byte sizes and SHA-256 hashes.

## Dopamine identity

`consensus_nt` defines transmitter identity. Raw transmitter prediction/confidence are provenance only.

## ROI availability

When the MaleCNS annotation export exposes `inputRois`/`outputRois`, those lists are normalised into the bounded snapshot. If only `roiInfo` is present, input/output ROI lists are derived from positive post/pre counts respectively.

If the flat annotation file does not provide broad ROI coverage, the builder makes a fail-soft query to the pinned `male-cns:v1.0` neuPrint dataset for only `bodyId`, `inputRois` and `outputRois`. GitHub Actions caches that compact response as compressed JSON, so we do not download the 6.8 GB synaptic-partner table or 12.7 GB synapse-point table just to construct the availability null. If the query is unavailable, the run remains reproducible but affected convergence candidates are explicitly downgraded to `global_only`. `snapshot_meta.json` records the metadata source and coverage.

For each snapshot target, CI computes the number of eligible traced neurons whose `outputRois` intersect the target's `inputRois`, plus the number of consensus-dopamine neurons inside that pool. These are the parameters for the v0.4 anatomical-availability null.

ROI overlap is intentionally described as availability, not contact probability.

## 3D geometry

The viewer uses official MaleCNS geometry. It prefers the lightweight CI-derived LOD of the official `fullbrain-major-shells`; if that source cannot be built, the optimized ROI fallback remains available. Individual neurons use official v1.0 centerline skeletons in the same MaleCNS EM coordinate space.

## Synapse positions

For direct dopamine-input findings, `dsc synapse-sites` makes a best-effort query against the public MaleCNS neuPrint dataset. Returned coordinates are preserved in native dataset units and the manifest records the 8-nm-to-nm conversion used by the viewer/analysis.

v0.4 also computes source-label spatial segregation on postsynaptic sites. This analysis only concerns the queried dopamine sources and is kept separate from the connectome discovery null.
