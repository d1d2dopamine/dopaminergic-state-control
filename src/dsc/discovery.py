from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .features import compute_core_features, robust_zscores
from .stats import benjamini_hochberg, benjamini_hochberg_total, hypergeom_sf

FEATURE_LABELS = {
    "in_strength": "total input strength",
    "out_strength": "total output strength",
    "in_partner_count": "number of input partners",
    "out_partner_count": "number of output partners",
    "input_entropy": "input distribution entropy",
    "output_entropy": "output distribution entropy",
    "max_input_share": "largest single-input share",
    "max_output_share": "largest single-output share",
    "reciprocal_partner_fraction": "reciprocal partner fraction",
    "reciprocal_output_weight_fraction": "reciprocal output-weight fraction",
    "input_type_diversity": "input cell-type diversity",
    "output_type_diversity": "output cell-type diversity",
    "log_strength_balance": "input/output strength balance",
}

PRIMARY_ASYMMETRY_FEATURES = [
    "in_strength",
    "out_strength",
    "in_partner_count",
    "out_partner_count",
    "input_type_diversity",
    "output_type_diversity",
]

STATUS_PRIORITY = {
    "survived_controls": 4,
    "survived_thresholds": 3,
    "candidate": 2,
    "global_only": 1,
    "threshold_sensitive": 0,
}


@dataclass(frozen=True)
class DiscoveryResult:
    features: pd.DataFrame
    findings: list[dict]
    core_ids: set[int]


def select_dopamine_core(nodes: pd.DataFrame, config: dict) -> set[int]:
    traced_only = bool(config["dataset"].get("traced_only", True))
    nt = nodes["nt"].fillna("").astype(str).str.lower().str.strip()
    mask = nt.isin({"dopamine", "da"})
    if traced_only:
        status = nodes["status"].fillna("").astype(str).str.lower()
        mask &= status.eq("traced")
    return set(nodes.loc[mask, "body_id"].astype(int).tolist())


def _thresholds(config: dict, meta: dict) -> list[int]:
    primary = int(config["dataset"].get("min_synapses", 1))
    configured = config["discovery"].get("robustness_thresholds", meta.get("robustness_thresholds", [1, 3, 5, 10]))
    out = {primary}
    for value in configured:
        try:
            out.add(max(1, int(value)))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def _normal_side(value) -> str:
    text = str(value).strip().upper()
    if text in {"L", "LEFT"}:
        return "L"
    if text in {"R", "RIGHT"}:
        return "R"
    return ""


def _metric_z(frame: pd.DataFrame, typ: str, metric: str, body: int, min_group: int) -> tuple[float, float] | None:
    group = frame.loc[frame["type"].astype(str).eq(str(typ))]
    if len(group) < min_group or metric not in group.columns:
        return None
    z = robust_zscores(group[metric])
    match = group.index[group["body_id"].astype(int).eq(int(body))]
    if len(match) != 1:
        return None
    idx = match[0]
    return float(group.loc[idx, metric]), float(z.loc[idx])


def _peer_robustness(
    finding: dict,
    threshold_features: dict[int, pd.DataFrame],
    config: dict,
) -> dict:
    min_group = int(config["discovery"].get("peer_min_type_size", 6))
    z_threshold = float(config["discovery"].get("peer_robust_z_threshold", 3.5))
    min_fraction = float(config["discovery"].get("robustness_min_pass_fraction", 0.75))
    primary_sign = 1 if finding.get("direction") == "high" else -1
    evidence = []
    signs = []
    passed = 0
    for threshold, frame in sorted(threshold_features.items()):
        result = _metric_z(frame, finding["peer_group"], finding["metric"], int(finding["focus_node"]), min_group)
        if result is None:
            evidence.append({"threshold": int(threshold), "available": False})
            continue
        value, z = result
        passes = abs(z) >= z_threshold
        if passes:
            passed += 1
        if abs(z) > 1e-12:
            signs.append(1 if z > 0 else -1)
        evidence.append({
            "threshold": int(threshold),
            "available": True,
            "observed": float(value),
            "robust_z": float(z),
            "passes": bool(passes),
        })
    available = sum(1 for e in evidence if e.get("available"))
    fraction = passed / available if available else 0.0
    sign_consistent = bool(signs) and all(s == primary_sign for s in signs)
    stable = available > 0 and fraction >= min_fraction and sign_consistent
    return {
        "thresholds": evidence,
        "passed_thresholds": int(passed),
        "available_thresholds": int(available),
        "pass_fraction": float(fraction),
        "sign_consistent": bool(sign_consistent),
        "stable": bool(stable),
    }


