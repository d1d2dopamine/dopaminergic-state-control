from __future__ import annotations

import concurrent.futures
import hashlib
import json
import struct
import tempfile
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
    req = urllib.request.Request(_source_url(relative), headers={"User-Agent": "dopaminergic-state-control/0.2.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.2.1"})
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


def _read_legacy_mesh(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a MaleCNS legacy mesh: uint32 N, N float32 XYZ, then uint32 triangle indices."""
    p = Path(path)
    raw = p.read_bytes()
    if len(raw) < 4:
        raise ValueError(f"Invalid MaleCNS mesh header: {p}")
    vertices = struct.unpack_from("<I", raw, 0)[0]
    vertex_end = 4 + vertices * 12
    if vertex_end > len(raw) or (len(raw) - vertex_end) % 12 != 0:
        raise ValueError(f"Invalid MaleCNS mesh byte size: {p}")
    xyz = np.frombuffer(raw, dtype="<f4", count=vertices * 3, offset=4).reshape((-1, 3)).copy()
    triangles = np.frombuffer(raw, dtype="<u4", offset=vertex_end).reshape((-1, 3)).copy()
    if triangles.size and int(triangles.max()) >= vertices:
        raise ValueError(f"MaleCNS mesh index out of range: {p}")
    return xyz, triangles


def _mesh_stats(path: str | Path) -> dict:
    xyz, triangles = _read_legacy_mesh(path)
    lo = xyz.min(axis=0).astype(float).tolist()
    hi = xyz.max(axis=0).astype(float).tolist()
    return {
        "vertices": int(len(xyz)),
        "triangles": int(len(triangles)),
        "bounds": [lo, hi],
    }


def _write_legacy_mesh(path: str | Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(vertices, dtype="<f4")
    triangles = np.asarray(triangles, dtype="<u4")
    with p.open("wb") as stream:
        stream.write(struct.pack("<I", len(vertices)))
        stream.write(vertices.tobytes(order="C"))
        stream.write(triangles.reshape(-1).tobytes(order="C"))


def _simplify_legacy_mesh(source: str | Path, destination: str | Path, divisions: int = 20) -> dict:
    """Create a deterministic low-detail surface from the official ROI mesh.

    Vertex clustering is used only for browser display. Each cluster is represented
    by one *original* MaleCNS surface vertex, so displayed coordinates stay in the
    source EM coordinate system. Degenerate/duplicate triangles are removed.
    The source mesh is never modified and its hash/statistics are retained separately.
    """
    divisions = int(divisions)
    if divisions < 4 or divisions > 128:
        raise ValueError("region LOD divisions must be between 4 and 128")

    vertices, triangles = _read_legacy_mesh(source)
    if len(vertices) == 0:
        raise ValueError(f"Empty MaleCNS mesh: {source}")

    lo = vertices.min(axis=0)
    hi = vertices.max(axis=0)
    span = np.maximum(hi - lo, np.float32(1e-6))
    q = np.floor((vertices - lo) / span * divisions).astype(np.int32)
    q = np.clip(q, 0, divisions - 1)
    keys = (q[:, 0].astype(np.int64) * divisions + q[:, 1]) * divisions + q[:, 2]
    _, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
    reduced_vertices = vertices[first]

    reduced_triangles = inverse[triangles]
    keep = (
        (reduced_triangles[:, 0] != reduced_triangles[:, 1])
        & (reduced_triangles[:, 1] != reduced_triangles[:, 2])
        & (reduced_triangles[:, 0] != reduced_triangles[:, 2])
    )
    reduced_triangles = reduced_triangles[keep]
    if len(reduced_triangles):
        canonical = np.sort(reduced_triangles, axis=1)
        _, unique_rows = np.unique(canonical, axis=0, return_index=True)
        reduced_triangles = reduced_triangles[np.sort(unique_rows)]

    _write_legacy_mesh(destination, reduced_vertices, reduced_triangles)
    return {
        "lod_vertices": int(len(reduced_vertices)),
        "lod_triangles": int(len(reduced_triangles)),
        "lod_bytes": int(Path(destination).stat().st_size),
        "lod_sha256": _sha256(Path(destination)),
        "lod_divisions": divisions,
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

    # Focus cells are always prioritized before optional context cells.
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
    max_vendored_skeletons: int = 128,
    region_lod_divisions: int = 20,
    source_cache_dir: str | Path | None = None,
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
    temp_cache = None

    if vendor_root:
        if source_cache_dir:
            source_root = Path(source_cache_dir)
            source_root.mkdir(parents=True, exist_ok=True)
        else:
            temp_cache = tempfile.TemporaryDirectory(prefix="dsc-malecns-geometry-")
            source_root = Path(temp_cache.name)

        def vendor_region(record: dict) -> dict:
            raw = source_root / "regions" / f"{record['source_id']}.bin"
            if raw.exists():
                source_size, source_sha = raw.stat().st_size, _sha256(raw)
            else:
                source_size, source_sha = _download(record["source_url"], raw)
            source_stats = _mesh_stats(raw)

            lod = vendor_root / "regions" / f"{record['source_id']}.bin"
            lod_stats = _simplify_legacy_mesh(raw, lod, divisions=region_lod_divisions)
            out = dict(record)
            out.update({
                "local_url": f"data/geometry/regions/{record['source_id']}.bin",
                "source_bytes": int(source_size),
                "source_sha256": source_sha,
                "source_vertices": source_stats["vertices"],
                "source_triangles": source_stats["triangles"],
                "bounds": source_stats["bounds"],
                **lod_stats,
            })
            return out

        # Downloads can overlap, but mesh reduction is cheap and deterministic.
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
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

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            skeleton_files = [r for r in pool.map(vendor_skeleton, skeleton_ids_to_vendor) if r is not None]
        vendored_skeleton_ids = [int(r["body_id"]) for r in skeleton_files]

    if temp_cache is not None:
        temp_cache.cleanup()

    source_triangles_total = int(sum(r.get("source_triangles", 0) for r in records))
    lod_triangles_total = int(sum(r.get("lod_triangles", 0) for r in records))
    lod_bytes_total = int(sum(r.get("lod_bytes", 0) for r in records))

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
        "region_lod": {
            "method": "deterministic voxel vertex clustering",
            "divisions_per_axis": int(region_lod_divisions),
            "source_triangles_total": source_triangles_total,
            "display_triangles_total": lod_triangles_total,
            "display_bytes_total": lod_bytes_total,
            "coordinates": "cluster representatives are original MaleCNS surface vertices",
        },
        "regions": records,
        "skeleton_files": skeleton_files,
        "note": (
            "Neuron skeleton files are official MaleCNS data. Browser ROI surfaces are deterministic low-detail derivatives of official MaleCNS meshes; "
            "source URLs, source hashes, source triangle counts, and LOD hashes are retained. The full source ROI meshes are used in CI but are not shipped to the browser."
        ),
    }
    write_json(output, payload)
    return payload
