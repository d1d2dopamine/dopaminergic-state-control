# Research site

The site is intentionally not a public-facing showcase. It is a compact instrument panel.

Design rules:

- grayscale only;
- no gradients, decorative cards, hero sections or marketing text;
- dense tables over decorative charts;
- raw IDs, methods, scores and null statistics remain visible;
- the 3D specimen view is the only major visualization because it carries anatomical information.

## 3D specimen

The viewer is custom WebGL2 with no visualization framework dependency. The GitHub Action copies official MaleCNS region meshes and the selected official neuron skeletons into the deployed Pages artifact; the viewer then loads them from the project's own site. The manifest preserves their FlyEM/Janelia source URLs and hashes.

Mouse drag rotates. Wheel zooms. `regions` toggles the background anatomy. Selecting another finding discards the previous highlighted skeleton buffers and loads the new focus/related cells.

For performance, regional geometry is loaded concurrently and rendered only when the scene changes; the renderer does not redraw ~7M source triangles continuously at 60 FPS.
