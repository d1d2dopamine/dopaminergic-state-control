# dopaminergic-state-control

Reproducible discovery engine for unusual structure in the dopaminergic neighborhood of the **Drosophila MaleCNS v1.0** connectome.

The workflow is intentionally practical: commit code, let GitHub Actions fetch/process the pinned connectome, then inspect candidate findings and real 3D MaleCNS anatomy on the project's own GitHub Pages site.

## v0.2.1

v0.2.1 keeps the peer-aware/statistical work from v0.2 and fixes the 3D runtime. v0.2 replaces the first broad anomaly screen with comparisons that are harder to fool:

- dopamine identity is `consensus_nt == dopamine`;
- neuron outliers are compared against the **same exact MaleCNS type**, not against the whole dopamine population;
- exact left/right pairs and multi-neuron left/right type groups are screened separately;
- convergence is tested with a global mixing null that holds the target's full traced in-degree fixed;
- FDR correction is conservative against the full traced target universe, not just targets already hit by dopamine neurons;
- the site is a minimal grayscale research dashboard;
- the 3D view uses **official MaleCNS neuron centerline skeletons** over a lightweight LOD deterministically derived in CI from official MaleCNS neuropil meshes.

A candidate is a lead, not a biological conclusion. The current convergence null controls for generic target degree but **not yet for neuropil/anatomical availability**.

## Research site

The generated site contains only four views:

`overview` → run counts + highest candidates  
`findings` → dense filterable candidate table  
`3d specimen` → real MaleCNS regional meshes + real selected neuron skeletons  
`run` → exact commit, hashes and scope

The 3D viewer does not invent neuron-to-neuron geometry. It highlights published neuron centerlines. Connectivity between neurons remains a graph-table fact unless synapse coordinates are explicitly added in a later experiment.

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
dsc geometry-manifest --output build/research/site/data/geometry.json
```

Normally you do not run this locally. Use **Actions → Update MaleCNS dopamine snapshot**. GitHub Actions caches the upstream flat-connectome files and deploys the finished site to GitHub Pages.

## 3D data provenance

The site loads geometry from official FlyEM/Janelia public storage:

- neuropil region meshes: `gs://flyem-male-cns/rois/fullbrain-roi-v5/mesh/`
- neuron centerline skeletons: `gs://flyem-male-cns/v1.0/segmentation/skeletons-malecns/skeletons-precomputed/`

Both share MaleCNS EM coordinates. Geometry is not copied from another visualization website. During the heavy workflow, GitHub Actions caches the official full-resolution region meshes, records their source hashes, and derives a low-detail browser surface from original MaleCNS surface vertices. Full multi-million-triangle ROI meshes are not shipped to the browser. A bounded, focus-first set of finding skeletons is copied unchanged; other contextual skeletons can stream from the same official public endpoint. `geometry.json` retains authoritative source URLs/hashes plus LOD hashes and triangle counts.

MaleCNS data are CC BY. Project code is MIT.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The synthetic fixture exists only to test the software and CI. Never interpret demo findings biologically.

## Русский

See [`docs/PLAN_RU.md`](docs/PLAN_RU.md), [`docs/DATA.md`](docs/DATA.md) and [`docs/FIRST_RUN_RU.md`](docs/FIRST_RUN_RU.md).
