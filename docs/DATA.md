# Data and provenance

## Connectome

Pinned dataset: `male-cns:v1.0`.

The heavy GitHub Action downloads the official flat files for annotations, consensus neurotransmitters and neuron-to-neuron weights. Raw upstream files stay in the Actions cache and are not committed.

The bounded snapshot contains every edge ≥ `min_synapses` touching a consensus-dopamine core neuron. During the same full-edge scan, v0.2 also records each snapshot target's full traced presynaptic partner count and strength at the same threshold. These fields support the convergence null.

`snapshot_meta.json` records the traced universe size and degree scope. `source.lock.json` records upstream URLs, byte sizes and SHA-256 hashes.

## Dopamine identity

`consensus_nt` defines transmitter identity. `predicted_nt` and prediction confidence are provenance only. This rule exists because the first real run demonstrated that raw predictions can misclassify many non-dopaminergic cells before consensus overrides are applied.

## 3D geometry

The generated site does not use a hand-built fly model.

`dsc geometry-manifest` queries official FlyEM/Janelia public storage. In the real GitHub Action it vendors the region meshes and a bounded, focus-first set of skeletons referenced by the current findings into the Pages artifact. Non-vendored contextual skeletons fall back to the same official public endpoint at view time. The project's own WebGL viewer loads:

- MaleCNS neuropil ROI meshes from `fullbrain-roi-v5/mesh/`;
- individual MaleCNS neuron centerline skeletons from the v1.0 precomputed skeleton directory.

The two sources use native MaleCNS EM coordinates (nanometers), so selected skeletons sit inside the published reconstructed anatomy without per-neuron warping. `geometry.json` records original URLs, byte sizes and SHA-256 hashes for the copied geometry.

The viewer deliberately does **not** draw fake straight lines between neurons. A connectome edge means synaptic connectivity; it is not a continuous anatomical cable from one cell center to another.
