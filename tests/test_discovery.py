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


def test_consensus_dopamine_selection_ignores_raw_prediction_confidence():
    import pandas as pd
    from dsc.discovery import select_dopamine_core

    nodes = pd.DataFrame([
        # Consensus says dopamine despite low raw-prediction confidence: keep it.
        {"body_id": 1, "type": "DAN", "side": "L", "status": "Traced", "nt": "dopamine", "nt_confidence": 0.10},
        # A high-confidence raw dopamine-like prediction must not matter once
        # consensus says acetylcholine: this row represents the failure mode
        # caught in the first MaleCNS run (many Kenyon cells).
        {"body_id": 2, "type": "KC", "side": "R", "status": "Traced", "nt": "acetylcholine", "nt_confidence": 0.99},
    ])
    config = {"dataset": {"traced_only": True}}
    assert select_dopamine_core(nodes, config) == {1}
