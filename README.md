# dopaminergic-state-control

**Automated candidate discovery in the dopaminergic neighborhood of the Drosophila MaleCNS connectome.**

The project is built around a practical workflow: code searches the network for unusual structure, GitHub Actions reproduces the run, and GitHub Pages shows the candidates. A candidate is a lead for an experiment, not a biological conclusion.

## v0.1

The first release:

- selects dopamine-predicted neurons from a bounded snapshot;
- computes structural graph features;
- surfaces robust feature outliers;
- surfaces high-convergence dopaminergic targets;
- builds a static Findings / Network / Runs website;
- records input/config hashes and run metadata;
- keeps discovery separate from hypothesis-testing experiments.

It does **not** claim to model ADHD, methylphenidate, D1/D2 receptor dynamics, or causal brain state transitions. See [`docs/SCIENTIFIC_SCOPE.md`](docs/SCIENTIFIC_SCOPE.md).

## Try it immediately

The repository contains a synthetic dataset with deliberate anomalies so the whole pipeline works before downloading MaleCNS.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
pytest
dsc run --snapshot data/demo --config configs/demo.yml --output build/demo --site-template site
python -m http.server 8000 --directory build/demo/site
```

Open `http://localhost:8000`.

## Real MaleCNS snapshot

The public MaleCNS v1.0 flat release is used directly; no Colab and no external web UI is required for the workflow.

```bash
dsc fetch-malecns \
  --raw-dir data/raw/male-cns-v1.0 \
  --output data/derived/male-cns-v1.0-dopamine \
  --min-nt-confidence 0.70 \
  --min-synapses 3

dsc run \
  --snapshot data/derived/male-cns-v1.0-dopamine \
  --config configs/discovery.yml \
  --output build/research \
  --site-template site
```

Snapshot construction downloads roughly 1.1 GB of connectivity plus annotation/transmitter tables. Those upstream files are never committed. The produced `source.lock.json` records the exact source hashes.

## GitHub workflow

- `CI` — tests every push/PR and rebuilds the synthetic run.
- `Update MaleCNS dopamine snapshot` — manual heavy job; downloads/caches MaleCNS, produces the bounded snapshot + research artifact, and deploys the real site immediately.
- `Build and deploy research site` — manual preview/deploy only; publishes a committed real snapshot when present, otherwise the demo. It does not run on every push, so it cannot overwrite a real research deployment accidentally.
- `Run experiment` — intentionally minimal harness for versioned experiments under `experiments/`.

For Pages, set **Settings → Pages → Source → GitHub Actions** once.

## Repository map

```text
src/dsc/                scientific/discovery engine
configs/                frozen run settings
data/demo/               synthetic CI fixture
data/derived/            small real snapshots (optional to commit)
experiments/             hypothesis-driven work only
docs/                    scope, plan, data and site docs
site/                    static site template
.github/workflows/       CI, heavy data update, Pages, experiments
```

## Research rule

> The engine may say “structurally unusual”. It may not say “mechanism”, “ADHD”, “methylphenidate effect”, or “causal” without a separately defined experiment.

## Data attribution

MaleCNS v1.0 is an external dataset and is not included in this repository. The MaleCNS project states that the dataset is CC-BY. Cite the original MaleCNS release/publication when using derived results.

## Русский

Практический план и границы проекта: [`docs/PLAN_RU.md`](docs/PLAN_RU.md).
