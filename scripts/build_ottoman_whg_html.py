import json
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
WHG_OTTOMAN_GEOJSON = DATA_DIR / "whg_ottoman_admin_units.geojson"
OUTPUT_HTML = WORKSPACE_ROOT / "ottoman_whg_viewer.html"

def build_ottoman_whg_html():
    if not WHG_OTTOMAN_GEOJSON.exists():
        print("Error: whg_ottoman_admin_units.geojson not found!")
        return

    with open(WHG_OTTOMAN_GEOJSON, "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Ottoman Empire WHG Administrative Atlas</title>
    
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
            background-color: #0b0f19;
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
        
        /* Glassmorphism Control Panel */
        .panel {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.88);
            backdrop-filter: blur(18px);
            -webkit-backdrop-filter: blur(18px);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 20px;
            padding: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
            width: 420px;
            max-height: calc(100vh - 40px);
            overflow-y: auto;
        }}
        .panel h1 {{
            font-size: 22px;
            font-weight: 700;
            background: linear-gradient(135deg, #ef4444, #f97316, #f59e0b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }}
        .panel p {{
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 18px;
            line-height: 1.5;
        }}
        .whg-badge {{
            display: inline-block;
            padding: 4px 10px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            margin-bottom: 14px;
        }}

        /* Division Pills */
        .pills-grid {{
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 16px;
            max-height: 160px;
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
            background: #ef4444;
            color: #fff;
            border-color: #f87171;
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
        }}

        /* Info Badge */
        .stats-card {{
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 14px;
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.6;
        }}
        .stats-card strong {{
            color: #f87171;
        }}

        /* Popup Styling */
        .leaflet-popup-content-wrapper {{
            background: rgba(15, 23, 42, 0.95) !important;
            backdrop-filter: blur(12px) !important;
            color: #f8fafc !important;
            border-radius: 14px !important;
            border: 1px solid rgba(239, 68, 68, 0.3) !important;
            box-shadow: 0 12px 30px rgba(0,0,0,0.7) !important;
        }}
        .leaflet-popup-tip {{
            background: rgba(15, 23, 42, 0.95) !important;
        }}
        .popup-title {{
            font-size: 16px;
            font-weight: 700;
            color: #f87171;
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

    <div class="panel">
        <h1>☪️ Ottoman Empire WHG Atlas</h1>
        <div class="whg-badge">🌐 Fetched via World Historical Gazetteer API (whgazetteer.org)</div>
        <p>Explore Ottoman Eyalets, Vilayets, and administrative capitals queried from WHG linked datasets.</p>

        <div class="pills-grid" id="pills-container">
            <div class="pill active" onclick="filterEyalet('ALL', event)">🌐 All Eyalets</div>
        </div>

        <div class="stats-card">
            <div><strong>API Source:</strong> World Historical Gazetteer API</div>
            <div><strong>Active Features:</strong> <span id="feat-count">38</span></div>
            <div><strong>Coverage:</strong> Rumelia, Anatolia, Levant, Egypt, Iraq, Maghreb & Arabia</div>
        </div>
    </div>

    <script>
        const whgGeojsonData = {json.dumps(geojson_data)};

        // Initialize Map centered on Istanbul / Middle East
        const map = L.map('map', {{
            center: [35.0, 36.0],
            zoom: 5,
            zoomControl: false
        }});

        L.control.zoom({{ position: 'topright' }}).addTo(map);

        // Dark Mode Tile Layer
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {{
            attribution: '&copy; CARTO & OpenStreetMap &mdash; WHG Data',
            subdomains: 'abcd',
            maxZoom: 19
        }}).addTo(map);

        let geojsonLayerGroup = L.layerGroup().addTo(map);

        // Populate Pills
        const eyaletNames = [...new Set(whgGeojsonData.features.map(f => f.properties.name))];
        const pillsContainer = document.getElementById("pills-container");
        eyaletNames.forEach(ename => {{
            const div = document.createElement("div");
            div.className = "pill";
            div.innerText = ename;
            div.onclick = function(e) {{ filterEyalet(ename, e); }};
            pillsContainer.appendChild(div);
        }});

        function filterEyalet(targetName, event) {{
            document.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
            if (event && event.target) {{
                event.target.classList.add('active');
            }}

            geojsonLayerGroup.clearLayers();
            let count = 0;

            whgGeojsonData.features.forEach(feat => {{
                const name = feat.properties.name;
                if (targetName === 'ALL' || name === targetName) {{
                    count++;
                    const layer = L.geoJSON(feat, {{
                        style: {{
                            color: "#ef4444",
                            fillColor: "#dc2626",
                            fillOpacity: 0.45,
                            weight: 2
                        }},
                        pointToLayer: function(feature, latlng) {{
                            return L.circleMarker(latlng, {{
                                radius: 8,
                                fillColor: "#ef4444",
                                color: "#ffffff",
                                weight: 2,
                                fillOpacity: 0.95
                            }});
                        }},
                        onEachFeature: function(feature, layer) {{
                            const props = feature.properties;
                            layer.bindPopup(`
                                <div class="popup-title">${{props.name}}</div>
                                <div class="popup-meta">
                                    <strong>Division Type:</strong> ${{props.division_type || 'Ottoman Eyalet'}}<br>
                                    <strong>WHG Place ID:</strong> ${{props.place_id || 'N/A'}}<br>
                                    <strong>Dataset:</strong> ${{props.dataset || 'WHG Link'}}<br>
                                    <strong>Source API:</strong> World Historical Gazetteer
                                </div>
                            `);
                        }}
                    }});
                    geojsonLayerGroup.addLayer(layer);
                }}
            }});

            document.getElementById("feat-count").innerText = count;
        }}

        // Initial Render
        filterEyalet('ALL');
    </script>
</body>
</html>
"""

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Saved Ottoman WHG Map Viewer to {OUTPUT_HTML}")

if __name__ == "__main__":
    build_ottoman_whg_html()
