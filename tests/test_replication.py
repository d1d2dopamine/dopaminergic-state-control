import pandas as pd

from dsc.replication import analyze_pam04_connectivity, male_cns_from_experiment
from dsc.subtypes import pam04_subtype


def test_pam04_subtype_only_uses_explicit_label():
    assert pam04_subtype("PAM04-dd") == "PAM04-dd"
    assert pam04_subtype("foo; PAM04_can") == "PAM04-can"
    assert pam04_subtype("PAM04") is None
    assert pam04_subtype("") is None


def test_external_analysis_detects_bilateral_within_subtype_outliers():
    rows = []
    ids = [f"n{i}" for i in range(10)]
    for i, rid in enumerate(ids):
        rows.append({
            "id": rid,
            "cell_type": "PAM04",
            "side": "left" if i < 5 else "right",
            "hemibrain": "PAM04-dd",
            "proofread": "TRUE",
        })
    meta = pd.DataFrame(rows)
    edges = []
    # Most cells receive four balanced inputs. n0 and n5 receive one highly
    # dominant input while retaining the same order of total input.
    for i, rid in enumerate(ids):
        weights = [40, 2, 2, 2] if i in {0, 5} else [12 + (i % 3), 11, 10, 9]
        for j, weight in enumerate(weights):
            edges.append({"pre": f"src{j}", "post": rid, "count": weight})
    result = analyze_pam04_connectivity(
        meta,
        pd.DataFrame(edges),
        dataset="synthetic",
        id_col="id",
        type_col="cell_type",
        side_col="side",
        hemibrain_type_col="hemibrain",
        pre_col="pre",
        post_col="post",
        weight_col="count",
        min_count=1,
        proofread_col="proofread",
        outlier_z=3.0,
        min_subtype_peers=4,
    )
    assert result["pam04_cells"] == 10
    assert result["motif"]["within_subtype_bilateral"] is True
    subtype = result["subtypes"][0]
    assert set(subtype["within_subtype_outliers"]) == {"n0", "n5"}


def test_malecns_subtype_resolution_retests_candidates():
    cells = []
    for i in range(8):
        value = 0.4 if i == 0 else 0.1 + i * 0.002
        cells.append({
            "body_id": i + 1,
            "side": "L" if i < 4 else "R",
            "known_subtype": "PAM04-dd",
            "candidate": i == 0,
            "metrics": {"max_input_share": value, "max_input_share_z": 5.0 if i == 0 else 0.0, "in_strength": 100, "in_partner_count": 10},
        })
    result = male_cns_from_experiment({"available": True, "cells": cells}, outlier_z=3.0, min_subtype_peers=4)
    candidate = next(c for c in result["cells"] if c.get("candidate"))
    assert candidate["within_subtype_outlier"] is True


def test_global_bilateral_outliers_do_not_count_as_subtype_replication():
    from dsc.replication import _replication_overall

    overall = _replication_overall({
        "male_cns": {"connectivity_tested": True},
        "banc": {
            "connectivity_tested": True,
            "subtypes": [],
            "motif": {"global_bilateral": True, "within_subtype_bilateral": False},
        },
        "flywire": {
            "connectivity_tested": True,
            "subtypes": [],
            "motif": {"global_bilateral": True, "within_subtype_bilateral": False},
        },
    })
    assert overall["status"] == "external_subtype_resolution_insufficient"
    assert overall["external_connectomes_with_bilateral_within_subtype_motif"] == 0
