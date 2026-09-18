from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

from .io import write_json
from .stats import benjamini_hochberg

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
    # We return both pre/post coordinates and apply the x8 transform in analysis/viewer.
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


def _source_eta_squared(points_nm: np.ndarray, labels: np.ndarray) -> float:
    if len(points_nm) < 2:
        return 0.0
    center = points_nm.mean(axis=0)
    total_ss = float(np.square(points_nm - center).sum())
    if total_ss <= 0:
        return 0.0
    within_ss = 0.0
    for source in np.unique(labels):
        subset = points_nm[labels == source]
        if len(subset) == 0:
            continue
        c = subset.mean(axis=0)
        within_ss += float(np.square(subset - c).sum())
    return float(max(0.0, min(1.0, 1.0 - within_ss / total_ss)))


def _spatial_metrics(points: list[dict], scale_to_nm: float = 8.0, permutations: int = 400, seed: int = 0) -> dict:
    """Describe whether different dopamine sources occupy distinct target territories.

    This is deliberately *not* a test that dopamine synapses are clustered versus
    every other transmitter. It only asks whether source identity explains the
    spatial distribution of the dopamine sites we queried.
    """
    valid = [p for p in points if p.get("post_xyz") is not None and p.get("pre") is not None]
    if len(valid) < 4:
        return {"available": False, "reason": "fewer than four postsynaptic sites"}
    xyz = np.asarray([p["post_xyz"] for p in valid], dtype=float) * float(scale_to_nm)
    labels = np.asarray([int(p["pre"]) for p in valid], dtype=np.int64)
    sources, counts = np.unique(labels, return_counts=True)
    if len(sources) < 2:
        return {"available": False, "reason": "fewer than two dopamine sources", "points": int(len(valid))}

    center = xyz.mean(axis=0)
    rms = float(np.sqrt(np.mean(np.sum(np.square(xyz - center), axis=1))))
    lo, hi = xyz.min(axis=0), xyz.max(axis=0)
    extent = float(np.linalg.norm(hi - lo))
    observed_eta2 = _source_eta_squared(xyz, labels)

    # Permute source identities while preserving the exact number of sites from
    # every queried source. Significant high eta2 means source-specific spatial
    # segregation/territories, not a causal mechanism.
    rng = np.random.default_rng(int(seed))
    exceed = 0
    if permutations > 0:
        for _ in range(int(permutations)):
            permuted = rng.permutation(labels)
            if _source_eta_squared(xyz, permuted) >= observed_eta2 - 1e-12:
                exceed += 1
        p_value = (exceed + 1.0) / (int(permutations) + 1.0)
    else:
        p_value = 1.0

    return {
        "available": True,
        "points": int(len(valid)),
        "sources": int(len(sources)),
        "rms_radius_nm": rms,
        "bounding_box_diagonal_nm": extent,
        "source_segregation_eta2": float(observed_eta2),
        "source_label_permutation_p": float(p_value),
        "source_counts": {str(int(s)): int(c) for s, c in zip(sources, counts)},
        "interpretation": "Fraction of postsynaptic spatial variance associated with dopamine-source identity; high significant values indicate source-specific territories among queried dopamine inputs.",
    }


def build_synapse_site_manifest(
    findings_path: str | Path,
    output: str | Path,
    max_sources: int = 24,
    max_points_per_finding: int = 4000,
    token: str | None = None,
    spatial_permutations: int = 400,
) -> dict:
    findings = json.loads(Path(findings_path).read_text(encoding="utf-8"))
    token = token or os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
    out: dict[str, dict] = {}
    total_points = 0
    spatial_ids: list[str] = []
    spatial_pvalues: list[float] = []

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
        source_order = finding.get("source_ids_by_weight") or finding.get("related_nodes", [])
        sources = [int(x) for x in source_order[: max(0, int(max_sources))]]
        try:
            points = _pair_synapses(target, sources, int(max_points_per_finding), token=token)
            seed_bytes = hashlib.sha256(fid.encode("utf-8")).digest()[:8]
            spatial = _spatial_metrics(
                points,
                scale_to_nm=8.0,
                permutations=int(spatial_permutations),
                seed=int.from_bytes(seed_bytes, "little"),
            )
            record = {
                "status": "ok",
                "target": target,
                "sources": sources,
                "queried_source_count": int(len(sources)),
                "all_source_count": int(finding.get("all_source_count", len(source_order))),
                "points": points,
                "truncated": len(points) >= int(max_points_per_finding),
                "spatial": spatial,
            }
            if spatial.get("available"):
                spatial_ids.append(fid)
                spatial_pvalues.append(float(spatial["source_label_permutation_p"]))
            out[fid] = record
            total_points += len(points)
        except Exception as exc:
            # 3D/spatial synapse evidence is a convenience layer, not a reason to
            # invalidate the connectome discovery run.
            out[fid] = {
                "status": "unavailable",
                "target": target,
                "sources": sources,
                "error": str(exc)[:600],
                "points": [],
            }

    qvalues = benjamini_hochberg(spatial_pvalues)
    for fid, q in zip(spatial_ids, qvalues):
        spatial = out[fid]["spatial"]
        spatial["source_label_permutation_q"] = float(q)
        eta2 = float(spatial.get("source_segregation_eta2", 0.0))
        if q <= 0.05 and eta2 >= 0.10:
            spatial["pattern"] = "source_specific_territories"
        else:
            spatial["pattern"] = "no_strong_source_segregation_evidence"

    payload = {
        "dataset": DATASET,
        "server": SERVER,
        "coordinate_units": "8nm voxels",
        "coordinate_scale_to_nm": 8.0,
        "max_sources": int(max_sources),
        "max_points_per_finding": int(max_points_per_finding),
        "spatial_permutations": int(spatial_permutations),
        "total_points": int(total_points),
        "findings": out,
        "note": (
            "Best-effort direct-connectivity visualization and spatial evidence. "
            "The spatial test concerns segregation among queried dopamine sources only; it is not a dopamine-versus-all-input clustering test."
        ),
    }
    write_json(output, payload)
    return payload


