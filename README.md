# dopaminergic-state-control

Reproducible discovery engine for unusual structure in the dopaminergic neighborhood of the **Drosophila MaleCNS v1.0** connectome.

The workflow is intentionally practical: commit code, let GitHub Actions fetch/process the pinned connectome, then inspect candidate findings and real 3D MaleCNS anatomy on the project's own GitHub Pages site.

## v0.3.0

v0.3 keeps the peer-aware discovery/statistics from v0.2 and turns the 3D page into a usable research viewer:

- dopamine identity is `consensus_nt == dopamine`;
- exact-type peer outliers, bilateral asymmetry and degree-controlled dopamine-input enrichment remain the discovery layer;
- the viewer prefers the official MaleCNS `fullbrain-major-shells` central-brain/optic-lobe geometry instead of drawing 80 overlapping ROI surfaces;
- a deterministic CI-built LOD is shipped to the browser while source URLs, hashes and source triangle counts remain in provenance;
- official MaleCNS neuron centerline skeletons are loaded focus-first;
- natural grab-style orbit, pan, zoom, anatomical camera presets, `fit neuron` and `fit brain` are available;
- brain and context opacity are adjustable, with a clipping control for looking inside the shell;
- camera state and finding selection can be preserved in the URL;
- for direct dopamine-input findings, CI makes a best-effort anonymous neuPrint query for the **real pre/post synapse positions** and overlays them as points;
- synapse-overlay failure is fail-soft and never turns a valid discovery run red.

A candidate is a lead, not a biological conclusion. The current convergence null controls for generic target degree but **not yet for neuropil/anatomical availability**.

## Research site

The generated site contains only four views:

`overview` → run counts + highest candidates  
`findings` → dense filterable candidate table  
`3d specimen` → real MaleCNS shell + selected real neuron skeletons + applicable synapse sites  
`run` → exact commit, hashes and scope

The 3D viewer does not invent neuron-to-neuron lines. Visible neurites are published MaleCNS centerlines. Synapse dots, when present, are queried from the MaleCNS neuPrint dataset and are shown only for findings that assert direct connectivity.

## Real MaleCNS run

```bash
dsc fetch-malecns \
  --raw-dir data/raw/male-cns-v1.0 \
  --output data/derived/male-cns-v1.0-dopamine \
  --min-synapses 3

dsc run \
  --snapshot data/derived/male-cns-v1.0-dopamine \
  --config configs/discovery.yml \
  --output build/research \
  --site-template site

dsc geometry-manifest \
  --output build/research/site/data/geometry.json \
  --vendor-dir build/research/site/data/geometry \
  --findings build/research/findings.json

dsc synapse-sites \
  --findings build/research/findings.json \
  --output build/research/site/data/synapses.json
```

Normally you do not run this locally. Use **Actions → Update MaleCNS dopamine snapshot**. GitHub Actions caches the upstream flat-connectome files and deploys the finished site to GitHub Pages.

## 3D data provenance

The viewer reads geometry from official FlyEM/Janelia public storage. The preferred context is `fullbrain-major-shells` segments 1–3 (central brain and both optic lobes); if that source cannot be built, the workflow falls back to the optimized `fullbrain-roi-v5` route from v0.2.1. Neuron centerlines come from `v1.0/segmentation/skeletons-malecns/skeletons-precomputed/`.

The source meshes are never altered in the cache. CI records source hashes, derives a deterministic display LOD, and ships only that lightweight geometry to Pages. MaleCNS data are CC BY. Project code is MIT.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The synthetic fixture exists only to test the software and CI. Never interpret demo findings biologically.

## Русский

See [`docs/PLAN_RU.md`](docs/PLAN_RU.md), [`docs/DATA.md`](docs/DATA.md) and [`docs/FIRST_RUN_RU.md`](docs/FIRST_RUN_RU.md).
