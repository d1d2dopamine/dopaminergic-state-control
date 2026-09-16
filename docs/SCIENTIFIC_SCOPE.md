# Scientific scope

`dopaminergic-state-control` is currently a connectomic discovery and falsification tool. It does not model ADHD, methylphenidate pharmacology, receptor kinetics, neural activity or a subjective brain state.

At v0.4, allowed claims are still structural/statistical: exact-type outlier, bilateral mismatch, dopamine-input enrichment under a stated null, threshold robustness, and source-specific spatial organisation of queried dopamine synapses.

## Nulls and what they mean

The preferred dopamine-input null conditions on two things:

1. the target's whole-connectome traced presynaptic partner count at the tested edge threshold;
2. anatomical availability defined by overlap between an eligible source neuron's `outputRois` and the target neuron's `inputRois`.

This is stronger than global random mixing but it is not a physical contact model. ROI overlap can still group cells that never come close enough to synapse. The null also does not control developmental lineage, receptor expression, synaptic dynamics, plasticity, state dependence or causal behavior.

ROI metadata can come either from the official flat annotation export or from a compact cached query to the pinned MaleCNS neuPrint dataset. If neither source can support the anatomical null for a target, the system falls back to the older global degree null and labels the result `global_only`. Network failure is therefore visible in provenance rather than silently changing the claim.

## Robustness

The default analysis threshold is 3 synapses. v0.4 also re-tests candidates at 1, 3, 5 and 10 synapses from the same bounded snapshot. Threshold survival is evidence against one arbitrary cutoff driving the result; it is not biological replication.

A discovery card becomes a biological hypothesis only after a separately versioned experiment defines the comparison, controls and falsification rule.
