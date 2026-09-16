from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd


def _entropy(weights: list[float]) -> float:
    total = float(sum(weights))
    if total <= 0:
        return 0.0
    p = np.asarray(weights, dtype=float) / total
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def compute_core_features(nodes: pd.DataFrame, edges: pd.DataFrame, core_ids: set[int]) -> pd.DataFrame:
    edge_rows = edges.to_dict("records")
    incoming: dict[int, list[tuple[int, int]]] = defaultdict(list)
    outgoing: dict[int, list[tuple[int, int]]] = defaultdict(list)
    edge_lookup: dict[tuple[int, int], int] = {}
    for e in edge_rows:
        pre, post, weight = int(e["pre"]), int(e["post"]), int(e["weight"])
        outgoing[pre].append((post, weight))
        incoming[post].append((pre, weight))
        edge_lookup[(pre, post)] = edge_lookup.get((pre, post), 0) + weight

    node_meta = nodes.set_index("body_id").to_dict("index")
    records: list[dict] = []
    for body in sorted(core_ids):
        ins = incoming.get(body, [])
        outs = outgoing.get(body, [])
        in_strength = sum(w for _, w in ins)
        out_strength = sum(w for _, w in outs)
        reciprocal_out_weight = sum(w for partner, w in outs if (partner, body) in edge_lookup)
        reciprocal_partner_count = sum(1 for partner, _ in outs if (partner, body) in edge_lookup)
        out_weights = [w for _, w in outs]
        in_weights = [w for _, w in ins]
        out_types = {str(node_meta.get(p, {}).get("type", "unknown")) for p, _ in outs}
        in_types = {str(node_meta.get(p, {}).get("type", "unknown")) for p, _ in ins}
        meta = node_meta.get(body, {})
        records.append(
            {
                "body_id": body,
                "type": str(meta.get("type", "unknown")),
                "side": str(meta.get("side", "unknown")),
                "in_strength": float(in_strength),
                "out_strength": float(out_strength),
                "in_partner_count": float(len(ins)),
                "out_partner_count": float(len(outs)),
                "input_entropy": _entropy(in_weights),
                "output_entropy": _entropy(out_weights),
                "max_input_share": (max(in_weights) / in_strength) if in_strength else 0.0,
                "max_output_share": (max(out_weights) / out_strength) if out_strength else 0.0,
                "reciprocal_partner_fraction": (reciprocal_partner_count / len(outs)) if outs else 0.0,
                "reciprocal_output_weight_fraction": (reciprocal_out_weight / out_strength) if out_strength else 0.0,
                "input_type_diversity": float(len(in_types)),
                "output_type_diversity": float(len(out_types)),
                "log_strength_balance": math.log1p(out_strength) - math.log1p(in_strength),
            }
        )
    return pd.DataFrame.from_records(records)


def robust_zscores(series: pd.Series) -> pd.Series:
    values = series.astype(float)
    median = float(values.median())
    mad = float((values - median).abs().median())
    if mad == 0.0:
        # Fall back to IQR-scaled deviation; if still degenerate, all scores are zero.
        q1, q3 = values.quantile([0.25, 0.75]).tolist()
        scale = float(q3 - q1) / 1.349 if q3 > q1 else 0.0
        if scale == 0.0:
            return pd.Series(np.zeros(len(values)), index=values.index)
        return (values - median) / scale
    return 0.67448975 * (values - median) / mad
