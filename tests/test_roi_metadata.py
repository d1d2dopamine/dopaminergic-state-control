import gzip
import json

import pandas as pd

import dsc.roi_metadata as rm


def test_fetch_roi_metadata_paginates_and_caches(tmp_path, monkeypatch):
    responses = [
        {
            "columns": ["bodyId", "inputRois", "outputRois"],
            "data": [[1, ["MB"], ["SMP"]], [2, [], ["MB", "SMP"]]],
        },
        {
            "columns": ["bodyId", "inputRois", "outputRois"],
            "data": [[3, ["VNC"], []]],
        },
    ]
    calls = []

    def fake_post(cypher, token=None, timeout=120, retries=3):
        calls.append(cypher)
        return responses.pop(0)

    monkeypatch.setattr(rm, "_post_cypher", fake_post)
    cache = tmp_path / "roi.json.gz"
    records, meta = rm.fetch_roi_metadata(cache, batch_size=2)
    assert records[1] == ('["MB"]', '["SMP"]')
    assert records[2][0] == "[]"
    assert records[3][1] == "[]"
    assert meta["source"] == "neuprint"
    assert len(calls) == 2
    assert cache.exists()

    # A second load must not touch neuPrint.
    monkeypatch.setattr(rm, "_post_cypher", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    cached, cached_meta = rm.fetch_roi_metadata(cache, batch_size=2)
    assert cached == records
    assert cached_meta["source"] == "cache"


def test_hydrate_roi_metadata_uses_fetch_only_when_flat_coverage_is_missing(monkeypatch):
    frame = pd.DataFrame([
        {"body_id": 1, "input_rois": "[]", "output_rois": "[]"},
        {"body_id": 2, "input_rois": "[]", "output_rois": "[]"},
    ])

    def fake_fetch(cache_path=None, token=None, batch_size=10000, max_batches=50):
        return {
            1: ('["MB"]', '["SMP"]'),
            2: ('["SMP"]', '["MB"]'),
        }, {"source": "neuprint", "records": 2}

    monkeypatch.setattr(rm, "fetch_roi_metadata", fake_fetch)
    hydrated, meta = rm.hydrate_roi_metadata(frame, {1, 2}, minimum_coverage=0.9)
    assert hydrated.loc[hydrated.body_id.eq(1), "input_rois"].iloc[0] == '["MB"]'
    assert meta["hydrated"] is True
    assert meta["after"]["input_fraction"] == 1.0
    assert meta["after"]["output_fraction"] == 1.0


def test_hydrate_roi_metadata_is_fail_soft(monkeypatch):
    frame = pd.DataFrame([
        {"body_id": 1, "input_rois": "[]", "output_rois": "[]"},
    ])
    monkeypatch.setattr(rm, "fetch_roi_metadata", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    unchanged, meta = rm.hydrate_roi_metadata(frame, {1})
    assert unchanged.iloc[0].input_rois == "[]"
    assert meta["source"] == "unavailable"
    assert "offline" in meta["error"]


def test_hydrate_roi_metadata_skips_network_when_flat_coverage_is_sufficient(monkeypatch):
    frame = pd.DataFrame([
        {"body_id": 1, "input_rois": '["MB"]', "output_rois": '["SMP"]'},
        {"body_id": 2, "input_rois": '["SMP"]', "output_rois": '["MB"]'},
    ])
    monkeypatch.setattr(rm, "fetch_roi_metadata", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
    unchanged, meta = rm.hydrate_roi_metadata(frame, {1, 2})
    assert meta["source"] == "flat_annotations"
    assert meta["hydrated"] is False
    assert unchanged.equals(frame)
