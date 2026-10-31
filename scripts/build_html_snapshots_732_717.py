import sys
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from shapely.geometry import shape, mapping
from backend.config import DATA_DIR

POLITIES_FILE = DATA_DIR / "cliopatria_polities.geojson"
RELATIONS_FILE = DATA_DIR / "cliopatria_relations.geojson"
ARTIFACT_DIR = Path(r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\774baf44-a3a2-459f-b9ce-635422daf237")

def build_snapshot_for_year(year: int):
    print(f"[BUILD SNAPSHOT {year}] Loading polities and relations for {year} AD...", flush=True)
    with open(POLITIES_FILE, "r", encoding="utf-8") as f:
        polities_geojson = json.load(f)
    with open(RELATIONS_FILE, "r", encoding="utf-8") as f:
        relations_geojson = json.load(f)

    colors = ['#f59e0b', '#3b82f6', '#10b981', '#ec4899', '#8b5cf6', '#06b6d4', '#f97316', '#a855f7', '#84cc16', '#eab308', '#6366f1', '#14b8a6']

    polity_list = []
    for idx, feat in enumerate(polities_geojson.get("features", [])):
        props = feat.get("properties", {})
        fy = props.get("FromYear", 9999)
        ty = props.get("ToYear", -9999)
        if fy <= year <= ty:
            geom_dict = feat.get("geometry")
            c_pt = [0, 0]
            s_geom = None
            if geom_dict:
                try:
                    s = shape(geom_dict)
                    if not s.is_empty:
                        s_simp = s.simplify(0.08, preserve_topology=True)
                        c_pt = [round(s.centroid.y, 4), round(s.centroid.x, 4)]
                        s_geom = mapping(s_simp)
                except Exception:
                    pass
            polity_list.append({
                "id": f"p_{idx+1}",
                "name": props.get("Name", "Unknown"),
                "from_year": fy,
                "to_year": ty,
                "type": "POLITY",
                "color": colors[len(polity_list) % len(colors)],
                "centroid": c_pt,
                "geometry": s_geom
            })

    relation_list = []
    for idx, feat in enumerate(relations_geojson.get("features", [])):
        props = feat.get("properties", {})
        fy = props.get("FromYear", 9999)
        ty = props.get("ToYear", -9999)
        if fy <= year <= ty:
            geom_dict = feat.get("geometry")
            c_pt = [0, 0]
            s_geom = None
            if geom_dict:
                try:
                    s = shape(geom_dict)
                    if not s.is_empty:
                        s_simp = s.simplify(0.08, preserve_topology=True)
                        c_pt = [round(s.centroid.y, 4), round(s.centroid.x, 4)]
                        s_geom = mapping(s_simp)
                except Exception:
                    pass
            relation_list.append({
                "id": f"r_{idx+1}",
                "name": props.get("Name", "Unknown"),
                "from_year": fy,
                "to_year": ty,
                "type": "RELATION",
                "color": "#ef4444",
                "centroid": c_pt,
                "geometry": s_geom
            })

    print(f"[BUILD SNAPSHOT {year}] Found {len(polity_list)} POLITIES and {len(relation_list)} RELATIONS in {year} AD.", flush=True)

    polities_json_str = json.dumps(polity_list, ensure_ascii=False)
    relations_json_str = json.dumps(relation_list, ensure_ascii=False)

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cliopatria __YEAR__ AD — Polities & Relations Explorer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        :root {
            --bg-dark: #090d16;
            --panel-bg: rgba(15, 23, 42, 0.88);
            --border-color: rgba(255, 255, 255, 0.1);
            --accent-gold: #f59e0b;
            --accent-blue: #3b82f6;
            --accent-red: #ef4444;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Outfit', sans-serif; background-color: var(--bg-dark); color: var(--text-primary); height: 100vh; display: flex; overflow: hidden; }

        .sidebar {
            width: 450px; background: var(--panel-bg); backdrop-filter: blur(16px);
            border-right: 1px solid var(--border-color); display: flex; flex-direction: column; z-index: 1000;
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
        }

        .header {
            padding: 22px 24px; border-bottom: 1px solid var(--border-color);
            background: linear-gradient(180deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0) 100%);
        }

        .badge-year {
            display: inline-flex; align-items: center; gap: 6px; background: rgba(245, 158, 11, 0.15);
            color: var(--accent-gold); border: 1px solid rgba(245, 158, 11, 0.3); padding: 4px 12px;
            border-radius: 20px; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;
        }

        h1 { font-family: 'Space Grotesk', sans-serif; font-size: 1.55rem; font-weight: 700; color: #ffffff; margin-bottom: 4px; }
        .subtitle { color: var(--text-secondary); font-size: 0.85rem; }

        .layer-toggle-container {
            padding: 14px 24px; border-bottom: 1px solid var(--border-color); background: rgba(15, 23, 42, 0.5);
            display: flex; gap: 8px;
        }

        .layer-btn {
            flex: 1; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
            background: rgba(30, 41, 59, 0.5); color: var(--text-secondary); font-size: 0.82rem; font-weight: 600;
            cursor: pointer; transition: all 0.2s ease; text-align: center;
        }

        .layer-btn.active-polity { background: rgba(59, 130, 246, 0.25); color: #60a5fa; border-color: rgba(59, 130, 246, 0.5); }
        .layer-btn.active-relation { background: rgba(239, 68, 68, 0.25); color: #f87171; border-color: rgba(239, 68, 68, 0.5); }
        .layer-btn.active-both { background: rgba(245, 158, 11, 0.25); color: #fbbf24; border-color: rgba(245, 158, 11, 0.5); }

        .controls { padding: 14px 24px; border-bottom: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 10px; }
        .search-box {
            width: 100%; padding: 10px 14px; background: rgba(30, 41, 59, 0.6); border: 1px solid var(--border-color);
            border-radius: 10px; color: white; font-family: inherit; font-size: 0.9rem; outline: none; transition: all 0.2s ease;
        }
        .search-box:focus { border-color: var(--accent-gold); background: rgba(30, 41, 59, 0.9); }

        .list-container { flex: 1; overflow-y: auto; padding: 16px 24px; display: flex; flex-direction: column; gap: 8px; }
        .list-container::-webkit-scrollbar { width: 6px; }
        .list-container::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 4px; }

        .card {
            background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 10px;
            padding: 12px 14px; cursor: pointer; transition: all 0.2s ease; display: flex; justify-content: space-between; align-items: center;
        }
        .card:hover { background: rgba(30, 41, 59, 0.85); transform: translateY(-1px); }
        .card.active { border-color: var(--accent-gold); background: rgba(245, 158, 11, 0.12); }
        .card-info { display: flex; align-items: center; gap: 10px; }
        .dot { width: 10px; height: 10px; border-radius: 50%; }
        .name { font-weight: 600; font-size: 0.92rem; color: #f1f5f9; }
        .type-pill { font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; margin-left: 6px; }
        .type-polity { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
        .type-relation { background: rgba(239, 68, 68, 0.2); color: #f87171; }
        .years { font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px; }

        #map { flex: 1; height: 100vh; background: #020617; }
        .leaflet-popup-content-wrapper { background: rgba(15, 23, 42, 0.92) !important; backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.2); color: #f8fafc !important; border-radius: 10px !important; }
        .popup-title { font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem; font-weight: 700; color: var(--accent-gold); margin-bottom: 4px; }
        .popup-type { font-size: 0.8rem; color: #94a3b8; font-weight: 500; }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="header">
            <div class="badge-year">⚡ Dual-Layer Catalogue • __YEAR__ AD</div>
            <h1>Polities & Relations (__YEAR__)</h1>
            <div class="subtitle">Separated Cliopatria Features (POLITY vs RELATION)</div>
        </div>

        <div class="layer-toggle-container">
            <button class="layer-btn active-polity" id="btn-polities">Polities (__POLITY_COUNT__)</button>
            <button class="layer-btn" id="btn-relations">Relations (__RELATION_COUNT__)</button>
            <button class="layer-btn" id="btn-both">Both Overlay</button>
        </div>

        <div class="controls">
            <input type="text" id="search" class="search-box" placeholder="Search polities or relations...">
        </div>

        <div class="list-container" id="list"></div>
    </div>

    <div id="map"></div>

    <script>
        const politiesData = __POLITIES_JSON__;
        const relationsData = __RELATIONS_JSON__;

        const map = L.map('map', { zoomControl: false }).setView([25.0, 35.0], 3);
        L.control.zoom({ position: 'topright' }).addTo(map);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {
            attribution: '&copy; CARTO &copy; OSM', maxZoom: 18
        }).addTo(map);

        const polityGroup = L.featureGroup().addTo(map);
        const relationGroup = L.featureGroup().addTo(map);
        const layerMap = {};

        function addFeaturesToGroup(dataList, group, defaultOpacity) {
            dataList.forEach(p => {
                if (p.geometry) {
                    const layer = L.geoJSON(p.geometry, {
                        style: {
                            color: p.color, weight: 2, opacity: 0.85,
                            fillColor: p.color, fillOpacity: defaultOpacity
                        }
                    });

                    layer.bindPopup(`
                        <div>
                            <div class="popup-title">${p.name}</div>
                            <div class="popup-type">Type: <b>${p.type}</b> (${p.from_year} AD – ${p.to_year} AD)</div>
                        </div>
                    `);

                    layer.on('click', () => highlightCard(p.id));
                    group.addLayer(layer);
                    layerMap[p.id] = layer;
                }
            });
        }

        addFeaturesToGroup(politiesData, polityGroup, 0.35);
        addFeaturesToGroup(relationsData, relationGroup, 0.20);

        let currentMode = 'polities'; // 'polities', 'relations', 'both'

        const btnPolities = document.getElementById('btn-polities');
        const btnRelations = document.getElementById('btn-relations');
        const btnBoth = document.getElementById('btn-both');

        function updateLayerVisibility() {
            if (currentMode === 'polities') {
                if (!map.hasLayer(polityGroup)) map.addLayer(polityGroup);
                if (map.hasLayer(relationGroup)) map.removeLayer(relationGroup);
                btnPolities.className = 'layer-btn active-polity';
                btnRelations.className = 'layer-btn';
                btnBoth.className = 'layer-btn';
            } else if (currentMode === 'relations') {
                if (map.hasLayer(polityGroup)) map.removeLayer(polityGroup);
                if (!map.hasLayer(relationGroup)) map.addLayer(relationGroup);
                btnPolities.className = 'layer-btn';
                btnRelations.className = 'layer-btn active-relation';
                btnBoth.className = 'layer-btn';
            } else {
                if (!map.hasLayer(polityGroup)) map.addLayer(polityGroup);
                if (!map.hasLayer(relationGroup)) map.addLayer(relationGroup);
                btnPolities.className = 'layer-btn';
                btnRelations.className = 'layer-btn';
                btnBoth.className = 'layer-btn active-both';
            }
            renderList();
        }

        btnPolities.addEventListener('click', () => { currentMode = 'polities'; updateLayerVisibility(); });
        btnRelations.addEventListener('click', () => { currentMode = 'relations'; updateLayerVisibility(); });
        btnBoth.addEventListener('click', () => { currentMode = 'both'; updateLayerVisibility(); });

        const listContainer = document.getElementById('list');
        const searchBox = document.getElementById('search');

        function getCurrentList() {
            if (currentMode === 'polities') return politiesData;
            if (currentMode === 'relations') return relationsData;
            return [...politiesData, ...relationsData];
        }

        function renderList() {
            const term = searchBox.value.toLowerCase();
            const fullList = getCurrentList();
            const filtered = fullList.filter(p => p.name.toLowerCase().includes(term));

            listContainer.innerHTML = '';
            filtered.forEach(p => {
                const card = document.createElement('div');
                card.className = 'card';
                card.id = `card-${p.id}`;
                const pillClass = p.type === 'POLITY' ? 'type-polity' : 'type-relation';
                card.innerHTML = `
                    <div class="card-info">
                        <div class="dot" style="background-color: ${p.color};"></div>
                        <div>
                            <div class="name">${p.name} <span class="type-pill ${pillClass}">${p.type}</span></div>
                            <div class="years">${p.from_year} – ${p.to_year} AD</div>
                        </div>
                    </div>
                `;

                card.addEventListener('click', () => {
                    if (layerMap[p.id]) {
                        map.fitBounds(layerMap[p.id].getBounds(), { padding: [40, 40], maxZoom: 7, animate: true });
                        layerMap[p.id].openPopup();
                    } else if (p.centroid && p.centroid[0] !== 0) {
                        map.setView(p.centroid, 5, { animate: true });
                    }
                    highlightCard(p.id);
                });

                listContainer.appendChild(card);
            });
        }

        function highlightCard(id) {
            document.querySelectorAll('.card').forEach(c => c.classList.remove('active'));
            const target = document.getElementById(`card-${id}`);
            if (target) {
                target.classList.add('active');
                target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }

        searchBox.addEventListener('input', renderList);
        updateLayerVisibility();
    </script>
</body>
</html>
"""

    html_content = html_template.replace("__YEAR__", str(year))
    html_content = html_content.replace("__POLITIES_JSON__", polities_json_str)
    html_content = html_content.replace("__RELATIONS_JSON__", relations_json_str)
    html_content = html_content.replace("__POLITY_COUNT__", str(len(polity_list)))
    html_content = html_content.replace("__RELATION_COUNT__", str(len(relation_list)))

    filename = f"cliopatria_{year}_empires.html"
    html_file = Path(filename)
    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    artifact_file = ARTIFACT_DIR / filename
    with open(artifact_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[BUILD SNAPSHOT {year}] Saved {html_file.resolve()} & artifact copy successfully!", flush=True)

if __name__ == "__main__":
    for y in [732, 717]:
        build_snapshot_for_year(y)
