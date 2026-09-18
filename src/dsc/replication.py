from __future__ import annotations

import json
import math
import shutil
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .features import robust_zscores
from .subtypes import normalize_side, pam04_subtype

BANC_META_URL = "https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_meta.feather"
BANC_EDGES_URL = "https://storage.googleapis.com/lee-lab_brain-and-nerve-cord-fly-connectome/compiled_data/banc_888/banc_888_edgelist_simple_v2.feather"
FLYWIRE_ANNOTATIONS_URL = "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/8587524c1748ce5ef2080822a2fc890fc03bf597/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
FLYWIRE_CONNECTIONS_URL = "https://zenodo.org/records/10676866/files/proofread_connections_783.feather?download=1"
PAM_SUBTYPE_REFERENCE = {
    "article": "Li et al. 2020, eLife 62576",
    "doi": "10.7554/eLife.62576",
    "supplement": "https://cdn.elifesciences.org/articles/62576/elife-62576-supp1-v2.xlsx",
    "use": "reference only in v0.5.0; subtype labels are accepted only when they are explicitly present in connectome metadata",
}

def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "unknown", "na"} else text


def _download(url: str, destination: Path, refresh: bool = False) -> Path:
    if destination.exists() and destination.stat().st_size > 0 and not refresh:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.5.0"})
    with urllib.request.urlopen(req, timeout=180) as src, temp.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    temp.replace(destination)
    return destination


def ensure_banc_sources(cache_dir: str | Path, refresh: bool = False) -> tuple[Path, Path]:
    root = Path(cache_dir) / "banc_v888"
    return (
        _download(BANC_META_URL, root / "banc_888_meta.feather", refresh=refresh),
        _download(BANC_EDGES_URL, root / "banc_888_edgelist_simple_v2.feather", refresh=refresh),
    )


def ensure_flywire_sources(
    cache_dir: str | Path,
    refresh: bool = False,
    include_connectivity: bool = True,
) -> tuple[Path, Path | None]:
    root = Path(cache_dir) / "flywire_v783"
    annotations = _download(
        FLYWIRE_ANNOTATIONS_URL,
        root / "Supplemental_file1_neuron_annotations.tsv",
        refresh=refresh,
    )
    connections = None
    if include_connectivity:
        connections = _download(
            FLYWIRE_CONNECTIONS_URL,
            root / "proofread_connections_783.feather",
            refresh=refresh,
        )
    return annotations, connections


def _read_target_edges_feather(
    path: str | Path,
    post_column: str,
    target_ids: list[str],
    columns: list[str],
) -> pd.DataFrame:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.feather as feather

    table = feather.read_table(path, columns=columns, memory_map=True)
    post = table[post_column].combine_chunks()
    if pa.types.is_integer(post.type):
        values = pa.array([int(x) for x in target_ids], type=post.type)
    else:
        values = pa.array([str(x) for x in target_ids], type=post.type)
    mask = pc.is_in(post, value_set=values)
    return table.filter(mask).to_pandas()


def _quantile(values: pd.Series, q: float) -> float | None:
    vals = pd.to_numeric(values, errors="coerce").dropna()
    return float(vals.quantile(q)) if len(vals) else None


