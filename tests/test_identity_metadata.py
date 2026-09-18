import pandas as pd

import dsc.identity_metadata as im


def test_identity_metadata_paginates_and_hydrates(tmp_path, monkeypatch):
    responses = [{
        "columns": ["bodyId", "flywireType", "hemibrainType", "supertype", "itoleeHl", "dimorphism", "synonyms"],
        "data": [
            [1, "PAM04", "PAM04-dd", "PAM04", "DL1", "isomorphic", ["MB-M8"]],
            [2, "PAM04", "PAM04-can", "PAM04", "DL1", "isomorphic", None],
        ],
    }]
    monkeypatch.setattr(im, "_post_cypher", lambda *a, **k: responses.pop(0))
    cache = tmp_path / "identity.json.gz"
    records, meta = im.fetch_identity_metadata(cache_path=cache, batch_size=100)
    assert records[1]["hemibrain_type"] == "PAM04-dd"
    assert records[1]["synonyms"] == "MB-M8"
    assert meta["records_with_identity"] == 2

    frame = pd.DataFrame([
        {"body_id": 1, "type": "PAM04", "flywire_type": "", "hemibrain_type": "", "supertype": "", "hemilineage": "", "dimorphism": "", "synonyms": ""},
        {"body_id": 2, "type": "PAM04", "flywire_type": "", "hemibrain_type": "", "supertype": "", "hemilineage": "", "dimorphism": "", "synonyms": ""},
    ])
    hydrated, hmeta = im.hydrate_identity_metadata(frame, cache_path=cache)
    assert hydrated.loc[hydrated.body_id.eq(1), "hemibrain_type"].iloc[0] == "PAM04-dd"
    assert hmeta["source"] == "cache"
    assert hmeta["after"]["hemibrain_type"] == 2


def test_identity_hydration_is_fail_soft(monkeypatch):
    frame = pd.DataFrame([{"body_id": 1, "type": "PAM04"}])
    monkeypatch.setattr(im, "fetch_identity_metadata", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    hydrated, meta = im.hydrate_identity_metadata(frame)
    assert meta["source"] == "unavailable"
    assert hydrated.loc[0, "hemibrain_type"] == ""
