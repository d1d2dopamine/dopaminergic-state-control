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


def _type_peer_outliers(features: pd.DataFrame, config: dict) -> list[dict]:
    """Find neurons unusual relative to their *own exact MaleCNS type*.

    One neuron becomes at most one finding: if it is extreme on several metrics,
    the strongest metric is shown and the others are retained as supporting
    metadata. This keeps the dashboard from being filled by repeated cards for
    the same reconstruction.
    """
    min_group = int(config["discovery"].get("peer_min_type_size", 6))
    threshold = float(config["discovery"].get("peer_robust_z_threshold", 3.5))
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
            findings.append({
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
                "interpretation": "Compared only with neurons carrying the same MaleCNS type label; still requires a targeted biological/technical check.",
            })

    features["peer_anomaly_score"] = score
    return findings

def _bilateral_asymmetry(features: pd.DataFrame, config: dict) -> list[dict]:
    """Surface unusually asymmetric left/right members of the same exact type."""
    ratio_threshold = float(config["discovery"].get("bilateral_ratio_threshold", 3.0))
    min_abs_strength = float(config["discovery"].get("bilateral_min_absolute_strength", 20.0))
    findings: list[dict] = []

    for typ, group in features.groupby("type", dropna=False):
        left = group[group["side"].astype(str).str.upper().eq("L")]
        right = group[group["side"].astype(str).str.upper().eq("R")]
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
        left = group[group["side"].astype(str).str.upper().eq("L")]
        right = group[group["side"].astype(str).str.upper().eq("R")]
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
    findings=[]
    for t,q in zip(tests,qvals):
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
            "score": float(-math.log10(max(q,1e-50)) + effect),
            "metric": t["metric"], "p_value": float(t["p"]), "q_value": float(q),
            "left_median": t["left_median"], "right_median": t["right_median"],
            "focus_node": int(focus), "related_nodes": [int(x) for x in ids[1:]],
            "status": "candidate",
            "interpretation": "Exact-type left/right permutation candidate; inspect reconstruction quality and bilateral sampling before biological interpretation.",
        })
    return findings