def analyze_pam04_connectivity(
    meta: pd.DataFrame,
    incoming_edges: pd.DataFrame,
    *,
    dataset: str,
    id_col: str,
    type_col: str,
    side_col: str,
    hemibrain_type_col: str | None,
    pre_col: str,
    post_col: str,
    weight_col: str,
    min_count: int,
    proofread_col: str | None = None,
    source_type_col: str | None = None,
    outlier_z: float = 3.5,
    min_subtype_peers: int = 4,
) -> dict:
    all_meta = meta.copy()
    all_meta[id_col] = all_meta[id_col].astype(str)
    all_meta[type_col] = all_meta[type_col].fillna("").astype(str)
    frame = all_meta.copy()
    if proofread_col and proofread_col in frame.columns:
        proof = frame[proofread_col].astype(str).str.upper().eq("TRUE") | frame[proofread_col].eq(True)
        frame = frame.loc[proof].copy()
    pam = frame.loc[frame[type_col].str.strip().eq("PAM04")].copy()
    if pam.empty:
        return {
            "dataset": dataset,
            "available": True,
            "connectivity_tested": True,
            "pam04_cells": 0,
            "reason": "No proofread PAM04 cells were found in the supplied metadata.",
            "min_connection_count": int(min_count),
            "cells": [],
            "subtypes": [],
            "motif": {"global_bilateral": False, "within_subtype_bilateral": False},
        }

    pam["side_norm"] = pam[side_col].map(normalize_side) if side_col in pam.columns else ""
    subtype_values = pam[hemibrain_type_col] if hemibrain_type_col and hemibrain_type_col in pam.columns else pd.Series([""] * len(pam), index=pam.index)
    pam["known_subtype"] = [pam04_subtype(value) for value in subtype_values]
    target_ids = set(pam[id_col].astype(str))

    edges = incoming_edges[[pre_col, post_col, weight_col]].copy()
    edges[pre_col] = edges[pre_col].astype(str)
    edges[post_col] = edges[post_col].astype(str)
    edges[weight_col] = pd.to_numeric(edges[weight_col], errors="coerce").fillna(0).astype(int)
    edges = edges.loc[edges[post_col].isin(target_ids)]
    # FlyWire supplies one row per pair and neuropil; BANC supplies one row per
    # pair. Grouping makes the analysis equivalent across both representations.
    pair = edges.groupby([pre_col, post_col], as_index=False)[weight_col].sum()
    pair = pair.loc[pair[weight_col] >= int(min_count)].copy()

    if source_type_col and source_type_col in all_meta.columns:
        source_type_lookup = dict(zip(all_meta[id_col].astype(str), all_meta[source_type_col].fillna("").astype(str)))
    else:
        source_type_lookup = dict(zip(all_meta[id_col].astype(str), all_meta[type_col].fillna("").astype(str)))

    records = []
    for row in pam.itertuples(index=False):
        rid = str(getattr(row, id_col))
        inc = pair.loc[pair[post_col].eq(rid)].sort_values(weight_col, ascending=False)
        total = int(inc[weight_col].sum())
        strongest = inc.iloc[0] if len(inc) else None
        strongest_weight = int(strongest[weight_col]) if strongest is not None else 0
        strongest_pre = str(strongest[pre_col]) if strongest is not None else None
        records.append({
            "id": rid,
            "side": normalize_side(getattr(row, side_col, "")),
            "known_subtype": pam04_subtype(getattr(row, hemibrain_type_col, "")) if hemibrain_type_col else None,
            "input_strength": total,
            "input_partners": int(len(inc)),
            "max_input_share": strongest_weight / total if total else 0.0,
            "strongest_input_id": strongest_pre,
            "strongest_input_type": source_type_lookup.get(strongest_pre, "") if strongest_pre else "",
            "strongest_input_weight": strongest_weight,
        })

    cells = pd.DataFrame(records)
    cells["global_robust_z"] = robust_zscores(cells["max_input_share"])
    cells["within_subtype_robust_z"] = np.nan
    for subtype, idx in cells.groupby("known_subtype", dropna=True).groups.items():
        if subtype and len(idx) >= int(min_subtype_peers):
            cells.loc[idx, "within_subtype_robust_z"] = robust_zscores(cells.loc[idx, "max_input_share"])
    cells["global_outlier"] = cells["global_robust_z"].abs() >= float(outlier_z)
    cells["within_subtype_outlier"] = cells["within_subtype_robust_z"].abs() >= float(outlier_z)

    subtype_rows = []
    for subtype, group in cells.dropna(subset=["known_subtype"]).groupby("known_subtype"):
        within_mask = group["within_subtype_outlier"]
        within_subset = group.loc[within_mask]
        subtype_rows.append({
            "subtype": subtype,
            "n": int(len(group)),
            "left": int(group["side"].eq("L").sum()),
            "right": int(group["side"].eq("R").sum()),
            "median_max_input_share": float(group["max_input_share"].median()),
            "q90_max_input_share": _quantile(group["max_input_share"], 0.9),
            "global_outliers": group.loc[group["global_outlier"], "id"].astype(str).tolist(),
            "within_subtype_outliers": group.loc[group["within_subtype_outlier"], "id"].astype(str).tolist(),
            "within_subtype_tested": bool(len(group) >= int(min_subtype_peers)),
            "within_subtype_bilateral": bool(
                within_subset["side"].eq("L").any() and within_subset["side"].eq("R").any()
            ),
        })

    def _bilateral(mask: pd.Series) -> bool:
        subset = cells.loc[mask]
        return bool(subset["side"].eq("L").any() and subset["side"].eq("R").any())

    within_subtype_bilateral = any(row["within_subtype_bilateral"] for row in subtype_rows)

    out_records = []
    for rec in cells.to_dict("records"):
        for key in ["global_robust_z", "within_subtype_robust_z"]:
            value = rec.get(key)
            rec[key] = None if value is None or not math.isfinite(float(value)) else float(value)
        rec["global_outlier"] = bool(rec["global_outlier"])
        rec["within_subtype_outlier"] = bool(rec["within_subtype_outlier"])
        rec["max_input_share"] = float(rec["max_input_share"])
        out_records.append(rec)

    return {
        "dataset": dataset,
        "available": True,
        "connectivity_tested": True,
        "pam04_cells": int(len(cells)),
        "min_connection_count": int(min_count),
        "outlier_z": float(outlier_z),
        "min_subtype_peers": int(min_subtype_peers),
        "cells": out_records,
        "subtypes": sorted(subtype_rows, key=lambda x: x["subtype"]),
        "motif": {
            "global_outlier_count": int(cells["global_outlier"].sum()),
            "global_bilateral": _bilateral(cells["global_outlier"]),
            "within_subtype_outlier_count": int(cells["within_subtype_outlier"].sum()),
            # Bilateral recurrence must occur inside the *same* annotated
            # subtype. A left outlier in PAM04-dd plus a right outlier in
            # PAM04-can is not a bilateral within-subtype motif.
            "within_subtype_bilateral": bool(within_subtype_bilateral),
        },
    }


