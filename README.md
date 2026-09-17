# dopaminergic-state-control

Reproducible discovery engine for unusual structure in the dopaminergic neighborhood of the **Drosophila MaleCNS v1.0** connectome.

The practical loop is: commit code → GitHub Actions fetches/processes the pinned connectome → statistical controls run → the project site shows a manual investigation queue and real 3D MaleCNS anatomy.

## v0.4.2 — Live State Lab

`v0.4.2` keeps the Experiment 001 PAM04 counterfactual model, but changes the main interaction from tables to a **live 3D circuit playback**.

- the State Lab now renders the official MaleCNS brain shell and PAM04 skeletons directly in the experiment page;
- all 32 PAM04 centerlines are loaded, while the selected upstream partners and strongest downstream partners are added as the active circuit context;
- selected PAM04 neurites brighten with model activity and deterministic pulse markers travel over the real skeleton geometry;
- candidate input/output synapses are queried best-effort from MaleCNS neuPrint and flash at their real coordinates when the relevant simulated event reaches that stage;
- a synchronized **simulated-event raster**, selected-neuron activity trace and compact live circuit graph move with the same timeline;
- playback has pause, frame stepping, 0.25×–4× speed, loop, camera presets, fit controls and optional pulse-following;
- `real`, `knockout`, `medianize`, `amplify` and deterministic `shuffle` remain available and update the visual playback;
- exported run JSON now records additional activity/event summaries and explicitly records that event ticks and pulse travel are visual/model outputs rather than physiological recordings;
- geometry CI vendors the Experiment 001 PAM04 population plus candidate partner skeletons so the live lab does not depend on dozens of browser-time remote skeleton requests.

The distinction is deliberate: **anatomy/connectivity are measured structure; glow, pulse timing, event ticks and receptor dynamics are simulated.** The viewer is for understanding and counterfactual comparison, not for pretending that MaleCNS contains electrophysiology.

### v0.4 scientific filtering retained

- dopamine identity remains `consensus_nt == dopamine`;
- the bounded snapshot now retains one-hop dopamine edges down to weight 1, while the primary analysis threshold stays configurable (default 3);
- whole-connectome target in-degree is recorded at robustness thresholds 1/3/5/10;
- exact-type outliers are re-tested across those thresholds;
- peer findings report opposite-side replication evidence and large single-partner-share flags;
- dopamine-input enrichment prefers an **ROI-overlap availability null**: an eligible source must have at least one `outputRoi` overlapping a target `inputRoi`;
- ROI availability is read from the flat annotations when present; otherwise CI fetches only compact `bodyId/inputRois/outputRois` metadata from the pinned MaleCNS neuPrint dataset and caches it as a small compressed file;
- if ROI metadata are missing/inconsistent for a target, the older global degree null is retained and the finding is marked `global_only` instead of being silently treated as anatomy-controlled;
- a `review_queue.json` contains only findings that survive threshold controls or the stronger anatomical controls;
- direct-connectivity findings query real neuPrint synapse sites and now quantify whether different dopamine sources occupy distinct spatial territories on the target;
- spatial source-territory tests use label permutations and BH correction across queried direct findings;
- GitHub Actions writes a compact research summary directly into the workflow run summary.

A candidate is still a lead, not a mechanism. ROI overlap is a necessary anatomical-availability condition, not a model of contact probability, receptor action, physiology or behavior.

## Research site

`overview` → run counts + current manual investigation queue  
`findings` → filterable candidates with control status, robustness, null model and optional spatial synapse evidence  
`state lab` → live 3D PAM04 circuit playback + event raster + counterfactual/receptor sandbox  
`3d specimen` → official MaleCNS shell + real selected neuron skeletons + applicable synapse sites  
`run` → exact commit, hashes, thresholds and data scope

The 3D viewer never invents neuron-to-neuron cables. Visible neurites are published MaleCNS centerlines; synapse dots come from the MaleCNS neuPrint dataset.

## Real MaleCNS run

Normally use **Actions → Update MaleCNS dopamine snapshot**. The default primary threshold is 3. The workflow keeps a weight-1 snapshot floor internally so robustness can be tested without downloading the connectome four times.

Equivalent CLI:

```bash
dsc fetch-malecns \
  --raw-dir data/raw/male-cns-v1.0 \
  --output data/derived/male-cns-v1.0-dopamine \
  --min-synapses 3 \
  --snapshot-floor 1 \
  --roi-cache data/cache/male-cns-v1.0-roi-availability.json.gz

dsc run \
  --snapshot data/derived/male-cns-v1.0-dopamine \
  --config configs/discovery.yml \
  --output build/research \
  --site-template site \
  --min-synapses 3

dsc geometry-manifest \
  --output build/research/site/data/geometry.json \
  --vendor-dir build/research/site/data/geometry \
  --findings build/research/findings.json \
  --experiment build/research/experiment_001_pam04.json

dsc synapse-sites \
  --findings build/research/findings.json \
  --output build/research/site/data/synapses.json \
  --max-sources 24 \
  --max-points 4000 \
  --spatial-permutations 400

dsc pam04-synapses \
  --experiment build/research/experiment_001_pam04.json \
  --output build/research/site/data/experiments/001_pam04_synapses.json
```

## Data provenance

Connectome, annotations, neurotransmitter consensus, geometry and synapse positions come from the pinned MaleCNS public sources. Raw large files remain in GitHub Actions cache. `source.lock.json`, `snapshot_meta.json`, `run_manifest.json` and `geometry.json` retain the relevant source URLs/hashes and analysis scope.

MaleCNS data are CC BY. Project code is MIT.

## Development

```bash
pip install -e '.[dev]'
pytest
```

The synthetic fixture exists only to test software/CI. Never interpret demo findings biologically.

## Русский

See [`docs/PLAN_RU.md`](docs/PLAN_RU.md), [`docs/DATA.md`](docs/DATA.md), [`docs/SCIENTIFIC_SCOPE.md`](docs/SCIENTIFIC_SCOPE.md) and [`docs/FIRST_RUN_RU.md`](docs/FIRST_RUN_RU.md).
