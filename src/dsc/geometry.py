from __future__ import annotations

import concurrent.futures
import hashlib
import json
import struct
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

from .io import write_json

BASE = "https://storage.googleapis.com/flyem-male-cns/"
REGION_VERSIONS = ["fullbrain-roi-v5", "fullbrain-roi-v4"]
SKELETON_ROOT = "v1.0/segmentation/skeletons-malecns/skeletons-precomputed/"


def _source_url(relative: str) -> str:
    return BASE + urllib.parse.quote(relative, safe="/:{}")


def _get_json(relative: str) -> dict:
    req = urllib.request.Request(_source_url(relative), headers={"User-Agent": "dopaminergic-state-control/0.2"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.2"})
    with urllib.request.urlopen(req, timeout=120) as src, temp.open("wb") as dst:
        while True:
            block = src.read(4 * 1024 * 1024)
            if not block:
                break
            dst.write(block)
            h.update(block)
            size += len(block)
    temp.replace(destination)
    return size, h.hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _mesh_stats(path: str | Path) -> dict:
    """Read the native MaleCNS legacy mesh header/vertices without touching indices.

    Format: uint32 vertex count, N float32 XYZ triples, then uint32 triangle indices.
    The exact source file stays unchanged; this only derives bounds for camera setup.
    """
    p = Path(path)
    size = p.stat().st_size
    with p.open("rb") as stream:
        header = stream.read(4)
        if len(header) != 4:
            raise ValueError(f"Invalid MaleCNS mesh header: {p}")
        vertices = struct.unpack("<I", header)[0]
        coords = np.fromfile(stream, dtype="<f4", count=vertices * 3)
    if coords.size != vertices * 3:
        raise ValueError(f"Truncated MaleCNS mesh vertices: {p}")
    remainder = size - 4 - vertices * 12
    if remainder < 0 or remainder % 12 != 0:
        raise ValueError(f"Invalid MaleCNS mesh byte size: {p}")
    xyz = coords.reshape((-1, 3))
    lo = xyz.min(axis=0).astype(float).tolist()
    hi = xyz.max(axis=0).astype(float).tolist()
    return {
        "vertices": int(vertices),
        "triangles": int(remainder // 12),
        "bounds": [lo, hi],
    }


def _segment_properties(version: str) -> dict[str, str]:
    inline = _get_json(f"rois/{version}/segment_properties/info")["inline"]
    return dict(zip(inline["ids"], inline["properties"][0]["values"]))


def _region_record(item: tuple[str, str, str]) -> dict:
    version, source_id, label = item
    mesh_root = f"rois/{version}/mesh/"
    info = _get_json(f"{mesh_root}{source_id}:0")
    fragments = info.get("fragments", [])
    if len(fragments) != 1:
        raise RuntimeError(f"ROI {source_id} ({label}) has {len(fragments)} mesh fragments; expected 1")
    relative = mesh_root + fragments[0]
    return {
        "source_id": int(source_id),
        "label": label,
        "source_url": _source_url(relative),
    }


def _finding_skeleton_ids(findings_path: str | Path | None) -> list[int]:
    """Return deterministic IDs with focus neurons first, then contextual neurons.

    This ordering matters when Pages vendoring is capped: every displayed finding
    gets its focus cell before extra comparison/source cells consume the budget.
    """
    if findings_path is None:
        return []
    findings = json.loads(Path(findings_path).read_text(encoding="utf-8"))
    ordered: list[int] = []
    seen: set[int] = set()

    def add(value) -> None:
        if value is None:
            return
        body = int(value)
        if body not in seen:
            seen.add(body)
            ordered.append(body)

    for finding in findings:
        add(finding.get("focus_node"))
    for finding in findings:
        for body in finding.get("related_nodes", []):
            add(body)
    return ordered


def build_geometry_manifest(
    output: str | Path,
    vendor_dir: str | Path | None = None,
    findings_path: str | Path | None = None,
    max_vendored_skeletons: int = 256,
) -> dict:
    last_error = None
    version = None
    regions = None
    for candidate in REGION_VERSIONS:
        try:
            regions = _segment_properties(candidate)
            version = candidate
            break
        except Exception as exc:
            last_error = exc
    if regions is None or version is None:
        raise RuntimeError(f"Could not read official MaleCNS ROI segment properties: {last_error}")

    items = [(version, i, label) for i, label in regions.items() if label not in {"CV-anterior", "CRN"}]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        records = list(pool.map(_region_record, items))
    records.sort(key=lambda r: (r["label"], r["source_id"]))

    vendor_root = Path(vendor_dir) if vendor_dir else None
    display_center = [376352.0, 313268.0, 538304.0]
    display_scale = 1e-4
    global_bounds = None

    if vendor_root:
        def vendor_region(record: dict) -> dict:
            dest = vendor_root / "regions" / f"{record['source_id']}.bin"
            if dest.exists():
                size, sha = dest.stat().st_size, _sha256(dest)
            else:
                size, sha = _download(record["source_url"], dest)
            record = dict(record)
            record.update(_mesh_stats(dest))
            record.update({
                "local_url": f"data/geometry/regions/{record['source_id']}.bin",
                "bytes": int(size),
                "sha256": sha,
            })
            return record

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            records = list(pool.map(vendor_region, records))
        records.sort(key=lambda r: (r["label"], r["source_id"]))

        lows = np.asarray([r["bounds"][0] for r in records], dtype=float)
        highs = np.asarray([r["bounds"][1] for r in records], dtype=float)
        lo = lows.min(axis=0)
        hi = highs.max(axis=0)
        global_bounds = [lo.tolist(), hi.tolist()]
        display_center = ((lo + hi) / 2.0).tolist()
        span = float(np.max(hi - lo))
        if span > 0:
            # Normalize the largest specimen extent to ~90 viewer units. The raw
            # coordinates and exact source bytes remain untouched and recorded.
            display_scale = 90.0 / span

    skeleton_ids = _finding_skeleton_ids(findings_path)
    skeleton_ids_to_vendor = skeleton_ids[: max(0, int(max_vendored_skeletons))]
    vendored_skeleton_ids: list[int] = []
    skeleton_files: list[dict] = []
    if vendor_root and skeleton_ids_to_vendor:
        def vendor_skeleton(body_id: int) -> dict | None:
            source = _source_url(SKELETON_ROOT + str(body_id))
            dest = vendor_root / "skeletons" / f"{body_id}.bin"
            try:
                if dest.exists():
                    size, sha = dest.stat().st_size, _sha256(dest)
                else:
                    size, sha = _download(source, dest)
            except Exception:
                return None
            return {
                "body_id": body_id,
                "source_url": source,
                "local_url": f"data/geometry/skeletons/{body_id}.bin",
                "bytes": int(size),
                "sha256": sha,
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            skeleton_files = [r for r in pool.map(vendor_skeleton, skeleton_ids_to_vendor) if r is not None]
        vendored_skeleton_ids = [int(r["body_id"]) for r in skeleton_files]

    payload = {
        "dataset": "male-cns:v1.0",
        "coordinate_space": "MaleCNS EM",
        "units": "nm",
        "license": "CC-BY",
        "region_source": BASE + f"rois/{version}/",
        "source_skeleton_url_template": _source_url(SKELETON_ROOT) + "{body_id}",
        "local_skeleton_url_template": "data/geometry/skeletons/{body_id}.bin" if vendor_root else None,
        "vendored_skeleton_ids": vendored_skeleton_ids,
        "finding_skeleton_ids_total": len(skeleton_ids),
        "max_vendored_skeletons": int(max_vendored_skeletons),
        "display_center": display_center,
        "display_scale": float(display_scale),
        "bounds": global_bounds,
        "regions": records,
        "skeleton_files": skeleton_files,
        "note": (
            "Geometry is official MaleCNS data. Region meshes and vendored skeletons are copied byte-for-byte into the Pages artifact; "
            "non-vendored finding skeletons fall back to the same official public skeleton endpoint. Source URLs and SHA-256 hashes are retained."
        ),
    }
    write_json(output, payload)
    return payload
