from pathlib import Path

import pandas as pd

from dsc.discovery import discover, select_dopamine_core
from dsc.io import load_config, load_snapshot, load_snapshot_meta


def test_demo_discovers_candidates():
    nodes, edges = load_snapshot(Path("data/demo"))
    config = load_config("configs/demo.yml")
    result = discover(nodes, edges, config, load_snapshot_meta("data/demo"))
    assert len(result.core_ids) == 12
    assert len(result.findings) > 0
    assert all(f["kind"] in {"within_type_outlier", "bilateral_asymmetry", "type_side_shift", "dopamine_input_enrichment"} for f in result.findings)
    assert "peer_anomaly_score" in result.features.columns


def test_findings_do_not_claim_mechanism():
    nodes, edges = load_snapshot(Path("data/demo"))
    result = discover(nodes, edges, load_config("configs/demo.yml"), load_snapshot_meta("data/demo"))
    text = " ".join(f["interpretation"] for f in result.findings).lower()
    assert "candidate" in text or "lead" in text
    assert "mechanism proven" not in text


def test_consensus_dopamine_selection_ignores_raw_prediction_confidence():
    nodes = pd.DataFrame([
        {"body_id": 1, "type": "DAN", "side": "L", "status": "Traced", "nt": "dopamine", "nt_confidence": 0.10},
        {"body_id": 2, "type": "KC", "side": "R", "status": "Traced", "nt": "acetylcholine", "nt_confidence": 0.99},
    ])
    config = {"dataset": {"traced_only": True}}
    assert select_dopamine_core(nodes, config) == {1}


def test_peer_outlier_is_not_global_type_difference():
    # Two types live on very different scales. A global detector would flag every B;
    # the peer detector should only flag the deliberately extreme B member.
    rows=[]
    for i,v in enumerate([10,11,9,10,10,60]):
        rows.append({"body_id":100+i,"type":"A","side":"L" if i%2==0 else "R","status":"Traced","nt":"dopamine","nt_confidence":1.0})
    for i,v in enumerate([1000,1010,990,1005,995,6000]):
        rows.append({"body_id":200+i,"type":"B","side":"L" if i%2==0 else "R","status":"Traced","nt":"dopamine","nt_confidence":1.0})
    nodes=pd.DataFrame(rows)
    edges=[]
    partner=10000
    # give each core a count proportional to the synthetic scale above
    vals=[10,11,9,10,10,60,1000,1010,990,1005,995,6000]
    for body,count in zip(nodes.body_id,vals):
        edges.append({"pre":int(body),"post":partner+int(body),"weight":int(count)})
    edge_df=pd.DataFrame(edges)
    cfg={"dataset":{"min_synapses":1,"traced_only":True},"discovery":{"peer_min_type_size":6,"peer_robust_z_threshold":3.0,"top_findings":50,"bilateral_ratio_threshold":999,"side_min_each":99,"convergence_min_core_sources":99}}
    result=discover(nodes,edge_df,cfg,{"eligible_traced_neurons":len(nodes),"degree_scope":"test"})
    peer=[f for f in result.findings if f["kind"]=="within_type_outlier"]
    assert any(f["focus_node"]==105 for f in peer)
    assert any(f["focus_node"]==205 for f in peer)
    assert not any(f["focus_node"] in {200,201,202,203,204} for f in peer)
