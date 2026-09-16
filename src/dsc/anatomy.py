from __future__ import annotations

import ast
import json
from collections import defaultdict
from typing import Iterable

import pandas as pd


def parse_roi_value(value) -> list[str]:
    """Normalise ROI list encodings from MaleCNS/neuPrint exports."""
    if value is None:
        return []
    if hasattr(value, "tolist") and not isinstance(value, str):
        try:
            value = value.tolist()
        except Exception:
            pass
    if isinstance(value, dict):
        value = list(value.keys())
    if isinstance(value, (list, tuple, set)):
        return sorted({str(x).strip() for x in value if str(x).strip() and str(x).lower() not in {"none", "nan"}})
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "nan", "unknown", "[]", "{}"}:
            return []
        parsed = None
        if text[:1] in "[{(":
            for loader in (json.loads, ast.literal_eval):
                try:
                    parsed = loader(text)
                    break
                except Exception:
                    continue
        if parsed is not None:
            return parse_roi_value(parsed)
        if "," in text:
            return sorted({x.strip().strip("'\"") for x in text.split(",") if x.strip().strip("'\"")})
        return [text]
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass
    return [str(value)]


def parse_roi_info(value) -> tuple[list[str], list[str]]:
    """Derive input/output ROI lists from a neuPrint-style roiInfo object."""
    if value is None:
        return [], []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return [], []
        parsed = None
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
                break
            except Exception:
                continue
        value = parsed if parsed is not None else {}
    if not isinstance(value, dict):
        return [], []
    inputs, outputs = [], []
    for roi, counts in value.items():
        if not isinstance(counts, dict):
            continue
        try:
            if float(counts.get("post", 0) or 0) > 0:
                inputs.append(str(roi))
            if float(counts.get("pre", 0) or 0) > 0:
                outputs.append(str(roi))
        except (TypeError, ValueError):
            continue
    return sorted(set(inputs)), sorted(set(outputs))


def roi_json(values: Iterable[str]) -> str:
    return json.dumps(sorted({str(x) for x in values if str(x)}), separators=(",", ":"))


def decode_rois(value) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return tuple(str(x) for x in parsed if str(x)) if isinstance(parsed, list) else ()
        except Exception:
            return tuple(parse_roi_value(value))
    return tuple(parse_roi_value(value))


def anatomical_pool_columns(
    nodes: pd.DataFrame,
    merged: pd.DataFrame,
    eligible_ids: set[int],
    core_ids: set[int],
) -> tuple[pd.DataFrame, dict]:
    """Attach ROI-overlap source-availability pools to bounded snapshot nodes.

    A source is available when one of its output ROIs overlaps one target input
    ROI. This is a necessary-but-not-sufficient anatomical condition, not a
    probabilistic wiring model.
    """
    eligible = merged.loc[merged["body_id"].isin(eligible_ids), ["body_id", "output_rois"]]
    by_roi: dict[str, set[int]] = defaultdict(set)
    source_rows_with_roi = 0
    for row in eligible.itertuples(index=False):
        rois = decode_rois(row.output_rois)
        if rois:
            source_rows_with_roi += 1
        for roi in rois:
            by_roi[roi].add(int(row.body_id))

    cache: dict[tuple[str, ...], tuple[int, int]] = {}

    def pool(input_rois_value) -> tuple[int, int]:
        key = tuple(sorted(set(decode_rois(input_rois_value))))
        if not key:
            return 0, 0
        if key in cache:
            return cache[key]
        candidates: set[int] = set()
        for roi in key:
            candidates.update(by_roi.get(roi, ()))
        result = (len(candidates), len(candidates.intersection(core_ids)))
        cache[key] = result
        return result

    pool_sizes, core_sizes, input_counts = [], [], []
    values = nodes["input_rois"] if "input_rois" in nodes.columns else ["[]"] * len(nodes)
    for value in values:
        rois = decode_rois(value)
        n, k = pool(value)
        input_counts.append(len(rois))
        pool_sizes.append(n)
        core_sizes.append(k)

    nodes = nodes.copy()
    nodes["input_roi_count"] = pd.Series(input_counts, index=nodes.index, dtype="int64")
    nodes["anatomical_pool_size"] = pd.Series(pool_sizes, index=nodes.index, dtype="int64")
    nodes["anatomical_dopamine_pool_size"] = pd.Series(core_sizes, index=nodes.index, dtype="int64")
    meta = {
        "source_neurons_with_output_rois": int(source_rows_with_roi),
        "eligible_source_neurons": int(len(eligible)),
        "distinct_output_rois": int(len(by_roi)),
        "snapshot_targets_with_anatomical_pool": int(sum(1 for n in pool_sizes if n > 0)),
        "snapshot_nodes": int(len(nodes)),
    }
    return nodes, meta


# Private aliases retained so old imports/tests from the development branch keep working.
_parse_roi_value = parse_roi_value
_parse_roi_info = parse_roi_info
_roi_json = roi_json
_decode_rois = decode_rois
_anatomical_pool_columns = anatomical_pool_columns
