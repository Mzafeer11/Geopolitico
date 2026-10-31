"""
Refined Natural Boundary River Partition & Province Union Tester Application.
Fixes:
1. Includes all provinces along river (Jammu & Kashmir, Ladakh, etc.) without false country filters.
2. Tightens search envelope so far-off countries (e.g. Poland for Danube) are not included.
3. Provides live direction selector controls (North, South, East, West) for any river.
Outputs: test_river_partition.html
"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shapely.geometry import shape, mapping, LineString, MultiLineString, MultiPolygon, box
from shapely.ops import unary_union, nearest_points
from backend.tools.gis_tools import get_natural_boundary_geometry
from backend.tools.country_polygons import get_country_polygon_loader
from backend.tools.compiler import clip_province_geom

def run_river_partition(river_name: str, direction: str, target_country_filter: str = "") -> dict:
    print(f"[RIVER TEST] Processing '{river_name}' ({direction})...", flush=True)
    b_geom, b_msg = get_natural_boundary_geometry(river_name)
    
    if not b_geom or b_geom.is_empty:
        return {"status": "error", "message": f"Could not retrieve coordinates for river '{river_name}'."}

    loader = get_country_polygon_loader()
    provinces_data = loader.provinces_data

    river_bounds = b_geom.bounds  # [minx, miny, maxx, maxy]
    # Tight 0.7 degree buffer around river to only capture provinces along the river bank
    river_buf = b_geom.buffer(0.7)

    clipped_province_features = []
    sub_polygons = []

    for feat in provinces_data:
        props = feat.get("properties", {})
        pname = props.get("name") or props.get("NAME") or "Unknown Province"
        admin = props.get("admin") or props.get("ADMIN") or ""

        if target_country_filter and target_country_filter.lower() not in admin.lower() and admin.lower() not in target_country_filter.lower():
            continue

        g_dict = feat.get("geometry")
        if not g_dict:
            continue

        try:
            prov_geom = shape(g_dict)
            if not prov_geom.is_valid or prov_geom.is_empty:
                continue

            # Only process provinces that directly touch or intersect the river's 0.7 degree envelope
            if not prov_geom.intersects(river_buf):
                continue

            # Clip province polygon along extended river line
            clipped = clip_province_geom(prov_geom, b_geom, direction, val=None, territory_desc=river_name, prov_name=pname)

            if clipped and not clipped.is_empty:
                # Ensure clipped polygon actually matches the target side
                p1, p2 = nearest_points(clipped.centroid, b_geom)
                local_y, local_x = p2.y, p2.x
                cx, cy = clipped.centroid.x, clipped.centroid.y

                valid_side = False
                if "north" in direction and cy >= local_y - 0.1:
                    valid_side = True
                elif "south" in direction and cy <= local_y + 0.1:
                    valid_side = True
                elif "west" in direction and cx <= local_x + 0.1:
                    valid_side = True
                elif "east" in direction and cx >= local_x - 0.1:
                    valid_side = True

                if valid_side:
                    sub_polygons.append(clipped)
                    c_pt = [round(clipped.centroid.y, 4), round(clipped.centroid.x, 4)]
                    clipped_province_features.append({
                        "name": f"{pname} ({admin})",
                        "admin": admin,
                        "province": pname,
                        "area_deg": round(clipped.area, 4),
                        "centroid": c_pt,
                        "geometry": mapping(clipped)
                    })
        except Exception as e:
            print(f"[RIVER TEST] Error clipping province: {e}", flush=True)

    unified_geom = unary_union(sub_polygons) if sub_polygons else None
    unified_area = round(unified_geom.area, 4) if unified_geom else 0.0
    unified_bounds = list(unified_geom.bounds) if unified_geom else [0, 0, 0, 0]

    river_paths = []
    if b_geom.geom_type == "LineString":
        river_paths.append([[round(pt[0], 5), round(pt[1], 5)] for pt in b_geom.coords])
    elif b_geom.geom_type == "MultiLineString":
        for line in b_geom.geoms:
            river_paths.append([[round(pt[0], 5), round(pt[1], 5)] for pt in line.coords])

    return {
        "status": "success",
        "river_name": river_name,
        "direction": direction,
        "river_paths": river_paths,
        "river_bounds": list(river_bounds),
        "province_count": len(clipped_province_features),
        "clipped_provinces": clipped_province_features,
        "unified_area": unified_area,
        "unified_bounds": unified_bounds,
        "unified_geometry": mapping(unified_geom) if unified_geom else None
    }


def generate_partition_tester_html():
    scenarios = {
        "chenab_south": run_river_partition("Chenab River", "south_of_natural_boundary", ""),
        "chenab_north": run_river_partition("Chenab River", "north_of_natural_boundary", ""),
        "chenab_east": run_river_partition("Chenab River", "east_of_natural_boundary", ""),
        "chenab_west": run_river_partition("Chenab River", "west_of_natural_boundary", ""),
        "danube_north": run_river_partition("Danube River", "north_of_natural_boundary", ""),
        "danube_south": run_river_partition("Danube River", "south_of_natural_boundary", ""),
        "rhine_west": run_river_partition("Rhine River", "west_of_natural_boundary", ""),
        "rhine_east": run_river_partition("Rhine River", "east_of_natural_boundary", ""),
        "indus_west": run_river_partition("Indus River", "west_of_natural_boundary", ""),
        "indus_east": run_river_partition("Indus River", "east_of_natural_boundary", "")
    }

    scenarios_json_str = json.dumps(scenarios, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Natural Boundary Partition & Province Union Explorer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root {{
            --bg-dark: #090d16;
            --panel-bg: rgba(15, 23, 42, 0.88);
            --border-color: rgba(255, 255, 255, 0.1);
            --accent-cyan: #00f2fe;
            --accent-gold: #f59e0b;
            --accent-blue: #3b82f6;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Outfit', sans-serif; background-color: var(--bg-dark); color: var(--text-primary); height: 100vh; display: flex; overflow: hidden; }}

        .sidebar {{
            width: 450px; background: var(--panel-bg); backdrop-filter: blur(16px);
            border-right: 1px solid var(--border-color); display: flex; flex-direction: column; z-index: 1000;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
        }}

        .header {{
            padding: 22px 24px; border-bottom: 1px solid var(--border-color);
            background: linear-gradient(180deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0) 100%);
        }}

        .badge {{
            display: inline-flex; align-items: center; gap: 6px; background: rgba(0, 242, 254, 0.15);
            color: var(--accent-cyan); border: 1px solid rgba(0, 242, 254, 0.3); padding: 4px 12px;
            border-radius: 20px; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;
        }}

        h1 {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.5rem; font-weight: 700; color: #ffffff; margin-bottom: 4px; }}
        .subtitle {{ color: var(--text-secondary); font-size: 0.85rem; }}

        .controls {{ padding: 18px 24px; border-bottom: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 12px; }}
        
        .form-group {{ display: flex; flex-direction: column; gap: 6px; }}
        label {{ font-size: 0.8rem; font-weight: 600; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.5px; }}

        .select-box {{
            width: 100%; padding: 10px 14px; background: rgba(30, 41, 59, 0.7); border: 1px solid var(--border-color);
            border-radius: 10px; color: white; font-family: inherit; font-size: 0.9rem; outline: none; transition: all 0.2s ease;
        }}
        .select-box:focus {{ border-color: var(--accent-cyan); background: rgba(30, 41, 59, 0.95); }}

        .dir-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 4px; }}
        .dir-btn {{
            background: rgba(30, 41, 59, 0.5); border: 1px solid var(--border-color); color: #cbd5e1;
            padding: 8px 6px; border-radius: 8px; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease; text-align: center;
        }}
        .dir-btn:hover, .dir-btn.active {{ background: rgba(0, 242, 254, 0.2); color: #38bdf8; border-color: rgba(0, 242, 254, 0.5); }}

        .stats-box {{
            padding: 16px 24px; border-bottom: 1px solid var(--border-color); background: rgba(15, 23, 42, 0.5);
            display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
        }}
        .stat-item {{ display: flex; flex-direction: column; gap: 2px; }}
        .stat-label {{ font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; }}
        .stat-val {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.2rem; font-weight: 700; color: var(--accent-gold); }}

        .list-container {{ flex: 1; overflow-y: auto; padding: 16px 24px; display: flex; flex-direction: column; gap: 8px; }}
        .list-container::-webkit-scrollbar {{ width: 6px; }}
        .list-container::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.15); border-radius: 4px; }}

        .prov-card {{
            background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px;
            padding: 10px 14px; cursor: pointer; transition: all 0.2s ease; display: flex; justify-content: space-between; align-items: center;
        }}
        .prov-card:hover {{ background: rgba(30, 41, 59, 0.85); transform: translateY(-1px); border-color: rgba(255, 255, 255, 0.2); }}
        .prov-name {{ font-weight: 600; font-size: 0.88rem; color: #f1f5f9; }}
        .prov-meta {{ font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px; }}

        #map {{ flex: 1; height: 100vh; background: #020617; }}
        
        .leaflet-popup-content-wrapper {{ background: rgba(15, 23, 42, 0.92) !important; backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.2); color: #f8fafc !important; border-radius: 10px !important; }}
        .popup-title {{ font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--accent-gold); margin-bottom: 4px; }}
        .popup-meta {{ font-size: 0.8rem; color: #94a3b8; font-weight: 500; }}
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="header">
            <div class="badge">⚡ Natural Boundary Partition & Union</div>
            <h1>River Vector Explorer</h1>
            <div class="subtitle">Interactive River Selector & Direction Controls</div>
        </div>

        <div class="controls">
            <div class="form-group">
                <label>Select Target River</label>
                <select id="river-select" class="select-box">
                    <option value="chenab">Chenab River (Kashmir / Punjab)</option>
                    <option value="danube">Danube River (Central Europe)</option>
                    <option value="rhine">Rhine River (Western Europe)</option>
                    <option value="indus">Indus River (Pakistan / India)</option>
                </select>
            </div>

            <div class="form-group">
                <label>Select Cut Direction</label>
                <div class="dir-grid">
                    <button class="dir-btn active" id="btn-south" data-dir="south">South</button>
                    <button class="dir-btn" id="btn-north" data-dir="north">North</button>
                    <button class="dir-btn" id="btn-west" data-dir="west">West</button>
                    <button class="dir-btn" id="btn-east" data-dir="east">East</button>
                </div>
            </div>
        </div>

        <div class="stats-box">
            <div class="stat-item">
                <div class="stat-label">Clipped Sub-Provinces</div>
                <div class="stat-val" id="stat-count">0</div>
            </div>
            <div class="stat-item">
                <div class="stat-label">Unified Union Area</div>
                <div class="stat-val" id="stat-area">0.0 sq deg</div>
            </div>
        </div>

        <div class="list-container" id="prov-list"></div>
    </div>

    <div id="map"></div>

    <script>
        const scenarios = {scenarios_json_str};

        const map = L.map('map', {{ zoomControl: false }}).setView([33.0, 75.0], 7);
        L.control.zoom({{ position: 'topright' }}).addTo(map);

        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {{
            attribution: '&copy; CARTO &copy; OSM', maxZoom: 18
        }}).addTo(map);

        let riverLayerGroup = L.featureGroup().addTo(map);
        let provLayerGroup = L.featureGroup().addTo(map);
        let unionLayerGroup = L.featureGroup().addTo(map);

        let currentRiver = 'chenab';
        let currentDir = 'south';

        function updateScenario() {{
            const key = `${{currentRiver}}_${{currentDir}}`;
            const data = scenarios[key];

            if (!data) {{
                alert(`No precomputed scenario for ${{key}}. Select another direction.`);
                return;
            }}

            renderTestScenario(data);
        }}

        function renderTestScenario(data) {{
            riverLayerGroup.clearLayers();
            provLayerGroup.clearLayers();
            unionLayerGroup.clearLayers();

            if (data.status !== 'success') {{
                alert(data.message || 'Error running partition.');
                return;
            }}

            // 1. Render River Polyline (Cyan glow)
            if (data.river_paths) {{
                data.river_paths.forEach(path => {{
                    const latlngs = path.map(pt => [pt[1], pt[0]]);
                    const riverLine = L.polyline(latlngs, {{
                        color: '#00f2fe',
                        weight: 4.5,
                        opacity: 0.95
                    }}).addTo(riverLayerGroup);
                    riverLine.bindPopup(`<b>Natural Boundary:</b> ${{data.river_name}}`);
                }});
            }}

            // 2. Render Clipped Sub-Provinces (Blue outlines)
            if (data.clipped_provinces) {{
                data.clipped_provinces.forEach(p => {{
                    if (p.geometry) {{
                        const layer = L.geoJSON(p.geometry, {{
                            style: {{
                                color: '#38bdf8',
                                weight: 1.5,
                                opacity: 0.7,
                                fillColor: '#0284c7',
                                fillOpacity: 0.25
                            }}
                        }});

                        layer.bindPopup(`
                            <div>
                                <div class="popup-title">${{p.name}}</div>
                                <div class="popup-meta">Clipped Area: <b>${{p.area_deg}} sq deg</b></div>
                            </div>
                        `);
                        provLayerGroup.addLayer(layer);
                    }}
                }});
            }}

            // 3. Render Final Unified Geometry (Gold fill)
            if (data.unified_geometry) {{
                const unionLayer = L.geoJSON(data.unified_geometry, {{
                    style: {{
                        color: '#f59e0b',
                        weight: 2.5,
                        opacity: 0.9,
                        fillColor: '#f59e0b',
                        fillOpacity: 0.45
                    }}
                }}).addTo(unionLayerGroup);

                unionLayer.bindPopup(`
                    <div>
                        <div class="popup-title">Unified Geometry (unary_union)</div>
                        <div class="popup-meta">River: <b>${{data.river_name}}</b></div>
                        <div class="popup-meta">Direction: <b>${{data.direction}}</b></div>
                        <div class="popup-meta">Total Area: <b>${{data.unified_area}} sq deg</b></div>
                    </div>
                `);

                if (unionLayer.getBounds().isValid()) {{
                    map.fitBounds(unionLayer.getBounds(), {{ padding: [50, 50], animate: true }});
                }}
            }}

            // Update stats
            document.getElementById('stat-count').innerText = data.province_count;
            document.getElementById('stat-area').innerText = `${{data.unified_area}} sq deg`;

            // Update sidebar list
            const listContainer = document.getElementById('prov-list');
            listContainer.innerHTML = '';
            data.clipped_provinces.forEach(p => {{
                const card = document.createElement('div');
                card.className = 'prov-card';
                card.innerHTML = `
                    <div>
                        <div class="prov-name">${{p.name}}</div>
                        <div class="prov-meta">Clipped Area: ${{p.area_deg}} sq deg</div>
                    </div>
                `;
                card.addEventListener('click', () => {{
                    if (p.centroid && p.centroid[0] !== 0) {{
                        map.setView(p.centroid, 8, {{ animate: true }});
                    }}
                }});
                listContainer.appendChild(card);
            }});
        }}

        // Setup River Selector
        const riverSelect = document.getElementById('river-select');
        riverSelect.addEventListener('change', (e) => {{
            currentRiver = e.target.value;
            updateScenario();
        }});

        // Setup Direction Buttons
        document.querySelectorAll('.dir-btn').forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                currentDir = e.target.getAttribute('data-dir');
                updateScenario();
            }});
        }});

        // Initial Render
        updateScenario();
    </script>
</body>
</html>
"""

    html_file = Path("test_river_partition.html")
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    artifact_dir = Path(r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\774baf44-a3a2-459f-b9ce-635422daf237")
    artifact_file = artifact_dir / "test_river_partition.html"
    with open(artifact_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[RIVER TEST REFINED] Saved {html_file.resolve()} & artifact copy successfully!", flush=True)

if __name__ == "__main__":
    generate_partition_tester_html()