def _bilateral_replication(features: pd.DataFrame, finding: dict, config: dict) -> dict:
    body = int(finding["focus_node"])
    typ = str(finding["peer_group"])
    metric = str(finding["metric"])
    group = features.loc[features["type"].astype(str).eq(typ)].copy()
    focus = group.loc[group["body_id"].astype(int).eq(body)]
    if len(focus) != 1:
        return {"available": False}
    focus_side = _normal_side(focus.iloc[0].get("side", ""))
    opposite = "R" if focus_side == "L" else "L" if focus_side == "R" else ""
    if not opposite:
        return {"available": False}
    z = robust_zscores(group[metric])
    group["_z"] = z
    opp = group.loc[group["side"].map(_normal_side).eq(opposite)]
    if opp.empty:
        return {"available": False, "focus_side": focus_side, "opposite_side": opposite}
    primary_z = float(finding.get("score", 0.0)) * (1 if finding.get("direction") == "high" else -1)
    sign = 1 if primary_z >= 0 else -1
    replication_z = float(config["discovery"].get("bilateral_replication_z", 2.5))
    replicated = opp.loc[(opp["_z"] * sign) >= replication_z]
    best = opp.iloc[int(np.argmax(np.abs(opp["_z"].to_numpy(float))))]
    return {
        "available": True,
        "focus_side": focus_side,
        "opposite_side": opposite,
        "opposite_n": int(len(opp)),
        "replicated": bool(len(replicated)),
        "replicate_ids": [int(x) for x in replicated["body_id"].tolist()[:6]],
        "strongest_opposite_id": int(best["body_id"]),
        "strongest_opposite_z": float(best["_z"]),
    }


def _dominant_share(features: pd.DataFrame, body: int, metric: str) -> tuple[float, str]:
    row = features.loc[features["body_id"].astype(int).eq(int(body))]
    if row.empty:
        return 0.0, "unknown"
    r = row.iloc[0]
    if metric.startswith("in_") or metric.startswith("input_") or metric == "max_input_share":
        return float(r.get("max_input_share", 0.0)), "input"
    if metric.startswith("out_") or metric.startswith("output_") or metric in {"max_output_share", "reciprocal_output_weight_fraction"}:
        return float(r.get("max_output_share", 0.0)), "output"
    iv = float(r.get("max_input_share", 0.0)); ov = float(r.get("max_output_share", 0.0))
    return (iv, "input") if iv >= ov else (ov, "output")


