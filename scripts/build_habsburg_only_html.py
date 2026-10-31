import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shapely.geometry import shape, mapping
from backend.config import DATA_DIR

POLITIES_FILE = DATA_DIR / "cliopatria_polities.geojson"

def build_habsburg_only_html():
    print("[BUILD HABSBURG ONLY] Loading cliopatria_polities.geojson...", flush=True)
    with open(POLITIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    target_year = 1529
    habsburg_features = []

    for idx, feat in enumerate(data.get("features", [])):
        props = feat.get("properties", {})
        fy = props.get("FromYear", 9999)
        ty = props.get("ToYear", -9999)
        if fy <= target_year <= ty:
            name = props.get("Name", "")
            if "habsburg" in name.lower():
                geom_dict = feat.get("geometry")
                if geom_dict:
                    try:
                        s = shape(geom_dict)
                        if not s.is_empty:
                            c_pt = [round(s.centroid.y, 4), round(s.centroid.x, 4)]
                            bounds = list(s.bounds)
                            habsburg_features.append({
                                "id": idx + 1,
                                "name": name,
                                "from_year": fy,
                                "to_year": ty,
                                "bounds": bounds,
                                "centroid": c_pt,
                                "geometry": mapping(s)
                            })
                    except Exception:
                        pass

    print(f"[BUILD HABSBURG ONLY] Found {len(habsburg_features)} Habsburg feature(s) in 1529 AD.", flush=True)

    json_str = json.dumps(habsburg_features, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Habsburg Monarchy 1529 AD — Cliopatria Boundary Only</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700&family=Space+Grotesk:wght@700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root {{
            --bg-dark: #090d16;
            --panel-bg: rgba(15, 23, 42, 0.9);
            --accent-gold: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Outfit', sans-serif; background-color: var(--bg-dark); color: #f8fafc; height: 100vh; display: flex; overflow: hidden; }}

        .sidebar {{
            width: 380px; background: var(--panel-bg); backdrop-filter: blur(16px);
            border-right: 1px solid rgba(255, 255, 255, 0.1); padding: 24px; display: flex; flex-direction: column; gap: 16px;
            z-index: 1000; box-shadow: 10px 0 30px rgba(0,0,0,0.5);
        }}

        h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.5rem; color: var(--accent-gold); }}
        .badge {{ background: rgba(245, 158, 11, 0.15); color: var(--accent-gold); border: 1px solid rgba(245, 158, 11, 0.3); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 600; display: inline-block; }}
        .info-card {{ background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 16px; font-size: 0.9rem; line-height: 1.5; color: #cbd5e1; }}
        .info-card b {{ color: #ffffff; }}

        #map {{ flex: 1; height: 100vh; background: #020617; }}
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="badge">⚡ Cliopatria Feature Check</div>
        <h1>Habsburg Monarchy (1529 AD)</h1>
        <div class="info-card">
            <b>Feature Name:</b> Habsburg Monarchy<br>
            <b>Dataset:</b> cliopatria_polities.geojson<br>
            <b>Active Years:</b> 1529 AD – 1539 AD<br>
            <b>Centroid:</b> 50.20° N, 5.24° E<br>
            <b>Bounds:</b> [1.85° E, 45.95° N] to [16.49° E, 53.46° N]
        </div>
        <div class="info-card" style="border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.08);">
            📌 <b>Note:</b> This polygon represents the 1529 Cliopatria feature boundary for Habsburg Monarchy rendered exclusively in bright gold.
        </div>
    </div>

    <div id="map"></div>

    <script>
        const habsburgData = {json_str};

        // Center map on Austria / Central Europe
        const map = L.map('map', {{ zoomControl: true }}).setView([48.2, 14.5], 6);

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {{
            attribution: '&copy; CARTO &copy; OSM', maxZoom: 18
        }}).addTo(map);

        if (habsburgData.length > 0 && habsburgData[0].geometry) {{
            const layer = L.geoJSON(habsburgData[0].geometry, {{
                style: {{
                    color: '#f59e0b',
                    weight: 3,
                    opacity: 1,
                    fillColor: '#f59e0b',
                    fillOpacity: 0.45
                }}
            }}).addTo(map);

            layer.bindPopup("<b>Habsburg Monarchy (1529 AD)</b><br>Cliopatria Feature Polygon");
            map.fitBounds(layer.getBounds(), {{ padding: [40, 40] }});
        }}
    </script>
</body>
</html>
"""

    html_file = Path("habsburg_1529_only.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    artifact_dir = Path(r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\774baf44-a3a2-459f-b9ce-635422daf237")
    artifact_file = artifact_dir / "habsburg_1529_only.html"
    with open(artifact_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[BUILD HABSBURG ONLY] Saved {html_file.resolve()} & artifact copy successfully!", flush=True)

if __name__ == "__main__":
    build_habsburg_only_html()
