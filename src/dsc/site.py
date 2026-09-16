from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from .io import write_json


def _serialise_nodes(nodes: pd.DataFrame, core_ids: set[int]) -> list[dict]:
    out = []
    for row in nodes.itertuples(index=False):
        out.append({
            "id": int(row.body_id),
            "type": str(row.type),
            "side": str(row.side),
            "status": str(row.status),
            "nt": str(row.nt),
            "nt_confidence": float(row.nt_confidence),
            "core": int(row.body_id) in core_ids,
        })
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
