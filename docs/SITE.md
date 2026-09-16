# Research site

The site is intentionally not a public-facing showcase. It is a compact instrument panel.

Design rules:

- grayscale only;
- no gradients, decorative cards, hero sections or marketing text;
- dense tables over decorative charts;
- raw IDs, methods, scores and null statistics remain visible;
- the 3D specimen view is the only major visualization because it carries anatomical information.

## 3D specimen

The viewer is custom WebGL2 with no visualization framework dependency. Neuron centerlines are official MaleCNS skeletons in native EM coordinates.

The **source** ROI meshes are also official MaleCNS geometry, but they contain about 7.27 million triangles in v1.0 and are intentionally not shipped raw to the browser. During the heavy GitHub Action, CI downloads/caches the source meshes, records their URLs and SHA-256 hashes, and deterministically derives a low-detail surface using voxel vertex clustering. Cluster representatives are original MaleCNS surface vertices. The browser receives only this display LOD.

This separation is deliberate:

- scientific source/provenance stays exact;
- the visualization remains a faithful anatomical context;
- opening the page does not allocate/upload millions of source triangles to the GPU.

The renderer caps canvas pixel count, uses depth testing for the brain surface, renders only on changes, and yields between progressive ROI loads. The focus skeleton is loaded first. Related skeletons are **off by default** and are fetched only when `context` is enabled.

Controls:

- drag: orbit;
- wheel: zoom;
- `fit neuron`: frame the selected focus skeleton;
- `fit brain`: frame the whole CNS;
- `regions`: toggle anatomical context;
- `context`: lazily load/show up to eight related real skeletons.
