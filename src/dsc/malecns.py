from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import pyarrow.ipc as ipc

from .anatomy import anatomical_pool_columns, parse_roi_info, parse_roi_value, roi_json
from .identity_metadata import hydrate_identity_metadata
from .roi_metadata import hydrate_roi_metadata

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES = {
    "annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "neurotransmitters": "body-neurotransmitters-male-cns-v1.0.feather",
    "edges": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}
DEFAULT_CONTROL_THRESHOLDS = (1, 3, 5, 10)


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.5"})
    with urllib.request.urlopen(req, timeout=120) as src, temp.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    temp.replace(destination)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def ensure_sources(raw_dir: str | Path, refresh: bool = False) -> dict[str, Path]:
    root = Path(raw_dir)
    paths: dict[str, Path] = {}
    for key, filename in FILES.items():
        path = root / filename
        if refresh or not path.exists():
            _download(f"{BASE}/{filename}", path)
        paths[key] = path
    return paths


def _find_column(columns: list[str], candidates: list[str]) -> str:
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    raise ValueError(f"None of {candidates} found in columns: {columns}")


def _optional_column(df: pd.DataFrame, candidates: list[str], default: str = "unknown") -> pd.Series:
    lower = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return df[lower[candidate.lower()]].fillna(default).astype(str)
    return pd.Series([default] * len(df), index=df.index, dtype="object")


def _read_annotations(path: Path) -> pd.DataFrame:
    df = feather.read_feather(path)
    columns = list(df.columns)
    lower = {c.lower(): c for c in columns}
    body = _find_column(columns, ["bodyId", "body", "body_id"])
    typ = _find_column(columns, ["type"])
    side = _optional_column(df, ["somaSide", "side"])
    status = _optional_column(df, ["status"])

    input_col = next((lower[x.lower()] for x in ["inputRois", "input_rois"] if x.lower() in lower), None)
    output_col = next((lower[x.lower()] for x in ["outputRois", "output_rois"] if x.lower() in lower), None)
    roi_info_col = next((lower[x.lower()] for x in ["roiInfo", "roi_info"] if x.lower() in lower), None)

    # The public annotation table may omit neuropil innervation entirely. Avoid
    # an expensive row-by-row pandas loop in that common case; the compact
    # neuPrint fallback below will hydrate the ROI metadata when needed.
    if not input_col and not output_col and not roi_info_col:
        input_rois = ["[]"] * len(df)
        output_rois = ["[]"] * len(df)
    else:
        input_values = df[input_col].tolist() if input_col else [None] * len(df)
        output_values = df[output_col].tolist() if output_col else [None] * len(df)
        roi_info_values = df[roi_info_col].tolist() if roi_info_col else [None] * len(df)
        input_rois: list[str] = []
        output_rois: list[str] = []
        for input_value, output_value, roi_info_value in zip(input_values, output_values, roi_info_values):
            ins = parse_roi_value(input_value) if input_col else []
            outs = parse_roi_value(output_value) if output_col else []
            if (not ins or not outs) and roi_info_col:
                fallback_in, fallback_out = parse_roi_info(roi_info_value)
                if not ins:
                    ins = fallback_in
                if not outs:
                    outs = fallback_out
            input_rois.append(roi_json(ins))
            output_rois.append(roi_json(outs))

    out = pd.DataFrame({
        "body_id": df[body].astype("int64"),
        "type": df[typ].fillna("unknown").astype(str),
        "side": side,
        "status": status,
        "superclass": _optional_column(df, ["superclass"]),
        "class": _optional_column(df, ["class"]),
        "subclass": _optional_column(df, ["subclass"]),
        "flywire_type": _optional_column(df, ["flywireType", "flywire_type"], default=""),
        "hemibrain_type": _optional_column(df, ["hemibrainType", "hemibrain_type"], default=""),
        "supertype": _optional_column(df, ["supertype"], default=""),
        "hemilineage": _optional_column(df, ["itoleeHl", "itoLeeHl", "hemilineage"], default=""),
        "dimorphism": _optional_column(df, ["dimorphism"], default=""),
        "synonyms": _optional_column(df, ["synonyms"], default=""),
        "input_rois": input_rois,
        "output_rois": output_rois,
    })
    return out.drop_duplicates("body_id")


def _read_nt(path: Path) -> pd.DataFrame:
    """Read MaleCNS transmitter annotations using the curated consensus field."""
    df = feather.read_feather(path)
    columns = list(df.columns)
    body = _find_column(columns, ["body", "bodyId", "body_id"])
    consensus = _find_column(columns, ["consensus_nt", "consensusNt"])
    predicted = next((c for c in ["predicted_nt", "predictedNt"] if c in df.columns), None)
    conf = next((c for c in ["predicted_nt_confidence", "predictedNtConfidence"] if c in df.columns), None)
    celltype = next((c for c in ["celltype_predicted_nt", "celltypePredictedNt"] if c in df.columns), None)
    out = pd.DataFrame({
        "body_id": df[body].astype("int64"),
        "nt": df[consensus].fillna("unknown").astype(str),
        "nt_confidence": pd.to_numeric(df[conf], errors="coerce").fillna(0.0) if conf else 0.0,
        "predicted_nt": df[predicted].fillna("unknown").astype(str) if predicted else "unknown",
        "celltype_predicted_nt": df[celltype].fillna("unknown").astype(str) if celltype else "unknown",
    })
    return out.drop_duplicates("body_id")


