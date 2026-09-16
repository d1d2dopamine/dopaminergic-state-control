# Research site

The site is intentionally not a public-facing showcase. It is a compact grayscale research instrument.

## 3D specimen v0.3

The viewer is custom WebGL2. It uses one lightweight anatomical context shell whenever the official MaleCNS `fullbrain-major-shells` source is available, with the v0.2 optimized ROI path as a fallback.

The browser never receives full-resolution source anatomy. GitHub Actions downloads/caches official geometry, records source provenance, builds a deterministic LOD and deploys only the LOD plus the finding-relevant skeletons.

Viewer behavior:

- drag = grab-style orbit;
- `Shift + drag`, right-drag or middle-drag = pan;
- wheel = zoom;
- double-click = fit selected focus neuron;
- anterior/posterior/dorsal/ventral/left/right camera presets;
- adjustable brain/context opacity;
- front clipping control for seeing internal neurites;
- focus neuron rendered above the faint shell;
- context neurons disabled by default and loaded lazily;
- camera state can be copied into the URL.

For `dopamine_input_enrichment` findings, the heavy workflow also attempts an anonymous MaleCNS neuPrint query for individual `SynapsesTo` sites. The browser converts the returned 8-nm voxel coordinates to the same native-nm coordinate space as the skeletons before applying the shared viewer transform. These points are optional visualization evidence: a failed query is recorded but does not fail the research run.
