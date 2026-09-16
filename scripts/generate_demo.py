from __future__ import annotations

from pathlib import Path
import random
import pandas as pd

random.seed(20260916)
out = Path("data/demo")
out.mkdir(parents=True, exist_ok=True)

nodes = []
for i in range(12):
    nodes.append({
        "body_id": 1000 + i,
        "type": f"DAN{i//2:02d}",
        "side": "L" if i % 2 == 0 else "R",
        "status": "Traced",
        "nt": "dopamine",
        "nt_confidence": round(0.88 + random.random() * 0.1, 3),
    })
for i in range(30):
    nodes.append({
        "body_id": 2000 + i,
        "type": f"Partner{i%8:02d}",
        "side": "L" if i % 2 == 0 else "R",
        "status": "Traced",
        "nt": ["acetylcholine", "gaba", "glutamate"][i % 3],
        "nt_confidence": 0.9,
    })

edges = []
for dan in range(1000, 1012):
    targets = random.sample(range(2000, 2030), 6)
    sources = random.sample(range(2000, 2030), 5)
    for t in targets:
        edges.append({"pre": dan, "post": t, "weight": random.randint(3, 25)})
    for s in sources:
        edges.append({"pre": s, "post": dan, "weight": random.randint(3, 22)})
# Deliberate structural outlier: one dopamine neuron with a dominant output partner and high output weight.
for _ in range(8):
    edges.append({"pre": 1011, "post": 2029, "weight": 90})
# Deliberate convergence candidate.
for dan in range(1000, 1008):
    edges.append({"pre": dan, "post": 2028, "weight": 18 + (dan % 4)})
# Add some reciprocal structure.
for dan in range(1000, 1006):
    edges.append({"pre": dan, "post": 2000 + (dan - 1000), "weight": 12})
    edges.append({"pre": 2000 + (dan - 1000), "post": dan, "weight": 9})

edf = pd.DataFrame(edges).groupby(["pre", "post"], as_index=False)["weight"].sum()
pd.DataFrame(nodes).to_csv(out / "nodes.csv", index=False)
edf.to_csv(out / "edges.csv", index=False)
print(f"wrote {len(nodes)} nodes and {len(edf)} edges")
