from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from .features import robust_zscores
from .subtypes import pam04_subtype


DEFAULT_MODEL = {
    "model_name": "PAM04 phenomenological rate + dopamine/receptor sandbox",
    "dt_ms": 20,
    "duration_ms": 3000,
    "pulse_start_ms": 450,
    "pulse_duration_ms": 900,
    "cell_tau_ms": 120,
    "dopamine_tau_ms": 380,
    "activation_threshold": 0.34,
    "activation_slope": 8.0,
    "baseline_input": 0.08,
    "dopamine_tone": 0.04,
    "dat_clearance": 1.0,
    "visual_event_rate_hz": 28.0,
    "visual_pulse_travel_ms": 260,
    "receptors": {
        "Dop1R1": {
            "family": "D1-like",
            "gain": 1.0,
            "half_activation": 0.36,
            "coupling_prior": 1.0,
        },
        "Dop1R2": {
            "family": "D1-like",
            "gain": 0.85,
            "half_activation": 0.52,
            "coupling_prior": 1.0,
        },
        "Dop2R": {
            "family": "D2-like",
            "gain": 0.9,
            "half_activation": 0.24,
            "coupling_prior": -1.0,
        },
    },
    "evidence": {
        "connectivity": "MaleCNS v1.0 synapse-count structure at the configured edge threshold",
        "dynamics": "phenomenological exploratory model; time constants and activation function are not measured PAM04 physiology",
        "receptor_expression": "not assigned per target cell in this experiment",
        "receptor_parameters": "normalized exploratory parameters; D1-like/D2-like coupling sign is a receptor-family prior, not a cell-specific causal measurement",
    },
}


def _text(value: Any, fallback: str = "unknown") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return fallback
    value = str(value).strip()
    return value if value and value.lower() != "nan" else fallback


def _partner_record(body: int, weight: int, node_meta: dict[int, dict], share: float) -> dict:
    meta = node_meta.get(int(body), {})
    return {
        "body_id": int(body),
        "weight": int(weight),
        "share": float(share),
        "type": _text(meta.get("type")),
        "side": _text(meta.get("side"), ""),
        "class": _text(meta.get("class")),
        "superclass": _text(meta.get("superclass")),
    }


def _candidate_findings(findings: list[dict]) -> dict[int, dict]:
    selected: dict[int, dict] = {}
    for finding in findings:
        if finding.get("kind") != "within_type_outlier" or str(finding.get("peer_group")) != "PAM04":
            continue
        body = int(finding["focus_node"])
        # Keep the most highly controlled/highest-score PAM04 finding per body.
        rank = (
            int(finding.get("control_tier", 0)),
            float(finding.get("score", 0.0)),
        )
        current = selected.get(body)
        current_rank = (
            int(current.get("control_tier", 0)),
            float(current.get("score", 0.0)),
        ) if current else (-1, -1.0)
        if rank > current_rank:
            selected[body] = finding
    return selected