def _edge_batches(path: Path):
    source = pa.memory_map(str(path), "r")
    reader = ipc.RecordBatchFileReader(source)
    for i in range(reader.num_record_batches):
        yield reader.get_batch(i)


def _counter_add(counter: Counter[int], values: pd.Series) -> None:
    for key, value in values.items():
        counter[int(key)] += int(value)


def build_dopamine_snapshot(
    raw_dir: str | Path,
    output_dir: str | Path,
    min_synapses: int = 3,
    traced_only: bool = True,
    refresh: bool = False,
    snapshot_floor: int = 1,
    control_thresholds: Iterable[int] = DEFAULT_CONTROL_THRESHOLDS,
    roi_cache: str | Path | None = None,
    identity_cache: str | Path | None = None,
) -> dict:
    paths = ensure_sources(raw_dir, refresh=refresh)
    annotations = _read_annotations(paths["annotations"])
    nt = _read_nt(paths["neurotransmitters"])
    merged = annotations.merge(nt, on="body_id", how="left")
    merged["nt"] = merged["nt"].fillna("unknown")
    merged["nt_confidence"] = merged["nt_confidence"].fillna(0.0)

    traced_mask = merged["status"].astype(str).str.lower().eq("traced")
    eligible_ids = set(merged.loc[traced_mask, "body_id"].astype(int)) if traced_only else set(merged["body_id"].astype(int))
    merged, roi_metadata_meta = hydrate_roi_metadata(merged, eligible_ids, cache_path=roi_cache)
    merged, identity_metadata_meta = hydrate_identity_metadata(merged, cache_path=identity_cache)
    dopamine_mask = merged["nt"].astype(str).str.lower().str.strip().isin(["dopamine", "da"])
    if traced_only:
        dopamine_mask &= traced_mask
    core_ids = set(merged.loc[dopamine_mask, "body_id"].astype(int))
    if not core_ids:
        raise RuntimeError("No consensus dopamine neurons selected from current MaleCNS files. Inspect source schema/labels.")
    if len(core_ids) > 1000:
        raise RuntimeError(
            f"Selected {len(core_ids)} consensus dopamine neurons; this is implausible for pinned MaleCNS v1.0. "
            "Check neurotransmitter schema before continuing."
        )

    thresholds = sorted({max(1, int(x)) for x in control_thresholds} | {max(1, int(min_synapses))})
    floor = min(max(1, int(snapshot_floor)), min(thresholds))
    tables = []
    full_in_partner_count = {t: Counter() for t in thresholds}
    full_in_strength = {t: Counter() for t in thresholds}
    eligible_array_cache = None
    core_array_cache = None

    for batch in _edge_batches(paths["edges"]):
        names = batch.schema.names
        pre_col = _find_column(names, ["body_pre", "pre"])
        post_col = _find_column(names, ["body_post", "post"])
        weight_col = _find_column(names, ["weight", "count"])
        pre = batch.column(names.index(pre_col))
        post = batch.column(names.index(post_col))
        weight = batch.column(names.index(weight_col))

        if eligible_array_cache is None or eligible_array_cache.type != pre.type:
            eligible_array_cache = pa.array(sorted(eligible_ids), type=pre.type)
        eligible_pre = pc.is_in(pre, value_set=eligible_array_cache)

        # Whole-connectome target degrees are retained at all robustness
        # thresholds, while the bounded one-hop snapshot itself uses the floor.
        for threshold in thresholds:
            strong = pc.greater_equal(weight, pa.scalar(int(threshold), type=weight.type))
            degree_batch = batch.filter(pc.and_(eligible_pre, strong)).select([post_col, weight_col]).to_pandas()
            if not degree_batch.empty:
                grouped = degree_batch.groupby(post_col)[weight_col].agg(["size", "sum"])
                _counter_add(full_in_partner_count[threshold], grouped["size"])
                _counter_add(full_in_strength[threshold], grouped["sum"])

        if core_array_cache is None or core_array_cache.type != pre.type:
            core_array_cache = pa.array(sorted(core_ids), type=pre.type)
        core_touch = pc.or_(pc.is_in(pre, value_set=core_array_cache), pc.is_in(post, value_set=core_array_cache))
        floor_mask = pc.greater_equal(weight, pa.scalar(int(floor), type=weight.type))
        filtered = batch.filter(pc.and_(core_touch, floor_mask))
        if filtered.num_rows:
            tables.append(pa.Table.from_batches([filtered]).select([pre_col, post_col, weight_col]))

    if not tables:
        raise RuntimeError("No edges survived the dopamine one-hop filter.")
    table = pa.concat_tables(tables)
    edges = table.to_pandas().rename(columns={table.column_names[0]: "pre", table.column_names[1]: "post", table.column_names[2]: "weight"})
    edges = edges[["pre", "post", "weight"]].astype("int64")
    partner_ids = set(edges["pre"].astype(int)) | set(edges["post"].astype(int))
    nodes = merged.loc[merged["body_id"].isin(partner_ids)].copy()
    missing = sorted(partner_ids - set(nodes["body_id"].astype(int)))
    if missing:
        nodes = pd.concat([nodes, pd.DataFrame({
            "body_id": missing, "type": "unknown", "side": "unknown", "status": "unknown",
            "superclass": "unknown", "class": "unknown", "subclass": "unknown",
            "flywire_type": "", "hemibrain_type": "", "supertype": "", "hemilineage": "", "dimorphism": "", "synonyms": "",
            "input_rois": "[]", "output_rois": "[]",
            "nt": "unknown", "nt_confidence": 0.0, "predicted_nt": "unknown", "celltype_predicted_nt": "unknown",
        })], ignore_index=True)

    for threshold in thresholds:
        nodes[f"full_in_partner_count_t{threshold}"] = nodes["body_id"].map(
            lambda x, t=threshold: full_in_partner_count[t].get(int(x), 0)
        ).astype("int64")
        nodes[f"full_in_strength_t{threshold}"] = nodes["body_id"].map(
            lambda x, t=threshold: full_in_strength[t].get(int(x), 0)
        ).astype("int64")

    # Backwards-compatible primary columns used by older downstream tools.
    nodes["full_in_partner_count"] = nodes[f"full_in_partner_count_t{int(min_synapses)}"]
    nodes["full_in_strength"] = nodes[f"full_in_strength_t{int(min_synapses)}"]
    nodes, anatomical_meta = anatomical_pool_columns(nodes, merged, eligible_ids, core_ids)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    node_cols = [
        "body_id", "type", "side", "status", "superclass", "class", "subclass",
        "flywire_type", "hemibrain_type", "supertype", "hemilineage", "dimorphism", "synonyms",
        "input_rois", "output_rois", "input_roi_count", "anatomical_pool_size", "anatomical_dopamine_pool_size",
        "nt", "nt_confidence", "predicted_nt", "celltype_predicted_nt",
        "full_in_partner_count", "full_in_strength",
    ]
    for threshold in thresholds:
        node_cols.extend([f"full_in_partner_count_t{threshold}", f"full_in_strength_t{threshold}"])
    # Avoid duplicate primary columns when the primary threshold is in controls.
    node_cols = list(dict.fromkeys(node_cols))
    nodes[node_cols].sort_values("body_id").to_csv(out / "nodes.csv", index=False)
    edges.sort_values(["pre", "post"]).to_csv(out / "edges.csv", index=False)

    snapshot_meta = {
        "dataset": "male-cns:v1.0",
        "eligible_traced_neurons": int(len(eligible_ids)),
        "dopamine_core_count": int(len(core_ids)),
        "analysis_edge_threshold_synapses": int(min_synapses),
        "snapshot_edge_floor_synapses": int(floor),
        "robustness_thresholds": thresholds,
        "degree_scope": "all eligible presynaptic neurons in the full MaleCNS edge table, threshold-specific",
        "anatomical_null": {
            "method": "source outputRois intersect target inputRois",
            "scope": "necessary anatomical availability, not a contact-probability model",
            "roi_metadata": roi_metadata_meta,
            **anatomical_meta,
        },
        "identity_metadata": identity_metadata_meta,
    }
    (out / "snapshot_meta.json").write_text(json.dumps(snapshot_meta, indent=2), encoding="utf-8")

    lock = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "male-cns:v1.0",
        "source": "Official MaleCNS public flat-connectome bucket",
        "license": "CC-BY",
        "files": {
            key: {"url": f"{BASE}/{FILES[key]}", "bytes": p.stat().st_size, "sha256": _sha256(p)}
            for key, p in paths.items()
        },
        "selection": {
            "nt_selector": "consensus_nt == dopamine",
            "predicted_nt_confidence_used_for_selection": False,
            "min_synapses": int(min_synapses),
            "snapshot_floor": int(floor),
            "robustness_thresholds": thresholds,
            "traced_only": traced_only,
            "dopamine_core_count": len(core_ids),
            "snapshot_node_count": int(len(nodes)),
            "snapshot_edge_count": int(len(edges)),
            "eligible_traced_neurons": int(len(eligible_ids)),
            "anatomical_targets_available": anatomical_meta["snapshot_targets_with_anatomical_pool"],
            "roi_metadata_source": roi_metadata_meta.get("source"),
            "roi_metadata_output_coverage": roi_metadata_meta.get("after", {}).get("output_fraction", 0.0),
            "identity_metadata_source": identity_metadata_meta.get("source"),
        },
    }
    (out / "source.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return lock
