import json

import pandas as pd

from dsc.discovery import discover
from dsc.anatomy import anatomical_pool_columns as _anatomical_pool_columns, parse_roi_info as _parse_roi_info, parse_roi_value as _parse_roi_value
from dsc.synapses import _spatial_metrics


def _cfg():
    return {
        "dataset": {"min_synapses": 3, "traced_only": True},
        "discovery": {
            "top_findings": 50,
            "peer_min_type_size": 99,
            "peer_robust_z_threshold": 3.5,
            "robustness_thresholds": [1, 3, 5, 10],
            "robustness_min_pass_fraction": 0.75,
            "bilateral_ratio_threshold": 999,
            "side_min_each": 99,
            "convergence_min_core_sources": 3,
            "convergence_fdr": 1.0,
            "convergence_min_enrichment": 1.0,
        },
    }


def test_roi_parser_accepts_list_string_and_roiinfo():
    assert _parse_roi_value(["MB", "SMP", "MB"]) == ["MB", "SMP"]
    assert _parse_roi_value('["MB","SMP"]') == ["MB", "SMP"]
    ins, outs = _parse_roi_info({"MB": {"pre": 5, "post": 2}, "SMP": {"pre": 0, "post": 3}})
    assert ins == ["MB", "SMP"]
    assert outs == ["MB"]


def test_anatomical_pool_is_output_to_input_roi_overlap():
    merged = pd.DataFrame([
        {"body_id": 1, "output_rois": json.dumps(["MB"]), "input_rois": "[]"},
        {"body_id": 2, "output_rois": json.dumps(["MB", "SMP"]), "input_rois": "[]"},
        {"body_id": 3, "output_rois": json.dumps(["VNC"]), "input_rois": "[]"},
        {"body_id": 10, "output_rois": "[]", "input_rois": json.dumps(["MB"])},
    ])
    nodes = merged.loc[merged.body_id.eq(10)].copy()
    out, meta = _anatomical_pool_columns(nodes, merged, {1, 2, 3, 10}, {1})
    row = out.iloc[0]
    assert row.anatomical_pool_size == 2
    assert row.anatomical_dopamine_pool_size == 1
    assert row.input_roi_count == 1
    assert meta["distinct_output_rois"] == 3


def test_convergence_prefers_roi_availability_null():
    nodes = []
    for body in [1, 2, 3]:
        nodes.append({
            "body_id": body, "type": "DAN", "side": "L", "status": "Traced", "nt": "dopamine",
            "full_in_partner_count_t1": 0, "full_in_partner_count_t3": 0,
            "full_in_partner_count_t5": 0, "full_in_partner_count_t10": 0,
            "anatomical_pool_size": 10, "anatomical_dopamine_pool_size": 3, "input_roi_count": 1,
        })
    nodes.append({
        "body_id": 50, "type": "TARGET", "side": "R", "status": "Traced", "nt": "acetylcholine",
        "full_in_partner_count_t1": 5, "full_in_partner_count_t3": 5,
        "full_in_partner_count_t5": 5, "full_in_partner_count_t10": 5,
        "anatomical_pool_size": 10, "anatomical_dopamine_pool_size": 3, "input_roi_count": 1,
    })
    edge_rows = []
    for body in [1, 2, 3]:
        edge_rows.append({"pre": body, "post": 50, "weight": 10})
    result = discover(pd.DataFrame(nodes), pd.DataFrame(edge_rows), _cfg(), {"eligible_traced_neurons": 100})
    finding = next(f for f in result.findings if f["kind"] == "dopamine_input_enrichment")
    assert finding["null_model"] == "roi_overlap"
    assert finding["expected_sources"] == 1.5
    assert finding["status"] == "survived_controls"
    assert finding["robustness"]["passed_thresholds"] == 4


def test_convergence_labels_global_fallback():
    nodes = []
    for body in [1, 2, 3]:
        nodes.append({"body_id": body, "type": "DAN", "side": "L", "status": "Traced", "nt": "dopamine"})
    nodes.append({"body_id": 50, "type": "TARGET", "side": "R", "status": "Traced", "nt": "acetylcholine"})
    edges = pd.DataFrame([{"pre": body, "post": 50, "weight": 10} for body in [1, 2, 3]])
    cfg = _cfg(); cfg["discovery"]["robustness_thresholds"] = [3]
    result = discover(pd.DataFrame(nodes), edges, cfg, {"eligible_traced_neurons": 100})
    finding = next(f for f in result.findings if f["kind"] == "dopamine_input_enrichment")
    assert finding["null_model"] == "global_degree"
    assert finding["status"] == "global_only"


def test_spatial_metric_detects_source_specific_territories():
    points = []
    for i in range(20):
        points.append({"pre": 1, "post_xyz": [i % 3, i // 3, 0]})
        points.append({"pre": 2, "post_xyz": [100 + i % 3, 100 + i // 3, 0]})
    result = _spatial_metrics(points, scale_to_nm=1.0, permutations=99, seed=7)
    assert result["available"]
    assert result["source_segregation_eta2"] > 0.9
    assert result["source_label_permutation_p"] <= 0.05
