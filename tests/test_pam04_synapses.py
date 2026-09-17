import json
from pathlib import Path

from dsc import synapses


def test_pam04_synapse_manifest_is_bounded_and_directional(tmp_path, monkeypatch):
    experiment = {
        "available": True,
        "candidate_ids": [1],
        "cells": [{
            "body_id": 1,
            "top_inputs": [{"body_id": 10}, {"body_id": 11}],
            "top_outputs": [{"body_id": 20}, {"body_id": 21}],
        }],
    }
    exp = tmp_path / "experiment.json"
    exp.write_text(json.dumps(experiment), encoding="utf-8")

    calls = []
    def fake_post(cypher, token=None, timeout=120, retries=3):
        calls.append(cypher)
        if "n.bodyId IN [10]" in cypher or "n.bodyId IN [10,11]" in cypher:
            row = [10, 1, 1, 2, 3, 4, 5, 6, 0.9, 0.8]
        else:
            row = [1, 20, 7, 8, 9, 10, 11, 12, 0.7, 0.6]
        return {
            "columns": ["pre", "post", "x_pre", "y_pre", "z_pre", "x_post", "y_post", "z_post", "confidence_pre", "confidence_post"],
            "data": [row],
        }
    monkeypatch.setattr(synapses, "_post_cypher", fake_post)
    out = tmp_path / "pam04_synapses.json"
    payload = synapses.build_pam04_synapse_manifest(exp, out, max_partners_per_direction=2, max_points_per_direction=25)
    assert payload["status"] == "ok"
    assert payload["total_points"] == 2
    rec = payload["candidates"]["1"]
    assert rec["input_points"][0]["pre"] == 10
    assert rec["output_points"][0]["post"] == 20
    assert len(calls) == 2
    assert "LIMIT 25" in calls[0]
    assert out.exists()
