import json
import os
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
HGIS_DIR = DATA_DIR / "hgis_datasets"
OUTPUT_HTML = WORKSPACE_ROOT / "empires_map_viewer.html"

def extract_empire_features():
    extracted = {
        "Ottomans": [],
        "Franks": [],
        "Umayyads": []
    }
    
    keywords_map = {
        "Ottomans": ["Ottoman", "Ottoman Empire", "Ottoman Sultanate", "Ottoman Tripolitania"],
        "Franks": ["Frank", "Franks", "Frankish", "Carolingian", "Merovingian", "Kingdom of the Franks", "West Franks", "Middle Franks", "East Franks", "Salian Franks", "Ripuarian Franks"],
        "Umayyads": ["Umayyad", "Umayyad Caliphate"]
    }
    
    # 1. Extract from Historical Basemaps
    bm_dir = HGIS_DIR / "euratlas_pre1800" / "historical_basemaps" / "historical-basemaps-master" / "geojson"
    if bm_dir.exists():
        for gfile in sorted(bm_dir.glob("world_*.geojson")):
            year_str = gfile.stem.replace("world_", "").replace("bc", " BCE").replace("ad", " CE")
            try:
                with open(gfile, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    name = props.get("NAME") or props.get("name") or ""
                    if not name:
                        continue
                    for group, kws in keywords_map.items():
                        if any(kw.lower() in name.lower() for kw in kws):
                            feat_copy = dict(feat)
                            feat_copy["properties"] = dict(props)
                            feat_copy["properties"]["group"] = group
                            feat_copy["properties"]["source_file"] = gfile.name
                            feat_copy["properties"]["display_year"] = year_str
                            extracted[group].append(feat_copy)
            except Exception as e:
                print(f"Error reading {gfile.name}: {e}")

    # 2. Extract from Cliopatria
    cliopatria_path = DATA_DIR / "cliopatria_polities.geojson"
    if not cliopatria_path.exists():
        cliopatria_path = DATA_DIR / "cliopatria_polities_only.geojson"
    
    if cliopatria_path.exists():
        try:
            with open(cliopatria_path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            for feat in cdata.get("features", []):
                props = feat.get("properties", {})
                name = props.get("Name") or ""
                if not name:
                    continue
                for group, kws in keywords_map.items():
                    if any(kw.lower() in name.lower() for kw in kws):
                        feat_copy = dict(feat)
                        feat_copy["properties"] = dict(props)
                        feat_copy["properties"]["group"] = group
                        feat_copy["properties"]["source_file"] = "Cliopatria"
                        feat_copy["properties"]["display_year"] = f"{props.get('FromYear')} to {props.get('ToYear')}"
                        extracted[group].append(feat_copy)
        except Exception as e:
            print(f"Error reading Cliopatria: {e}")

    print(f"Extracted Features -> Ottomans: {len(extracted['Ottomans'])}, Franks: {len(extracted['Franks'])}, Umayyads: {len(extracted['Umayyads'])}")
    return extracted

def build_html():
    features_data = extract_empire_features()
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Historical Imperial Atlas: Ottomans, Franks & Umayyads</title>
    
    <!-- Google Fonts & Leaflet CSS -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            overflow: hidden;
            height: 100vh;
            width: 100vw;
        }}
        #map {{
            height: 100vh;
            width: 100vw;
            z-index: 1;
        }}
        
        /* Glassmorphism Header Controls */
        .top-panel {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.82);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 20px 24px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            max-width: 420px;
            transition: all 0.3s ease;
        }}
        .top-panel h1 {{
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, #38bdf8, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .top-panel p {{
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 16px;
            line-height: 1.4;
        }}
        
        /* Filter Buttons */
        .filter-group {{
            display: flex;
            gap: 8px;
            margin-bottom: 14px;
            flex-wrap: wrap;
        }}
        .btn-filter {{
            flex: 1;
            min-width: 100px;
            padding: 10px 14px;
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            background: rgba(30, 41, 59, 0.7);
            color: #cbd5e1;
            font-family: inherit;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .btn-filter:hover {{
            background: rgba(51, 65, 85, 0.9);
            color: #fff;
            transform: translateY(-1px);
        }}
        .btn-filter.active-ottoman {{
            background: linear-gradient(135deg, #dc2626, #b91c1c);
            color: #fff;
            border-color: #ef4444;
            box-shadow: 0 4px 14px rgba(220, 38, 38, 0.4);
        }}
        .btn-filter.active-franks {{
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #fff;
            border-color: #3b82f6;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
        }}
        .btn-filter.active-umayyads {{
            background: linear-gradient(135deg, #059669, #047857);
            color: #fff;
            border-color: #10b981;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);
        }}
        .btn-filter.active-all {{
            background: linear-gradient(135deg, #7c3aed, #6d28d9);
            color: #fff;
            border-color: #8b5cf6;
            box-shadow: 0 4px 14px rgba(124, 58, 237, 0.4);
        }}

        /* Legend & Info Sidebar */
        .info-sidebar {{
            position: absolute;
            bottom: 24px;
            right: 24px;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.85);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px;
            padding: 20px;
            width: 320px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
        }}
        .info-sidebar h3 {{
            font-size: 15px;
            font-weight: 600;
            color: #f1f5f9;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            margin-bottom: 10px;
            color: #cbd5e1;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid rgba(255, 255, 255, 0.3);
        }}
        .stat-badge {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 12px;
            background: rgba(255, 255, 255, 0.1);
            color: #94a3b8;
        }}
        
        /* Popup Styling */
        .leaflet-popup-content-wrapper {{
            background: rgba(15, 23, 42, 0.95) !important;
            backdrop-filter: blur(12px) !important;
            color: #f8fafc !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255, 255, 255, 0.15) !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6) !important;
        }}
        .leaflet-popup-tip {{
            background: rgba(15, 23, 42, 0.95) !important;
        }}
        .popup-title {{
            font-size: 16px;
            font-weight: 700;
            color: #38bdf8;
            margin-bottom: 6px;
        }}
        .popup-meta {{
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.5;
        }}
    </style>
</head>
<body>

    <div id="map"></div>

    <div class="top-panel">
        <h1>Imperial Spatial Atlas</h1>
        <p>Interactive vector boundaries & subnational polities for the Ottoman Empire, Frankish Realm, and Umayyad Caliphate.</p>
        
        <div class="filter-group">
            <button class="btn-filter active-all" id="btn-all" onclick="filterGroup('All')">🌐 All Empires</button>
            <button class="btn-filter" id="btn-ottoman" onclick="filterGroup('Ottomans')">☪️ Ottomans</button>
            <button class="btn-filter" id="btn-franks" onclick="filterGroup('Franks')">⚔️ Franks</button>
            <button class="btn-filter" id="btn-umayyads" onclick="filterGroup('Umayyads')">🌙 Umayyads</button>
        </div>
    </div>

    <div class="info-sidebar">
        <h3>Legend & Active Layers <span class="stat-badge" id="feature-count-badge">0 Features</span></h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #ef4444;"></div>
            <span><strong>Ottoman Empire</strong> (1400 – 1800 CE)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #3b82f6;"></div>
            <span><strong>Frankish Realm</strong> (400 – 888 CE)</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #10b981;"></div>
            <span><strong>Umayyad Caliphate</strong> (661 – 750 CE)</span>
        </div>
    </div>

    <script>
        const geojsonRawData = {json.dumps(features_data)};

        // Initialize Leaflet Map
        const map = L.map('map', {{
            center: [32.0, 30.0],
            zoom: 4,
            zoomControl: false
        }});

        L.control.zoom({{ position: 'topright' }}).addTo(map);

        // Dark Matter Basemap Layer
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {{
            attribution: '&copy; <a href="https://carto.com/">CARTO</a> & OpenStreetMap',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        let geojsonLayerGroup = L.layerGroup().addTo(map);

        const groupStyles = {{
            "Ottomans": {{ color: "#ef4444", fillColor: "#dc2626", fillOpacity: 0.35, weight: 2 }},
            "Franks": {{ color: "#3b82f6", fillColor: "#2563eb", fillOpacity: 0.35, weight: 2 }},
            "Umayyads": {{ color: "#10b981", fillColor: "#059669", fillOpacity: 0.35, weight: 2 }}
        }};

        function renderFeatures(filter) {{
            geojsonLayerGroup.clearLayers();
            let totalRendered = 0;

            const groupsToRender = filter === "All" ? ["Ottomans", "Franks", "Umayyads"] : [filter];

            groupsToRender.forEach(group => {{
                const features = geojsonRawData[group] || [];
                features.forEach(feat => {{
                    totalRendered++;
                    const style = groupStyles[group];
                    
                    const layer = L.geoJSON(feat, {{
                        style: function() {{
                            return style;
                        }},
                        onEachFeature: function(feature, layer) {{
                            const props = feature.properties || {{}};
                            const title = props.Name || props.NAME || props.name || group;
                            const year = props.display_year || (props.FromYear ? props.FromYear + ' - ' + props.ToYear : 'Historical');
                            const source = props.source_file || 'HGIS';
                            
                            layer.bindPopup(`
                                <div class="popup-title">${{title}}</div>
                                <div class="popup-meta">
                                    <strong>Empire/Realm:</strong> ${{group}}<br>
                                    <strong>Period/Slice:</strong> ${{year}}<br>
                                    <strong>Source Archive:</strong> ${{source}}
                                </div>
                            `);

                            layer.on('mouseover', function() {{
                                this.setStyle({{ fillOpacity: 0.65, weight: 3 }});
                            }});
                            layer.on('mouseout', function() {{
                                this.setStyle(style);
                            }});
                        }}
                    }});
                    geojsonLayerGroup.addLayer(layer);
                }});
            }});

            document.getElementById("feature-count-badge").innerText = totalRendered + " Polygons";
        }}

        function filterGroup(groupName) {{
            // Update Active Buttons
            document.querySelectorAll('.btn-filter').forEach(btn => btn.className = 'btn-filter');
            if (groupName === 'All') document.getElementById('btn-all').className = 'btn-filter active-all';
            if (groupName === 'Ottomans') document.getElementById('btn-ottoman').className = 'btn-filter active-ottoman';
            if (groupName === 'Franks') document.getElementById('btn-franks').className = 'btn-filter active-franks';
            if (groupName === 'Umayyads') document.getElementById('btn-umayyads').className = 'btn-filter active-umayyads';

            renderFeatures(groupName);
        }}

        // Initial Render
        filterGroup('All');
    </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Interactive Empire Map Viewer saved to {OUTPUT_HTML}")

if __name__ == "__main__":
    build_html()