def male_cns_from_experiment(experiment: dict, outlier_z: float = 3.5, min_subtype_peers: int = 4) -> dict:
    if not experiment.get("available"):
        return {"dataset": "male-cns:v1.0", "available": False, "connectivity_tested": False, "cells": [], "subtypes": []}
    rows = []
    for cell in experiment.get("cells", []):
        metrics = cell.get("metrics", {})
        rows.append({
            "id": str(cell.get("body_id")),
            "side": normalize_side(cell.get("side")),
            "known_subtype": cell.get("known_subtype"),
            "max_input_share": float(metrics.get("max_input_share", 0.0) or 0.0),
            "global_robust_z": float(metrics.get("max_input_share_z", 0.0) or 0.0),
            "input_strength": float(metrics.get("in_strength", 0.0) or 0.0),
            "input_partners": int(metrics.get("in_partner_count", 0) or 0),
            "candidate": bool(cell.get("candidate")),
            "candidate_status": cell.get("candidate_status"),
        })
    cells = pd.DataFrame(rows)
    if cells.empty:
        return {"dataset": "male-cns:v1.0", "available": True, "connectivity_tested": True, "pam04_cells": 0, "cells": [], "subtypes": []}
    cells["within_subtype_robust_z"] = np.nan
    for subtype, idx in cells.groupby("known_subtype", dropna=True).groups.items():
        if subtype and len(idx) >= int(min_subtype_peers):
            cells.loc[idx, "within_subtype_robust_z"] = robust_zscores(cells.loc[idx, "max_input_share"])
    cells["global_outlier"] = cells["global_robust_z"].abs() >= float(outlier_z)
    cells["within_subtype_outlier"] = cells["within_subtype_robust_z"].abs() >= float(outlier_z)

    subtype_rows = []
    for subtype, group in cells.dropna(subset=["known_subtype"]).groupby("known_subtype"):
        within_subset = group.loc[group["within_subtype_outlier"]]
        subtype_rows.append({
            "subtype": subtype,
            "n": int(len(group)),
            "left": int(group["side"].eq("L").sum()),
            "right": int(group["side"].eq("R").sum()),
            "median_max_input_share": float(group["max_input_share"].median()),
            "global_outliers": group.loc[group["global_outlier"], "id"].tolist(),
            "within_subtype_outliers": group.loc[group["within_subtype_outlier"], "id"].tolist(),
            "within_subtype_tested": bool(len(group) >= int(min_subtype_peers)),
            "within_subtype_bilateral": bool(
                within_subset["side"].eq("L").any() and within_subset["side"].eq("R").any()
            ),
        })

    out = []
    for rec in cells.to_dict("records"):
        value = rec.get("within_subtype_robust_z")
        rec["within_subtype_robust_z"] = None if value is None or not math.isfinite(float(value)) else float(value)
        rec["global_robust_z"] = float(rec["global_robust_z"])
        rec["global_outlier"] = bool(rec["global_outlier"])
        rec["within_subtype_outlier"] = bool(rec["within_subtype_outlier"])
        out.append(rec)

    def bilateral(column: str) -> bool:
        g = cells.loc[cells[column]]
        return bool(g["side"].eq("L").any() and g["side"].eq("R").any())

    within_subtype_bilateral = any(row["within_subtype_bilateral"] for row in subtype_rows)

    return {
        "dataset": "male-cns:v1.0",
        "available": True,
        "connectivity_tested": True,
        "pam04_cells": int(len(cells)),
        "outlier_z": float(outlier_z),
        "min_subtype_peers": int(min_subtype_peers),
        "cells": out,
        "subtypes": sorted(subtype_rows, key=lambda x: x["subtype"]),
        "motif": {
            "global_outlier_count": int(cells["global_outlier"].sum()),
            "global_bilateral": bilateral("global_outlier"),
            "within_subtype_outlier_count": int(cells["within_subtype_outlier"].sum()),
            "within_subtype_bilateral": bool(within_subtype_bilateral),
        },
    }


