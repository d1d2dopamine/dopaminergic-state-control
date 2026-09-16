import json
import struct
from pathlib import Path

import numpy as np

from dsc.geometry import _finding_skeleton_ids, _mesh_stats


def test_mesh_stats_reads_native_bounds(tmp_path: Path):
    vertices = np.asarray([[1, 2, 3], [4, -5, 6], [7, 8, -9]], dtype='<f4')
    indices = np.asarray([0, 1, 2], dtype='<u4')
    path = tmp_path / 'mesh.bin'
    path.write_bytes(struct.pack('<I', len(vertices)) + vertices.tobytes() + indices.tobytes())
    stats = _mesh_stats(path)
    assert stats['vertices'] == 3
    assert stats['triangles'] == 1
    assert stats['bounds'] == [[1.0, -5.0, -9.0], [7.0, 8.0, 6.0]]


def test_finding_skeleton_order_prioritizes_focus(tmp_path: Path):
    path = tmp_path / 'findings.json'
    path.write_text(json.dumps([
        {'focus_node': 10, 'related_nodes': [11, 12]},
        {'focus_node': 20, 'related_nodes': [10, 21]},
    ]))
    assert _finding_skeleton_ids(path) == [10, 20, 11, 12, 21]
