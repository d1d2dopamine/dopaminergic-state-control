from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

NODE_REQUIRED = {"body_id", "type", "side", "status", "nt", "nt_confidence"}
EDGE_REQUIRED = {"pre", "post", "weight"}


def load_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_snapshot(snapshot_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(snapshot_dir)
    nodes_path = root / "nodes.csv"
    edges_path = root / "edges.csv"
    if not nodes_path.exists() or not edges_path.exists():
        raise FileNotFoundError(f"Snapshot must contain nodes.csv and edges.csv: {root}")
    nodes = pd.read_csv(nodes_path)
    edges = pd.read_csv(edges_path)
    missing_nodes = NODE_REQUIRED - set(nodes.columns)
    missing_edges = EDGE_REQUIRED - set(edges.columns)
    if missing_nodes:
        raise ValueError(f"nodes.csv missing columns: {sorted(missing_nodes)}")
    if missing_edges:
        raise ValueError(f"edges.csv missing columns: {sorted(missing_edges)}")
    nodes["body_id"] = nodes["body_id"].astype("int64")
    edges[["pre", "post", "weight"]] = edges[["pre", "post", "weight"]].astype("int64")
    return nodes, edges


def write_json(path: str | Path, payload: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