def _type_peer_outliers(
    features: pd.DataFrame,
    config: dict,
    threshold_features: dict[int, pd.DataFrame] | None = None,
) -> list[dict]:
    """Find neurons unusual relative to their own exact MaleCNS type.

    v0.4 also asks whether the same outlier survives several edge-weight
    thresholds and whether an opposite-side peer shows a similar deviation.
    """
    min_group = int(config["discovery"].get("peer_min_type_size", 6))
    threshold = float(config["discovery"].get("peer_robust_z_threshold", 3.5))
    dominant_flag = float(config["discovery"].get("dominant_partner_share_flag", 0.50))
    threshold_features = threshold_features or {}
    findings: list[dict] = []
    score = pd.Series(np.zeros(len(features)), index=features.index, dtype=float)

    for typ, group in features.groupby("type", dropna=False):
        if len(group) < min_group:
            continue
        candidates: dict[int, list[dict]] = defaultdict(list)
        for col, label in FEATURE_LABELS.items():
            if col not in group.columns:
                continue
            z = robust_zscores(group[col])
            features.loc[group.index, f"peer_z_{col}"] = z
            score.loc[group.index] = np.maximum(score.loc[group.index], z.abs())
            for idx, row in group.loc[z.abs() >= threshold].iterrows():
                body = int(row["body_id"])
                candidates[body].append({
                    "metric": col,
                    "label": label,
                    "z": float(z.loc[idx]),
                    "value": float(row[col]),
                })

        peers = [int(x) for x in group["body_id"].tolist()]
        for body, metrics in candidates.items():
            metrics.sort(key=lambda m: abs(m["z"]), reverse=True)
            primary = metrics[0]
            related = [x for x in peers if x != body][:12]
            finding = {
                "id": f"peer-{primary['metric']}-{body}",
                "kind": "within_type_outlier",
                "title": f"Within-type outlier: {typ}",
                "summary": (
                    f"{typ} neuron {body} differs from the other {len(group)-1} neurons of the same type "
                    f"for {primary['label']}: value={primary['value']:.3g}, within-type robust z={primary['z']:.2f}."
                ),
                "score": abs(primary["z"]),
                "direction": "high" if primary["z"] > 0 else "low",
                "metric": primary["metric"],
                "observed": primary["value"],
                "peer_group": str(typ),
                "peer_group_size": int(len(group)),
                "other_outlier_metrics": [
                    {"metric": m["metric"], "robust_z": m["z"], "observed": m["value"]}
                    for m in metrics[1:]
                ],
                "focus_node": body,
                "related_nodes": related,
                "status": "candidate",
                "interpretation": "Exact-type structural candidate; technical robustness and bilateral evidence are reported separately and do not prove a biological mechanism.",
            }
            if threshold_features:
                robustness = _peer_robustness(finding, threshold_features, config)
                finding["robustness"] = robustness
                finding["status"] = "survived_thresholds" if robustness["stable"] else "threshold_sensitive"
            bilateral = _bilateral_replication(features, finding, config)
            finding["bilateral_check"] = bilateral
            share, share_side = _dominant_share(features, body, primary["metric"])
            finding["dominant_partner_share"] = float(share)
            finding["dominant_partner_direction"] = share_side
            finding["quality_flags"] = ["large_single_partner_share"] if share >= dominant_flag else []
            finding["control_tier"] = STATUS_PRIORITY.get(finding["status"], 0)
            findings.append(finding)

    features["peer_anomaly_score"] = score
    return findings


def _bilateral_asymmetry(features: pd.DataFrame, config: dict) -> list[dict]:
    """Surface unusually asymmetric left/right members of the same exact type."""
    ratio_threshold = float(config["discovery"].get("bilateral_ratio_threshold", 3.0))
    min_abs_strength = float(config["discovery"].get("bilateral_min_absolute_strength", 20.0))
    findings: list[dict] = []

    for typ, group in features.groupby("type", dropna=False):
        left = group[group["side"].map(_normal_side).eq("L")]
        right = group[group["side"].map(_normal_side).eq("R")]
        if len(left) != 1 or len(right) != 1:
            continue
        a, b = left.iloc[0], right.iloc[0]
        best = None
        for col in PRIMARY_ASYMMETRY_FEATURES:
            av, bv = float(a[col]), float(b[col])
            hi, lo = max(abs(av), abs(bv)), min(abs(av), abs(bv))
            ratio = (hi + 1.0) / (lo + 1.0)
            if col.endswith("strength") and hi < min_abs_strength:
                continue
            if best is None or ratio > best[0]:
                best = (ratio, col, av, bv)
        if best is None or best[0] < ratio_threshold:
            continue
        ratio, col, av, bv = best
        focus = int(a["body_id"] if abs(av) >= abs(bv) else b["body_id"])
        partner = int(b["body_id"] if focus == int(a["body_id"]) else a["body_id"])
        findings.append({
            "id": f"bilateral-{str(typ)}-{focus}-{partner}",
            "kind": "bilateral_asymmetry",
            "title": f"Bilateral asymmetry: {typ}",
            "summary": (
                f"The left/right {typ} pair differs {ratio:.2f}x on {FEATURE_LABELS[col]} "
                f"(L={av:.3g}, R={bv:.3g})."
            ),
            "score": float(math.log2(ratio) + 2.0),
            "metric": col,
            "ratio": float(ratio),
            "focus_node": focus,
            "related_nodes": [partner],
            "status": "candidate",
            "control_tier": STATUS_PRIORITY["candidate"],
            "interpretation": "A bilateral structural mismatch in the same type. Check segmentation/annotation quality before biological interpretation.",
        })
    return findings