def _candidate_resolution(male: dict, external: dict) -> list[dict]:
    if not external.get("available") or not external.get("connectivity_tested"):
        return []
    ext_subtypes = {row.get("subtype"): row for row in external.get("subtypes", [])}
    rows = []
    for cell in male.get("cells", []):
        if not cell.get("candidate"):
            continue
        subtype = cell.get("known_subtype")
        if not subtype:
            rows.append({"male_id": cell["id"], "subtype": None, "status": "male_subtype_unresolved"})
            continue
        ext = ext_subtypes.get(subtype)
        if not ext:
            rows.append({"male_id": cell["id"], "subtype": subtype, "status": "subtype_absent_external"})
            continue
        if not ext.get("within_subtype_tested"):
            status = "external_subtype_too_small"
        elif ext.get("within_subtype_bilateral"):
            status = "same_subtype_bilateral_outlier"
        elif ext.get("within_subtype_outliers"):
            status = "same_subtype_unilateral_outlier"
        else:
            status = "same_subtype_no_outlier"
        rows.append({
            "male_id": cell["id"],
            "subtype": subtype,
            "status": status,
            "external_n": ext.get("n", 0),
            "external_outlier_ids": ext.get("within_subtype_outliers", []),
        })
    return rows


def _replication_overall(datasets: dict[str, dict], candidate_cross_dataset: dict[str, list[dict]] | None = None) -> dict:
    candidate_cross_dataset = candidate_cross_dataset or {}
    male = datasets.get("male_cns", {})
    male_candidates = [cell for cell in male.get("cells", []) if cell.get("candidate")]
    male_testable = [
        cell for cell in male_candidates
        if cell.get("known_subtype") and cell.get("within_subtype_robust_z") is not None
    ]
    male_persisting = [cell for cell in male_testable if cell.get("within_subtype_outlier")]

    tested_external = [
        value for key, value in datasets.items()
        if key != "male_cns" and value.get("connectivity_tested")
    ]
    subtype_testable = [
        value for value in tested_external
        if any(row.get("within_subtype_tested") for row in value.get("subtypes", []))
    ]
    # The replication target is explicitly *within known subtype*. A global
    # bilateral PAM04 outlier is context, not replication, because known
    # subtype structure could explain it.
    supporting_dataset_names = []
    persisting_ids = {str(cell.get("id")) for cell in male_persisting}
    for dataset_name, rows in candidate_cross_dataset.items():
        if any(
            str(row.get("male_id")) in persisting_ids
            and row.get("status") == "same_subtype_bilateral_outlier"
            for row in rows
        ):
            supporting_dataset_names.append(dataset_name)

    if male_candidates and male_testable and not male_persisting:
        status = "male_candidate_explained_by_known_subtype"
    elif male_candidates and not male_testable:
        status = "male_subtype_resolution_insufficient"
    elif not male_candidates:
        status = "no_control_surviving_male_candidate"
    elif not tested_external:
        status = "external_connectivity_not_available"
    elif not subtype_testable:
        status = "external_subtype_resolution_insufficient"
    elif len(tested_external) >= 2 and len(supporting_dataset_names) >= 2:
        status = "motif_seen_in_both_external_connectomes"
    elif supporting_dataset_names:
        status = "motif_seen_in_at_least_one_external_connectome"
    else:
        status = "motif_not_seen_in_tested_external_connectomes"
    return {
        "status": status,
        "male_candidates": len(male_candidates),
        "male_candidates_with_subtype_test": len(male_testable),
        "male_candidates_persisting_within_subtype": len(male_persisting),
        "external_connectomes_tested": len(tested_external),
        "external_connectomes_with_subtype_test": len(subtype_testable),
        "external_connectomes_supporting_persisting_male_subtype": len(supporting_dataset_names),
        "supporting_external_datasets": sorted(supporting_dataset_names),
        "note": "Structural replication requires a control-surviving MaleCNS candidate to persist within an explicit known subtype and the same subtype to show bilateral within-subtype outliers in an external connectome. Global or cross-subtype bilateral PAM04 outliers do not count.",
    }


