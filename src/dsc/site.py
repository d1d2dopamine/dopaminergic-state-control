from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from .io import write_json


def _serialise_nodes(nodes: pd.DataFrame, core_ids: set[int]) -> list[dict]:
    fields = ["body_id", "type", "side", "status", "nt", "nt_confidence", "superclass", "class", "subclass", "full_in_partner_count", "full_in_strength"]
    available = [f for f in fields if f in nodes.columns]
    out = []
    for _, row in nodes[available].iterrows():
        record = {
            "id": int(row["body_id"]),
            "type": str(row.get("type", "unknown")),
            "side": str(row.get("side", "unknown")),
            "status": str(row.get("status", "unknown")),
            "nt": str(row.get("nt", "unknown")),
            "nt_confidence": float(row.get("nt_confidence", 0.0)),
            "core": int(row["body_id"]) in core_ids,
        }
        for key in ["superclass", "class", "subclass"]:
            if key in row:
                record[key] = str(row[key])
        for key in ["full_in_partner_count", "full_in_strength"]:
            if key in row and pd.notna(row[key]):
                record[key] = int(row[key])
        out.append(record)
    return out


def _serialise_edges(edges: pd.DataFrame) -> list[dict]:
    return [{"pre": int(r.pre), "post": int(r.post), "weight": int(r.weight)} for r in edges.itertuples(index=False)]


def build_site(template_dir: str | Path, output_dir: str | Path, nodes: pd.DataFrame, edges: pd.DataFrame,
               findings: list[dict], features: pd.DataFrame, core_ids: set[int], manifest: dict) -> None:
    src = Path(template_dir)
    dst = Path(output_dir)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    data_dir = dst / "data"
    data_dir.mkdir(exist_ok=True)
    write_json(data_dir / "findings.json", findings)
    write_json(data_dir / "network.json", {"nodes": _serialise_nodes(nodes, core_ids), "edges": _serialise_edges(edges)})
    write_json(data_dir / "features.json", json.loads(features.to_json(orient="records")))
    write_json(data_dir / "run.json", manifest)