def _type_side_asymmetry(features: pd.DataFrame, config: dict) -> list[dict]:
    """Permutation test for left/right shifts within multi-neuron exact types."""
    min_each = int(config["discovery"].get("side_min_each", 3))
    permutations = int(config["discovery"].get("side_permutations", 1000))
    q_threshold = float(config["discovery"].get("side_fdr", 0.05))
    rng = np.random.default_rng(int(config["discovery"].get("random_seed", 20260916)))
    tests: list[dict] = []
    for typ, group in features.groupby("type", dropna=False):
        left = group[group["side"].map(_normal_side).eq("L")]
        right = group[group["side"].map(_normal_side).eq("R")]
        if len(left) < min_each or len(right) < min_each:
            continue
        for col in PRIMARY_ASYMMETRY_FEATURES:
            lv = left[col].to_numpy(float); rv = right[col].to_numpy(float)
            obs = abs(float(np.median(lv) - np.median(rv)))
            if obs == 0:
                continue
            joined = np.concatenate([lv, rv]); n_left = len(lv); exceed = 0
            for _ in range(permutations):
                perm = rng.permutation(joined)
                diff = abs(float(np.median(perm[:n_left]) - np.median(perm[n_left:])))
                if diff >= obs - 1e-12:
                    exceed += 1
            p = (exceed + 1.0) / (permutations + 1.0)
            tests.append({
                "type": str(typ), "metric": col, "p": p, "observed_difference": obs,
                "left_median": float(np.median(lv)), "right_median": float(np.median(rv)),
                "left_ids": [int(x) for x in left["body_id"].tolist()],
                "right_ids": [int(x) for x in right["body_id"].tolist()],
            })
    qvals = benjamini_hochberg([t["p"] for t in tests])
    findings = []
    for t, q in zip(tests, qvals):
        if q > q_threshold:
            continue
        scale = float(np.median(np.abs(features.loc[features["type"].astype(str).eq(t["type"]), t["metric"]].to_numpy(float)))) + 1.0
        effect = t["observed_difference"] / scale
        ids = (t["left_ids"][:6] + t["right_ids"][:6])
        focus = ids[0]
        findings.append({
            "id": f"side-shift-{t['type']}-{t['metric']}",
            "kind": "type_side_shift",
            "title": f"Left/right shift within {t['type']}",
            "summary": (
                f"{t['type']} shows a left/right shift in {FEATURE_LABELS[t['metric']]}: "
                f"median L={t['left_median']:.3g}, R={t['right_median']:.3g}; permutation BH q={q:.3g}."
            ),
            "score": float(-math.log10(max(q, 1e-50)) + effect),
            "metric": t["metric"], "p_value": float(t["p"]), "q_value": float(q),
            "left_median": t["left_median"], "right_median": t["right_median"],
            "focus_node": int(focus), "related_nodes": [int(x) for x in ids[1:]],
            "status": "candidate",
            "control_tier": STATUS_PRIORITY["candidate"],
            "interpretation": "Exact-type left/right permutation candidate; inspect reconstruction quality and bilateral sampling before biological interpretation.",
        })
    return findings


