from __future__ import annotations

import gzip
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

SERVER = "https://neuprint.janelia.org"
DATASET = "male-cns:v1.0"
FIELDS = {
    "flywire_type": "flywireType",
    "hemibrain_type": "hemibrainType",
    "supertype": "supertype",
    "hemilineage": "itoleeHl",
    "dimorphism": "dimorphism",
    "synonyms": "synonyms",
}


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
    raise RuntimeError(f"neuPrint identity query failed: {last_error}")


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(x).strip() for x in value if str(x).strip())
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    text = str(value).strip()
    return "" if text.lower() in {"none", "nan", "unknown"} else text


def _read_cache(path: Path) -> dict[int, dict[str, str]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            payload = json.loads(stream.read().decode("utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("dataset") != DATASET:
        raise ValueError(f"identity cache is for {payload.get('dataset')!r}, expected {DATASET!r}")
    records: dict[int, dict[str, str]] = {}
    for body, values in payload.get("records", {}).items():
        try:
            records[int(body)] = {key: _clean(values.get(key)) for key in FIELDS}
        except (TypeError, ValueError):
            continue
    return records


def _write_cache(path: Path, records: dict[int, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    payload = {
        "dataset": DATASET,
        "schema": 1,
        "records": {str(body): values for body, values in records.items()},
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if path.suffix == ".gz":
        with gzip.open(temp, "wb", compresslevel=6) as stream:
            stream.write(raw)
    else:
        temp.write_bytes(raw)
    temp.replace(path)


def fetch_identity_metadata(
    cache_path: str | Path | None = None,
    token: str | None = None,
    batch_size: int = 10000,
    max_batches: int = 50,
) -> tuple[dict[int, dict[str, str]], dict]:
    cache = Path(cache_path) if cache_path else None
    cache_error = None
    if cache and cache.exists():
        try:
            records = _read_cache(cache)
            if records:
                annotated = sum(1 for values in records.values() if any(values.values()))
                return records, {
                    "source": "cache",
                    "cache_path": str(cache),
                    "records": len(records),
                    "records_with_identity": annotated,
                }
            cache_error = "cache contained no records"
        except Exception as exc:
            cache_error = f"{type(exc).__name__}: {exc}"

    token = token or os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
    records: dict[int, dict[str, str]] = {}
    last_body = -1
    batches = 0
    batch_size = max(1, int(batch_size))
    returns = ["n.bodyId AS bodyId"] + [f"n.{prop} AS {prop}" for prop in FIELDS.values()]
    while batches < max(1, int(max_batches)):
        cypher = (
            "MATCH (n:Neuron)\n"
            f"WHERE n.bodyId > {int(last_body)}\n"
            "RETURN " + ", ".join(returns) + "\n"
            "ORDER BY n.bodyId\n"
            f"LIMIT {batch_size}"
        )
        response = _post_cypher(cypher, token=token)
        columns = response.get("columns", [])
        index = {name: i for i, name in enumerate(columns)}
        if "bodyId" not in index:
            raise RuntimeError(f"unexpected neuPrint identity columns: {columns}")
        rows = response.get("data", [])
        if not rows:
            break
        previous_last = last_body
        for row in rows:
            try:
                body = int(row[index["bodyId"]])
            except (TypeError, ValueError):
                continue
            values = {}
            for output_name, property_name in FIELDS.items():
                values[output_name] = _clean(row[index[property_name]]) if property_name in index else ""
            records[body] = values
            last_body = max(last_body, body)
        batches += 1
        if last_body <= previous_last:
            raise RuntimeError("neuPrint identity pagination did not advance bodyId")
        if len(rows) < batch_size:
            break
    else:
        raise RuntimeError(f"neuPrint identity pagination exceeded max_batches={max_batches}")

    if not records:
        raise RuntimeError("neuPrint identity query returned no neuron metadata")
    if cache:
        _write_cache(cache, records)
    annotated = sum(1 for values in records.values() if any(values.values()))
    return records, {
        "source": "neuprint",
        "cache_path": str(cache) if cache else None,
        "records": len(records),
        "records_with_identity": annotated,
        "batches": batches,
        "replaced_cache_error": cache_error,
    }


def hydrate_identity_metadata(
    merged: pd.DataFrame,
    cache_path: str | Path | None = None,
    token: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    frame = merged.copy()
    for key in FIELDS:
        if key not in frame.columns:
            frame[key] = ""
        frame[key] = frame[key].fillna("").astype(str)

    before = {key: int(frame[key].str.strip().ne("").sum()) for key in FIELDS}
    # If the flat table already contains the useful matching fields for almost
    # every typed neuron, avoid a network query.
    typed = max(1, int(frame.get("type", pd.Series(dtype=str)).astype(str).str.lower().ne("unknown").sum()))
    enough = before["hemibrain_type"] / typed >= 0.8 and before["flywire_type"] / typed >= 0.8
    if enough:
        return frame, {"source": "flat_annotations", "before": before, "after": before, "hydrated": False}

    try:
        records, fetch_meta = fetch_identity_metadata(cache_path=cache_path, token=token)
        body_ids = frame["body_id"].astype(int)
        for key in FIELDS:
            lookup = {body: values.get(key, "") for body, values in records.items()}
            fetched = body_ids.map(lookup).fillna("").astype(str)
            current = frame[key].fillna("").astype(str)
            mask = current.str.strip().eq("") & fetched.str.strip().ne("")
            frame.loc[mask, key] = fetched.loc[mask]
        after = {key: int(frame[key].str.strip().ne("").sum()) for key in FIELDS}
        return frame, {**fetch_meta, "before": before, "after": after, "hydrated": True}
    except Exception as exc:
        return frame, {
            "source": "unavailable",
            "before": before,
            "after": before,
            "hydrated": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
