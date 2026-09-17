import json
import struct
from pathlib import Path

import numpy as np

from dsc.geometry import _finding_skeleton_ids, _mesh_stats, _simplify_legacy_mesh


def _write_mesh(path: Path, vertices: np.ndarray, indices: np.ndarray) -> None:
    path.write_bytes(struct.pack('<I', len(vertices)) + vertices.astype('<f4').tobytes() + indices.astype('<u4').reshape(-1).tobytes())


def test_mesh_stats_reads_native_bounds(tmp_path: Path):
    vertices = np.asarray([[1, 2, 3], [4, -5, 6], [7, 8, -9]], dtype='<f4')
    indices = np.asarray([[0, 1, 2]], dtype='<u4')
    path = tmp_path / 'mesh.bin'
    _write_mesh(path, vertices, indices)
    stats = _mesh_stats(path)
    assert stats['vertices'] == 3
    assert stats['triangles'] == 1
    assert stats['bounds'] == [[1.0, -5.0, -9.0], [7.0, 8.0, 6.0]]


def test_lod_mesh_is_smaller_and_valid(tmp_path: Path):
    # Dense planar grid: enough repeated spatial cells for deterministic clustering.
    side = 40
    vertices = np.asarray([[x, y, (x + y) % 3 * 0.01] for y in range(side) for x in range(side)], dtype='<f4')
    tris = []
    for y in range(side - 1):
        for x in range(side - 1):
            a = y * side + x
            b = a + 1
            c = a + side
            d = c + 1
            tris.extend([[a, b, c], [b, d, c]])
    triangles = np.asarray(tris, dtype='<u4')
    source = tmp_path / 'source.bin'
    lod = tmp_path / 'lod.bin'
    _write_mesh(source, vertices, triangles)
    result = _simplify_legacy_mesh(source, lod, divisions=8)
    assert result['lod_vertices'] < len(vertices)
    assert result['lod_triangles'] < len(triangles)
    stats = _mesh_stats(lod)
    assert stats['vertices'] == result['lod_vertices']
    assert stats['triangles'] == result['lod_triangles']
    assert lod.stat().st_size < source.stat().st_size


def test_finding_skeleton_order_prioritizes_focus(tmp_path: Path):
    path = tmp_path / 'findings.json'
    path.write_text(json.dumps([
        {'focus_node': 10, 'related_nodes': [11, 12]},
        {'focus_node': 20, 'related_nodes': [10, 21]},
    ]))
    assert _finding_skeleton_ids(path) == [10, 20, 11, 12, 21]


def test_experiment_skeleton_ids_prioritize_live_lab_population(tmp_path):
    import json
    from dsc.geometry import _experiment_skeleton_ids
    payload = {
        "available": True,
        "candidate_ids": [1],
        "cells": [
            {"body_id": 1, "top_inputs": [{"body_id": 10}], "top_outputs": [{"body_id": 20}]},
            {"body_id": 2, "top_inputs": [{"body_id": 11}], "top_outputs": [{"body_id": 21}]},
        ],
    }
    p = tmp_path / "experiment.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert _experiment_skeleton_ids(p) == [1, 2, 10, 20]