def _convergence_enrichment(nodes: pd.DataFrame, edges: pd.DataFrame, core: set[int], config: dict, meta: dict) -> list[dict]:
    """Test whether dopamine sources are over-represented among a target's inputs.

    Null: among the eligible traced neurons, presynaptic identities are mixed at
    random while holding the target's full traced in-degree fixed. This controls
    for a major v0.1 failure mode: generic high-degree hubs appearing interesting
    solely because they receive many inputs. It is still a global-mixing null and
    does not yet control for neuropil/anatomical availability.
    """
    incoming_core: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for e in edges.itertuples(index=False):
        pre, post, weight = int(e.pre), int(e.post), int(e.weight)
        if pre in core and post not in core:
            incoming_core[post].append((pre, weight))

    node_meta = nodes.set_index("body_id").to_dict("index")
    N = meta.get("eligible_traced_neurons")
    if N is None:
        # Demo/legacy fallback: this is explicitly weaker and is labeled below.
        N = int(max(len(nodes), len(core) + 1))
        degree_scope = "snapshot fallback"
    else:
        N = int(N)
        degree_scope = str(meta.get("degree_scope", "full traced graph"))
    K = int(len(core))
    min_sources = int(config["discovery"].get("convergence_min_core_sources", 3))
    rows: list[dict] = []
    fallback_degree = None
    if "full_in_partner_count" not in nodes.columns:
        fallback_degree = edges.groupby("post")["pre"].nunique().to_dict()

    for target, sources in incoming_core.items():
        unique = sorted({s for s, _ in sources})
        k = len(unique)
        target_meta = node_meta.get(target, {})
        d = int(target_meta.get("full_in_partner_count", 0) or 0)
        if d <= 0:
            # Legacy/demo snapshots do not carry whole-connectome degree.
            d = max(k, int((fallback_degree or {}).get(target, k)))
        p = hypergeom_sf(k - 1, N, K, min(d, N))
        expected = min(d, N) * (K / N)
        source_weights = defaultdict(int)
        for s, w in sources:
            source_weights[int(s)] += int(w)
        display_sources = [s for s, _ in sorted(source_weights.items(), key=lambda kv: (-kv[1], kv[0]))[:16]]
        rows.append({
            "target": int(target),
            "k": int(k),
            "d": int(d),
            "expected": float(expected),
            "p": float(p),
            "total_weight": int(sum(w for _, w in sources)),
            "sources": unique,
            "display_sources": display_sources,
            "target_type": str(target_meta.get("type", "unknown")),
            "degree_scope": degree_scope,
        })

    total_target_tests = int(meta.get("eligible_traced_neurons") or max(len(nodes), len(rows)))
    qvals = benjamini_hochberg_total([r["p"] for r in rows], total_target_tests)
    for r, q in zip(rows, qvals):
        r["q"] = q

    q_threshold = float(config["discovery"].get("convergence_fdr", 0.05))
    min_enrichment = float(config["discovery"].get("convergence_min_enrichment", 2.0))
    out = []
    for r in rows:
        enrichment = (r["k"] + 0.5) / (r["expected"] + 0.5)
        if r["k"] < min_sources or r["q"] > q_threshold or enrichment < min_enrichment:
            continue
        score = min(50.0, -math.log10(max(r["q"], 1e-50))) + math.log2(enrichment)
        out.append({
            "id": f"convergence-enrichment-{r['target']}",
            "kind": "dopamine_input_enrichment",
            "title": "Dopamine input enrichment",
            "summary": (
                f"{r['target_type']} ({r['target']}) receives input from {r['k']} dopamine neurons; "
                f"global degree-controlled expectation={r['expected']:.2f} across {r['d']} traced presynaptic partners "
                f"(enrichment={enrichment:.2f}x, BH q={r['q']:.2g})."
            ),
            "score": float(score),
            "observed_sources": int(r["k"]),
            "expected_sources": float(r["expected"]),
            "full_input_partner_count": int(r["d"]),
            "enrichment": float(enrichment),
            "p_value": float(r["p"]),
            "q_value": float(r["q"]),
            "focus_node": int(r["target"]),
            "related_nodes": [int(x) for x in r["display_sources"]],
            "all_source_count": int(r["k"]),
            "status": "candidate",
            "interpretation": (
                "Survives a global mixing null that controls for target in-degree and FDR correction against the full traced target universe. It does not yet control for neuropil/anatomical availability; treat as a lead, not a mechanism."
            ),
        })
    return out


def discover(nodes: pd.DataFrame, edges: pd.DataFrame, config: dict, meta: dict | None = None) -> DiscoveryResult:
    meta = meta or {}
    min_synapses = int(config["dataset"].get("min_synapses", 1))
    edges = edges.loc[edges["weight"].astype(int) >= min_synapses].copy()
    core = select_dopamine_core(nodes, config)
    if not core:
        raise ValueError("No dopaminergic core nodes were selected. Check nt/status labels.")

    features = compute_core_features(nodes, edges, core)
    findings: list[dict] = []
    findings.extend(_type_peer_outliers(features, config))
    findings.extend(_bilateral_asymmetry(features, config))
    findings.extend(_type_side_asymmetry(features, config))
    findings.extend(_convergence_enrichment(nodes, edges, core, config, meta))

    # Scores from different detectors are not on the same statistical scale.
    # Do not let one method (especially tiny p-values from enrichment tests)
    # crowd every other method out of the site. Rank within method and interleave.
    method_order = [
        "within_type_outlier",
        "bilateral_asymmetry",
        "type_side_shift",
        "dopamine_input_enrichment",
    ]
    by_method: dict[str, list[dict]] = {}
    for kind in method_order:
        group = [f for f in findings if f.get("kind") == kind]
        group.sort(key=lambda f: (float(f.get("score", 0.0)), str(f.get("id", ""))), reverse=True)
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
    return DiscoveryResult(features=features, findings=interleaved, core_ids=core)
