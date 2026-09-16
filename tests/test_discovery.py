from pathlib import Path

from dsc.discovery import discover
from dsc.io import load_config, load_snapshot


def test_demo_discovers_candidates():
    nodes, edges = load_snapshot(Path("data/demo"))
    config = load_config("configs/demo.yml")
    result = discover(nodes, edges, config)
    assert len(result.core_ids) == 12
    assert len(result.findings) > 0
    assert any(f["kind"] == "dopamine_convergence" for f in result.findings)
    assert "anomaly_score" in result.features.columns


def test_findings_do_not_claim_mechanism():
    nodes, edges = load_snapshot(Path("data/demo"))
    result = discover(nodes, edges, load_config("configs/demo.yml"))
    text = " ".join(f["interpretation"] for f in result.findings).lower()
    assert "candidate" in text
