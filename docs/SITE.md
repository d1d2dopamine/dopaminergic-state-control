# Research site

The site is a compact grayscale research instrument, not a public-facing showcase.

## Findings v0.4

The table now exposes control status, threshold survival, null type and optional spatial synapse evidence. `review_queue.json` contains only `survived_controls` and `survived_thresholds` findings.

## 3D specimen

The v0.3 WebGL2 viewer remains intentionally lightweight: official MaleCNS context shell, focus-first real skeletons, lazy context, natural orbit/pan/zoom, camera presets, clipping and URL-preserved views.

v0.4 adds analysis metadata around the existing synapse overlay. For direct dopamine-input findings the sidebar can display the number of queried sites, source-segregation eta², permutation BH q and the resulting descriptive spatial pattern.

The viewer never draws an invented continuous cable between two neurons.


## State Lab v0.4.1

`state-lab.html` is the interactive surface for Experiment 001. The build derives the PAM04 structural matrix from the same MaleCNS snapshot used by discovery. The browser compares the unmodified structural model with a counterfactual under identical stimulus/model settings.

Available interventions are candidate knockout, medianization of the candidate input profile, dominant-input amplification and deterministic input-channel shuffling. The dopamine/receptor controls are normalized exploratory parameters. They are intentionally labelled as assumptions because the connectome does not provide per-target Dop1R1/Dop1R2/Dop2R abundance.

The **export run JSON** action captures the parameters and source run provenance. If that JSON is committed under `experiments/001_pam04/scenarios/`, the heavy MaleCNS GitHub workflow reproduces it with the Python implementation of the same model and stores the result in the research artifact/site data.