def _degree_for_target(nodes_meta: dict, target: int, threshold: int, edges_at_threshold: pd.DataFrame, legacy_primary: bool = False) -> int:
    target_meta = nodes_meta.get(target, {})
    column = f"full_in_partner_count_t{threshold}"
    value = target_meta.get(column)
    if value is not None and not pd.isna(value):
        try:
            parsed = int(value)
            if parsed >= 0:
                return parsed
        except (TypeError, ValueError):
            pass
    if legacy_primary:
        legacy = target_meta.get("full_in_partner_count")
        if legacy is not None and not pd.isna(legacy):
            try:
                return max(0, int(legacy))
            except (TypeError, ValueError):
                pass
    # Legacy/demo fallback: bounded snapshot degree only.
    if edges_at_threshold.empty:
        return 0
    return int(edges_at_threshold.loc[edges_at_threshold["post"].astype(int).eq(target), "pre"].nunique())


def _null_parameters(target_meta: dict, d: int, k: int, global_n: int, global_k: int) -> tuple[int, int, str]:
    try:
        anatomy_n = int(target_meta.get("anatomical_pool_size", 0) or 0)
        anatomy_k = int(target_meta.get("anatomical_dopamine_pool_size", 0) or 0)
    except (TypeError, ValueError):
        anatomy_n = anatomy_k = 0
    # The observed draw must be possible under the availability pool. If source
    # ROI annotations are incomplete for this target, fail back to the global
    # degree null instead of silently forcing impossible parameters.
    if anatomy_n >= max(d, 1) and anatomy_k >= k and 0 < anatomy_k < anatomy_n:
        return anatomy_n, anatomy_k, "roi_overlap"
    return global_n, global_k, "global_degree"


def _convergence_rows_for_threshold(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    core: set[int],
    threshold: int,
    meta: dict,
) -> dict[int, dict]:
    filtered = edges.loc[edges["weight"].astype(int) >= int(threshold)]
    incoming_core: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e in filtered.itertuples(index=False):
        pre, post, weight = int(e.pre), int(e.post), int(e.weight)
        if pre in core and post not in core:
            incoming_core[post].append((pre, weight))

    node_meta = nodes.set_index("body_id").to_dict("index")
    global_n = int(meta.get("eligible_traced_neurons") or max(len(nodes), len(core) + 1))
    global_k = int(len(core))
    rows: list[dict] = []
    for target, sources in incoming_core.items():
        source_weights = defaultdict(int)
        for source, weight in sources:
            source_weights[int(source)] += int(weight)
        ordered_sources = [s for s, _ in sorted(source_weights.items(), key=lambda kv: (-kv[1], kv[0]))]
        k = len(source_weights)
        legacy_primary_threshold = int(meta.get("analysis_edge_threshold_synapses", meta.get("edge_threshold_synapses", -1)) or -1)
        d = max(k, _degree_for_target(node_meta, target, threshold, filtered, legacy_primary=(threshold == legacy_primary_threshold)))
        target_meta = node_meta.get(target, {})
        N, K, null_model = _null_parameters(target_meta, d, k, global_n, global_k)
        draws = min(d, N)
        p = hypergeom_sf(k - 1, N, K, draws)
        expected = draws * (K / N) if N else 0.0
        global_expected = min(d, global_n) * (global_k / global_n) if global_n else 0.0
        rows.append({
            "target": int(target),
            "k": int(k),
            "d": int(d),
            "expected": float(expected),
            "global_expected": float(global_expected),
            "p": float(p),
            "total_weight": int(sum(source_weights.values())),
            "source_ids_by_weight": ordered_sources,
            "target_type": str(target_meta.get("type", "unknown")),
            "null_model": null_model,
            "null_population": int(N),
            "null_dopamine_population": int(K),
            "input_roi_count": int(target_meta.get("input_roi_count", 0) or 0),
        })

    total_target_tests = int(meta.get("eligible_traced_neurons") or max(len(nodes), len(rows)))
    qvals = benjamini_hochberg_total([r["p"] for r in rows], total_target_tests)
    result: dict[int, dict] = {}
    for row, q in zip(rows, qvals):
        row["q"] = float(q)
        row["enrichment"] = float((row["k"] + 0.5) / (row["expected"] + 0.5))
        row["global_enrichment"] = float((row["k"] + 0.5) / (row["global_expected"] + 0.5))
        result[int(row["target"])] = row
    return result


