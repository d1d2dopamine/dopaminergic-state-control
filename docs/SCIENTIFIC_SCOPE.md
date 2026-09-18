# Scientific scope

`dopaminergic-state-control` is a connectomic discovery, falsification and exploratory modeling project.

It does **not** model ADHD, methylphenidate pharmacology, measured receptor abundance, measured neural firing, or a subjective brain state.

## Claims allowed in v0.5

The strongest claims the current pipeline can support are structural/statistical:

- exact-type outlier at a stated connection threshold;
- robustness across thresholds;
- bilateral structural evidence;
- dopamine-input enrichment under a stated null;
- spatial organization of queried synapse sites;
- whether a PAM04 outlier persists within an explicitly annotated known subtype;
- whether a comparable structural outlier motif appears in BANC v888 and/or FlyWire v783.

A cross-connectome positive result is not automatically a new subtype or mechanism. Independent connectomes differ by specimen, sex, reconstruction, annotation and synapse-detection pipeline.

## Known subtype control

PAM04 is not treated as an unstructured population. v0.5 only recognizes subtype labels that are explicitly present in annotation/matching fields such as `PAM04-*`.

The project does not derive subtype labels from `max_input_share` and then test `max_input_share` within those same derived groups.

The literature reference for established PAM subtype names is Li et al. (2020), eLife 62576, Supplementary file 1 (`10.7554/eLife.62576`). In v0.5 this is a provenance reference, not an automatically imported clustering table.

If a MaleCNS candidate stops being unusual after conditioning on the known subtype, the correct interpretation is that the detector rediscovered established structure.

## Anatomical null

For dopamine-input convergence, the preferred null fixes the target's traced presynaptic partner count and restricts eligible sources using overlap between source `outputRois` and target `inputRois`.

v0.5 repairs ROI hydration by falling back to neuPrint `roiInfo` when the explicit arrays are empty.

ROI overlap remains a necessary availability condition, not a physical contact/wiring-probability model. It does not control lineage, receptor expression, dynamics, plasticity, internal state or causal behavior.

If usable ROI coverage is unavailable, the result is explicitly `global_only`.

## State Lab

State Lab is a counterfactual sandbox.

Measured/structural:
- neuron skeleton geometry;
- connectome edge weights;
- queried synapse coordinates.

Simulated/exploratory:
- glow/activity traces;
- pulse travel;
- event/spike-like raster ticks;
- time constants;
- dopamine concentration units;
- DAT clearance;
- receptor gains/coupling.

A visually strong simulation effect is a model-sensitivity result, not evidence that the same activity occurred in the living animal.

## Falsification rule

Experiment 001 should be closed or demoted if the PAM04 lead is explained by known subtype structure, fails independent connectome replication, or depends on fragile model parameters. A negative result remains part of the project record and should trigger the same replication workflow on the next candidate rather than post-hoc rescue of PAM04.
