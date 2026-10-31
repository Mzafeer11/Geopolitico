import json
import os
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

def fill_holes_and_dissolve(shapely_geoms, buffer_dist=0.003, simplify_tol=0.002):
    buffered_geoms = [g.buffer(buffer_dist) for g in shapely_geoms if g and not g.is_empty]
    union_geom = unary_union(buffered_geoms)
    union_geom = union_geom.buffer(-buffer_dist)
    
    if union_geom.is_empty:
        return None, None

    def remove_holes(geom):
        if geom.geom_type == 'Polygon':
            return Polygon(geom.exterior)
        elif geom.geom_type == 'MultiPolygon':
            solid_polys = [Polygon(p.exterior) for p in geom.geoms if not p.is_empty]
            return MultiPolygon(solid_polys)
        return geom

    solid_geom = remove_holes(union_geom)
    centroid_pt = (round(solid_geom.centroid.y, 4), round(solid_geom.centroid.x, 4))
    
    try:
        simplified = solid_geom.simplify(simplify_tol, preserve_topology=True)
        return mapping(simplified), centroid_pt
    except Exception:
        return mapping(solid_geom), centroid_pt

def main():
    json_path = r'c:\Users\ADMIN\Desktop\Geopolitico\custom_regional_painted_divisions.json'
    pak2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\Pakistan Districts\pak_admin2.geojson'
    ind2_gadm_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_IND_2.json\gadm41_IND_2.json'
    ind4_path = r'c:\Users\ADMIN\Desktop\Geopolitico\Indian Data\geoBoundaries-IND-ADM4.geojson'
    afg2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_AFG_2.json\gadm41_AFG_2.json'
    irn2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_IRN_2.json\gadm41_IRN_2.json'
    tjk2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_TJK_2.json\gadm41_TJK_2.json'
    chn3_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_CHN_3.json\gadm41_CHN_3.json'
    if not os.path.exists(chn3_path):
        chn3_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_CHN_3.json'
    chn2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_CHN_2.json\gadm41_CHN_2.json'

    with open(json_path, 'r', encoding='utf-8') as f:
        painted_units = json.load(f)

    with open(pak2_path, 'r', encoding='utf-8') as f:
        pak2_data = json.load(f)

    with open(ind2_gadm_path, 'r', encoding='utf-8') as f:
        ind2_data = json.load(f)

    with open(ind4_path, 'r', encoding='utf-8') as f:
        ind4_data = json.load(f)

    with open(afg2_path, 'r', encoding='utf-8') as f:
        afg2_data = json.load(f)

    with open(irn2_path, 'r', encoding='utf-8') as f:
        irn2_data = json.load(f)

    tjk2_data = {'features': []}
    if os.path.exists(tjk2_path):
        try:
            with open(tjk2_path, 'r', encoding='utf-8') as f:
                tjk2_data = json.load(f)
        except Exception as e:
            print(f"[WARN] Error loading Tajikistan dataset: {e}")

    chn3_data = {'features': []}
    if os.path.exists(chn3_path):
        try:
            with open(chn3_path, 'r', encoding='utf-8') as f:
                chn3_data = json.load(f)
            print(f"[LOAD] Loaded China Admin 3 dataset with {len(chn3_data.get('features', []))} features.")
        except Exception as e:
            print(f"[WARN] Error loading China Admin 3 dataset: {e}")

    chn2_data = {'features': []}
    if os.path.exists(chn2_path):
        try:
            with open(chn2_path, 'r', encoding='utf-8') as f:
                chn2_data = json.load(f)
        except Exception as e:
            pass

    # Build lookup of ID -> Feature Geometry & Centroid Coordinates
    geom_by_id = {}
    center_by_id = {}

    # 1. PAK features
    for idx, feat in enumerate(pak2_data['features']):
        props = feat['properties']
        pcode = props.get('adm2_pcode') or f'PAK2_{idx}'
        uid = f'PAK_{pcode}_{idx}'
        geom_by_id[uid] = feat['geometry']
        shp = shape(feat['geometry'])
        center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))

    # 2. IND GADM L2 features
    target_ind_states = ['JammuandKashmir', 'Punjab', 'Gujarat', 'Rajasthan', 'Haryana', 'HimachalPradesh', 'Chandigarh', 'Maharashtra', 'MadhyaPradesh', 'NCTofDelhi', 'UttarPradesh', 'Uttarakhand', 'DadraandNagarHaveli', 'DamanandDiu']
    for idx, feat in enumerate(ind2_data['features']):
        props = feat['properties']
        st = props.get('NAME_1', '')
        unit_name = props.get('NAME_2', '')
        if st in target_ind_states:
            if unit_name.lower() in ['leh', 'kargil', 'leh(ladakh)'] or st.lower() == 'ladakh':
                continue
            gid = props.get('GID_2') or f'IND2_{idx}'
            uid = f'IND_{gid}_{idx}'
            geom_by_id[uid] = feat['geometry']
            shp = shape(feat['geometry'])
            center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))

    # 3. LADAKH ADM4 features
    excluded_keywords = ['aksai', 'chin', 'gilgit', 'baltistan', 'new jammu', 'azad', 'muzaffarabad', 'mirpur']
    ladakh_valid_names = [
        'deskit', 'panamic', 'turtuk', 'nyoma', 'durbuk', 'rupsho', 'rong', 
        'leh', 'thiksay', 'nimoo', 'kharu', 'chuchot', 'saspol', 'khaltsi', 
        'sukerbachan', 'singay lalok wanla', 'drass', 'bhimbat', 'kargil', 
        'sankoo', 'taisuru', 'zansker', 'karsha', 'lungnak', 'shaker chaktan', 
        'shargol', 'soudh', 'pashkum', 'lotsum', 'barsoo', 'gm pora (trespone)'
    ]

    for idx, feat in enumerate(ind4_data['features']):
        props = feat.get('properties', {})
        sname = (props.get('shapeName') or '').strip()
        sname_lower = sname.lower()
        sid = props.get('shapeID') or f'IND4_{idx}'

        if any(kw in sname_lower for kw in excluded_keywords):
            continue

        try:
            geom_shape = shape(feat['geometry'])
            c = geom_shape.centroid
            if sname_lower in ladakh_valid_names:
                uid = f'LADAKH_ADM4_{sid}_{idx}'
                geom_by_id[uid] = feat['geometry']
                center_by_id[uid] = (round(c.y, 4), round(c.x, 4))
        except Exception:
            pass

    # 4. AFG GADM L2 features
    for idx, feat in enumerate(afg2_data.get('features', [])):
        props = feat.get('properties', {})
        gid = props.get('GID_2') or f'AFG2_{idx}'
        uid = f'AFG_{gid}_{idx}'
        geom_by_id[uid] = feat['geometry']
        shp = shape(feat['geometry'])
        center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))

    # 5. IRN GADM L2 features
    for idx, feat in enumerate(irn2_data.get('features', [])):
        props = feat.get('properties', {})
        gid = props.get('GID_2') or f'IRN2_{idx}'
        uid = f'IRN_{gid}_{idx}'
        geom_by_id[uid] = feat['geometry']
        shp = shape(feat['geometry'])
        center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))

    # 6. TJK GADM L2 features
    for idx, feat in enumerate(tjk2_data.get('features', [])):
        props = feat.get('properties', {})
        gid = props.get('GID_2') or f'TJK2_{idx}'
        uid = f'TJK_{gid}_{idx}'
        geom_by_id[uid] = feat['geometry']
        shp = shape(feat['geometry'])
        center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))

    # 7. CHN GADM L3 features
    target_chn_provinces = ['Xizang', 'XinjiangUygur', 'Gansu', 'Qinghai']
    for idx, feat in enumerate(chn3_data.get('features', [])):
        props = feat.get('properties', {})
        p_name_raw = props.get('NAME_1', '')
        if p_name_raw in target_chn_provinces:
            gid = props.get('GID_3') or f'CHN3_{idx}'
            uid = f'CHN_{gid}_{idx}'
            geom_by_id[uid] = feat['geometry']
            try:
                shp = shape(feat['geometry'])
                center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))
            except Exception:
                pass

    # 8. Legacy CHN GADM L2 features (for existing custom_regional_painted_divisions.json)
    for idx, feat in enumerate(chn2_data.get('features', [])):
        props = feat.get('properties', {})
        p_name_raw = props.get('NAME_1', '')
        if p_name_raw in target_chn_provinces:
            gid = props.get('GID_2') or f'CHN2_{idx}'
            uid = f'CHN_{gid}_{idx}'
            geom_by_id[uid] = feat['geometry']
            try:
                shp = shape(feat['geometry'])
                center_by_id[uid] = (round(shp.centroid.y, 4), round(shp.centroid.x, 4))
            except Exception:
                pass

    # Group shapely geometries by color
    geoms_by_color = {}
    unit_info_by_color = {}

    for item in painted_units:
        uid = item.get('id')
        col = item.get('color')
        name = item.get('name')
        
        if not col or col.lower() == '#334155':
            continue

        geom_dict = geom_by_id.get(uid)
        if not geom_dict:
            continue

        try:
            shp = shape(geom_dict)
            if not shp.is_valid:
                shp = shp.buffer(0)

            if col not in geoms_by_color:
                geoms_by_color[col] = []
                unit_info_by_color[col] = []
            geoms_by_color[col].append(shp)
            
            coord = center_by_id.get(uid, (round(shp.centroid.y, 4), round(shp.centroid.x, 4)))
            unit_info_by_color[col].append({
                'name': name,
                'id': uid,
                'lat': coord[0],
                'lng': coord[1]
            })
        except Exception as e:
            print(f"Error processing geometry for {name}: {e}")

    # Default Province Names & Suggested Capitals
    default_province_info = {
        "#3b82f6": {"name": "Azad & Jammu State", "suggested_capital": "Muzaffarabad"},
        "#06b6d4": {"name": "Southern Kashmir & Jammu", "suggested_capital": "Jammu"},
        "#ef4444": {"name": "Balochistan Coast & South Sindh", "suggested_capital": "Gwadar"},
        "#84cc16": {"name": "Northern Balochistan & Tribal Region", "suggested_capital": "Pishin"},
        "#eab308": {"name": "Central Balochistan State", "suggested_capital": "Kalat"},
        "#8b5cf6": {"name": "Gilgit-Baltistan Region", "suggested_capital": "Gilgit"},
        "#6366f1": {"name": "Diamir & Hazara Region", "suggested_capital": "Abbottabad"},
        "#b45309": {"name": "Potohar & Capital State", "suggested_capital": "Islamabad"},
        "#22c55e": {"name": "Southern Punjab State", "suggested_capital": "Multan"},
        "#14b8a6": {"name": "Central & Upper Punjab", "suggested_capital": "Lahore"},
        "#f97316": {"name": "Upper Sindh State", "suggested_capital": "Sukkur"},
        "#ec4899": {"name": "Ladakh Territory", "suggested_capital": "Leh"}
    }

    # Load saved custom province definitions if custom_named_provinces_with_capitals.json exists
    custom_named_path = r'c:\Users\ADMIN\Desktop\Geopolitico\custom_named_provinces_with_capitals.json'
    saved_provinces_by_color = {}

    if os.path.exists(custom_named_path):
        try:
            with open(custom_named_path, 'r', encoding='utf-8') as f:
                saved_list = json.load(f)
            for cp in saved_list:
                col = cp.get('color')
                if col:
                    saved_provinces_by_color[col.lower()] = {
                        'province_name': cp.get('province_name'),
                        'capital_name': cp.get('capital_name'),
                        'capital_coordinates': cp.get('capital_coordinates')
                    }
            print(f"[PRELOAD] Pre-loaded {len(saved_provinces_by_color)} custom province definitions from '{custom_named_path}'.")
        except Exception as e:
            print(f"[WARN] Error loading custom provinces JSON: {e}")

    # Perform solid dissolve
    merged_province_features = []

    for idx, (col, shp_list) in enumerate(geoms_by_color.items()):
        solid_mapping, prov_centroid = fill_holes_and_dissolve(shp_list, buffer_dist=0.003, simplify_tol=0.002)
        if not solid_mapping:
            continue

        saved_info = saved_provinces_by_color.get(col.lower())
        if saved_info and saved_info.get('province_name'):
            prov_name = saved_info['province_name']
            sug_cap = saved_info.get('capital_name') or ''
        else:
            p_info = default_province_info.get(col, {"name": f"Custom Province {idx+1}", "suggested_capital": "Capital City"})
            prov_name = p_info["name"]
            sug_cap = p_info["suggested_capital"]

        units_list = unit_info_by_color[col]
        unit_names = [u['name'] for u in units_list]

        # Determine best default capital match among member units
        cap_item = next((u for u in units_list if sug_cap and sug_cap.lower() in u['name'].lower()), None)
        if not cap_item:
            cap_item = units_list[0]
            if sug_cap:
                cap_name = sug_cap
                cap_coords = saved_info.get('capital_coordinates') if saved_info else None
                cap_lat = cap_coords[0] if (cap_coords and len(cap_coords) == 2) else cap_item['lat']
                cap_lng = cap_coords[1] if (cap_coords and len(cap_coords) == 2) else cap_item['lng']
            else:
                cap_name = cap_item['name']
                cap_lat = cap_item['lat']
                cap_lng = cap_item['lng']
        else:
            cap_name = cap_item['name']
            cap_lat = cap_item['lat']
            cap_lng = cap_item['lng']

        merged_province_features.append({
            'type': 'Feature',
            'geometry': solid_mapping,
            'properties': {
                'id': f'PROVINCE_{idx+1}',
                'province_name': prov_name,
                'suggested_capital': cap_name,
                'capital_lat': cap_lat,
                'capital_lng': cap_lng,
                'color': col,
                'unit_count': len(units_list),
                'member_units': units_list,
                'display_units': ", ".join(unit_names[:8]) + ("..." if len(unit_names) > 8 else "")
            }
        })

    print(f"Successfully generated {len(merged_province_features)} province features with pinpoint capital coordinates & smart suggestions!")

    provinces_payload = {
        'type': 'FeatureCollection',
        'features': merged_province_features
    }

    provinces_json_str = json.dumps(provinces_payload)

    # Generate HTML content with real-time capital pinpointing & smart suggestions
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Custom Province & Capital Pinpointer Tool</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        body {
            background-color: #0f172a;
            color: #f8fafc;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #334155;
            z-index: 1000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
        }
        .header-title {
            display: flex;
            flex-direction: column;
        }
        .header-title h1 {
            font-size: 18px;
            font-weight: 700;
            color: #38bdf8;
            letter-spacing: -0.01em;
        }
        .header-title p {
            font-size: 12px;
            color: #94a3b8;
        }
        #container {
            display: flex;
            flex: 1;
            position: relative;
        }
        #map {
            width: 100%;
            height: 100%;
            background: #020617;
        }
        /* Controls Panel */
        .controls-panel {
            position: absolute;
            top: 16px;
            right: 16px;
            width: 400px;
            max-height: calc(100vh - 90px);
            background: rgba(15, 23, 42, 0.95);
            backdrop-filter: blur(12px);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px;
            z-index: 1000;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .section-title {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #94a3b8;
            margin-bottom: 4px;
        }
        .province-list {
            flex: 1;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding-right: 4px;
        }
        .province-card {
            background: rgba(30, 41, 59, 0.75);
            border: 1px solid #334155;
            border-left: 5px solid #38bdf8;
            border-radius: 8px;
            padding: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .province-card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
        }
        .input-group {
            display: flex;
            flex-direction: column;
            gap: 3px;
        }
        .input-label {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            color: #94a3b8;
        }
        .province-input, .capital-select {
            width: 100%;
            padding: 7px 10px;
            background: #0f172a;
            border: 1px solid #475569;
            border-radius: 6px;
            color: #f8fafc;
            font-size: 13px;
            font-weight: 600;
            outline: none;
            transition: all 0.2s ease;
        }
        .province-input:focus, .capital-select:focus {
            border-color: #38bdf8;
            box-shadow: 0 0 6px rgba(56, 189, 248, 0.4);
        }
        .suggestions-badge {
            font-size: 10px;
            color: #eab308;
            font-weight: 600;
        }
        .unit-summary {
            font-size: 11px;
            color: #64748b;
        }
        .action-btns {
            display: flex;
            gap: 8px;
            margin-top: 4px;
        }
        .btn {
            flex: 1;
            padding: 10px 14px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 13px;
            cursor: pointer;
            border: none;
            transition: all 0.2s ease;
            text-align: center;
        }
        .btn-store {
            background: #0284c7;
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);
        }
        .btn-store:hover {
            background: #0369a1;
            transform: translateY(-1px);
        }
        /* Custom Leaflet Star Marker */
        .capital-star-icon {
            text-align: center;
            line-height: 24px;
            font-size: 18px;
            filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.8));
            animation: pulse-star 2s infinite alternate;
        }
        @keyframes pulse-star {
            0% { transform: scale(1.0); }
            100% { transform: scale(1.25); }
        }
        /* Leaflet Popup Styling */
        .leaflet-popup-content-wrapper {
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #475569;
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
            padding: 4px;
        }
        .leaflet-popup-tip {
            background: #1e293b;
        }
        .popup-header {
            font-size: 15px;
            font-weight: 700;
            color: #38bdf8;
            border-bottom: 1px solid #334155;
            padding-bottom: 4px;
            margin-bottom: 6px;
        }
        .popup-badge {
            display: inline-block;
            padding: 2px 6px;
            background: rgba(234, 179, 8, 0.2);
            color: #eab308;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
    </style>
</head>
<body>

<header>
    <div class="header-title">
        <h1>🗺️ Custom Province & Capital Pinpointer</h1>
        <p>Name Custom Provinces & Instant Capital Pinpointing with Smart Auto-Suggestions</p>
    </div>
</header>

<div id="container">
    <div id="map"></div>

    <div class="controls-panel">
        <div>
            <div class="section-title">Configure Provinces & Pinpoint Capitals (${merged_province_features.__len__()} Custom States)</div>
            <p style="font-size:11px; color:#94a3b8;">Select or type a capital district below to immediately pinpoint it on the map with ⭐:</p>
        </div>

        <div class="province-list" id="province-card-container"></div>
        <div class="action-btns" style="display:flex; flex-direction:column; gap:8px;">
            <button class="btn btn-store" id="btn-store">💾 Save Custom Provinces JSON</button>
            <button class="btn" id="btn-download-png-dissolved" style="background:linear-gradient(135deg, #10b981 0%, #059669 100%); color:#fff; border:none; padding:10px 14px; border-radius:8px; font-weight:700; cursor:pointer;">📷 Download Custom Provinces PNG</button>
            <button class="btn" id="btn-download-png-pakistan" style="background:linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color:#fff; border:none; padding:10px 14px; border-radius:8px; font-weight:700; cursor:pointer;">🇵🇰 Download Full Pakistan PNG (No Internal Borders)</button>
        </div>
    </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
    const provincesData = """ + provinces_json_str + """;
    const customProvinces = {}; // id -> { name, capital_name, lat, lng }
    const capitalMarkers = {}; // id -> Leaflet marker

    // Initialize Leaflet Map
    const map = L.map('map', {
        zoomControl: false
    }).setView([31.5, 73.5], 6);

    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        maxZoom: 18
    }).addTo(map);

    let provinceLayer;

    // Render Solid Dissolved Custom Provinces (Zero internal lines!)
    provinceLayer = L.geoJSON(provincesData, {
        style: function(feature) {
            const col = feature.properties.color;
            return {
                fillColor: col,
                fillOpacity: 0.88,
                color: '#ffffff',
                weight: 2.5, // Crisp outer province boundary
                opacity: 1.0
            };
        },
        onEachFeature: function(feature, layer) {
            const props = feature.properties;

            layer.on({
                mouseover: function(e) {
                    const l = e.target;
                    l.setStyle({
                        weight: 4.0,
                        color: '#f8fafc',
                        fillOpacity: 0.98
                    });
                    l.bringToFront();
                },
                mouseout: function(e) {
                    provinceLayer.resetStyle(e.target);
                },
                click: function(e) {
                    const provInfo = customProvinces[props.id] || {};
                    const currentName = provInfo.name || props.province_name;
                    const capName = provInfo.capital_name || props.suggested_capital;

                    L.popup()
                        .setLatLng(e.latlng)
                        .setContent(`
                            <div class="popup-badge">Custom Unified Province</div>
                            <div class="popup-header" style="color:${props.color};">${currentName}</div>
                            <div style="font-size:12px; color:#eab308; margin-bottom:4px;">
                                ⭐ <strong>Capital District:</strong> ${capName}
                            </div>
                        `)
                        .openOn(map);
                }
            });
        }
    }).addTo(map);

    // Auto-fit map bounds
    if (provinceLayer.getBounds().isValid()) {
        map.fitBounds(provinceLayer.getBounds(), { padding: [40, 40] });
    }

    // Custom Star Icon Generator
    function createStarIcon(colorHex) {
        return L.divIcon({
            className: 'custom-capital-star',
            html: `<div class="capital-star-icon" style="color:#f59e0b;">⭐</div>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });
    }

    // Pinpoint capital on map
    function pinpointCapital(provId, capName, lat, lng, colorHex) {
        if (capitalMarkers[provId]) {
            map.removeLayer(capitalMarkers[provId]);
        }

        const marker = L.marker([lat, lng], {
            icon: createStarIcon(colorHex)
        }).addTo(map);

        marker.bindPopup(`
            <div class="popup-badge" style="background:rgba(245,158,11,0.2); color:#f59e0b;">Capital HQ</div>
            <div class="popup-header" style="color:#ffffff;">${capName}</div>
            <div style="font-size:11px; color:#94a3b8;">
                📍 Coordinates: ${lat.toFixed(4)}, ${lng.toFixed(4)}
            </div>
        `);

        capitalMarkers[provId] = marker;
    }

    // Build Province Cards in Sidebar
    const cardContainer = document.getElementById('province-card-container');

    provincesData.features.forEach((feat, idx) => {
        const props = feat.properties;
        const provId = props.id;
        const initialCap = props.suggested_capital;
        const initialLat = props.capital_lat;
        const initialLng = props.capital_lng;

        customProvinces[provId] = {
            name: props.province_name,
            capital_name: initialCap,
            lat: initialLat,
            lng: initialLng
        };

        // Pinpoint default capital on map
        pinpointCapital(provId, initialCap, initialLat, initialLng, props.color);

        const card = document.createElement('div');
        card.className = 'province-card';
        card.style.borderLeftColor = props.color;

        let optionsHTML = '';
        props.member_units.forEach(unit => {
            const isSelected = unit.name.toLowerCase() === initialCap.toLowerCase() ? 'selected' : '';
            optionsHTML += `<option value="${unit.name}" data-lat="${unit.lat}" data-lng="${unit.lng}" ${isSelected}>${unit.name}</option>`;
        });

        card.innerHTML = `
            <div class="province-header">
                <input type="text" class="province-title-input" id="input-name-${provId}" value="${props.province_name}">
                <span class="unit-count-chip" style="background:${props.color}; color:#fff;">${props.unit_count} Units</span>
            </div>
            <div class="capital-selector-row">
                <label style="font-size:11px; font-weight:700; color:#eab308; min-width:80px;">⭐ Capital HQ:</label>
                <select class="capital-select" id="select-cap-${provId}">
                    ${optionsHTML}
                </select>
            </div>
            <div class="unit-summary">
                <strong>Member Units:</strong> ${props.display_units}
            </div>
        `;

        cardContainer.appendChild(card);

        // Province title input listener
        const nameInput = card.querySelector(`#input-name-${provId}`);
        nameInput.addEventListener('input', (e) => {
            customProvinces[provId].name = e.target.value;
        });

        // Capital select listener -> INSTANT PINPOINT ON MAP
        const capSelect = card.querySelector(`#select-cap-${provId}`);
        capSelect.addEventListener('change', (e) => {
            const selectedOpt = e.target.options[e.target.selectedIndex];
            const capName = selectedOpt.value;
            const lat = parseFloat(selectedOpt.getAttribute('data-lat'));
            const lng = parseFloat(selectedOpt.getAttribute('data-lng'));

            customProvinces[provId].capital_name = capName;
            customProvinces[provId].lat = lat;
            customProvinces[provId].lng = lng;

            pinpointCapital(provId, capName, lat, lng, props.color);
            map.flyTo([lat, lng], 8, { duration: 1.2 });
            capitalMarkers[provId].openPopup();
        });
    });

    // Save & Store Custom Provinces JSON Button
    document.getElementById('btn-store').addEventListener('click', () => {
        const storedProvinces = [];

        provincesData.features.forEach(f => {
            const props = f.properties;
            const provId = props.id;
            const info = customProvinces[provId] || {};

            storedProvinces.push({
                province_id: provId,
                province_name: info.name || props.province_name,
                capital_name: info.capital_name || props.suggested_capital,
                capital_coordinates: [info.lat || props.capital_lat, info.lng || props.capital_lng],
                color: props.color,
                district_count: props.unit_count,
                member_districts: props.member_units.map(m => m.name),
                geometry: f.geometry
            });
        });

        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(storedProvinces, null, 2));
        const dlAnchor = document.createElement('a');
        dlAnchor.setAttribute("href", dataStr);
        dlAnchor.setAttribute("download", "custom_named_provinces_with_capitals.json");
        document.body.appendChild(dlAnchor);
        dlAnchor.click();
        dlAnchor.remove();

        alert(`Successfully stored ${storedProvinces.length} custom named provinces with pinpointed capitals to custom_named_provinces_with_capitals.json!`);
    });

    // Download Clean PNG Map for Dissolved Provinces (Multi-Column Grid Legend)
    document.getElementById('btn-download-png-dissolved').addEventListener('click', () => {
        let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;

        function checkCoords(coords) {
            if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
                const lon = coords[0], lat = coords[1];
                if (lon < minLon) minLon = lon;
                if (lon > maxLon) maxLon = lon;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
            } else if (Array.isArray(coords)) {
                coords.forEach(checkCoords);
            }
        }

        provincesData.features.forEach(f => {
            if (f.geometry && f.geometry.coordinates) {
                checkCoords(f.geometry.coordinates);
            }
        });

        const totalItems = provincesData.features.length;

        if (totalItems === 0) {
            alert('No custom provinces found!');
            return;
        }

        // Dynamic Multi-Column Grid Calculation
        const maxRowsPerCol = 22;
        const numCols = Math.min(4, Math.max(1, Math.ceil(totalItems / maxRowsPerCol)));
        const colWidth = 320;
        const legendWidth = numCols * colWidth + 50;
        const mapWidth = 2000;
        const canvasWidth = mapWidth + legendWidth;

        const rowHeight = 44;
        const headerSpace = 130;
        const rowsCount = Math.ceil(totalItems / numCols);
        const canvasHeight = Math.max(1500, headerSpace + rowsCount * rowHeight + 60);

        const lonSpan = maxLon - minLon || 1;
        const latSpan = maxLat - minLat || 1;
        minLon -= lonSpan * 0.05; maxLon += lonSpan * 0.05;
        minLat -= latSpan * 0.05; maxLat += latSpan * 0.05;

        const canvas = document.createElement('canvas');
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        const ctx = canvas.getContext('2d');

        // Dark Background
        ctx.fillStyle = '#090d16';
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);

        function project(lon, lat) {
            const x = ((lon - minLon) / (maxLon - minLon)) * (mapWidth - 100) + 50;
            const y = canvasHeight - (((lat - minLat) / (maxLat - minLat)) * (canvasHeight - 100) + 50);
            return [x, y];
        }

        function drawPolygonCoords(rings) {
            ctx.beginPath();
            rings.forEach(ring => {
                ring.forEach((pt, i) => {
                    const [px, py] = project(pt[0], pt[1]);
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                });
            });
            ctx.closePath();
            ctx.fill();
            ctx.stroke();
        }

        // Draw Dissolved Map Shapes (No basemap tiles!)
        provincesData.features.forEach(f => {
            const props = f.properties;
            ctx.fillStyle = props.color || '#38bdf8';
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2.5;

            const g = f.geometry;
            if (g.type === 'Polygon') {
                drawPolygonCoords(g.coordinates);
            } else if (g.type === 'MultiPolygon') {
                g.coordinates.forEach(poly => drawPolygonCoords(poly));
            }
        });

        // Draw Legend Panel on Right Side
        ctx.fillStyle = 'rgba(15, 23, 42, 0.96)';
        ctx.fillRect(mapWidth, 0, legendWidth, canvasHeight);

        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(mapWidth, 0);
        ctx.lineTo(mapWidth, canvasHeight);
        ctx.stroke();

        // Legend Header
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 28px Inter, sans-serif';
        ctx.fillText('🗺️ DISSOLVED PROVINCES MAP', mapWidth + 30, 52);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '15px Inter, sans-serif';
        ctx.fillText(`${totalItems} Custom Regions & Capitals`, mapWidth + 30, 80);

        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mapWidth + 30, 98);
        ctx.lineTo(canvasWidth - 30, 98);
        ctx.stroke();

        // Render Items in Multi-Column Grid (Zero Overflow!)
        const startY = 135;
        provincesData.features.forEach((f, idx) => {
            const colIdx = Math.floor(idx / rowsCount);
            const rowIdx = idx % rowsCount;

            const xPos = mapWidth + 30 + colIdx * colWidth;
            const yPos = startY + rowIdx * rowHeight;

            if (yPos > canvasHeight - 30) return;

            const props = f.properties;
            const provId = props.id;
            const info = customProvinces[provId] || {};
            const provName = info.name || props.province_name;
            const capName = info.capital_name || props.suggested_capital;

            // Swatch chip
            ctx.fillStyle = props.color || '#38bdf8';
            ctx.fillRect(xPos, yPos - 16, 20, 20);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.2;
            ctx.strokeRect(xPos, yPos - 16, 20, 20);

            // Province Name
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 15px Inter, sans-serif';
            const nameText = provName.length > 22 ? provName.substring(0, 20) + '..' : provName;
            ctx.fillText(nameText, xPos + 28, yPos - 2);

            // Capital Name & Unit Count
            ctx.fillStyle = '#f59e0b';
            ctx.font = '12px Inter, sans-serif';
            const capText = `⭐ ${capName}`;
            const capTrunc = capText.length > 26 ? capText.substring(0, 24) + '..' : capText;
            ctx.fillText(capTrunc, xPos + 28, yPos + 14);
        });

        // Trigger PNG Download
        const imgURI = canvas.toDataURL('image/png');
        const dlAnchor = document.createElement('a');
        dlAnchor.setAttribute('href', imgURI);
        dlAnchor.setAttribute('download', 'dissolved_custom_provinces_map.png');
        document.body.appendChild(dlAnchor);
        dlAnchor.click();
        dlAnchor.remove();
    });

    // Download Full Pakistan PNG (No Internal Province Borders)
    document.getElementById('btn-download-png-pakistan').addEventListener('click', () => {
        const pakFeatures = provincesData.features.filter(f => {
            const members = f.properties.member_units || [];
            return members.some(m => (m.country || '').toLowerCase() === 'pakistan' || (m.source || '').toLowerCase().includes('pakistan'));
        });

        const featuresToRender = pakFeatures.length > 0 ? pakFeatures : provincesData.features;

        let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;

        function checkCoords(coords) {
            if (typeof coords[0] === 'number' && typeof coords[1] === 'number') {
                const lon = coords[0], lat = coords[1];
                if (lon < minLon) minLon = lon;
                if (lon > maxLon) maxLon = lon;
                if (lat < minLat) minLat = lat;
                if (lat > maxLat) maxLat = lat;
            } else if (Array.isArray(coords)) {
                coords.forEach(checkCoords);
            }
        }

        featuresToRender.forEach(f => {
            if (f.geometry && f.geometry.coordinates) {
                checkCoords(f.geometry.coordinates);
            }
        });

        const totalItems = featuresToRender.length;
        if (totalItems === 0) {
            alert('No Pakistan provinces found!');
            return;
        }

        const maxRowsPerCol = 22;
        const numCols = Math.min(4, Math.max(1, Math.ceil(totalItems / maxRowsPerCol)));
        const colWidth = 320;
        const legendWidth = numCols * colWidth + 50;
        const mapWidth = 2000;
        const canvasWidth = mapWidth + legendWidth;

        const rowHeight = 44;
        const headerSpace = 130;
        const rowsCount = Math.ceil(totalItems / numCols);
        const canvasHeight = Math.max(1500, headerSpace + rowsCount * rowHeight + 60);

        const lonSpan = maxLon - minLon || 1;
        const latSpan = maxLat - minLat || 1;
        minLon -= lonSpan * 0.05; maxLon += lonSpan * 0.05;
        minLat -= latSpan * 0.05; maxLat += latSpan * 0.05;

        const canvas = document.createElement('canvas');
        canvas.width = canvasWidth;
        canvas.height = canvasHeight;
        const ctx = canvas.getContext('2d');

        // Dark Background
        ctx.fillStyle = '#090d16';
        ctx.fillRect(0, 0, canvasWidth, canvasHeight);

        function project(lon, lat) {
            const x = ((lon - minLon) / (maxLon - minLon)) * (mapWidth - 100) + 50;
            const y = canvasHeight - (((lat - minLat) / (maxLat - minLat)) * (canvasHeight - 100) + 50);
            return [x, y];
        }

        function drawPolygonCoordsNoBorder(rings) {
            ctx.beginPath();
            rings.forEach(ring => {
                ring.forEach((pt, i) => {
                    const [px, py] = project(pt[0], pt[1]);
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                });
            });
            ctx.closePath();
            ctx.fill(); // SEAMLESS FILL ONLY, NO INTERNAL BORDER STROKES!
        }

        // Draw Map Shapes WITHOUT internal borders (all solid Pakistan green fill!)
        featuresToRender.forEach(f => {
            ctx.fillStyle = '#10b981'; // Solid Emerald Green (#10b981)

            const g = f.geometry;
            if (g.type === 'Polygon') {
                drawPolygonCoordsNoBorder(g.coordinates);
            } else if (g.type === 'MultiPolygon') {
                g.coordinates.forEach(poly => drawPolygonCoordsNoBorder(poly));
            }
        });

        // Draw Legend Panel on Right Side
        ctx.fillStyle = 'rgba(15, 23, 42, 0.96)';
        ctx.fillRect(mapWidth, 0, legendWidth, canvasHeight);

        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(mapWidth, 0);
        ctx.lineTo(mapWidth, canvasHeight);
        ctx.stroke();

        // Legend Header
        ctx.fillStyle = '#10b981';
        ctx.font = 'bold 28px Inter, sans-serif';
        ctx.fillText('🇵🇰 FULL PAKISTAN MAP', mapWidth + 30, 52);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '15px Inter, sans-serif';
        ctx.fillText(`${totalItems} Provinces (Solid Green, No Internal Borders)`, mapWidth + 30, 80);

        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mapWidth + 30, 98);
        ctx.lineTo(canvasWidth - 30, 98);
        ctx.stroke();

        // Render Items in Multi-Column Grid
        const startY = 135;
        featuresToRender.forEach((f, idx) => {
            const colIdx = Math.floor(idx / rowsCount);
            const rowIdx = idx % rowsCount;

            const xPos = mapWidth + 30 + colIdx * colWidth;
            const yPos = startY + rowIdx * rowHeight;

            if (yPos > canvasHeight - 30) return;

            const props = f.properties;
            const provId = props.id;
            const info = customProvinces[provId] || {};
            const provName = info.name || props.province_name;
            const capName = info.capital_name || props.suggested_capital;

            // Swatch chip (Solid Green)
            ctx.fillStyle = '#10b981';
            ctx.fillRect(xPos, yPos - 16, 20, 20);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.2;
            ctx.strokeRect(xPos, yPos - 16, 20, 20);

            // Province Name
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 15px Inter, sans-serif';
            const nameText = provName.length > 22 ? provName.substring(0, 20) + '..' : provName;
            ctx.fillText(nameText, xPos + 28, yPos - 2);

            // Capital Name & Unit Count
            ctx.fillStyle = '#f59e0b';
            ctx.font = '12px Inter, sans-serif';
            const capText = `⭐ ${capName}`;
            const capTrunc = capText.length > 26 ? capText.substring(0, 24) + '..' : capText;
            ctx.fillText(capTrunc, xPos + 28, yPos + 14);
        });

        // Trigger PNG Download
        const imgURI = canvas.toDataURL('image/png');
        const dlAnchor = document.createElement('a');
        dlAnchor.setAttribute('href', imgURI);
        dlAnchor.setAttribute('download', 'full_pakistan_solid_map.png');
        document.body.appendChild(dlAnchor);
        dlAnchor.click();
        dlAnchor.remove();
    });
</script>

</body>
</html>
"""

    out_file = r'c:\Users\ADMIN\Desktop\Geopolitico\scratch\custom_provinces_preview.html'
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    frontend_out = r'c:\Users\ADMIN\Desktop\Geopolitico\frontend\custom_provinces_preview.html'
    with open(frontend_out, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Successfully generated custom province preview HTML at:\n  1. {out_file}\n  2. {frontend_out}")

if __name__ == '__main__':
    main()
