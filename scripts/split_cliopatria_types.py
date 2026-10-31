"""
Simple, Non-Overengineered Separation of Cliopatria Dataset by 'Type' Field:
- data/cliopatria_polities.geojson (Type == 'POLITY')
- data/cliopatria_relations.geojson (Type == 'RELATION')
"""

import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from backend.config import DATA_DIR

INPUT_FILE = DATA_DIR / "cliopatria_polities_only.geojson"
POLITIES_OUTPUT = DATA_DIR / "cliopatria_polities.geojson"
RELATIONS_OUTPUT = DATA_DIR / "cliopatria_relations.geojson"

def split_by_type():
    print(f"[SPLIT] Loading {INPUT_FILE.name}...", flush=True)
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_features = data.get("features", [])
    print(f"[SPLIT] Total features: {len(raw_features)}", flush=True)

    polity_features = []
    relation_features = []

    for f in raw_features:
        f_type = f.get("properties", {}).get("Type", "")
        if f_type == "RELATION":
            relation_features.append(f)
        else:
            polity_features.append(f)

    print(f"[SPLIT] Polities count (Type == POLITY): {len(polity_features)}")
    print(f"[SPLIT] Relations count (Type == RELATION): {len(relation_features)}")

    with open(POLITIES_OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": polity_features}, f, ensure_ascii=False)

    with open(RELATIONS_OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": relation_features}, f, ensure_ascii=False)

    print(f"[SPLIT] Successfully created {POLITIES_OUTPUT.name} and {RELATIONS_OUTPUT.name}!")

if __name__ == "__main__":
    split_by_type()
