import pandas as pd

from dsc.experiment_pam04 import build_pam04_experiment


def _fixture():
    nodes = pd.DataFrame([
        {"body_id": 1, "type": "PAM04", "side": "L", "status": "Traced", "nt": "dopamine", "nt_confidence": 1.0, "class": "DAN", "superclass": "cb_intrinsic"},
        {"body_id": 2, "type": "PAM04", "side": "R", "status": "Traced", "nt": "dopamine", "nt_confidence": 1.0, "class": "DAN", "superclass": "cb_intrinsic"},
        {"body_id": 10, "type": "SLP321", "side": "L", "status": "Traced", "nt": "acetylcholine", "nt_confidence": 1.0, "class": "unknown", "superclass": "cb_intrinsic"},
        {"body_id": 11, "type": "MBON13", "side": "R", "status": "Traced", "nt": "glutamate", "nt_confidence": 1.0, "class": "MBON", "superclass": "cb_intrinsic"},
        {"body_id": 20, "type": "MBON02", "side": "L", "status": "Traced", "nt": "glutamate", "nt_confidence": 1.0, "class": "MBON", "superclass": "cb_intrinsic"},
    ])
    edges = pd.DataFrame([
        {"pre": 10, "post": 1, "weight": 20},
        {"pre": 11, "post": 1, "weight": 3},
        {"pre": 10, "post": 2, "weight": 3},
        {"pre": 11, "post": 2, "weight": 16},
        {"pre": 1, "post": 20, "weight": 8},
        {"pre": 2, "post": 20, "weight": 9},
    ])
    features = pd.DataFrame([
        {"body_id": 1, "type": "PAM04", "side": "L", "in_strength": 23.0, "out_strength": 8.0, "in_partner_count": 2.0, "out_partner_count": 1.0, "max_input_share": 20/23, "max_output_share": 1.0, "input_entropy": 0.6, "output_entropy": 0.0},
        {"body_id": 2, "type": "PAM04", "side": "R", "in_strength": 19.0, "out_strength": 9.0, "in_partner_count": 2.0, "out_partner_count": 1.0, "max_input_share": 16/19, "max_output_share": 1.0, "input_entropy": 0.65, "output_entropy": 0.0},
    ])
    findings = [{
        "id": "peer-max_input_share-1", "kind": "within_type_outlier", "peer_group": "PAM04", "focus_node": 1,
        "status": "survived_thresholds", "control_tier": 3, "score": 7.0, "metric": "max_input_share",
        "robustness": {"passed_thresholds": 3, "available_thresholds": 4}, "bilateral_check": {"replicated": True},
    }]
    return nodes, edges, features, findings


def test_pam04_experiment_contains_measured_structure_and_candidates():
    nodes, edges, features, findings = _fixture()
    payload = build_pam04_experiment(nodes, edges, features, findings, min_synapses=3, top_input_channels=1)
    assert payload["available"] is True
    assert payload["cell_count"] == 2
    assert 1 in payload["candidate_ids"]
    names = [x["name"] for x in payload["input_channels"]]
    assert "SLP321" in names  # candidate-dominant channel is retained even under a small top-N cap
    cell = next(x for x in payload["cells"] if x["body_id"] == 1)
    assert cell["top_inputs"][0]["body_id"] == 10
    assert cell["top_outputs"][0]["type"] == "MBON02"


def test_pam04_experiment_marks_dynamic_and_receptor_layers_as_assumptions():
    nodes, edges, features, findings = _fixture()
    payload = build_pam04_experiment(nodes, edges, features, findings)
    assert "phenomenological" in payload["model"]["evidence"]["dynamics"]
    assert payload["model"]["evidence"]["receptor_expression"].startswith("not assigned")
    assert any("not direct measurements" in x for x in payload["assumptions"])


def test_pam04_experiment_gracefully_handles_snapshot_without_pam04():
    nodes, edges, features, findings = _fixture()
    features = features.assign(type="PAM05")
    payload = build_pam04_experiment(nodes, edges, features, findings)
    assert payload["available"] is False
    assert payload["experiment_id"] == "001_pam04"


def test_pam04_experiment_exposes_channel_members_for_live_3d_context():
    nodes, edges, features, findings = _fixture()
    payload = build_pam04_experiment(nodes, edges, features, findings, min_synapses=3)
    slp = next(x for x in payload["input_channels"] if x["name"] == "SLP321")
    assert slp["members"][0]["body_id"] == 10
    assert any(t["body_id"] == 1 for t in slp["members"][0]["targets"])
    mbon = next(x for x in payload["output_channels"] if x["name"] == "MBON02")
    assert mbon["members"][0]["body_id"] == 20
    assert {x["body_id"] for x in mbon["members"][0]["sources"]} == {1, 2}