def _convergence_enrichment(nodes: pd.DataFrame, edges: pd.DataFrame, core: set[int], config: dict, meta: dict) -> list[dict]:
    """Dopamine-input enrichment under an ROI-availability null when possible.

    Primary null (v0.4): eligible source outputRois must overlap target inputRois,
    while the target's whole-connectome in-degree is held fixed. If ROI metadata
    is missing/incomplete, the older global degree-controlled null is retained
    and the finding is explicitly marked global_only.
    """
    thresholds = _thresholds(config, meta)
    primary_threshold = int(config["dataset"].get("min_synapses", 1))
    rows_by_threshold = {
        threshold: _convergence_rows_for_threshold(nodes, edges, core, threshold, meta)
        for threshold in thresholds
    }
    primary_rows = rows_by_threshold.get(primary_threshold, {})
    q_threshold = float(config["discovery"].get("convergence_fdr", 0.05))
    min_enrichment = float(config["discovery"].get("convergence_min_enrichment", 2.0))
    min_sources = int(config["discovery"].get("convergence_min_core_sources", 3))
    min_fraction = float(config["discovery"].get("robustness_min_pass_fraction", 0.75))

    out = []
    for target, row in primary_rows.items():
        if row["k"] < min_sources or row["q"] > q_threshold or row["enrichment"] < min_enrichment:
            continue
        robustness = []
        passed = 0
        for threshold in thresholds:
            r = rows_by_threshold[threshold].get(target)
            if r is None:
                robustness.append({"threshold": int(threshold), "available": False, "passes": False})
                continue
            passes = bool(r["k"] >= min_sources and r["q"] <= q_threshold and r["enrichment"] >= min_enrichment)
            passed += int(passes)
            robustness.append({
                "threshold": int(threshold),
                "available": True,
                "observed_sources": int(r["k"]),
                "expected_sources": float(r["expected"]),
                "enrichment": float(r["enrichment"]),
                "q_value": float(r["q"]),
                "null_model": str(r["null_model"]),
                "passes": passes,
            })
        available = sum(1 for r in robustness if r.get("available"))
        pass_fraction = passed / available if available else 0.0
        stable = available > 0 and pass_fraction >= min_fraction
        anatomy = row["null_model"] == "roi_overlap"
        if anatomy and stable:
            status = "survived_controls"
        elif anatomy:
            status = "threshold_sensitive"
        else:
            status = "global_only"
        score = min(50.0, -math.log10(max(row["q"], 1e-50))) + math.log2(max(row["enrichment"], 1e-12))
        display_sources = row["source_ids_by_weight"][:16]
        null_label = "ROI-availability" if anatomy else "global degree"
        out.append({
            "id": f"convergence-enrichment-{target}",
            "kind": "dopamine_input_enrichment",
            "title": "Dopamine input enrichment",
            "summary": (
                f"{row['target_type']} ({target}) receives input from {row['k']} dopamine neurons; "
                f"{null_label} expectation={row['expected']:.2f} across {row['d']} traced presynaptic partners "
                f"(enrichment={row['enrichment']:.2f}x, BH q={row['q']:.2g})."
            ),
            "score": float(score),
            "observed_sources": int(row["k"]),
            "expected_sources": float(row["expected"]),
            "global_expected_sources": float(row["global_expected"]),
            "full_input_partner_count": int(row["d"]),
            "enrichment": float(row["enrichment"]),
            "global_enrichment": float(row["global_enrichment"]),
            "p_value": float(row["p"]),
            "q_value": float(row["q"]),
            "null_model": row["null_model"],
            "null_population": int(row["null_population"]),
            "null_dopamine_population": int(row["null_dopamine_population"]),
            "input_roi_count": int(row["input_roi_count"]),
            "focus_node": int(target),
            "related_nodes": [int(x) for x in display_sources],
            "source_ids_by_weight": [int(x) for x in row["source_ids_by_weight"]],
            "all_source_count": int(row["k"]),
            "robustness": {
                "thresholds": robustness,
                "passed_thresholds": int(passed),
                "available_thresholds": int(available),
                "pass_fraction": float(pass_fraction),
                "stable": bool(stable),
            },
            "status": status,
            "control_tier": STATUS_PRIORITY.get(status, 0),
            "interpretation": (
                "Uses an ROI-overlap availability null plus whole-connectome target degree and threshold robustness. "
                "This is still a structural candidate, not evidence that dopamine causes a behavioral state."
                if anatomy else
                "ROI availability metadata was insufficient for this target, so only the older global degree null was available. Treat this as a lower-priority lead."
            ),
        })
    return out