def build_pam04_experiment(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    features: pd.DataFrame,
    findings: list[dict],
    min_synapses: int = 3,
    top_input_channels: int = 18,
    top_output_channels: int = 14,
    top_partners_per_cell: int = 12,
    top_channel_members: int = 12,
) -> dict:
    """Build a compact browser-ready dossier/sandbox for Experiment 001.

    The structural layer is measured connectome data. The dynamic and receptor
    layers are explicitly phenomenological and are never written back as findings.
    """
    pam = features.loc[features["type"].astype(str).eq("PAM04")].copy()
    if pam.empty:
        return {
            "available": False,
            "experiment_id": "001_pam04",
            "title": "PAM04 input specialization",
            "reason": "No PAM04 neurons are present in this snapshot.",
            "model": DEFAULT_MODEL,
        }

    pam_ids = [int(x) for x in pam["body_id"].tolist()]
    pam_set = set(pam_ids)
    filtered = edges.loc[edges["weight"].astype(int) >= int(min_synapses), ["pre", "post", "weight"]].copy()
    filtered[["pre", "post", "weight"]] = filtered[["pre", "post", "weight"]].astype(int)

    node_meta = nodes.set_index("body_id", drop=False).to_dict("index")
    incoming = filtered.loc[filtered["post"].isin(pam_set)].copy()
    outgoing = filtered.loc[filtered["pre"].isin(pam_set)].copy()
    incoming["channel"] = incoming["pre"].map(lambda x: _text(node_meta.get(int(x), {}).get("type")))
    outgoing["channel"] = outgoing["post"].map(lambda x: _text(node_meta.get(int(x), {}).get("type")))

    candidate_by_body = _candidate_findings(findings)
    candidate_ids = [
        body for body, finding in candidate_by_body.items()
        if finding.get("status") in {"survived_controls", "survived_thresholds"}
    ]
    if not candidate_ids:
        fallback = pam.sort_values("max_input_share", ascending=False)
        for side in ["L", "R"]:
            subset = fallback.loc[fallback["side"].astype(str).str.upper().eq(side)]
            if not subset.empty:
                candidate_ids.append(int(subset.iloc[0]["body_id"]))
    candidate_ids = list(dict.fromkeys(candidate_ids))

    max_share_z = robust_zscores(pam["max_input_share"])
    pam["max_input_share_z"] = max_share_z
    for side in ["L", "R"]:
        subset = pam.loc[pam["side"].astype(str).str.upper().eq(side)].sort_values("max_input_share_z", ascending=False)
        if not subset.empty:
            body = int(subset.iloc[0]["body_id"])
            if body not in candidate_ids:
                candidate_ids.append(body)

    input_totals = incoming.groupby("channel")["weight"].sum().sort_values(ascending=False)
    output_totals = outgoing.groupby("channel")["weight"].sum().sort_values(ascending=False)
    input_names = input_totals.head(max(1, int(top_input_channels))).index.tolist()
    output_names = output_totals.head(max(1, int(top_output_channels))).index.tolist()
    for body in candidate_ids:
        strongest = incoming.loc[incoming["post"].eq(int(body))].sort_values("weight", ascending=False)
        if not strongest.empty:
            channel = str(strongest.iloc[0]["channel"])
            if channel not in input_names:
                input_names.append(channel)

    # Add an explicit aggregate bucket so the compact simulator does not silently
    # discard the long tail of real connectivity.
    if len(input_totals) > len(input_names):
        input_names.append("other")
    if len(output_totals) > len(output_names):
        output_names.append("other")

    cell_index = {body: i for i, body in enumerate(pam_ids)}
    input_matrix = np.zeros((len(input_names), len(pam_ids)), dtype=float)
    output_matrix = np.zeros((len(output_names), len(pam_ids)), dtype=float)
    input_name_index = {name: i for i, name in enumerate(input_names) if name != "other"}
    output_name_index = {name: i for i, name in enumerate(output_names) if name != "other"}
    input_other = input_names.index("other") if "other" in input_names else None
    output_other = output_names.index("other") if "other" in output_names else None

    for row in incoming.itertuples(index=False):
        ci = cell_index[int(row.post)]
        ri = input_name_index.get(str(row.channel), input_other)
        if ri is not None:
            input_matrix[ri, ci] += float(row.weight)
    for row in outgoing.itertuples(index=False):
        ci = cell_index[int(row.pre)]
        ri = output_name_index.get(str(row.channel), output_other)
        if ri is not None:
            output_matrix[ri, ci] += float(row.weight)

    cell_records = []
    for _, row in pam.iterrows():
        body = int(row["body_id"])
        inc = incoming.loc[incoming["post"].eq(body)].sort_values("weight", ascending=False)
        out = outgoing.loc[outgoing["pre"].eq(body)].sort_values("weight", ascending=False)
        inc_total = int(inc["weight"].sum())
        out_total = int(out["weight"].sum())
        finding = candidate_by_body.get(body)
        meta = node_meta.get(body, {})
        known_subtype = pam04_subtype(meta.get("hemibrain_type"), meta.get("synonyms"), meta.get("supertype"))
        cell_records.append({
            "body_id": body,
            "side": _text(row.get("side"), ""),
            "known_subtype": known_subtype,
            "cross_dataset_identity": {
                "flywire_type": _text(meta.get("flywire_type"), ""),
                "hemibrain_type": _text(meta.get("hemibrain_type"), ""),
                "supertype": _text(meta.get("supertype"), ""),
                "hemilineage": _text(meta.get("hemilineage"), ""),
                "dimorphism": _text(meta.get("dimorphism"), ""),
                "synonyms": _text(meta.get("synonyms"), ""),
            },
            "candidate": body in candidate_ids,
            "candidate_status": finding.get("status") if finding else None,
            "candidate_metric": finding.get("metric") if finding else None,
            "candidate_score": float(finding.get("score", 0.0)) if finding else None,
            "bilateral_check": finding.get("bilateral_check") if finding else None,
            "robustness": finding.get("robustness") if finding else None,
            "metrics": {
                "in_strength": float(row.get("in_strength", 0.0)),
                "out_strength": float(row.get("out_strength", 0.0)),
                "in_partner_count": float(row.get("in_partner_count", 0.0)),
                "out_partner_count": float(row.get("out_partner_count", 0.0)),
                "max_input_share": float(row.get("max_input_share", 0.0)),
                "max_input_share_z": float(row.get("max_input_share_z", 0.0)),
                "max_output_share": float(row.get("max_output_share", 0.0)),
                "input_entropy": float(row.get("input_entropy", 0.0)),
                "output_entropy": float(row.get("output_entropy", 0.0)),
            },
            "top_inputs": [
                _partner_record(int(r.pre), int(r.weight), node_meta, int(r.weight) / inc_total if inc_total else 0.0)
                for r in inc.head(int(top_partners_per_cell)).itertuples(index=False)
            ],
            "top_outputs": [
                _partner_record(int(r.post), int(r.weight), node_meta, int(r.weight) / out_total if out_total else 0.0)
                for r in out.head(int(top_partners_per_cell)).itertuples(index=False)
            ],
        })

    # Re-test the discovery metric inside any explicitly annotated legacy PAM04
    # subtype. This is the first falsification step: an exact-type outlier can be
    # explained by known subtype structure rather than a new within-subtype motif.
    subtype_rows = []
    subtype_groups: dict[str, list[dict]] = defaultdict(list)
    for cell in cell_records:
        if cell.get("known_subtype"):
            subtype_groups[str(cell["known_subtype"])].append(cell)
    for subtype, group in sorted(subtype_groups.items()):
        vals = pd.Series([float(c["metrics"]["max_input_share"]) for c in group], dtype=float)
        zs = robust_zscores(vals) if len(group) >= 4 else np.full(len(group), np.nan)
        for cell, z in zip(group, zs):
            cell["within_subtype_max_input_share_z"] = None if not np.isfinite(z) else float(z)
            if cell.get("candidate"):
                if len(group) < 4:
                    explanation = "subtype_too_small"
                elif abs(float(z)) >= 3.5:
                    explanation = "persists_within_known_subtype"
                else:
                    explanation = "compatible_with_known_subtype_structure"
                cell["subtype_resolution"] = {
                    "status": explanation,
                    "subtype": subtype,
                    "peer_n": len(group),
                    "within_subtype_robust_z": None if not np.isfinite(z) else float(z),
                }
        subtype_rows.append({
            "subtype": subtype,
            "n": len(group),
            "left": sum(str(c.get("side", "")).upper() == "L" for c in group),
            "right": sum(str(c.get("side", "")).upper() == "R" for c in group),
            "median_max_input_share": float(vals.median()),
            "tested_within_subtype": len(group) >= 4,
        })
    for cell in cell_records:
        if cell.get("candidate") and not cell.get("known_subtype"):
            cell["subtype_resolution"] = {
                "status": "known_subtype_unresolved",
                "subtype": None,
                "peer_n": 0,
                "within_subtype_robust_z": None,
            }

    def input_members(name: str) -> list[dict]:
        if name == "other":
            return []
        subset = incoming.loc[incoming["channel"].astype(str).eq(str(name))]
        records = []
        for body, group in subset.groupby("pre"):
            group = group.groupby("post", as_index=False)["weight"].sum().sort_values("weight", ascending=False)
            total = int(group["weight"].sum())
            rec = _partner_record(int(body), total, node_meta, total / max(1, int(subset["weight"].sum())))
            rec["targets"] = [{"body_id": int(r.post), "weight": int(r.weight)} for r in group.head(12).itertuples(index=False)]
            records.append(rec)
        records.sort(key=lambda x: (-int(x["weight"]), int(x["body_id"])))
        return records[: max(1, int(top_channel_members))]

    def output_members(name: str) -> list[dict]:
        if name == "other":
            return []
        subset = outgoing.loc[outgoing["channel"].astype(str).eq(str(name))]
        records = []
        for body, group in subset.groupby("post"):
            group = group.groupby("pre", as_index=False)["weight"].sum().sort_values("weight", ascending=False)
            total = int(group["weight"].sum())
            rec = _partner_record(int(body), total, node_meta, total / max(1, int(subset["weight"].sum())))
            rec["sources"] = [{"body_id": int(r.pre), "weight": int(r.weight)} for r in group.head(12).itertuples(index=False)]
            records.append(rec)
        records.sort(key=lambda x: (-int(x["weight"]), int(x["body_id"])))
        return records[: max(1, int(top_channel_members))]

    input_channels = []
    for idx, name in enumerate(input_names):
        weights = input_matrix[idx].astype(float)
        input_channels.append({
            "name": name,
            "total_weight": float(weights.sum()),
            "weights": weights.tolist(),
            "active_cells": int(np.count_nonzero(weights)),
            "members": input_members(str(name)),
        })
    output_channels = []
    for idx, name in enumerate(output_names):
        weights = output_matrix[idx].astype(float)
        output_channels.append({
            "name": name,
            "total_weight": float(weights.sum()),
            "weights": weights.tolist(),
            "active_cells": int(np.count_nonzero(weights)),
            "members": output_members(str(name)),
        })

    values = pam["max_input_share"].astype(float)
    distribution = {
        "metric": "max_input_share",
        "median": float(values.median()),
        "q1": float(values.quantile(0.25)),
        "q3": float(values.quantile(0.75)),
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "cells": [
            {
                "body_id": int(r.body_id),
                "side": _text(r.side, ""),
                "value": float(r.max_input_share),
                "robust_z": float(r.max_input_share_z),
            }
            for r in pam.sort_values("max_input_share", ascending=False).itertuples(index=False)
        ],
    }

    return {
        "available": True,
        "experiment_id": "001_pam04",
        "title": "PAM04 input specialization",
        "dataset": "male-cns:v1.0",
        "primary_edge_threshold": int(min_synapses),
        "type": "PAM04",
        "cell_count": int(len(pam_ids)),
        "left_count": int((pam["side"].astype(str).str.upper() == "L").sum()),
        "right_count": int((pam["side"].astype(str).str.upper() == "R").sum()),
        "candidate_ids": [int(x) for x in candidate_ids],
        "known_subtypes": subtype_rows,
        "cells": cell_records,
        "input_channels": input_channels,
        "output_channels": output_channels,
        "distribution": distribution,
        "model": DEFAULT_MODEL,
        "assumptions": [
            "Synapse counts are used as structural weights; they are not direct measurements of synaptic efficacy.",
            "The browser simulator is a normalized rate model for counterfactual comparison, not a biophysical reconstruction of PAM04 membrane dynamics.",
            "Dopamine concentration, DAT clearance and receptor activation use normalized units.",
            "Dop1R1/Dop1R2/Dop2R are not assigned to individual downstream cells here because cell-specific receptor abundance is not present in the MaleCNS connectome snapshot.",
            "A simulated effect is a model sensitivity result, not evidence that the same effect occurs in a living fly.",
            "Legacy PAM04 subtype labels are taken only from cross-dataset/hemibrain annotations when explicitly available; connectivity is not used to invent a subtype label.",
            "Animated pulse fronts and event rasters are deterministic visualisations derived from the rate model; they are not recorded action potentials or measured conduction delays.",
        ],
    }
