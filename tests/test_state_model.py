import copy

import pandas as pd

from dsc.experiment_pam04 import build_pam04_experiment
from dsc.state_model import compare_pam04, default_parameters, normalize_parameters


def _experiment():
    nodes = pd.DataFrame([
        {"body_id": 1, "type": "PAM04", "side": "L", "status": "Traced", "nt": "dopamine", "nt_confidence": 1.0},
        {"body_id": 2, "type": "PAM04", "side": "R", "status": "Traced", "nt": "dopamine", "nt_confidence": 1.0},
        {"body_id": 10, "type": "SLP321", "side": "L", "status": "Traced", "nt": "acetylcholine", "nt_confidence": 1.0},
        {"body_id": 11, "type": "MBON13", "side": "R", "status": "Traced", "nt": "glutamate", "nt_confidence": 1.0},
        {"body_id": 20, "type": "MBON02", "side": "L", "status": "Traced", "nt": "glutamate", "nt_confidence": 1.0},
    ])
    edges = pd.DataFrame([
        {"pre": 10, "post": 1, "weight": 20}, {"pre": 11, "post": 1, "weight": 3},
        {"pre": 10, "post": 2, "weight": 3}, {"pre": 11, "post": 2, "weight": 16},
        {"pre": 1, "post": 20, "weight": 8}, {"pre": 2, "post": 20, "weight": 9},
    ])
    features = pd.DataFrame([
        {"body_id": 1, "type": "PAM04", "side": "L", "in_strength": 23.0, "out_strength": 8.0, "in_partner_count": 2.0, "out_partner_count": 1.0, "max_input_share": 20/23, "max_output_share": 1.0, "input_entropy": 0.6, "output_entropy": 0.0},
        {"body_id": 2, "type": "PAM04", "side": "R", "in_strength": 19.0, "out_strength": 9.0, "in_partner_count": 2.0, "out_partner_count": 1.0, "max_input_share": 16/19, "max_output_share": 1.0, "input_entropy": 0.65, "output_entropy": 0.0},
    ])
    findings = [{"kind":"within_type_outlier","peer_group":"PAM04","focus_node":1,"status":"survived_thresholds","control_tier":3,"score":7.0,"metric":"max_input_share"}]
    return build_pam04_experiment(nodes, edges, features, findings, top_input_channels=2, top_output_channels=2)


def test_state_model_real_matches_its_baseline():
    experiment = _experiment()
    params = default_parameters(experiment)
    params["stimulus"] = "SLP321"
    result = compare_pam04(experiment, params)
    assert result["summary"]["delta_peak_dopamine"] == 0.0
    assert result["baseline"]["dopamine"] == result["intervention"]["dopamine"]
    assert result["summary"]["candidate_simulated_events"] >= 0
    assert result["summary"]["candidate_activity_auc"] > 0


def test_state_model_knockout_changes_candidate_response_deterministically():
    experiment = _experiment()
    scenario = default_parameters(experiment)
    scenario.update({"mode": "knockout", "candidate": "1", "stimulus": "SLP321", "stimulus_strength": 3.0})
    a = compare_pam04(experiment, scenario)
    b = compare_pam04(experiment, copy.deepcopy(scenario))
    assert a["intervention"]["dopamine"] == b["intervention"]["dopamine"]
    assert a["summary"]["intervention_peak_dopamine"] < a["summary"]["baseline_peak_dopamine"]


def test_browser_export_shape_is_accepted_by_python_reproducer():
    experiment = _experiment()
    scenario = {"parameters": {"mode": "amplify", "candidate": "1", "candidate_gain": 2.5, "stimulus": "SLP321", "receptor_gains": {"Dop2R": 1.4}}}
    params = normalize_parameters(experiment, scenario)
    assert params["mode"] == "amplify"
    assert params["candidate_gain"] == 2.5
    assert params["receptor_gains"]["Dop2R"] == 1.4
