from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from .anatomy import parse_roi_info, parse_roi_value, roi_json

SERVER = "https://neuprint.janelia.org"
DATASET = "male-cns:v1.0"


def _post_cypher(cypher: str, token: str | None = None, timeout: int = 120, retries: int = 3) -> dict:
    payload = json.dumps({"cypher": cypher, "dataset": DATASET}).encode("utf-8")
    headers = {
        "User-Agent": "dopaminergic-state-control/0.5.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    delay = 1.5
    last_error: Exception | None = None
    for attempt in range(max(1, int(retries))):
        req = urllib.request.Request(SERVER + "/api/custom/custom", data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if "data" not in body:
                raise RuntimeError(f"neuPrint response missing data: {str(body)[:300]}")
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < max(1, int(retries)):
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"neuPrint query failed: {last_error}")


def _cache_payload(records: dict[int, tuple[str, str]]) -> dict:
    return {
        "dataset": DATASET,
        "schema": 2,
        "records": {
            str(int(body)): {"input_rois": values[0], "output_rois": values[1]}
            for body, values in records.items()
        },
    }


def _write_cache(path: Path, records: dict[int, tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    payload = json.dumps(_cache_payload(records), separators=(",", ":")).encode("utf-8")
    if path.suffix == ".gz":
        with gzip.open(temp, "wb", compresslevel=6) as stream:
            stream.write(payload)
    else:
        temp.write_bytes(payload)
    temp.replace(path)


def _read_cache(path: Path) -> dict[int, tuple[str, str]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            payload = json.loads(stream.read().decode("utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dataset") != DATASET:
        raise ValueError(f"ROI cache is for {payload.get('dataset')!r}, expected {DATASET!r}")
    records = {}
    for body, values in payload.get("records", {}).items():
        try:
            records[int(body)] = (
                roi_json(parse_roi_value(values.get("input_rois"))),
                roi_json(parse_roi_value(values.get("output_rois"))),
            )
        except (TypeError, ValueError):
            continue
    return records


def fetch_roi_metadata(
    cache_path: str | Path | None = None,
    token: str | None = None,
    batch_size: int = 10000,
    max_batches: int = 50,
) -> tuple[dict[int, tuple[str, str]], dict]:
    """Fetch compact neuron neuropil-availability metadata from MaleCNS neuPrint.

    Only bodyId/inputRois/outputRois are requested. This is several orders of
    magnitude smaller than downloading the 6.8/12.7 GB synapse tables and is
    cacheable by the GitHub Actions workflow.
    """
    cache = Path(cache_path) if cache_path else None
    cache_read_error = None
    if cache and cache.exists():
        try:
            records = _read_cache(cache)
            nonempty_in = sum(1 for values in records.values() if values[0] != "[]")
            nonempty_out = sum(1 for values in records.values() if values[1] != "[]")
            if records and nonempty_in and nonempty_out:
                return records, {
                    "source": "cache",
                    "cache_path": str(cache),
                    "records": int(len(records)),
                    "records_with_input_rois": int(nonempty_in),
                    "records_with_output_rois": int(nonempty_out),
                }
            cache_read_error = f"cache had no usable ROI coverage (input={nonempty_in}, output={nonempty_out})"
        except Exception as exc:
            # A truncated Actions cache must not permanently disable the anatomy
            # control. Re-query the pinned neuPrint dataset and replace it.
            cache_read_error = f"{type(exc).__name__}: {exc}"

    token = token or os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
    records: dict[int, tuple[str, str]] = {}
    last_body = -1
    batches = 0
    batch_size = max(1, int(batch_size))

    while batches < max(1, int(max_batches)):
        cypher = f"""
MATCH (n:Neuron)
WHERE n.bodyId > {int(last_body)}
RETURN n.bodyId AS bodyId, n.inputRois AS inputRois, n.outputRois AS outputRois, n.roiInfo AS roiInfo
ORDER BY n.bodyId
LIMIT {batch_size}
""".strip()
        response = _post_cypher(cypher, token=token)
        columns = response.get("columns", [])
        index = {name: i for i, name in enumerate(columns)}
        required = {"bodyId"}
        if not required.issubset(index):
            raise RuntimeError(f"unexpected neuPrint ROI columns: {columns}")
        rows = response.get("data", [])
        if not rows:
            break

        previous_last = last_body
        for row in rows:
            try:
                body = int(row[index["bodyId"]])
            except (TypeError, ValueError):
                continue
            ins_values = parse_roi_value(row[index["inputRois"]]) if "inputRois" in index else []
            out_values = parse_roi_value(row[index["outputRois"]]) if "outputRois" in index else []
            if (not ins_values or not out_values) and "roiInfo" in index:
                fallback_in, fallback_out = parse_roi_info(row[index["roiInfo"]])
                if not ins_values:
                    ins_values = fallback_in
                if not out_values:
                    out_values = fallback_out
            ins = roi_json(ins_values)
            outs = roi_json(out_values)
            records[body] = (ins, outs)
            last_body = max(last_body, body)
        batches += 1
        if last_body <= previous_last:
            raise RuntimeError("neuPrint ROI pagination did not advance bodyId")
        if len(rows) < batch_size:
            break
    else:
        raise RuntimeError(f"neuPrint ROI pagination exceeded max_batches={max_batches}")

    if not records:
        raise RuntimeError("neuPrint ROI query returned no neuron metadata")
    nonempty_in = sum(1 for values in records.values() if values[0] != "[]")
    nonempty_out = sum(1 for values in records.values() if values[1] != "[]")
    if not nonempty_in or not nonempty_out:
        raise RuntimeError(
            f"neuPrint ROI query returned no usable ROI coverage (input={nonempty_in}, output={nonempty_out})"
        )
    if cache:
        _write_cache(cache, records)
    return records, {
        "source": "neuprint",
        "cache_path": str(cache) if cache else None,
        "records": int(len(records)),
        "records_with_input_rois": int(nonempty_in),
        "records_with_output_rois": int(nonempty_out),
        "batches": int(batches),
        "replaced_cache_error": cache_read_error,
    }


def _coverage(frame: pd.DataFrame, eligible_ids: set[int]) -> dict[str, float | int]:
    eligible = frame.loc[frame["body_id"].isin(eligible_ids)]
    n = int(len(eligible))
    if n == 0:
        return {"eligible": 0, "input_with_roi": 0, "output_with_roi": 0, "input_fraction": 0.0, "output_fraction": 0.0}
    input_nonempty = eligible["input_rois"].fillna("[]").astype(str).ne("[]")
    output_nonempty = eligible["output_rois"].fillna("[]").astype(str).ne("[]")
    return {
        "eligible": n,
        "input_with_roi": int(input_nonempty.sum()),
        "output_with_roi": int(output_nonempty.sum()),
        "input_fraction": float(input_nonempty.mean()),
        "output_fraction": float(output_nonempty.mean()),
    }


def hydrate_roi_metadata(
    merged: pd.DataFrame,
    eligible_ids: set[int],
    cache_path: str | Path | None = None,
    minimum_coverage: float = 0.90,
    token: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Fill missing ROI lists from the pinned MaleCNS neuPrint dataset, fail-soft.

    If the flat annotation file already contains broad ROI coverage, no network
    request is made. If neuPrint is unavailable, the caller receives the original
    frame plus explicit provenance/error metadata; downstream convergence then
    falls back to the global null and labels itself accordingly.
    """
    frame = merged.copy()
    before = _coverage(frame, eligible_ids)
    threshold = float(minimum_coverage)
    enough = before["input_fraction"] >= threshold and before["output_fraction"] >= threshold
    if enough:
        return frame, {
            "source": "flat_annotations",
            "minimum_coverage": threshold,
            "before": before,
            "after": before,
            "hydrated": False,
        }

    try:
        records, fetch_meta = fetch_roi_metadata(cache_path=cache_path, token=token)
        body_ids = frame["body_id"].astype(int)
        in_map = {body: value[0] for body, value in records.items()}
        out_map = {body: value[1] for body, value in records.items()}
        fetched_in = body_ids.map(in_map)
        fetched_out = body_ids.map(out_map)
        in_mask = fetched_in.notna()
        out_mask = fetched_out.notna()
        frame.loc[in_mask, "input_rois"] = fetched_in.loc[in_mask].astype(str)
        frame.loc[out_mask, "output_rois"] = fetched_out.loc[out_mask].astype(str)
        after = _coverage(frame, eligible_ids)
        return frame, {
            **fetch_meta,
            "minimum_coverage": threshold,
            "before": before,
            "after": after,
            "hydrated": True,
        }
    except Exception as exc:
        return frame, {
            "source": "unavailable",
            "minimum_coverage": threshold,
            "before": before,
            "after": before,
            "hydrated": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
