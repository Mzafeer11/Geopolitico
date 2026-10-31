import json
import os
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
HGIS_DIR = WORKSPACE_ROOT / "data" / "hgis_datasets"
OUTPUT_HTML = WORKSPACE_ROOT / "franks_hgis_viewer.html"

FRANKISH_KEYWORDS = [
    "Frank", "Franks", "Frankish", "Carolingian", "Merovingian", 
    "West Franks", "Middle Franks", "East Franks", "Salian Franks", "Ripuarian Franks"
]

def extract_franks_from_hgis_only():
    bm_dir = HGIS_DIR / "euratlas_pre1800" / "historical_basemaps" / "historical-basemaps-master" / "geojson"
    if not bm_dir.exists():
        print(f"Error: Directory not found {bm_dir}")
        return []

    franks_features = []

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
                if any(kw.lower() in name.lower() for kw in FRANKISH_KEYWORDS):
                    feat_copy = dict(feat)
                    feat_copy["properties"] = dict(props)
                    feat_copy["properties"]["source_file"] = str(gfile.relative_to(HGIS_DIR))
                    feat_copy["properties"]["display_year"] = year_str
                    feat_copy["properties"]["division_name"] = name
                    franks_features.append(feat_copy)
        except Exception as e:
            print(f"Error reading {gfile.name}: {e}")

    print(f"Extracted {len(franks_features)} Frankish administrative/subnational units strictly from HGIS_DATASETS.")
    return franks_features

def build_franks_html():
    features = extract_franks_from_hgis_only()

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Frankish Realm Subnational Divisions (HGIS Data)</title>
    
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
            background-color: #090d16;
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
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 20px 24px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
            max-width: 440px;
        }}
        .top-panel h1 {{
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, #60a5fa, #3b82f6, #93c5fd);
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
        
        /* Subnational Division Pills */
        .div-pills {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 12px;
            max-height: 140px;
            overflow-y: auto;
        }}
        .pill {{
            padding: 6px 12px;
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            background: rgba(30, 41, 59, 0.7);
            color: #cbd5e1;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .pill:hover, .pill.active {{
            background: #2563eb;
            color: #fff;
            border-color: #60a5fa;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
        }}

        /* Legend & Info Sidebar */
        .info-sidebar {{
            position: absolute;
            bottom: 24px;
            right: 24px;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 20px;
            width: 320px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
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
        .stat-badge {{
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 12px;
            background: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}
        .source-tag {{
            font-size: 11px;
            color: #64748b;
            margin-top: 8px;
            font-style: italic;
        }}

        /* Popup Styling */
        .leaflet-popup-content-wrapper {{
            background: rgba(15, 23, 42, 0.95) !important;
            backdrop-filter: blur(12px) !important;
            color: #f8fafc !important;
            border-radius: 12px !important;
            border: 1px solid rgba(59, 130, 246, 0.3) !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6) !important;
        }}
        .leaflet-popup-tip {{
            background: rgba(15, 23, 42, 0.95) !important;
        }}
        .popup-title {{
            font-size: 16px;
            font-weight: 700;
            color: #60a5fa;
            margin-bottom: 6px;
        }}
        .popup-meta {{
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.5;
        }}
    </style>
</head>
<body>

    <div id="map"></div>

    <div class="top-panel">
        <h1>⚔️ Frankish Subnational Divisions</h1>
        <p>Extracted <strong>exclusively</strong> from <code>data/hgis_datasets</code> (Historical Basemaps pre-1800).</p>
        
        <div class="div-pills" id="pills-container">
            <div class="pill active" onclick="filterDivision('ALL')">🌐 All Divisions</div>
        </div>
    </div>

    <div class="info-sidebar">
        <h3>Frankish GIS Layers <span class="stat-badge" id="feature-count-badge">0 Polygons</span></h3>
        <p style="font-size: 12px; color: #94a3b8; line-height: 1.5;">
            Includes <strong>Merovingian</strong> & <strong>Carolingian</strong> imperial extents, plus <strong>West Franks</strong>, <strong>Middle Franks</strong>, and <strong>East Franks</strong> partitions.
        </p>
        <div class="source-tag">Source: data/hgis_datasets/euratlas_pre1800/</div>
    </div>

    <script>
        const franksFeatures = {json.dumps(features)};

        // Initialize Map centered on Western Europe
        const map = L.map('map', {{
            center: [48.5, 7.5],
            zoom: 5,
            zoomControl: false
        }});

        L.control.zoom({{ position: 'topright' }}).addTo(map);

        // Dark Matter Tile Layer
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {{
            attribution: '&copy; CARTO & OpenStreetMap',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        let geojsonLayerGroup = L.layerGroup().addTo(map);

        // Color palette for different divisions
        const colorPalette = [
            "#3b82f6", "#2563eb", "#60a5fa", "#1d4ed8", "#93c5fd", 
            "#8b5cf6", "#7c3aed", "#a78bfa", "#38bdf8", "#0284c7"
        ];

        // Populate Pills
        const divisionNames = [...new Set(franksFeatures.map(f => f.properties.division_name))];
        const pillsContainer = document.getElementById("pills-container");
        divisionNames.forEach(dname => {{
        divisionNames.forEach(dname => {
            const div = document.createElement("div");
            div.className = "pill";
            div.innerText = dname;
            div.onclick = function(e) { filterDivision(dname, e); };
            pillsContainer.appendChild(div);
        });

        function filterDivision(targetName, event) {
            document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
            if (event && event.target) {
                event.target.classList.add('active');
            } else {
                const activePill = Array.from(document.querySelectorAll('.pill')).find(p => p.innerText.includes(targetName) || (targetName === 'ALL' && p.innerText.includes('All')));
                if (activePill) activePill.classList.add('active');
            }

            geojsonLayerGroup.clearLayers();
            let count = 0;

            franksFeatures.forEach((feat, idx) => {
                const name = feat.properties.division_name;
                if (targetName === 'ALL' || name === targetName) {
                    count++;
                    const color = colorPalette[idx % colorPalette.length];
                    const layer = L.geoJSON(feat, {
                        style: {
                            color: color,
                            fillColor: color,
                            fillOpacity: 0.4,
                            weight: 2
                        },
                        onEachFeature: function(feature, layer) {
                            const props = feature.properties;
                            layer.bindPopup(`
                                <div class="popup-title">${props.division_name}</div>
                                <div class="popup-meta">
                                    <strong>Time Slice:</strong> Year ${props.display_year}<br>
                                    <strong>HGIS File:</strong> ${props.source_file}
                                </div>
                            `);
                            layer.on('mouseover', function() {
                                this.setStyle({ fillOpacity: 0.7, weight: 3 });
                            });
                            layer.on('mouseout', function() {
                                this.setStyle({ fillOpacity: 0.4, weight: 2 });
                            });
                        }
                    });
                    geojsonLayerGroup.addLayer(layer);
                }
            });

            document.getElementById("feature-count-badge").innerText = count + " Polygons";
        }

        // Initial Render
        filterDivision('ALL');
    </script>
</body>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved Frankish HGIS Map Viewer strictly from hgis_datasets to {OUTPUT_HTML}")

if __name__ == "__main__":
    build_franks_html()
