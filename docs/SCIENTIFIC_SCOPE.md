# Scientific scope

## What v0.1 is

A reproducible **candidate discovery engine** for the dopaminergic neighborhood of the MaleCNS connectome.

It asks a deliberately narrow question:

> Which parts of the structurally defined dopaminergic network look unusual enough to justify a targeted, separately specified experiment?

The first release computes graph features for dopamine-predicted, optionally traced neurons and surfaces structural outliers and convergence candidates.

## What v0.1 is not

It is **not**:

- a model of ADHD;
- a model of methylphenidate pharmacology;
- evidence that a structural outlier is functionally important;
- a neural dynamics simulation;
- a D1/D2 receptor model;
- an automated paper-writing or mechanism-claiming system.

MaleCNS is one anatomical specimen. A candidate can be caused by biology, annotation choices, reconstruction uncertainty, thresholding, or ordinary variation. Every candidate needs its own null model and literature/experimental context.

## Discovery → experiment boundary

`Findings` are generated automatically and are intentionally worded as candidates.

A finding becomes an `Experiment` only when a human writes down:

1. the question;
2. the expected null;
3. the controls;
4. the metric before seeing the final result;
5. the stopping/acceptance rule;
6. which data are exploratory and which are confirmatory.

This boundary should remain visible in code and on the website.
