# dopaminergic-state-control

Reproducible discovery and falsification engine for unusual structure in the dopaminergic neighborhood of adult **Drosophila** connectomes.

The working loop is: commit code → GitHub Actions builds a pinned MaleCNS snapshot → statistical controls produce a manual investigation queue → focused experiments try to explain or falsify candidates → independent connectomes are used for structural replication.

## v0.5.0 — PAM04 replication / falsification

`v0.5.0` freezes the visual direction of the project and moves Experiment 001 from “interesting MaleCNS outlier” to a cross-connectome test.

The focused question is now:

> Does a high-input-concentration PAM04 motif persist **within explicitly annotated PAM04 subtypes** and recur in independent adult connectomes?

The heavy workflow now:

- hydrates MaleCNS cross-dataset identity fields from the pinned `male-cns:v1.0` neuPrint dataset;
- extracts only explicit `PAM04-*` subtype labels; it does not invent subtypes from our own connectivity metric;
- re-tests the MaleCNS candidate distribution within a known subtype when at least four subtype peers are available;
- downloads/caches the published **BANC v888** metadata and neuron-to-neuron edge list, then runs the same PAM04 input-concentration analysis there;
- downloads/caches **FlyWire v783** annotations and the proofread neuron-neuron connectivity table, then runs the same analysis there;
- writes `experiment_001_replication.json` with per-dataset results and candidate-specific cross-dataset status;
- shows the replication/falsification status in State Lab and on the overview page.

A positive cross-connectome result is still structural evidence only. It does not establish firing, dopamine release, receptor action, behavior, or a new biological subtype.

Known PAM subtype nomenclature is anchored to Li et al. (2020), eLife 62576, Supplementary file 1 (DOI `10.7554/eLife.62576`). v0.5 treats that publication as a reference and only assigns a subtype when an explicit connectome annotation/match field already contains a `PAM04-*` label; it does not silently reconstruct the paper's clustering.

## ROI control repair

The previous compact MaleCNS ROI cache could contain zero usable `inputRois/outputRois`. v0.5 invalidates that cache format and queries `roiInfo` as a fallback, deriving input ROIs from positive postsynaptic counts and output ROIs from positive presynaptic counts.

If usable ROI coverage still cannot be obtained, dopamine-convergence findings remain explicitly `global_only`; the pipeline does not silently pretend an anatomical null was applied.

## Experiment 001 / State Lab

The v0.4.2 live 3D simulator is retained:

- official MaleCNS brain shell and real neuron centerlines;
- all PAM04 skeletons plus selected upstream/downstream circuit context;
- real queried synapse coordinates when available;
- synchronized model glow, pulse fronts, event raster, activity trace and compact circuit graph;
- `real`, `knockout`, `medianize`, `amplify`, deterministic `shuffle`;
- exploratory dopamine tone / DAT / Dop1R1 / Dop1R2 / Dop2R controls.

The distinction remains strict: **anatomy and connectivity are measured structure; glow, pulse timing, event ticks, receptor dynamics and rate-model activity are simulated.**

State Lab now also exposes the cross-connectome replication panel, so the visual sandbox sits next to the evidence that determines whether PAM04 is worth continuing.

## Discovery controls retained

- dopamine identity: `consensus_nt == dopamine`;
- one-hop dopamine snapshot floor 1, primary analysis threshold configurable (default 3);
- robustness thresholds 1 / 3 / 5 / 10;
- exact-type robust outliers;
- opposite-side evidence and dominant-partner-share flags;
- ROI-overlap availability null for dopamine convergence when ROI coverage is usable;
- global-degree fallback with explicit `global_only` status otherwise;
- real neuPrint synapse-site queries and source-territory permutation tests;
- `review_queue.json` is a manual investigation queue, not a biological validation list.

## Real heavy run

Normally use **Actions → Update MaleCNS dopamine snapshot** with `min_synapses = 3`.

Equivalent core CLI:

```bash
dsc fetch-malecns \
  --raw-dir data/raw/male-cns-v1.0 \
  --output data/derived/male-cns-v1.0-dopamine \
  --min-synapses 3 \
  --snapshot-floor 1 \
  --roi-cache data/cache/male-cns-v1.0-roi-availability.json.gz \
  --identity-cache data/cache/male-cns-v1.0-identity.json.gz

dsc run \
  --snapshot data/derived/male-cns-v1.0-dopamine \
  --config configs/discovery.yml \
  --output build/research \
  --site-template site \
  --min-synapses 3

dsc pam04-replication \
  --experiment build/research/experiment_001_pam04.json \
  --output build/research/experiment_001_replication.json \
  --cache-dir data/cache/pam04-replication
```

The first v0.5 heavy run is substantially larger than v0.4 because it can cache BANC v888 and FlyWire v783 source tables. The raw external tables remain cache inputs; the research artifact/site receives only the small derived replication summary.

## Data provenance

Primary discovery uses MaleCNS v1.0. Experiment 001 replication additionally uses published BANC v888 and FlyWire v783 annotations/connectivity. Source URLs and analysis thresholds are written into the derived replication JSON.

Project code is MIT. External connectome data retain their original source licenses/terms; this repository does not repackage the large raw BANC or FlyWire tables into release artifacts.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The synthetic fixture exists only to test software/CI. Never interpret demo findings biologically.

## Русский

See [`docs/PLAN_RU.md`](docs/PLAN_RU.md), [`docs/DATA.md`](docs/DATA.md), [`docs/SCIENTIFIC_SCOPE.md`](docs/SCIENTIFIC_SCOPE.md), [`docs/FIRST_RUN_RU.md`](docs/FIRST_RUN_RU.md) and [`docs/SITE.md`](docs/SITE.md).
