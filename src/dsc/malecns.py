from __future__ import annotations

import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow.compute as pc
import pyarrow.feather as feather
import pyarrow.ipc as ipc
import pyarrow as pa

BASE = "https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
FILES = {
    "annotations": "body-annotations-male-cns-v1.0-minconf-0.5.feather",
    "neurotransmitters": "body-neurotransmitters-male-cns-v1.0.feather",
    "edges": "connectome-weights-male-cns-v1.0-minconf-0.5.feather",
}


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.1"})
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


def _read_annotations(path: Path) -> pd.DataFrame:
    df = feather.read_feather(path)
    body = _find_column(list(df.columns), ["bodyId", "body", "body_id"])
    typ = _find_column(list(df.columns), ["type"])
    side = next((c for c in ["somaSide", "side"] if c in df.columns), None)
    status = next((c for c in ["status"] if c in df.columns), None)
    out = pd.DataFrame({
        "body_id": df[body].astype("int64"),
        "type": df[typ].fillna("unknown").astype(str),
        "side": df[side].fillna("unknown").astype(str) if side else "unknown",
        "status": df[status].fillna("unknown").astype(str) if status else "unknown",
    })
    return out.drop_duplicates("body_id")


def _read_nt(path: Path) -> pd.DataFrame:
    """Read MaleCNS transmitter annotations using the curated consensus field.

    MaleCNS exposes several transmitter properties. ``predicted_nt`` is a
    per-neuron model prediction, while ``consensus_nt`` incorporates the
    cell-type aggregate and experimental overrides and is the appropriate
    field for defining transmitter identity in this project. Prediction
    confidence is retained only as provenance; it is not used to filter the
    consensus dopamine set.
    """
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


def build_dopamine_snapshot(raw_dir: str | Path, output_dir: str | Path, min_synapses: int = 3,
                            traced_only: bool = True, refresh: bool = False) -> dict:
    paths = ensure_sources(raw_dir, refresh=refresh)
    annotations = _read_annotations(paths["annotations"])
    nt = _read_nt(paths["neurotransmitters"])
    merged = annotations.merge(nt, on="body_id", how="left")
    merged["nt"] = merged["nt"].fillna("unknown")
    merged["nt_confidence"] = merged["nt_confidence"].fillna(0.0)

    # IMPORTANT: ``nt`` is MaleCNS consensus_nt. Do not gate it by
    # predicted_nt_confidence: the consensus field already encodes the curated
    # transmitter assignment and can intentionally override raw predictions.
    dopamine_mask = merged["nt"].astype(str).str.lower().str.strip().isin(["dopamine", "da"])
    if traced_only:
        dopamine_mask &= merged["status"].astype(str).str.lower().eq("traced")
    core_ids = set(merged.loc[dopamine_mask, "body_id"].astype(int))
    if not core_ids:
        raise RuntimeError("No consensus dopamine neurons selected from current MaleCNS files. Inspect source schema/labels.")
    # MaleCNS v1.0 has hundreds, not thousands, of consensus dopamine neurons.
    # This broad guard is intentionally a schema-sanity check, not a biological
    # assertion for future datasets. It prevents silently using predicted_nt as
    # transmitter identity again.
    if len(core_ids) > 1000:
        raise RuntimeError(
            f"Selected {len(core_ids)} consensus dopamine neurons; this is implausible for pinned MaleCNS v1.0. "
            "Check neurotransmitter schema before continuing."
        )

    tables = []
    for batch in _edge_batches(paths["edges"]):
        names = batch.schema.names
        pre_col = _find_column(names, ["body_pre", "pre"])
        post_col = _find_column(names, ["body_post", "post"])
        weight_col = _find_column(names, ["weight", "count"])
        pre = batch.column(names.index(pre_col))
        post = batch.column(names.index(post_col))
        weight = batch.column(names.index(weight_col))
        core_arr = pa.array(sorted(core_ids), type=pre.type)
        mask = pc.or_(pc.is_in(pre, value_set=core_arr), pc.is_in(post, value_set=core_arr))
        mask = pc.and_(mask, pc.greater_equal(weight, pa.scalar(int(min_synapses), type=weight.type)))
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
            "nt": "unknown", "nt_confidence": 0.0,
        })], ignore_index=True)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    nodes[["body_id", "type", "side", "status", "nt", "nt_confidence", "predicted_nt", "celltype_predicted_nt"]].sort_values("body_id").to_csv(out / "nodes.csv", index=False)
    edges.sort_values(["pre", "post"]).to_csv(out / "edges.csv", index=False)

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
        },
    }
    (out / "source.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return lock
