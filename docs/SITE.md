# Research site

The site is a compact grayscale research instrument, not a public-facing showcase.

## Overview / findings

The overview shows current run counts, the manual investigation queue and the Experiment 001 replication status when available.

The findings table retains control status, threshold survival, null type and optional spatial synapse evidence. `review_queue.json` is a manual-investigation queue, not a biological validation list.

## 3D specimen

The standalone WebGL2 viewer is the anatomy inspector: official MaleCNS context shell, real neuron centerlines, camera controls, clipping and URL-preserved views. It never draws invented neuron-to-neuron cables.

## State Lab v0.5

State Lab keeps the v0.4.2 synchronized visual playback:

- real MaleCNS geometry;
- model-dependent neurite brightness;
- moving pulse markers;
- best-effort real candidate synapse positions;
- simulated event raster;
- selected-neuron activity trace;
- compact circuit graph;
- counterfactual interventions and exploratory dopamine/DAT/receptor controls.

Pulse fronts and event ticks are visualization/model outputs, not recorded action potentials or conduction delays.

v0.5 adds a **cross-connectome replication** panel. It displays MaleCNS, BANC and FlyWire PAM04 counts, whether connectivity was actually tested, within-subtype structural results, and candidate-specific cross-dataset status.

The panel is intentionally separate from the simulator so a striking visual model effect cannot be mistaken for replication evidence.

## Exported runs

`export run JSON` captures State Lab parameters, source provenance and model summaries. Committed scenario JSON files can be reproduced in CI. These scenario results remain exploratory unless the structural candidate survives the v0.5 falsification path.
