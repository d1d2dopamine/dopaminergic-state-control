from pathlib import Path

from dsc.pipeline import run_pipeline


def test_pipeline_builds_site(tmp_path: Path):
    out = tmp_path / "run"
    manifest = run_pipeline("data/demo", "configs/demo.yml", out, "site")
    assert manifest["dataset"] == "synthetic-demo"
    assert manifest["snapshot_meta"]["eligible_traced_neurons"] == 42
    assert (out / "findings.json").exists()
    assert (out / "review_queue.json").exists()
    assert (out / "site" / "index.html").exists()
    assert (out / "site" / "network.html").exists()
    assert (out / "site" / "assets" / "brain.js").exists()
    assert not (out / "site" / "data" / "network.json").exists()
    assert (out / "site" / "data" / "run.json").exists()
    assert (out / "site" / "data" / "review_queue.json").exists()
