from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .io import write_json

SERVER = "https://neuprint.janelia.org"
DATASET = "male-cns:v1.0"


def _post_cypher(cypher: str, token: str | None = None, timeout: int = 120, retries: int = 3) -> dict:
    payload = json.dumps({"cypher": cypher, "dataset": DATASET}).encode("utf-8")
    headers = {
        "User-Agent": "dopaminergic-state-control/0.3.0",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    delay = 1.5
    last_error: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(SERVER + "/api/custom/custom", data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if "data" not in body:
                raise RuntimeError(f"neuPrint response missing data: {str(body)[:300]}")
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"neuPrint query failed: {last_error}")


def _pair_synapses(target: int, sources: list[int], max_points: int, token: str | None = None) -> list[dict]:
    if not sources or max_points <= 0:
        return []
    ids = ",".join(str(int(x)) for x in sources)
    # Synapse locations in neuPrint are stored in the dataset's 8-nm voxel coordinates.
    # We return both pre/post coordinates and apply the x8 transform only in the viewer.
    cypher = f"""
MATCH (n:Neuron)-[e:ConnectsTo]->(m:Neuron),
      (n)-[:Contains]->(nss:SynapseSet)-[:ConnectsTo]->(mss:SynapseSet)<-[:Contains]-(m),
      (nss)-[:Contains]->(ns:Synapse)-[:SynapsesTo]->(ms:Synapse)<-[:Contains]-(mss)
WHERE n.bodyId IN [{ids}] AND m.bodyId = {int(target)}
WITH DISTINCT n, m, ns, ms
RETURN n.bodyId AS pre, m.bodyId AS post,
       ns.location.x AS x_pre, ns.location.y AS y_pre, ns.location.z AS z_pre,
       ms.location.x AS x_post, ms.location.y AS y_post, ms.location.z AS z_post,
       ns.confidence AS confidence_pre, ms.confidence AS confidence_post
LIMIT {int(max_points)}
""".strip()
    response = _post_cypher(cypher, token=token)
    columns = response.get("columns", [])
    index = {name: i for i, name in enumerate(columns)}
    required = ["pre", "post", "x_pre", "y_pre", "z_pre", "x_post", "y_post", "z_post"]
    if any(k not in index for k in required):
        raise RuntimeError(f"unexpected neuPrint columns: {columns}")
    rows = []
    for row in response.get("data", []):
        try:
            rows.append({
                "pre": int(row[index["pre"]]),
                "post": int(row[index["post"]]),
                "pre_xyz": [int(row[index["x_pre"]]), int(row[index["y_pre"]]), int(row[index["z_pre"]])],
                "post_xyz": [int(row[index["x_post"]]), int(row[index["y_post"]]), int(row[index["z_post"]])],
                "confidence_pre": float(row[index["confidence_pre"]]) if "confidence_pre" in index and row[index["confidence_pre"]] is not None else None,
                "confidence_post": float(row[index["confidence_post"]]) if "confidence_post" in index and row[index["confidence_post"]] is not None else None,
            })
        except (TypeError, ValueError):
            continue
    return rows


def build_synapse_site_manifest(
    findings_path: str | Path,
    output: str | Path,
    max_sources: int = 8,
    max_points_per_finding: int = 2500,
    token: str | None = None,
) -> dict:
    findings = json.loads(Path(findings_path).read_text(encoding="utf-8"))
    token = token or os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
    out: dict[str, dict] = {}
    total_points = 0
    for finding in findings:
        fid = str(finding.get("id", ""))
        if not fid:
            continue
        if finding.get("kind") != "dopamine_input_enrichment":
            out[fid] = {
                "status": "not_applicable",
                "reason": "This detector does not assert direct connectivity between focus and comparison cells.",
                "points": [],
            }
            continue
        target = int(finding["focus_node"])
        sources = [int(x) for x in finding.get("related_nodes", [])[: max(0, int(max_sources))]]
        try:
            points = _pair_synapses(target, sources, int(max_points_per_finding), token=token)
            out[fid] = {
                "status": "ok",
                "target": target,
                "sources": sources,
                "points": points,
                "truncated": len(points) >= int(max_points_per_finding),
            }
            total_points += len(points)
        except Exception as exc:
            # 3D synapse overlay is a convenience layer, not a reason to fail the research run.
            out[fid] = {
                "status": "unavailable",
                "target": target,
                "sources": sources,
                "error": str(exc)[:600],
                "points": [],
            }

    payload = {
        "dataset": DATASET,
        "server": SERVER,
        "coordinate_units": "8nm voxels",
        "coordinate_scale_to_nm": 8.0,
        "max_sources": int(max_sources),
        "max_points_per_finding": int(max_points_per_finding),
        "total_points": int(total_points),
        "findings": out,
        "note": "Best-effort visualization data. Failure to query neuPrint does not invalidate the connectome discovery run.",
    }
    write_json(output, payload)
    return payload