def discover(nodes: pd.DataFrame, edges: pd.DataFrame, config: dict, meta: dict | None = None) -> DiscoveryResult:
    meta = meta or {}
    primary_min_synapses = int(config["dataset"].get("min_synapses", 1))
    core = select_dopamine_core(nodes, config)
    if not core:
        raise ValueError("No dopaminergic core nodes were selected. Check nt/status labels.")

    thresholds = _thresholds(config, meta)
    threshold_features = {
        threshold: compute_core_features(nodes, edges.loc[edges["weight"].astype(int) >= threshold].copy(), core)
        for threshold in thresholds
    }
    features = threshold_features[primary_min_synapses]
    findings: list[dict] = []
    findings.extend(_type_peer_outliers(features, config, threshold_features))
    findings.extend(_bilateral_asymmetry(features, config))
    findings.extend(_type_side_asymmetry(features, config))
    findings.extend(_convergence_enrichment(nodes, edges, core, config, meta))

    # Scores from different detectors are not on the same statistical scale.
    # Rank controls first within each method, then interleave methods so a single
    # test family cannot occupy the entire review queue.
    method_order = [
        "within_type_outlier",
        "bilateral_asymmetry",
        "type_side_shift",
        "dopamine_input_enrichment",
    ]
    by_method: dict[str, list[dict]] = {}
    for kind in method_order:
        group = [f for f in findings if f.get("kind") == kind]
        group.sort(
            key=lambda f: (
                int(f.get("control_tier", STATUS_PRIORITY.get(str(f.get("status", "candidate")), 0))),
                float(f.get("score", 0.0)),
                str(f.get("id", "")),
            ),
            reverse=True,
        )
        for rank, f in enumerate(group, start=1):
            f["method_rank"] = rank
            f["method_candidate_count"] = len(group)
        by_method[kind] = group

    top_findings = int(config["discovery"].get("top_findings", 50))
    interleaved: list[dict] = []
    rank = 0
    while len(interleaved) < top_findings:
        added = False
        for kind in method_order:
            group = by_method[kind]
            if rank < len(group):
                interleaved.append(group[rank])
                added = True
                if len(interleaved) >= top_findings:
                    break
        if not added:
            break
        rank += 1
    for overall_rank, finding in enumerate(interleaved, start=1):
        finding["review_rank"] = overall_rank
    return DiscoveryResult(features=features, findings=interleaved, core_ids=core)
