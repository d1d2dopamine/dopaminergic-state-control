from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .features import compute_core_features, robust_zscores

FEATURE_LABELS = {
    "in_strength": "unusual total input strength",
    "out_strength": "unusual total output strength",
    "in_partner_count": "unusual number of input partners",
    "out_partner_count": "unusual number of output partners",
    "input_entropy": "unusual input distribution",
    "output_entropy": "unusual output distribution",
    "max_input_share": "input dominated by an unusual single partner",
    "max_output_share": "output dominated by an unusual single partner",
    "reciprocal_partner_fraction": "unusual reciprocity",
    "reciprocal_output_weight_fraction": "unusual reciprocal output weight",
    "input_type_diversity": "unusual input cell-type diversity",
    "output_type_diversity": "unusual output cell-type diversity",
    "log_strength_balance": "unusual input/output balance",
}


@dataclass(frozen=True)
class DiscoveryResult:
    features: pd.DataFrame
    findings: list[dict]
    core_ids: set[int]


def select_dopamine_core(nodes: pd.DataFrame, config: dict) -> set[int]:
    traced_only = bool(config["dataset"].get("traced_only", True))
    nt = nodes["nt"].fillna("").astype(str).str.lower().str.strip()
    # ``nt`` in real snapshots is the MaleCNS consensus_nt field. Prediction
    # confidence must not override or filter a curated consensus assignment.
    mask = nt.isin({"dopamine", "da"})
    if traced_only:
        status = nodes["status"].fillna("").astype(str).str.lower()
        mask &= status.eq("traced")
    return set(nodes.loc[mask, "body_id"].astype(int).tolist())


def discover(nodes: pd.DataFrame, edges: pd.DataFrame, config: dict) -> DiscoveryResult:
    min_synapses = int(config["dataset"].get("min_synapses", 1))
    edges = edges.loc[edges["weight"].astype(int) >= min_synapses].copy()
    core = select_dopamine_core(nodes, config)
    if not core:
        raise ValueError("No dopaminergic core nodes were selected. Check nt labels/confidence/status.")

    features = compute_core_features(nodes, edges, core)
    threshold = float(config["discovery"].get("robust_z_threshold", 3.5))
    top_findings = int(config["discovery"].get("top_findings", 50))
    findings: list[dict] = []

    feature_cols = [c for c in FEATURE_LABELS if c in features.columns]
    score_columns: list[str] = []
    for col in feature_cols:
        zcol = f"z_{col}"
        features[zcol] = robust_zscores(features[col])
        score_columns.append(zcol)
        for _, row in features.loc[features[zcol].abs() >= threshold].iterrows():
            z = float(row[zcol])
            body = int(row["body_id"])
            findings.append(
                {
                    "id": f"feature-{col}-{body}",
                    "kind": "structural_outlier",
                    "title": FEATURE_LABELS[col].capitalize(),
                    "summary": (
                        f"Dopaminergic neuron {row['type']} ({body}) is an outlier for {col}: "
                        f"value={float(row[col]):.3g}, robust z={z:.2f}."
                    ),
                    "score": abs(z),
                    "direction": "high" if z > 0 else "low",
                    "metric": col,
                    "observed": float(row[col]),
                    "robust_z": z,
                    "focus_node": body,
                    "related_nodes": [],
                    "status": "candidate",
                    "interpretation": "Structural anomaly only; biological meaning requires a targeted test and literature check.",
                }
            )

    if score_columns:
        abs_scores = features[score_columns].abs()
        features["anomaly_score"] = abs_scores.max(axis=1)
    else:
        features["anomaly_score"] = 0.0

    # Convergence: non-core partners receiving from several dopamine neurons.
    incoming_core: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e in edges.itertuples(index=False):
        pre, post, weight = int(e.pre), int(e.post), int(e.weight)
        if pre in core and post not in core:
            incoming_core[post].append((pre, weight))

    min_sources = int(config["discovery"].get("convergence_min_core_sources", 3))
    conv = []
    for target, sources in incoming_core.items():
        unique_sources = {s for s, _ in sources}
        if len(unique_sources) >= min_sources:
            conv.append((target, len(unique_sources), sum(w for _, w in sources), sorted(unique_sources)))
    conv.sort(key=lambda x: (x[1], x[2]), reverse=True)
    node_types = nodes.set_index("body_id")["type"].astype(str).to_dict()
    for rank, (target, n_sources, total_weight, sources) in enumerate(
        conv[: int(config["discovery"].get("convergence_top_n", 10))], start=1
    ):
        # Score is deliberately descriptive, not a p-value.
        score = float(n_sources) + min(float(total_weight) / 100.0, 5.0)
        findings.append(
            {
                "id": f"convergence-{target}",
                "kind": "dopamine_convergence",
                "title": "Strong dopaminergic convergence candidate",
                "summary": (
                    f"Target {node_types.get(target, 'unknown')} ({target}) receives >= {min_synapses} synapse edges "
                    f"from {n_sources} dopaminergic neurons (combined weight {total_weight})."
                ),
                "score": score,
                "rank": rank,
                "focus_node": int(target),
                "related_nodes": [int(x) for x in sources],
                "status": "candidate",
                "interpretation": "Candidate only. A null model controlling for degree and anatomy is required before calling this unexpected.",
            }
        )

    findings.sort(key=lambda f: float(f.get("score", 0.0)), reverse=True)
    findings = findings[:top_findings]
    return DiscoveryResult(features=features, findings=findings, core_ids=core)
