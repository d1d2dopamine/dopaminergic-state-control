# Experiments

Discovery is exploratory. Experiments live here only after a candidate has a written question and null model.

Suggested layout:

```
experiments/
  001_example/
    hypothesis.md
    config.yml
    run.py
    expected_outputs.md
```

Do not silently change discovery thresholds to make an experiment significant. If a protocol changes, create a new version and keep the old result.


## Experiment 001

`001_pam04/` contains the first focused follow-up: PAM04 input specialization. Browser-exported scenario JSON files can be committed to `001_pam04/scenarios/`; the real MaleCNS workflow reproduces them deterministically.
