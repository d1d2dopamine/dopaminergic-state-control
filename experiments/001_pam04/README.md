# Experiment 001 — PAM04 input specialization

## Question

Does an unusually concentrated PAM04 input profile persist after known-subtype conditioning, recur in independent adult connectomes, and only then produce a robust functional difference in a simple connectome-constrained model?

The experiment starts from a MaleCNS structural lead. It does **not** assume the lead is a new subtype.

## Stage A — MaleCNS subtype resolution

For all PAM04 cells the build stores available cross-dataset identity metadata.

A `known_subtype` is accepted only when an explicit annotation/matching field contains a label such as `PAM04-*`.

The established subtype nomenclature is cross-checked against Li et al. (2020), eLife 62576, Supplementary file 1 (`10.7554/eLife.62576`). The supplement is provenance only in v0.5; the pipeline does not infer a subtype from our discovery metric.

For subtype groups with at least four cells, `max_input_share` is re-tested within the subtype. This separates:

- an outlier that persists inside a known subtype;
- a global PAM04 outlier explained by established subtype structure;
- unresolved/too-small cases.

## Stage B — independent structural replication

`dsc pam04-replication` applies the same high-input-concentration logic to:

- BANC v888 strict-proofread PAM04 neurons;
- FlyWire v783 PAM04 neurons.

The test looks for within-known-subtype outliers and bilateral recurrence. It does not require matching root IDs across specimens.

A positive result is structural replication only. Different connectomes use different specimens and reconstruction/synapse pipelines.

## Stage C — State Lab

Only after the structural candidate is worth retaining do we interpret the live counterfactual model.

Available interventions:

- `real`;
- `knockout`;
- `medianize`;
- `amplify`;
- deterministic `shuffle`.

The live 3D view uses official MaleCNS skeletons and best-effort real synapse coordinates. Glow, pulse travel, event raster and receptor dynamics are simulated and are not physiological recordings.

## Falsification path

PAM04 is demoted/closed if:

1. the MaleCNS effect disappears under reasonable edge thresholds;
2. known-subtype conditioning explains the candidate;
3. the external connectomes do not reproduce a comparable structural motif;
4. the apparent effect is reconstruction/annotation driven;
5. model consequences vanish under reasonable parameter sweeps.

A negative result is recorded rather than rescued post hoc. The same replication framework can then be applied to PAM05/PAM13.
