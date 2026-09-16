# Provenance

Real-data snapshot runs write `source.lock.json` next to the derived snapshot. It records official URLs, file sizes, SHA-256 hashes, selection thresholds and counts.

Large MaleCNS source files belong in `data/raw/` or the GitHub runner temporary directory and are ignored by git.
