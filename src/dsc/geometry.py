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
MAJOR_SHELL_GROUP = "fullbrain-major-shells"
MAJOR_SHELL_SEGMENTS = (1, 2, 3)
SKELETON_ROOT = "v1.0/segmentation/skeletons-malecns/skeletons-precomputed/"


def _source_url(relative: str) -> str:
    return BASE + urllib.parse.quote(relative, safe="/:{}")


def _get_json(relative: str) -> dict:
    req = urllib.request.Request(_source_url(relative), headers={"User-Agent": "dopaminergic-state-control/0.5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    h = hashlib.sha256()
    size = 0
    req = urllib.request.Request(url, headers={"User-Agent": "dopaminergic-state-control/0.5.0"})
    with urllib.request.urlopen(req, timeout=180) as src, temp.open("wb") as dst:
        while True:
            block = src.read(4 * 1024 * 1024)
            if not block:
                break
            dst.write(block)
            h.update(block)
            size += len(block)
    temp.replace(destination)
    return size, h.hexdigest()


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _read_legacy_mesh(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read the MaleCNS legacy mesh format: uint32 N, N float32 XYZ, triangle uint32 indices."""
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
    return {"vertices": int(len(xyz)), "triangles": int(len(triangles)), "bounds": [lo, hi]}


def _write_legacy_mesh(path: str | Path, vertices: np.ndarray, triangles: np.ndarray) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(vertices, dtype="<f4")
    triangles = np.asarray(triangles, dtype="<u4")
    with p.open("wb") as stream:
        stream.write(struct.pack("<I", len(vertices)))
        stream.write(vertices.tobytes(order="C"))
        stream.write(triangles.reshape(-1).tobytes(order="C"))


def _merge_meshes(meshes: list[tuple[np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    if not meshes:
        raise ValueError("No meshes to merge")
    vertices_out: list[np.ndarray] = []
    triangles_out: list[np.ndarray] = []
    offset = 0
    for vertices, triangles in meshes:
        vertices = np.asarray(vertices, dtype="<f4")
        triangles = np.asarray(triangles, dtype="<u4")
        vertices_out.append(vertices)
        triangles_out.append(triangles + np.uint32(offset))
        offset += len(vertices)
    return np.concatenate(vertices_out, axis=0), np.concatenate(triangles_out, axis=0)


def _simplify_arrays(vertices: np.ndarray, triangles: np.ndarray, divisions: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic vertex-cluster LOD which keeps original MaleCNS surface coordinates."""
    divisions = int(divisions)
    if divisions < 4 or divisions > 160:
        raise ValueError("LOD divisions must be between 4 and 160")
    vertices = np.asarray(vertices, dtype="<f4")
    triangles = np.asarray(triangles, dtype="<u4")
    if len(vertices) == 0:
        raise ValueError("Empty MaleCNS mesh")
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
        # Remove duplicate triangles regardless of winding, retaining deterministic source order.
        canonical = np.sort(reduced_triangles, axis=1)
        _, unique_rows = np.unique(canonical, axis=0, return_index=True)
        reduced_triangles = reduced_triangles[np.sort(unique_rows)]
    return reduced_vertices.astype("<f4", copy=False), reduced_triangles.astype("<u4", copy=False)


def _simplify_legacy_mesh(source: str | Path, destination: str | Path, divisions: int = 20) -> dict:
    vertices, triangles = _read_legacy_mesh(source)
    reduced_vertices, reduced_triangles = _simplify_arrays(vertices, triangles, divisions)
    _write_legacy_mesh(destination, reduced_vertices, reduced_triangles)
    return {
        "lod_vertices": int(len(reduced_vertices)),
        "lod_triangles": int(len(reduced_triangles)),
        "lod_bytes": int(Path(destination).stat().st_size),
        "lod_sha256": _sha256(destination),
        "lod_divisions": int(divisions),
    }


def _precomputed_fragment_urls(group: str, segment: int | str) -> list[str]:
    root = f"rois/{group}/mesh/"
    info = _get_json(f"{root}{segment}:0")
    fragments = info.get("fragments", [])
    if not fragments:
        raise RuntimeError(f"No mesh fragments for {group}/{segment}")
    return [_source_url(root + fragment) for fragment in fragments]


def _segment_properties(version: str) -> dict[str, str]:
    inline = _get_json(f"rois/{version}/segment_properties/info")["inline"]
    return dict(zip(inline["ids"], inline["properties"][0]["values"]))


def _region_record(item: tuple[str, str, str]) -> dict:
    version, source_id, label = item
    urls = _precomputed_fragment_urls(version, source_id)
    if len(urls) != 1:
        raise RuntimeError(f"ROI {source_id} ({label}) has {len(urls)} fragments; expected 1")
    return {"source_id": int(source_id), "label": label, "source_url": urls[0]}


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

    for finding in findings:
        add(finding.get("focus_node"))
    for finding in findings:
        for body in finding.get("related_nodes", []):
            add(body)
    return ordered


def _experiment_skeleton_ids(experiment_path: str | Path | None) -> list[int]:
    if experiment_path is None:
        return []
    payload = json.loads(Path(experiment_path).read_text(encoding="utf-8"))
    if not payload.get("available"):
        return []
    ordered: list[int] = []
    seen: set[int] = set()
    def add(value) -> None:
        if value is None:
            return
        body = int(value)
        if body not in seen:
            seen.add(body)
            ordered.append(body)
    for body in payload.get("candidate_ids", []):
        add(body)
    for cell in payload.get("cells", []):
        add(cell.get("body_id"))
    candidate_set = {int(x) for x in payload.get("candidate_ids", [])}
    for cell in payload.get("cells", []):
        if int(cell.get("body_id", -1)) not in candidate_set:
            continue
        for partner in cell.get("top_inputs", []):
            add(partner.get("body_id"))
        for partner in cell.get("top_outputs", []):
            add(partner.get("body_id"))
    return ordered


def _build_major_shell(
    vendor_root: Path,
    source_root: Path,
    lod_divisions: int,
) -> dict:
    """Build one browser mesh from the official central-brain + optic-lobe shells."""
    raw_meshes: list[tuple[np.ndarray, np.ndarray]] = []
    sources: list[dict] = []
    for segment in MAJOR_SHELL_SEGMENTS:
        urls = _precomputed_fragment_urls(MAJOR_SHELL_GROUP, segment)
        for fragment_index, url in enumerate(urls):
            raw = source_root / "major-shell" / f"{segment}-{fragment_index}.bin"
            if raw.exists():
                size, sha = raw.stat().st_size, _sha256(raw)
            else:
                size, sha = _download(url, raw)
            vertices, triangles = _read_legacy_mesh(raw)
            raw_meshes.append((vertices, triangles))
            sources.append({
                "segment": int(segment),
                "fragment": int(fragment_index),
                "source_url": url,
                "source_bytes": int(size),
                "source_sha256": sha,
                "source_vertices": int(len(vertices)),
                "source_triangles": int(len(triangles)),
            })

    merged_vertices, merged_triangles = _merge_meshes(raw_meshes)
    source_lo = merged_vertices.min(axis=0)
    source_hi = merged_vertices.max(axis=0)
    display_vertices, display_triangles = _simplify_arrays(merged_vertices, merged_triangles, lod_divisions)
    out_path = vendor_root / "brain-shell.bin"
    _write_legacy_mesh(out_path, display_vertices, display_triangles)
    return {
        "mode": "major-shell",
        "group": MAJOR_SHELL_GROUP,
        "segments": list(MAJOR_SHELL_SEGMENTS),
        "local_url": "data/geometry/brain-shell.bin",
        "source_files": sources,
        "source_vertices": int(len(merged_vertices)),
        "source_triangles": int(len(merged_triangles)),
        "display_vertices": int(len(display_vertices)),
        "display_triangles": int(len(display_triangles)),
        "display_bytes": int(out_path.stat().st_size),
        "display_sha256": _sha256(out_path),
        "lod_divisions": int(lod_divisions),
        "bounds": [source_lo.astype(float).tolist(), source_hi.astype(float).tolist()],
    }


def _build_roi_fallback(
    vendor_root: Path,
    source_root: Path,
    lod_divisions: int,
) -> tuple[list[dict], dict]:
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        records = list(pool.map(_region_record, items))
    records.sort(key=lambda r: (r["label"], r["source_id"]))

    def vendor_region(record: dict) -> dict:
        raw = source_root / "regions" / f"{record['source_id']}.bin"
        if raw.exists():
            source_size, source_sha = raw.stat().st_size, _sha256(raw)
        else:
            source_size, source_sha = _download(record["source_url"], raw)
        source_stats = _mesh_stats(raw)
        lod = vendor_root / "regions" / f"{record['source_id']}.bin"
        lod_stats = _simplify_legacy_mesh(raw, lod, divisions=lod_divisions)
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(vendor_region, records))
    records.sort(key=lambda r: (r["label"], r["source_id"]))

    lows = np.asarray([r["bounds"][0] for r in records], dtype=float)
    highs = np.asarray([r["bounds"][1] for r in records], dtype=float)
    bounds = [lows.min(axis=0).tolist(), highs.max(axis=0).tolist()]
    summary = {
        "mode": "roi-fallback",
        "version": version,
        "source_triangles": int(sum(r["source_triangles"] for r in records)),
        "display_triangles": int(sum(r["lod_triangles"] for r in records)),
        "display_bytes": int(sum(r["lod_bytes"] for r in records)),
        "bounds": bounds,
    }
    return records, summary


def build_geometry_manifest(
    output: str | Path,
    vendor_dir: str | Path | None = None,
    findings_path: str | Path | None = None,
    experiment_path: str | Path | None = None,
    max_vendored_skeletons: int = 128,
    region_lod_divisions: int = 20,
    source_cache_dir: str | Path | None = None,
    shell_lod_divisions: int = 46,
) -> dict:
    vendor_root = Path(vendor_dir) if vendor_dir else None
    display_center = [376352.0, 313268.0, 538304.0]
    display_scale = 1e-4
    global_bounds = None
    regions: list[dict] = []
    brain_shell = None
    geometry_mode = "metadata-only"
    temp_cache = None

    if vendor_root:
        vendor_root.mkdir(parents=True, exist_ok=True)
        if source_cache_dir:
            source_root = Path(source_cache_dir)
            source_root.mkdir(parents=True, exist_ok=True)
        else:
            temp_cache = tempfile.TemporaryDirectory(prefix="dsc-malecns-geometry-")
            source_root = Path(temp_cache.name)

        # Prefer the official coarse anatomical shell used by MaleCNS viewers.
        # If that source changes or is unavailable, fall back to the v0.2 ROI path.
        try:
            brain_shell = _build_major_shell(vendor_root, source_root, int(shell_lod_divisions))
            geometry_mode = "major-shell"
            global_bounds = brain_shell["bounds"]
        except Exception as exc:
            regions, fallback = _build_roi_fallback(vendor_root, source_root, int(region_lod_divisions))
            geometry_mode = "roi-fallback"
            global_bounds = fallback["bounds"]
            brain_shell = {"mode": "roi-fallback", "error": str(exc), **fallback}

        lo = np.asarray(global_bounds[0], dtype=float)
        hi = np.asarray(global_bounds[1], dtype=float)
        display_center = ((lo + hi) / 2.0).tolist()
        span = float(np.max(hi - lo))
        if span > 0:
            display_scale = 90.0 / span

    experiment_skeleton_ids = _experiment_skeleton_ids(experiment_path)
    finding_skeleton_ids = _finding_skeleton_ids(findings_path)
    skeleton_ids = list(dict.fromkeys(experiment_skeleton_ids + finding_skeleton_ids))
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

    if geometry_mode == "major-shell" and brain_shell:
        source_triangles_total = int(brain_shell.get("source_triangles", 0))
        display_triangles_total = int(brain_shell.get("display_triangles", 0))
        display_bytes_total = int(brain_shell.get("display_bytes", 0))
    else:
        source_triangles_total = int(sum(r.get("source_triangles", 0) for r in regions))
        display_triangles_total = int(sum(r.get("lod_triangles", 0) for r in regions))
        display_bytes_total = int(sum(r.get("lod_bytes", 0) for r in regions))

    payload = {
        "dataset": "male-cns:v1.0",
        "coordinate_space": "MaleCNS EM",
        "units": "nm",
        "license": "CC-BY",
        "geometry_mode": geometry_mode,
        "brain_shell": brain_shell,
        "source_skeleton_url_template": _source_url(SKELETON_ROOT) + "{body_id}",
        "local_skeleton_url_template": "data/geometry/skeletons/{body_id}.bin" if vendor_root else None,
        "vendored_skeleton_ids": vendored_skeleton_ids,
        "finding_skeleton_ids_total": len(finding_skeleton_ids),
        "experiment_skeleton_ids_total": len(experiment_skeleton_ids),
        "max_vendored_skeletons": int(max_vendored_skeletons),
        "display_center": display_center,
        "display_scale": float(display_scale),
        "bounds": global_bounds,
        # Canonical viewer mapping: screen-X = -EM-X, screen-Y = -EM-Z, screen-Z = EM-Y.
        # This is applied identically to shell, skeletons and synapse coordinates.
        "viewer_axes": {"x": "-EM_X", "y": "-EM_Z", "z": "EM_Y"},
        "region_lod": {
            "method": "deterministic voxel vertex clustering",
            "source_triangles_total": source_triangles_total,
            "display_triangles_total": display_triangles_total,
            "display_bytes_total": display_bytes_total,
        },
        "regions": regions,
        "skeleton_files": skeleton_files,
        "note": (
            "The browser prefers one deterministic LOD derived from the official fullbrain-major-shells source (central brain + optic lobes). "
            "If that source cannot be built, the workflow falls back to optimized official fullbrain ROI surfaces. Neuron skeletons remain official MaleCNS centerlines."
        ),
    }
    write_json(output, payload)
    return payload