def build_pam04_replication(
    experiment: dict,
    *,
    cache_dir: str | Path,
    include_banc: bool = True,
    include_flywire: bool = True,
    flywire_connectivity: bool = True,
    refresh: bool = False,
    outlier_z: float = 3.5,
    min_subtype_peers: int = 4,
) -> dict:
    male = male_cns_from_experiment(experiment, outlier_z=outlier_z, min_subtype_peers=min_subtype_peers)
    report: dict[str, Any] = {
        "experiment_id": "001_pam04",
        "question": "Does a high-input-concentration PAM04 motif persist within known subtypes and across independent adult connectomes?",
        "interpretation_scope": "structural replication only; not evidence of firing, dopamine release, behavior or receptor action",
        "datasets": {"male_cns": male},
        "candidate_cross_dataset": {},
        "sources": {
            "male_cns": "male-cns:v1.0",
            "banc": {"version": "v888", "meta": BANC_META_URL, "edges": BANC_EDGES_URL},
            "flywire": {"version": "783", "annotations": FLYWIRE_ANNOTATIONS_URL, "connections": FLYWIRE_CONNECTIONS_URL},
            "known_pam_subtype_reference": PAM_SUBTYPE_REFERENCE,
        },
    }

    if include_banc:
        try:
            import pyarrow.feather as feather
            meta_path, edge_path = ensure_banc_sources(cache_dir, refresh=refresh)
            meta = feather.read_table(meta_path).to_pandas()
            pam_ids = meta.loc[meta.get("cell_type", pd.Series(index=meta.index, dtype=str)).fillna("").astype(str).eq("PAM04"), "banc_888_id"].astype(str).tolist()
            edge = _read_target_edges_feather(edge_path, "post", pam_ids, ["pre", "post", "count"])
            banc = analyze_pam04_connectivity(
                meta,
                edge,
                dataset="banc:v888",
                id_col="banc_888_id",
                type_col="cell_type",
                side_col="side",
                hemibrain_type_col="hemibrain_cell_type",
                pre_col="pre",
                post_col="post",
                weight_col="count",
                min_count=5,
                proofread_col="proofread",
                source_type_col="cell_type",
                outlier_z=outlier_z,
                min_subtype_peers=min_subtype_peers,
            )
            report["datasets"]["banc"] = banc
            report["candidate_cross_dataset"]["banc"] = _candidate_resolution(male, banc)
        except Exception as exc:
            report["datasets"]["banc"] = {
                "dataset": "banc:v888",
                "available": False,
                "connectivity_tested": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    if include_flywire:
        try:
            ann_path, conn_path = ensure_flywire_sources(cache_dir, refresh=refresh, include_connectivity=flywire_connectivity)
            meta = pd.read_csv(ann_path, sep="\t", dtype=str, low_memory=False)
            if not flywire_connectivity or conn_path is None:
                fw = {
                    "dataset": "flywire:783",
                    "available": True,
                    "connectivity_tested": False,
                    "pam04_cells": int(meta.get("cell_type", pd.Series(dtype=str)).fillna("").eq("PAM04").sum()),
                    "note": "PAM04 annotations loaded, but the 852 MB proofread connectivity table was not requested.",
                }
            else:
                pam_ids = meta.loc[meta.get("cell_type", pd.Series(index=meta.index, dtype=str)).fillna("").eq("PAM04"), "root_id"].astype(str).tolist()
                edge = _read_target_edges_feather(conn_path, "post_pt_root_id", pam_ids, ["pre_pt_root_id", "post_pt_root_id", "syn_count"])
                fw = analyze_pam04_connectivity(
                    meta,
                    edge,
                    dataset="flywire:783",
                    id_col="root_id",
                    type_col="cell_type",
                    side_col="side",
                    hemibrain_type_col="hemibrain_type",
                    pre_col="pre_pt_root_id",
                    post_col="post_pt_root_id",
                    weight_col="syn_count",
                    min_count=5,
                    proofread_col=None,
                    source_type_col="cell_type",
                    outlier_z=outlier_z,
                    min_subtype_peers=min_subtype_peers,
                )
            report["datasets"]["flywire"] = fw
            report["candidate_cross_dataset"]["flywire"] = _candidate_resolution(male, fw)
        except Exception as exc:
            report["datasets"]["flywire"] = {
                "dataset": "flywire:783",
                "available": False,
                "connectivity_tested": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    report["overall"] = _replication_overall(report["datasets"], report["candidate_cross_dataset"])
    return report


def write_pam04_replication(
    experiment_path: str | Path,
    output_path: str | Path,
    cache_dir: str | Path,
    **kwargs,
) -> dict:
    experiment = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    payload = build_pam04_replication(experiment, cache_dir=cache_dir, **kwargs)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
