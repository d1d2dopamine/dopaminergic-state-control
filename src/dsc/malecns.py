from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import pyarrow.ipc as ipc

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES = {
    "annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "neurotransmitters": "body-neurotransmitters-male-cns-v1.0.feather",
    "edges": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.2"})
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
    body = _find_column(list(df.columns), ["bodyId", "body", "body_id"])
    typ = _find_column(list(df.columns), ["type"])
    side = _optional_column(df, ["somaSide", "side"])
    status = _optional_column(df, ["status"])
    out = pd.DataFrame({
        "body_id": df[body].astype("int64"),
        "type": df[typ].fillna("unknown").astype(str),
        "side": side,
        "status": status,
        "superclass": _optional_column(df, ["superclass"]),
        "class": _optional_column(df, ["class"]),
        "subclass": _optional_column(df, ["subclass"]),
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


def build_dopamine_snapshot(raw_dir: str | Path, output_dir: str | Path, min_synapses: int = 3,
                            traced_only: bool = True, refresh: bool = False) -> dict:
    paths = ensure_sources(raw_dir, refresh=refresh)
    annotations = _read_annotations(paths["annotations"])
    nt = _read_nt(paths["neurotransmitters"])
    merged = annotations.merge(nt, on="body_id", how="left")
    merged["nt"] = merged["nt"].fillna("unknown")
    merged["nt_confidence"] = merged["nt_confidence"].fillna(0.0)

    traced_mask = merged["status"].astype(str).str.lower().eq("traced")
    eligible_ids = set(merged.loc[traced_mask, "body_id"].astype(int)) if traced_only else set(merged["body_id"].astype(int))
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

    tables = []
    full_in_partner_count: Counter[int] = Counter()
    full_in_strength: Counter[int] = Counter()
    eligible_array_cache = None

    for batch in _edge_batches(paths["edges"]):
        names = batch.schema.names
        pre_col = _find_column(names, ["body_pre", "pre"])
        post_col = _find_column(names, ["body_post", "post"])
        weight_col = _find_column(names, ["weight", "count"])
        pre = batch.column(names.index(pre_col))
        post = batch.column(names.index(post_col))
        weight = batch.column(names.index(weight_col))

        # Full traced-input degree/strength at the same edge threshold. This is
        # needed for the convergence enrichment null; it prevents high-degree
        # targets from looking interesting merely because they receive many inputs.
        if eligible_array_cache is None or eligible_array_cache.type != pre.type:
            eligible_array_cache = pa.array(sorted(eligible_ids), type=pre.type)
        eligible_pre = pc.is_in(pre, value_set=eligible_array_cache)
        strong = pc.greater_equal(weight, pa.scalar(int(min_synapses), type=weight.type))
        degree_batch = batch.filter(pc.and_(eligible_pre, strong)).select([post_col, weight_col]).to_pandas()
        if not degree_batch.empty:
            grouped = degree_batch.groupby(post_col)[weight_col].agg(["size", "sum"])
            _counter_add(full_in_partner_count, grouped["size"])
            _counter_add(full_in_strength, grouped["sum"])

        core_arr = pa.array(sorted(core_ids), type=pre.type)
        core_touch = pc.or_(pc.is_in(pre, value_set=core_arr), pc.is_in(post, value_set=core_arr))
        mask = pc.and_(core_touch, strong)
        filtered = batch.filter(mask)
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
            "nt": "unknown", "nt_confidence": 0.0, "predicted_nt": "unknown", "celltype_predicted_nt": "unknown",
        })], ignore_index=True)

    nodes["full_in_partner_count"] = nodes["body_id"].map(lambda x: full_in_partner_count.get(int(x), 0)).astype("int64")
    nodes["full_in_strength"] = nodes["body_id"].map(lambda x: full_in_strength.get(int(x), 0)).astype("int64")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    node_cols = [
        "body_id", "type", "side", "status", "superclass", "class", "subclass",
        "nt", "nt_confidence", "predicted_nt", "celltype_predicted_nt",
        "full_in_partner_count", "full_in_strength",
    ]
    nodes[node_cols].sort_values("body_id").to_csv(out / "nodes.csv", index=False)
    edges.sort_values(["pre", "post"]).to_csv(out / "edges.csv", index=False)

    snapshot_meta = {
        "dataset": "male-cns:v1.0",
        "eligible_traced_neurons": int(len(eligible_ids)),
        "dopamine_core_count": int(len(core_ids)),
        "edge_threshold_synapses": int(min_synapses),
        "degree_scope": "all eligible presynaptic neurons in the full MaleCNS edge table",
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
            "min_synapses": min_synapses,
            "traced_only": traced_only,
            "dopamine_core_count": len(core_ids),
            "snapshot_node_count": int(len(nodes)),
            "snapshot_edge_count": int(len(edges)),
            "eligible_traced_neurons": int(len(eligible_ids)),
        },
    }
    (out / "source.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return lock
