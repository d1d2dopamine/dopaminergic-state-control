# Website

The site is plain HTML/CSS/JavaScript. There is no framework and no backend.

Generated files are copied into `build/<run>/site/data/`:

- `findings.json`
- `network.json`
- `features.json`
- `run.json`

GitHub Pages only serves the generated static directory.

Pages:

- **Overview** — run summary and highest-score candidates.
- **Findings** — searchable candidate list.
- **Network** — local graph around the selected candidate.
- **Runs** — exact provenance manifest.

The UI intentionally does not present anomaly score as biological importance.