def _multi_pair_synapses(pre_ids: list[int], post_ids: list[int], max_points: int, token: str | None = None) -> list[dict]:
    """Fetch exact synapse sites for a bounded set of directed neuron pairs."""
    pre_ids = [int(x) for x in dict.fromkeys(pre_ids) if int(x) > 0]
    post_ids = [int(x) for x in dict.fromkeys(post_ids) if int(x) > 0]
    if not pre_ids or not post_ids or max_points <= 0:
        return []
    pres = ",".join(str(x) for x in pre_ids)
    posts = ",".join(str(x) for x in post_ids)
    cypher = f"""
MATCH (n:Neuron)-[:ConnectsTo]->(m:Neuron),
      (n)-[:Contains]->(nss:SynapseSet)-[:ConnectsTo]->(mss:SynapseSet)<-[:Contains]-(m),
      (nss)-[:Contains]->(ns:Synapse)-[:SynapsesTo]->(ms:Synapse)<-[:Contains]-(mss)
WHERE n.bodyId IN [{pres}] AND m.bodyId IN [{posts}]
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
    rows: list[dict] = []
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


def build_pam04_synapse_manifest(
    experiment_path: str | Path,
    output: str | Path,
    max_partners_per_direction: int = 10,
    max_points_per_direction: int = 2500,
    token: str | None = None,
) -> dict:
    """Best-effort real synapse sites for the PAM04 State Lab candidates.

    Only the strongest measured input/output partners already present in the
    Experiment 001 dossier are queried. Failure never invalidates the structural
    experiment; the live viewer simply falls back to skeleton-only animation.
    """
    experiment = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    token = token or os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
    payload = {
        "dataset": DATASET,
        "server": SERVER,
        "coordinate_units": "8nm voxels",
        "coordinate_scale_to_nm": 8.0,
        "max_partners_per_direction": int(max_partners_per_direction),
        "max_points_per_direction": int(max_points_per_direction),
        "candidates": {},
        "total_points": 0,
    }
    if not experiment.get("available"):
        payload["status"] = "not_applicable"
        payload["reason"] = "Experiment 001 PAM04 data unavailable"
        write_json(output, payload)
        return payload

    cells = {int(c["body_id"]): c for c in experiment.get("cells", [])}
    candidate_ids = [int(x) for x in experiment.get("candidate_ids", [])]
    for candidate in candidate_ids:
        cell = cells.get(candidate, {})
        input_ids = [int(x["body_id"]) for x in cell.get("top_inputs", [])[: max(0, int(max_partners_per_direction))]]
        output_ids = [int(x["body_id"]) for x in cell.get("top_outputs", [])[: max(0, int(max_partners_per_direction))]]
        record = {
            "input_partner_ids": input_ids,
            "output_partner_ids": output_ids,
            "input_points": [],
            "output_points": [],
            "status": "ok",
        }
        errors: list[str] = []
        try:
            record["input_points"] = _multi_pair_synapses(input_ids, [candidate], int(max_points_per_direction), token=token)
        except Exception as exc:
            errors.append("input: " + str(exc)[:400])
        try:
            record["output_points"] = _multi_pair_synapses([candidate], output_ids, int(max_points_per_direction), token=token)
        except Exception as exc:
            errors.append("output: " + str(exc)[:400])
        if errors:
            record["status"] = "partial" if record["input_points"] or record["output_points"] else "unavailable"
            record["errors"] = errors
        record["point_count"] = int(len(record["input_points"]) + len(record["output_points"]))
        payload["total_points"] += record["point_count"]
        payload["candidates"][str(candidate)] = record

    payload["status"] = "ok" if payload["total_points"] else "unavailable"
    write_json(output, payload)
    return payload
