# Experiment 001 — PAM04 input specialization

## Question

Does the unusually concentrated input profile observed in a small subset of PAM04 dopaminergic neurons make those cells more selective or influential in a simple connectome-constrained counterfactual model?

This experiment begins with the MaleCNS structural candidate. It does **not** assume that the candidate is a biological subtype.

## Structural comparisons

The build generates a dossier for all PAM04 neurons at the configured primary edge threshold. It includes:

- exact-type distribution of `max_input_share`;
- strongest individual input/output partners;
- aggregated upstream and downstream cell-type channels;
- discovery robustness and bilateral evidence when a PAM04 cell is present in the review queue.

## State Lab

The static research site contains an interactive browser-only sandbox. It compares the real structural profile against counterfactuals using identical model parameters:

- `real` — measured connectome weights;
- `knockout` — selected candidate PAM04 activity is forced to zero;
- `medianize` — selected candidate input-channel profile is replaced by the PAM04 median profile while preserving its total input weight;
- `amplify` — the selected candidate's strongest input channel is multiplied by a user-controlled factor;
- `shuffle` — selected candidate input-channel weights are deterministically permuted while preserving the same values.

The dynamic layer is deliberately phenomenological. It is useful for asking whether a structural feature *could matter in the model*, not for claiming measured firing rates or behavior.

## Dopamine receptor sandbox

The viewer exposes normalized `Dop1R1`, `Dop1R2`, and `Dop2R` response channels plus DAT clearance. These are exploratory model parameters. MaleCNS does not provide per-target receptor abundance, so the project must not present these traces as measured receptor activity in a particular postsynaptic neuron.

The D1-like versus D2-like coupling sign is treated only as a receptor-family prior. Every exported run records the exact user parameters and assumptions.

## Falsification path

A PAM04 candidate becomes less interesting if:

1. the effect disappears under reasonable edge thresholds;
2. medianizing the candidate's unusual input structure has negligible output consequences across parameter sweeps;
3. the apparent specialization is driven by a single reconstruction/annotation artifact;
4. the pattern fails independent connectome replication when comparable data are available.
