# Research site

The site is a compact grayscale research instrument, not a public-facing showcase.

## Findings v0.4

The table exposes control status, threshold survival, null type and optional spatial synapse evidence. `review_queue.json` is a manual-investigation queue, not a claim that every item has passed every biological control.

## 3D specimen

The standalone WebGL2 viewer remains the anatomy inspector: official MaleCNS context shell, real neuron centerlines, lazy context, natural orbit/pan/zoom, camera presets, clipping and URL-preserved views. It never draws invented neuron-to-neuron cables.

## State Lab v0.4.2

`state-lab.html` is now primarily a synchronized visual playback surface for Experiment 001.

The live viewer loads the same official MaleCNS brain shell used by the specimen page, all PAM04 centerlines, selected upstream partner skeletons and a bounded set of strong downstream partners. The heavy workflow additionally performs a fail-soft neuPrint query for candidate input/output synapse coordinates. When available, those real synapse sites flash during playback.

The timeline drives four linked views:

- real 3D anatomy whose neurite brightness follows normalized model activity;
- moving pulse markers over real skeleton geometry;
- a simulated-event raster derived deterministically from the rate trace;
- a selected-neuron activity trace and compact circuit graph.

The pulse fronts and event ticks are visualization/model outputs. They are **not** recorded action potentials, calcium traces or measured MaleCNS conduction delays. The UI keeps this distinction visible because the purpose is to understand counterfactuals, not to make a static connectome look physiologically measured.

Available interventions remain candidate knockout, medianization of the candidate input profile, dominant-input amplification and deterministic input-channel shuffling. The dopamine/receptor controls are normalized exploratory parameters; the connectome does not provide per-target Dop1R1/Dop1R2/Dop2R abundance.

The **export run JSON** action captures parameters, source provenance and activity/event summary. If that JSON is committed under `experiments/001_pam04/scenarios/`, the heavy MaleCNS workflow reproduces the underlying rate-model comparison with the Python implementation.
