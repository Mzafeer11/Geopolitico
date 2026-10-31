import json
import os
from shapely.geometry import shape, mapping, box

def simplify_geom(geom_dict, tolerance=0.003):
    try:
        s = shape(geom_dict)
        simplified = s.simplify(tolerance, preserve_topology=True)
        return mapping(simplified)
    except Exception:
        return geom_dict

def main():
    pak2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\Pakistan Districts\pak_admin2.geojson'
    ind2_gadm_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_IND_2.json\gadm41_IND_2.json'
    ind4_path = r'c:\Users\ADMIN\Desktop\Geopolitico\Indian Data\geoBoundaries-IND-ADM4.geojson'

    afg2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_AFG_2.json\gadm41_AFG_2.json'
    irn2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_IRN_2.json\gadm41_IRN_2.json'
    tjk2_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_TJK_2.json\gadm41_TJK_2.json'
    chn3_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_CHN_3.json\gadm41_CHN_3.json'
    if not os.path.exists(chn3_path):
        chn3_path = r'c:\Users\ADMIN\Desktop\Geopolitico\gadm41_CHN_3.json'

    custom_named_path = r'c:\Users\ADMIN\Desktop\Geopolitico\custom_named_provinces_with_capitals.json'
    painted_json_path = r'c:\Users\ADMIN\Desktop\Geopolitico\custom_regional_painted_divisions.json'

    gmba_polys_path = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\f83657ce-68ad-4fb0-9fed-4aef6c30d42e\scratch\gmba_defense_mountains.geojson"
    gmba_lines_path = r"C:\Users\ADMIN\.gemini\antigravity-ide\brain\f83657ce-68ad-4fb0-9fed-4aef6c30d42e\scratch\gmba_defense_mountain_lines.geojson"
    ne_regions_path = r"c:\Users\ADMIN\Desktop\Geopolitico\data\ne_10m_geography_regions_polys.geojson"

    river_paths = [
        r"c:\Users\ADMIN\Desktop\Geopolitico\data\ne_10m_rivers_lake_centerlines.geojson",
        r"c:\Users\ADMIN\Desktop\Geopolitico\data\ne_10m_rivers_europe.geojson",
        r"c:\Users\ADMIN\Desktop\Geopolitico\data\ne_50m_rivers_lake_centerlines.geojson",
        r"c:\Users\ADMIN\Desktop\Geopolitico\data\hgis_datasets\dare_awmc\dare\roman-empire-master\data\10m_rivers_lake_centerlines.geojson"
    ]

    # Mapping of unit_id -> { 'color': hex, 'province_name': str, 'capital_name': str }
    unit_custom_info = {}
    district_name_custom_info = {}
    custom_provinces_data = []

    # 1. Preload custom_named_provinces_with_capitals.json if available
    if os.path.exists(custom_named_path):
        try:
            with open(custom_named_path, 'r', encoding='utf-8') as f:
                custom_provinces_data = json.load(f)
            for cp in custom_provinces_data:
                p_name = cp.get('province_name', '')
                c_name = cp.get('capital_name', '')
                hex_col = cp.get('color', '')
                uids = cp.get('member_unit_ids', [])
                districts = cp.get('member_districts', [])

                info_dict = {
                    'color': hex_col,
                    'province_name': p_name,
                    'capital_name': c_name
                }

                for uid in uids:
                    if uid:
                        unit_custom_info[uid] = info_dict

                for d in districts:
                    if d:
                        clean_d = d.lower().replace(' district', '').replace(' sub-division', '').strip()
                        district_name_custom_info[clean_d] = info_dict
                        district_name_custom_info[d.lower().strip()] = info_dict

            print(f"[PRELOAD] Pre-loaded {len(custom_provinces_data)} custom provinces from '{custom_named_path}'.")
        except Exception as e:
            print(f"[WARN] Error reading '{custom_named_path}': {e}")

    # 2. Augment with custom_regional_painted_divisions.json if available
    if os.path.exists(painted_json_path):
        try:
            with open(painted_json_path, 'r', encoding='utf-8') as f:
                painted_list = json.load(f)
            count = 0
            for item in painted_list:
                uid = item.get('id')
                col = item.get('color')
                if uid and col and col != '#334155':
                    if uid not in unit_custom_info:
                        unit_custom_info[uid] = {}
                    unit_custom_info[uid]['color'] = col
                    count += 1
            print(f"[PRELOAD] Pre-loaded {count} painted unit colors from '{painted_json_path}'.")
        except Exception as e:
            print(f"[WARN] Error reading '{painted_json_path}': {e}")

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
            print(f"[LOAD] Loaded China Admin 3 dataset with {len(chn3_data.get('features', []))} total features.")
        except Exception as e:
            print(f"[WARN] Error loading China Admin 3 dataset: {e}")

    combined_features = []
    pak_count = 0
    ind_count = 0
    ladakh_count = 0
    afg_count = 0
    iran_count = 0
    tjk_count = 0
    chn_count = 0

    def get_unit_info(uid, unit_name):
        if uid in unit_custom_info:
            return unit_custom_info[uid]
        clean_name = unit_name.lower().replace(' district', '').replace(' sub-division', '').strip()
        if clean_name in district_name_custom_info:
            return district_name_custom_info[clean_name]
        if unit_name.lower().strip() in district_name_custom_info:
            return district_name_custom_info[unit_name.lower().strip()]
        return {}

    # 1. Pakistan Folder Features (Admin 2 Districts from pak_admin2.geojson)
    for idx, feat in enumerate(pak2_data.get('features', [])):
        props = feat.get('properties', {})
        pak_count += 1

        d_name = props.get('adm2_name') or props.get('adm2_ref_name') or 'District'
        p_name = props.get('adm1_name') or 'Pakistan'
        pcode = props.get('adm2_pcode') or f'PAK2_{idx}'
        uid = f'PAK_{pcode}_{idx}'

        sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
        info = get_unit_info(uid, d_name)
        initial_col = info.get('color') or '#334155'
        c_prov = info.get('province_name', '')
        c_cap = info.get('capital_name', '')

        combined_features.append({
            'type': 'Feature',
            'geometry': sim_geom,
            'properties': {
                'id': uid,
                'district': d_name,
                'province': p_name,
                'country': 'Pakistan',
                'initial_color': initial_col,
                'custom_province': c_prov,
                'capital_name': c_cap,
                'name': f"{d_name} District",
                'source': 'Pakistan Districts Folder (pak_admin2.geojson)',
                'display_name': f"{d_name} District ({p_name}, Pakistan)"
            }
        })

    # 2. Indian States Features (Jammu & Kashmir, Punjab, Gujarat, Rajasthan, Haryana, Himachal Pradesh, Chandigarh, Maharashtra, Madhya Pradesh, Delhi, UP, UK, DNH, DD from gadm41_IND_2.json)
    target_ind_states = [
        'JammuandKashmir', 'Punjab', 'Gujarat', 'Rajasthan', 'Haryana',
        'HimachalPradesh', 'Chandigarh', 'Maharashtra', 'MadhyaPradesh',
        'NCTofDelhi', 'UttarPradesh', 'Uttarakhand', 'DadraandNagarHaveli', 'DamanandDiu','Bihar', 'Goa'
    ]
    state_label_map = {
        'JammuandKashmir': 'Jammu & Kashmir',
        'Punjab': 'Punjab',
        'Gujarat': 'Gujarat',
        'Rajasthan': 'Rajasthan',
        'Haryana': 'Haryana',
        'HimachalPradesh': 'Himachal Pradesh',
        'Chandigarh': 'Chandigarh',
        'Maharashtra': 'Maharashtra',
        'MadhyaPradesh': 'Madhya Pradesh',
        'NCTofDelhi': 'Delhi (NCT)',
        'UttarPradesh': 'Uttar Pradesh',
        'Uttarakhand': 'Uttarakhand',
        'DadraandNagarHaveli': 'Dadra & Nagar Haveli',
        'DamanandDiu': 'Daman & Diu'
    }

    for idx, feat in enumerate(ind2_data.get('features', [])):
        props = feat.get('properties', {})
        st = props.get('NAME_1', '')
        unit_name = props.get('NAME_2', '')

        if st in target_ind_states:
            if unit_name.lower() in ['leh', 'kargil', 'leh(ladakh)'] or st.lower() == 'ladakh':
                continue

            ind_count += 1
            prov_label = state_label_map.get(st, st)
            gid = props.get('GID_2') or f'IND2_{idx}'
            uid = f'IND_{gid}_{idx}'

            sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
            info = get_unit_info(uid, unit_name)
            initial_col = info.get('color') or '#334155'
            c_prov = info.get('province_name', '')
            c_cap = info.get('capital_name', '')

            combined_features.append({
                'type': 'Feature',
                'geometry': sim_geom,
                'properties': {
                    'id': uid,
                    'district': unit_name,
                    'province': prov_label,
                    'country': 'India',
                    'initial_color': initial_col,
                    'custom_province': c_prov,
                    'capital_name': c_cap,
                    'name': f"{unit_name} District",
                    'source': f"India {prov_label} Admin 2 Districts (GADM L2)",
                    'display_name': f"{unit_name} District ({prov_label}, India)"
                }
            })

    # 3. Clean Ladakh ADM4 Sub-divisions (geoBoundaries-IND-ADM4.geojson)
    excluded_keywords = ['aksai', 'chin', 'gilgit', 'baltistan', 'new jammu', 'azad', 'muzaffarabad', 'mirpur']
    ladakh_valid_names = [
        'deskit', 'panamic', 'turtuk', 'nyoma', 'durbuk', 'rupsho', 'rong',
        'leh', 'thiksay', 'nimoo', 'kharu', 'chuchot', 'saspol', 'khaltsi',
        'sukerbachan', 'singay lalok wanla', 'drass', 'bhimbat', 'kargil',
        'sankoo', 'taisuru', 'zansker', 'karsha', 'lungnak', 'shaker chaktan',
        'shargol', 'soudh', 'pashkum', 'lotsum', 'barsoo', 'gm pora (trespone)'
    ]

    region_map = {
        'Deskit': 'Nubra Region',
        'Panamic': 'Nubra Region',
        'Turtuk': 'Nubra Region',
        'Nyoma': 'Changthang Region',
        'Durbuk': 'Changthang Region',
        'Rupsho': 'Changthang Region',
        'Rong': 'Changthang Region',
        'Leh': 'Leh Region',
        'Thiksay': 'Leh Region',
        'Nimoo': 'Leh Region',
        'Kharu': 'Leh Region',
        'Chuchot': 'Leh Region',
        'Saspol': 'Sham / Khaltse Region',
        'Khaltsi': 'Sham / Khaltse Region',
        'Sukerbachan': 'Sham / Khaltse Region',
        'Singay Lalok Wanla': 'Sham / Khaltse Region',
        'Drass': 'Drass Region',
        'Bhimbat': 'Drass Region',
        'Kargil': 'Kargil Region',
        'Sankoo': 'Suru Valley',
        'Taisuru': 'Suru Valley',
        'Barsoo': 'Suru Valley',
        'Zansker': 'Zanskar Region',
        'Karsha': 'Zanskar Region',
        'Lungnak': 'Zanskar Region',
        'Shaker Chaktan': 'Chiktan Region',
        'Shargol': 'Wakhan / Shargol Region',
        'Soudh': 'Kargil Region',
        'Pashkum': 'Kargil Region',
        'Lotsum': 'Kargil Region',
        'GM Pora (Trespone)': 'Kargil Region'
    }

    for idx, feat in enumerate(ind4_data.get('features', [])):
        props = feat.get('properties', {})
        sname = (props.get('shapeName') or '').strip()
        sname_lower = sname.lower()
        sid = props.get('shapeID') or f'IND4_{idx}'

        if any(kw in sname_lower for kw in excluded_keywords):
            continue

        try:
            if sname_lower in ladakh_valid_names:
                ladakh_count += 1
                sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
                uid = f'LADAKH_ADM4_{sid}_{idx}'

                matched_title = next((k for k in region_map if k.lower() == sname_lower), sname)
                sub_reg = region_map.get(matched_title, "Ladakh Sub-division")

                info = get_unit_info(uid, sname)
                initial_col = info.get('color') or '#334155'
                c_prov = info.get('province_name', '')
                c_cap = info.get('capital_name', '')

                combined_features.append({
                    'type': 'Feature',
                    'geometry': sim_geom,
                    'properties': {
                        'id': uid,
                        'district': f"{sname} ({sub_reg})",
                        'province': 'Ladakh',
                        'country': 'India',
                        'initial_color': initial_col,
                        'custom_province': c_prov,
                        'capital_name': c_cap,
                        'name': f"{sname} Sub-division",
                        'source': 'Indian Data Folder (geoBoundaries-IND-ADM4.geojson)',
                        'display_name': f"{sname} Sub-division ({sub_reg}, Ladakh)"
                    }
                })
        except Exception:
            pass

    # 4. Afghanistan GADM Level 2 Districts (from gadm41_AFG_2.json)
    for idx, feat in enumerate(afg2_data.get('features', [])):
        props = feat.get('properties', {})
        d_name = (props.get('NAME_2') or props.get('NAME_1') or 'District').strip()
        p_name = (props.get('NAME_1') or 'Afghanistan').strip()
        gid = props.get('GID_2') or f'AFG2_{idx}'
        uid = f'AFG_{gid}_{idx}'

        afg_count += 1
        sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
        info = get_unit_info(uid, d_name)
        initial_col = info.get('color') or '#334155'
        c_prov = info.get('province_name', '')
        c_cap = info.get('capital_name', '')

        combined_features.append({
            'type': 'Feature',
            'geometry': sim_geom,
            'properties': {
                'id': uid,
                'district': d_name,
                'province': p_name,
                'country': 'Afghanistan',
                'initial_color': initial_col,
                'custom_province': c_prov,
                'capital_name': c_cap,
                'name': f"{d_name} District",
                'source': 'Afghanistan GADM L2 Districts (gadm41_AFG_2.json)',
                'display_name': f"{d_name} District ({p_name}, Afghanistan)"
            }
        })

    # 5. Iran GADM Level 2 Counties / Shahrestans (from gadm41_IRN_2.json)
    for idx, feat in enumerate(irn2_data.get('features', [])):
        props = feat.get('properties', {})
        d_name = (props.get('NAME_2') or props.get('NAME_1') or 'County').strip()
        p_name = (props.get('NAME_1') or 'Iran').strip()
        gid = props.get('GID_2') or f'IRN2_{idx}'
        uid = f'IRN_{gid}_{idx}'

        iran_count += 1
        sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
        info = get_unit_info(uid, d_name)
        initial_col = info.get('color') or '#334155'
        c_prov = info.get('province_name', '')
        c_cap = info.get('capital_name', '')

        combined_features.append({
            'type': 'Feature',
            'geometry': sim_geom,
            'properties': {
                'id': uid,
                'district': d_name,
                'province': p_name,
                'country': 'Iran',
                'initial_color': initial_col,
                'custom_province': c_prov,
                'capital_name': c_cap,
                'name': f"{d_name} District",
                'source': 'Iran GADM L2 Counties (gadm41_IRN_2.json)',
                'display_name': f"{d_name} District ({p_name}, Iran)"
            }
        })

    # 6. Tajikistan GADM Level 2 Districts (from gadm41_TJK_2.json)
    for idx, feat in enumerate(tjk2_data.get('features', [])):
        props = feat.get('properties', {})
        d_name = (props.get('NAME_2') or props.get('NAME_1') or 'District').strip()
        p_name = (props.get('NAME_1') or 'Tajikistan').strip()
        gid = props.get('GID_2') or f'TJK2_{idx}'
        uid = f'TJK_{gid}_{idx}'

        tjk_count += 1
        sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
        info = get_unit_info(uid, d_name)
        initial_col = info.get('color') or '#334155'
        c_prov = info.get('province_name', '')
        c_cap = info.get('capital_name', '')

        combined_features.append({
            'type': 'Feature',
            'geometry': sim_geom,
            'properties': {
                'id': uid,
                'district': d_name,
                'province': p_name,
                'country': 'Tajikistan',
                'initial_color': initial_col,
                'custom_province': c_prov,
                'capital_name': c_cap,
                'name': f"{d_name} District",
                'source': 'Tajikistan GADM L2 Districts (gadm41_TJK_2.json)',
                'display_name': f"{d_name} District ({p_name}, Tajikistan)"
            }
        })

    # 7. China GADM Level 3 Counties (from gadm41_CHN_3.json)
    target_chn_provinces = ['Xizang', 'XinjiangUygur', 'Gansu', 'Qinghai']
    chn_label_map = {
        'Xizang': 'Tibet (Xizang)',
        'XinjiangUygur': 'Xinjiang',
        'Gansu': 'Gansu',
        'Qinghai': 'Qinghai'
    }


    for idx, feat in enumerate(chn3_data.get('features', [])):
        props = feat.get('properties', {})
        p_name_raw = props.get('NAME_1', '')
        if p_name_raw in target_chn_provinces:
            prov_label = chn_label_map.get(p_name_raw, p_name_raw)
            pref_name = (props.get('NAME_2') or '').strip()
            c_name = (props.get('NAME_3') or pref_name or 'County').strip()
            gid = props.get('GID_3') or f'CHN3_{idx}'
            eng_type = props.get('ENGTYPE_3') or 'County'
            uid = f'CHN_{gid}_{idx}'

            chn_count += 1
            sim_geom = simplify_geom(feat['geometry'], tolerance=0.003)
            info = get_unit_info(uid, c_name)

            initial_col = info.get('color')
            c_prov = info.get('province_name', '')
            c_cap = info.get('capital_name', '')

            if not initial_col and pref_name == 'Ngari':
                initial_col = '#ade1db'
                if not c_prov:
                    c_prov = 'Baltistan'
                if not c_cap:
                    c_cap = 'Skardu District'

            if not initial_col:
                initial_col = '#334155'

            combined_features.append({
                'type': 'Feature',
                'geometry': sim_geom,
                'properties': {
                    'id': uid,
                    'district': c_name,
                    'prefecture': pref_name,
                    'province': prov_label,
                    'country': 'China',
                    'initial_color': initial_col,
                    'custom_province': c_prov,
                    'capital_name': c_cap,
                    'name': f"{c_name} ({eng_type})",
                    'source': f"China {prov_label} Admin 3 Counties (gadm41_CHN_3.json)",
                    'display_name': f"{c_name} [{pref_name}, {prov_label}, China]"
                }
            })

    print(f"Combined total features extracted:")
    print(f"  1. Pakistan Admin 2 Districts: {pak_count}")
    print(f"  2. Indian States Admin 2 Districts: {ind_count}")
    print(f"  3. Clean Ladakh ADM4 Sub-divisions: {ladakh_count}")
    print(f"  4. Afghanistan GADM L2 Districts: {afg_count}")
    print(f"  5. Iran GADM L2 Counties: {iran_count}")
    print(f"  6. Tajikistan GADM L2 Districts: {tjk_count}")
    print(f"  7. China GADM L3 Counties: {chn_count}")
    print(f"Total Administrative Units: {len(combined_features)}")

    geojson_payload = {
        'type': 'FeatureCollection',
        'features': combined_features
    }

    # Load GMBA Mountains & Lines
    gmba_mountains_str = '{"type":"FeatureCollection","features":[]}'
    gmba_lines_str = '{"type":"FeatureCollection","features":[]}'
    if os.path.exists(gmba_polys_path):
        with open(gmba_polys_path, 'r', encoding='utf-8') as f:
            gmba_mountains_str = f.read().strip()
    if os.path.exists(gmba_lines_path):
        with open(gmba_lines_path, 'r', encoding='utf-8') as f:
            gmba_lines_str = f.read().strip()

    # Extract Deserts from Natural Earth
    deserts_features = []
    if os.path.exists(ne_regions_path):
        with open(ne_regions_path, 'r', encoding='utf-8') as f:
            ne_raw = json.load(f)
        for feat in ne_raw['features']:
            props = feat.get('properties', {})
            mname = props.get('NAME', '')
            ftype = props.get('FEATURECLA', '')
            if ftype == 'Desert' and mname.upper() != 'PUNJAB':
                try:
                    shp = shape(feat['geometry'])
                    if not shp.is_empty:
                        minx, miny, maxx, maxy = shp.bounds
                        if maxx >= 44 and minx <= 98 and maxy >= 16 and miny <= 45:
                            c = shp.centroid
                            simplified = shp.simplify(0.015, preserve_topology=True)
                            deserts_features.append({
                                "type": "Feature",
                                "geometry": mapping(simplified),
                                "properties": {
                                    "name": mname,
                                    "type": "Desert",
                                    "center_lat": round(c.y, 4),
                                    "center_lng": round(c.x, 4)
                                }
                            })
                except Exception:
                    pass
    deserts_str = json.dumps({"type": "FeatureCollection", "features": deserts_features})

    # =========================================================================
    # EXTRACT & MERGE ALL RIVER FILES (10m, Europe, 50m, Classical Dare)
    # =========================================================================
    theater_box = box(40, 10, 105, 45)
    accepted_river_features = []
    accepted_river_lines = []

    for rpath in river_paths:
        if not os.path.exists(rpath):
            continue
        try:
            with open(rpath, 'r', encoding='utf-8') as rf:
                rdata = json.load(rf)
            for feat in rdata.get('features', []):
                try:
                    geom = shape(feat['geometry'])
                    if not geom.intersects(theater_box):
                        continue
                    clipped = geom.intersection(theater_box)
                    if clipped.is_empty:
                        continue

                    # Deduplicate near-identical lines
                    is_dup = False
                    for acc in accepted_river_lines:
                        if not clipped.bounds or not acc.bounds:
                            continue
                        minx, miny, maxx, maxy = clipped.bounds
                        aminx, aminy, amaxx, amaxy = acc.bounds
                        if maxx < aminx - 0.1 or minx > amaxx + 0.1 or maxy < aminy - 0.1 or miny > amaxy + 0.1:
                            continue
                        if acc.buffer(0.04).contains(clipped):
                            is_dup = True
                            break

                    if not is_dup:
                        accepted_river_lines.append(clipped)
                        props = feat.get('properties', {})
                        r_name = props.get('name') or props.get('NAME') or props.get('Name') or props.get('name_en') or 'Unnamed River'
                        s_rank = props.get('scalerank') or props.get('SCALERANK') or 6
                        f_cla = props.get('featurecla') or 'River'
                        accepted_river_features.append({
                            'type': 'Feature',
                            'geometry': mapping(clipped.simplify(0.005, preserve_topology=True)),
                            'properties': {
                                'name': r_name,
                                'scalerank': s_rank,
                                'featurecla': f_cla
                            }
                        })
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Error loading river dataset '{rpath}': {e}")

    rivers_str = json.dumps({"type": "FeatureCollection", "features": accepted_river_features})
    print(f"[HYDROLOGY] Loaded {len(accepted_river_features)} comprehensive river centerlines across all datasets.")
    print(f"[TERRAIN] Loaded GMBA Mountains, Lines, and {len(deserts_features)} Desert Shields.")

    geojson_str = json.dumps(geojson_payload)
    custom_prov_json_str = json.dumps(custom_provinces_data)

    # Generate HTML content
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Interactive Regional Division Color Painter</title>
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
        /* Color Palette Sidebar / Toolbar */
        .controls-panel {
            position: absolute;
            top: 16px;
            right: 16px;
            width: 360px;
            background: rgba(15, 23, 42, 0.94);
            backdrop-filter: blur(12px);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 16px;
            z-index: 1000;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            gap: 14px;
        }
        .section-title {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #94a3b8;
            margin-bottom: 8px;
        }
        .palette-grid {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 8px;
        }
        .color-swatch {
            width: 100%;
            height: 32px;
            border-radius: 6px;
            cursor: pointer;
            border: 2px solid transparent;
            transition: all 0.15s ease;
        }
        .color-swatch:hover {
            transform: scale(1.08);
            box-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
        }
        .color-swatch.active {
            border-color: #ffffff;
            box-shadow: 0 0 12px rgba(255, 255, 255, 0.7);
            transform: scale(1.08);
        }
        .info-box {
            background: rgba(30, 41, 59, 0.85);
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 12px;
            min-height: 90px;
        }
        .info-detail {
            margin-top: 6px;
            font-size: 12px;
            line-height: 1.5;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 4px;
        }
        .info-label {
            color: #94a3b8;
            font-weight: 500;
        }
        .info-val {
            color: #38bdf8;
            font-weight: 600;
            text-align: right;
            max-width: 220px;
        }
        .action-btns {
            display: flex;
            gap: 8px;
        }
        .btn {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-reset {
            background: #334155;
            color: #cbd5e1;
        }
        .btn-reset:hover {
            background: #475569;
        }
        .btn-export {
            background: #0284c7;
            color: #ffffff;
        }
        .btn-export:hover {
            background: #0369a1;
        }
        /* Custom Leaflet Dark Popup */
        .leaflet-popup-content-wrapper {
            background: #0f172a;
            color: #f8fafc;
            border: 1px solid #334155;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        }
        .leaflet-popup-tip {
            background: #1e293b;
        }
        .popup-header {
            font-size: 14px;
            font-weight: 700;
            color: #38bdf8;
            border-bottom: 1px solid #334155;
            padding-bottom: 4px;
            margin-bottom: 6px;
        }
        .popup-badge {
            display: inline-block;
            padding: 2px 6px;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .division-legend {
            max-height: 150px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 4px;
            padding-right: 4px;
        }
        .legend-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 4px;
        }
        .legend-color-chip {
            width: 14px;
            height: 14px;
            border-radius: 3px;
            margin-right: 8px;
            display: inline-block;
        }
        /* Leaflet Panes Z-Index Order */
        .leaflet-pane.leaflet-unitsPane-pane { z-index: 350; }
        .leaflet-pane.leaflet-desertsPane-pane { z-index: 410; }
        .leaflet-pane.leaflet-mountainsPane-pane { z-index: 430; }
        .leaflet-pane.leaflet-mountainLinesPane-pane { z-index: 440; }
        .leaflet-pane.leaflet-riversPane-pane { z-index: 450; }
    </style>
</head>
<body>

<header>
    <div class="header-title">
        <h1>🗺️ Regional Division Color Painter</h1>
        <p>Interactive Mountains, Rivers & Deserts | Click to Inspect | Toggle OFF to Paint | PAK · IND · AFG · IRN · TJK · CHN</p>
    </div>
    <div style="display:flex; align-items:center; gap:16px;">
        <!-- Terrain & Hydro Toggles -->
        <div style="display:flex; align-items:center; gap:12px; background:rgba(15,23,42,0.85); padding:6px 14px; border-radius:8px; border:1px solid #334155;">
            <label style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:700; color:#fbbf24; cursor:pointer;" title="Click lines to inspect mountain ridges. Toggle OFF to paint district beneath.">
                <input type="checkbox" id="chk-mtn-lines" checked style="accent-color:#fbbf24; cursor:pointer;">
                <span>🏔️ Mountain Lines</span>
            </label>
            <label style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:700; color:#f59e0b; cursor:pointer;" title="Click zones to inspect GMBA mountain extents & elevations. Toggle OFF to paint district beneath.">
                <input type="checkbox" id="chk-mtn-zones" checked style="accent-color:#f59e0b; cursor:pointer;">
                <span>⛰️ Mountain Zones</span>
            </label>
            <label style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:700; color:#38bdf8; cursor:pointer;" title="Click rivers to inspect waterways. Toggle OFF to paint district beneath.">
                <input type="checkbox" id="chk-rivers" checked style="accent-color:#38bdf8; cursor:pointer;">
                <span>🌊 Rivers</span>
            </label>
            <label style="display:flex; align-items:center; gap:5px; font-size:11px; font-weight:700; color:#d97706; cursor:pointer;" title="Click deserts to inspect desert shields. Toggle OFF to paint district beneath.">
                <input type="checkbox" id="chk-deserts" checked style="accent-color:#d97706; cursor:pointer;">
                <span>🏜️ Deserts</span>
            </label>
        </div>
    </div>
</header>

<div id="container">
    <div id="map"></div>

    <div class="controls-panel">
        <div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <div class="section-title" style="margin-bottom:0;">Color Palette (30 Colors)</div>
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-size:10px; color:#94a3b8; font-weight:600;">Custom:</span>
                    <input type="color" id="custom-color-picker" value="#38bdf8" style="width:28px; height:24px; border:none; cursor:pointer; background:none; border-radius:4px;">
                </div>
            </div>
            <div class="palette-grid" id="palette-container"></div>
        </div>

        <div class="info-box">
            <div style="font-weight:600; color:#94a3b8; font-size:12px;">Active Inspector:</div>
            <div class="info-detail" id="unit-detail-panel">
                <div style="font-size:12px; color:#64748b;">Click any administrative unit, mountain range, river, or desert to inspect details.</div>
            </div>
        </div>

        <div>
            <div class="section-title">Painted Summary</div>
            <div class="division-legend" id="legend-list"></div>
        </div>

        <div class="action-btns">
            <button class="btn btn-reset" id="btn-reset">Reset All</button>
            <button class="btn btn-export" id="btn-export">Export Mapping JSON</button>
            <button class="btn" id="btn-download-png" style="background:linear-gradient(135deg, #10b981 0%, #059669 100%); color:#fff; border:none; padding:10px 14px; border-radius:6px; font-weight:700; cursor:pointer;">📷 Download PNG Map</button>
        </div>
    </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
    const geojsonData = """ + geojson_str + """;
    const customProvincesData = """ + custom_prov_json_str + """;
    const gmbaMountainsData = """ + gmba_mountains_str + """;
    const gmbaMountainLinesData = """ + gmba_lines_str + """;
    const desertsData = """ + deserts_str + """;
    const riversData = """ + rivers_str + """;

    // 30 Curated Palette Colors + Custom Color Picker
    const palette = [
        { name: "Ruby Red", hex: "#ef4444" },
        { name: "Crimson Red", hex: "#dc2626" },
        { name: "Dark Carmine", hex: "#991b1b" },
        { name: "Coral Rose", hex: "#fb7185" },
        { name: "Burnt Orange", hex: "#ea580c" },
        { name: "Saffron Orange", hex: "#f97316" },

        { name: "Amber Gold", hex: "#d97706" },
        { name: "Gold Yellow", hex: "#eab308" },
        { name: "Lemon Yellow", hex: "#facc15" },
        { name: "Lime Green", hex: "#84cc16" },
        { name: "Emerald Green", hex: "#10b981" },
        { name: "Forest Green", hex: "#15803d" },

        { name: "Jade Mint", hex: "#34d399" },
        { name: "Teal Turquoise", hex: "#14b8a6" },
        { name: "Dark Cyan", hex: "#0891b2" },
        { name: "Sky Cyan", hex: "#06b6d4" },
        { name: "Light Blue", hex: "#38bdf8" },
        { name: "Royal Blue", hex: "#3b82f6" },

        { name: "Deep Cobalt", hex: "#1d4ed8" },
        { name: "Navy Sapphire", hex: "#1e3a8a" },
        { name: "Indigo Deep", hex: "#6366f1" },
        { name: "Plum Violet", hex: "#8b5cf6" },
        { name: "Amethyst Purple", hex: "#a855f7" },
        { name: "Orchid Lavender", hex: "#c084fc" },

        { name: "Hot Pink", hex: "#f43f5e" },
        { name: "Magenta Pink", hex: "#ec4899" },
        { name: "Fuchsia Purple", hex: "#d946ef" },
        { name: "Bronze / Copper", hex: "#b45309" },
        { name: "Slate Gray", hex: "#64748b" },
        { name: "Ice White", hex: "#f8fafc" }
    ];

    let activeColor = palette[0].hex;
    const divisionColors = {}; // id -> hex color

    // Pre-populate divisionColors from feature initial_color
    geojsonData.features.forEach(f => {
        if (f.properties.initial_color && f.properties.initial_color !== '#334155') {
            divisionColors[f.properties.id] = f.properties.initial_color;
        }
    });

    // Build Palette Swatches
    const paletteContainer = document.getElementById('palette-container');
    palette.forEach((col, idx) => {
        const swatch = document.createElement('div');
        swatch.className = 'color-swatch' + (idx === 0 ? ' active' : '');
        swatch.style.backgroundColor = col.hex;
        swatch.title = col.name + ' (' + col.hex + ')';
        swatch.addEventListener('click', () => {
            document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
            swatch.classList.add('active');
            activeColor = col.hex;
            document.getElementById('custom-color-picker').value = col.hex;
        });
        paletteContainer.appendChild(swatch);
    });

    // Wire Custom Color Picker
    const customPicker = document.getElementById('custom-color-picker');
    customPicker.addEventListener('input', (e) => {
        activeColor = e.target.value;
        document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('active'));
    });

    // Initialize Leaflet Map
    const map = L.map('map', {
        zoomControl: false
    }).setView([32.5, 74.5], 6);

    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?key=cb1_2l84_1_a4a33a1ad51e9fc32f33f972', {
        attribution: '&copy; OpenStreetMap &copy; CARTO',
        maxZoom: 18
    }).addTo(map);

    // Dedicated Panes for Layer Stacking & Visibility
    map.createPane('unitsPane');
    map.getPane('unitsPane').style.zIndex = 350;

    map.createPane('desertsPane');
    map.getPane('desertsPane').style.zIndex = 410;

    map.createPane('mountainsPane');
    map.getPane('mountainsPane').style.zIndex = 430;

    map.createPane('mountainLinesPane');
    map.getPane('mountainLinesPane').style.zIndex = 440;

    map.createPane('riversPane');
    map.getPane('riversPane').style.zIndex = 450;

    let mountainLinesLayer, mountainsLayer, desertsLayer, riversLayer;

    // District Styling & Interactivity
    function getStyle(feature) {
        const id = feature.properties.id;
        const assignedColor = divisionColors[id] || '#334155';
        const hasColor = !!divisionColors[id];
        return {
            fillColor: assignedColor,
            fillOpacity: hasColor ? 0.85 : 0.45,
            color: '#ffffff',
            weight: 1.2,
            opacity: 0.80
        };
    }

    let geojsonLayer;

    function updateDetailPanel(props) {
        const panelEl = document.getElementById('unit-detail-panel');
        panelEl.innerHTML = `
            <div class="info-row">
                <span class="info-label">Name:</span>
                <span class="info-val">${props.name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">District / Region:</span>
                <span class="info-val">${props.district}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Province / State:</span>
                <span class="info-val" style="color:#f1f5f9;">${props.province}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Country:</span>
                <span class="info-val" style="color:#a855f7;">${props.country}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Data Source:</span>
                <span class="info-val" style="color:#eab308; font-size:10px;">${props.source}</span>
            </div>
        `;
    }

    function highlightFeature(e) {
        const layer = e.target;
        const props = layer.feature.properties;
        updateDetailPanel(props);

        layer.setStyle({
            weight: 2.5,
            color: '#38bdf8',
            fillOpacity: 0.90
        });
        layer.bringToFront();
    }

    function resetHighlight(e) {
        const layer = e.target;
        geojsonLayer.resetStyle(layer);
    }

    function onFeatureClick(e) {
        const layer = e.target;
        const props = layer.feature.properties;
        const id = props.id;

        if (divisionColors[id] === activeColor) {
            delete divisionColors[id];
        } else {
            divisionColors[id] = activeColor;
        }

        geojsonLayer.resetStyle(layer);
        updateLegend();
        updateDetailPanel(props);

        // Popup showing details
        L.popup()
            .setLatLng(e.latlng)
            .setContent(`
                <div class="popup-badge">${props.country} Unit</div>
                <div class="popup-header">${props.name}</div>
                <div style="font-size:12px; color:#cbd5e1; margin-bottom:4px;">
                    📌 <strong>State / Region:</strong> ${props.province} (${props.district})
                </div>
                <div style="font-size:10px; color:#94a3b8;">
                    📂 <strong>Source:</strong> ${props.source}
                </div>
                <div style="margin-top:8px; font-size:11px; color:${divisionColors[id] || '#94a3b8'}; font-weight:700;">
                    ${divisionColors[id] ? 'Painted: ' + divisionColors[id] : 'Color Cleared'}
                </div>
            `)
            .openOn(map);
    }

    function onEachFeature(feature, layer) {
        layer.on({
            mouseover: highlightFeature,
            mouseout: resetHighlight,
            click: onFeatureClick
        });
    }

    geojsonLayer = L.geoJSON(geojsonData, {
        style: getStyle,
        pane: 'unitsPane',
        onEachFeature: onEachFeature
    }).addTo(map);

    // =========================================================================
    // 1. DESERTS LAYER (Interactive Inspection + StopPropagation)
    // =========================================================================
    function desertStyle(feature) {
        return {
            fillColor: '#d97706',
            fillOpacity: 0.25,
            color: '#b45309',
            weight: 1.8,
            dashArray: '4, 4',
            opacity: 0.85,
            pane: 'desertsPane'
        };
    }

    function onDesertClick(e) {
        L.DomEvent.stopPropagation(e);
        const props = e.target.feature.properties;
        const panelEl = document.getElementById('unit-detail-panel');
        panelEl.innerHTML = `
            <div class="info-row">
                <span class="info-label">Desert Shield:</span>
                <span class="info-val" style="color:#d97706; font-weight:700;">🏜️ ${props.name}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Terrain Type:</span>
                <span class="info-val">Arid Sand / Salt Flat Wasteland</span>
            </div>
            <div class="info-row">
                <span class="info-label">Strategic Role:</span>
                <span class="info-val" style="color:#f59e0b;">Impassable Natural Choke & Logistics Buffer</span>
            </div>
        `;
        L.popup()
            .setLatLng(e.latlng)
            .setContent(`
                <div class="popup-badge" style="background:rgba(217,119,6,0.2); color:#f59e0b;">🏜️ Desert Barrier</div>
                <div class="popup-header" style="color:#f59e0b;">${props.name} Desert</div>
                <div style="font-size:11px; color:#cbd5e1; margin-top:4px;">
                    🏜️ <strong>Terrain:</strong> Impassable Arid Wasteland<br>
                    🛡️ <strong>Tactics:</strong> Defensive Desert Buffer / Chokepoint<br>
                    <span style="font-size:10px; color:#fbbf24; font-style:italic;">(Desert toggle ON: Click inspects desert without painting. Toggle OFF to paint district underneath.)</span>
                </div>
            `)
            .openOn(map);
    }

    desertsLayer = L.geoJSON(desertsData, {
        style: desertStyle,
        pane: 'desertsPane',
        interactive: true,
        onEachFeature: function(feature, layer) {
            layer.on({
                click: onDesertClick,
                mouseover: function(e) {
                    layer.setStyle({ fillOpacity: 0.40, weight: 2.5 });
                },
                mouseout: function(e) {
                    desertsLayer.resetStyle(layer);
                }
            });
        }
    }).addTo(map);

    // =========================================================================
    // 2. MOUNTAINS (GMBA ZONES & LINES) (Interactive Inspection + StopPropagation)
    // =========================================================================
    function onMountainClick(e) {
        L.DomEvent.stopPropagation(e);
        const props = e.target.feature.properties;
        const panelEl = document.getElementById('unit-detail-panel');
        const mName = props.name || props.gmba_name || 'Mountain Range';
        const elevSpan = (props.elev_low != null && props.elev_high != null) ? `${props.elev_low} m – ${props.elev_high} m` : 'Alpine Heights';
        const zoneStr = props.zone || 'Mountain Citadel';
        const countriesStr = props.countries || 'Regional';

        panelEl.innerHTML = `
            <div class="info-row">
                <span class="info-label">Mountain Range:</span>
                <span class="info-val" style="color:#fbbf24; font-weight:700;">🏔️ ${mName}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Elevation Span:</span>
                <span class="info-val" style="color:#38bdf8;">${elevSpan}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Defense Citadel:</span>
                <span class="info-val" style="color:#eab308; font-size:11px;">${zoneStr}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Countries:</span>
                <span class="info-val" style="color:#c084fc; font-size:11px;">${countriesStr}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Inventory Level:</span>
                <span class="info-val" style="color:#94a3b8; font-size:10px;">GMBA Level ${props.level || '3'} (${props.source || 'GMBA v2.0'})</span>
            </div>
        `;

        L.popup()
            .setLatLng(e.latlng)
            .setContent(`
                <div class="popup-badge" style="background:rgba(245,158,11,0.25); color:#fbbf24;">🏔️ GMBA Mountain Range</div>
                <div class="popup-header" style="color:#fbbf24;">${mName}</div>
                <div style="font-size:11px; color:#cbd5e1; margin-top:4px;">
                    ⛰️ <strong>Elevation:</strong> ${elevSpan}<br>
                    🛡️ <strong>Citadel Zone:</strong> ${zoneStr}<br>
                    🌍 <strong>Countries:</strong> ${countriesStr}<br>
                    <span style="font-size:10px; color:#fbbf24; font-style:italic;">(Mountain layer active: Protected from painting. Toggle OFF to paint district underneath.)</span>
                </div>
            `)
            .openOn(map);
    }

    function mountainZoneStyle(feature) {
        const c = feature.properties.color || '#d97706';
        return {
            fillColor: c,
            fillOpacity: 0.28,
            color: c,
            weight: 1.2,
            dashArray: '4, 2',
            opacity: 0.70,
            pane: 'mountainsPane'
        };
    }

    mountainsLayer = L.geoJSON(gmbaMountainsData, {
        style: mountainZoneStyle,
        pane: 'mountainsPane',
        interactive: true,
        onEachFeature: function(feature, layer) {
            layer.on({
                click: onMountainClick,
                mouseover: function(e) {
                    layer.setStyle({ fillOpacity: 0.50, weight: 2.2 });
                },
                mouseout: function(e) {
                    mountainsLayer.resetStyle(layer);
                }
            });
        }
    }).addTo(map);

    function mountainLineStyle(feature) {
        const c = feature.properties.color || '#fbbf24';
        return {
            color: c,
            weight: 2.8,
            dashArray: '8, 3',
            opacity: 0.95,
            pane: 'mountainLinesPane'
        };
    }

    mountainLinesLayer = L.geoJSON(gmbaMountainLinesData, {
        style: mountainLineStyle,
        pane: 'mountainLinesPane',
        interactive: true,
        onEachFeature: function(feature, layer) {
            layer.on({
                click: onMountainClick,
                mouseover: function(e) {
                    layer.setStyle({ weight: 4.5, opacity: 1.0 });
                },
                mouseout: function(e) {
                    mountainLinesLayer.resetStyle(layer);
                }
            });
        }
    }).addTo(map);

    // =========================================================================
    // 3. RIVERS LAYER (Interactive Centerlines + StopPropagation)
    // =========================================================================
    function riverStyle(feature) {
        const sr = feature.properties.scalerank || 6;
        const weight = sr <= 2 ? 3.2 : (sr <= 4 ? 2.3 : (sr <= 6 ? 1.6 : 1.1));
        return {
            color: '#38bdf8',
            weight: weight,
            opacity: 0.90,
            pane: 'riversPane'
        };
    }

    function onRiverClick(e) {
        L.DomEvent.stopPropagation(e);
        const props = e.target.feature.properties;
        const panelEl = document.getElementById('unit-detail-panel');
        const rName = props.name || 'Major River / Waterway';
        const rank = props.scalerank != null ? `Scale Rank ${props.scalerank}` : 'Navigable River';

        panelEl.innerHTML = `
            <div class="info-row">
                <span class="info-label">River / Waterway:</span>
                <span class="info-val" style="color:#38bdf8; font-weight:700;">🌊 ${rName}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Hierarchy Rank:</span>
                <span class="info-val">${rank}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Classification:</span>
                <span class="info-val">${props.featurecla || 'River Waterway'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Defensive Role:</span>
                <span class="info-val" style="color:#10b981;">Natural Water Trench / River Defense Line</span>
            </div>
        `;

        L.popup()
            .setLatLng(e.latlng)
            .setContent(`
                <div class="popup-badge" style="background:rgba(56,189,248,0.25); color:#38bdf8;">🌊 River Barrier</div>
                <div class="popup-header" style="color:#38bdf8;">${rName}</div>
                <div style="font-size:11px; color:#cbd5e1; margin-top:4px;">
                    🌊 <strong>Classification:</strong> ${props.featurecla || 'River'}<br>
                    📐 <strong>Rank:</strong> ${rank}<br>
                    🛡️ <strong>Tactics:</strong> Natural Water Moat & Strategic Barrier<br>
                    <span style="font-size:10px; color:#38bdf8; font-style:italic;">(River toggle ON: Click inspects waterway. Toggle OFF to paint district underneath.)</span>
                </div>
            `)
            .openOn(map);
    }

    riversLayer = L.geoJSON(riversData, {
        style: riverStyle,
        pane: 'riversPane',
        interactive: true,
        onEachFeature: function(feature, layer) {
            layer.on({
                click: onRiverClick,
                mouseover: function(e) {
                    layer.setStyle({ color: '#7dd3fc', weight: 4.5, opacity: 1.0 });
                },
                mouseout: function(e) {
                    riversLayer.resetStyle(layer);
                }
            });
        }
    }).addTo(map);

    // =========================================================================
    // LAYER CHECKBOX TOGGLES
    // =========================================================================
    document.getElementById('chk-mtn-lines').addEventListener('change', (e) => {
        if (e.target.checked) {
            map.addLayer(mountainLinesLayer);
        } else {
            map.removeLayer(mountainLinesLayer);
        }
    });

    document.getElementById('chk-mtn-zones').addEventListener('change', (e) => {
        if (e.target.checked) {
            map.addLayer(mountainsLayer);
        } else {
            map.removeLayer(mountainsLayer);
        }
    });

    document.getElementById('chk-rivers').addEventListener('change', (e) => {
        if (e.target.checked) {
            map.addLayer(riversLayer);
        } else {
            map.removeLayer(riversLayer);
        }
    });

    document.getElementById('chk-deserts').addEventListener('change', (e) => {
        if (e.target.checked) {
            map.addLayer(desertsLayer);
        } else {
            map.removeLayer(desertsLayer);
        }
    });

    // Auto-fit map bounds
    if (geojsonLayer.getBounds().isValid()) {
        map.fitBounds(geojsonLayer.getBounds(), { padding: [30, 30] });
    }

    // Update Legend Summary
    function updateLegend() {
        const legendList = document.getElementById('legend-list');
        legendList.innerHTML = '';

        const counts = {};
        palette.forEach(p => counts[p.hex] = 0);

        Object.values(divisionColors).forEach(c => {
            if (counts[c] !== undefined) counts[c]++;
        });

        palette.forEach(p => {
            const cnt = counts[p.hex];
            if (cnt > 0) {
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.innerHTML = `
                    <div style="display:flex; align-items:center;">
                        <span class="legend-color-chip" style="background-color:${p.hex};"></span>
                        <span>${p.name}</span>
                    </div>
                    <span style="font-weight:700; color:#38bdf8;">${cnt}</span>
                `;
                legendList.appendChild(item);
            }
        });
    }
    updateLegend();

    // Reset All Button
    document.getElementById('btn-reset').addEventListener('click', () => {
        if (confirm('Are you sure you want to clear all painted divisions?')) {
            Object.keys(divisionColors).forEach(id => delete divisionColors[id]);
            geojsonLayer.resetStyle();
            updateLegend();
            document.getElementById('unit-detail-panel').innerHTML = '<div style="font-size:12px; color:#64748b;">Colors reset. Click a unit to paint.</div>';
        }
    });

    // Export Mapping JSON
    document.getElementById('btn-export').addEventListener('click', () => {
        const exportData = [];
        geojsonData.features.forEach(f => {
            const id = f.properties.id;
            exportData.push({
                id: id,
                name: f.properties.name,
                district: f.properties.district,
                province: f.properties.province,
                country: f.properties.country,
                color: divisionColors[id] || '#334155'
            });
        });

        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(exportData, null, 2));
        const downloadAnchor = document.createElement('a');
        downloadAnchor.setAttribute("href", dataStr);
        downloadAnchor.setAttribute("download", "custom_regional_painted_divisions.json");
        document.body.appendChild(downloadAnchor);
        downloadAnchor.click();
        downloadAnchor.remove();
    });

    // Download Clean PNG Map with Multi-Column Legend
    document.getElementById('btn-download-png').addEventListener('click', () => {
        const paintedFeatures = [];
        const provinceSummary = {};

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

        geojsonData.features.forEach(f => {
            const id = f.properties.id;
            const col = divisionColors[id];
            if (col && col !== '#334155') {
                paintedFeatures.push({
                    geometry: f.geometry,
                    color: col,
                    name: f.properties.custom_province || f.properties.province || f.properties.name,
                    capital: f.properties.capital_name || ''
                });

                if (!provinceSummary[col]) {
                    provinceSummary[col] = {
                        color: col,
                        name: f.properties.custom_province || f.properties.province || f.properties.name || 'Region',
                        capital: f.properties.capital_name || 'N/A',
                        count: 0
                    };
                }
                provinceSummary[col].count++;

                if (f.geometry && f.geometry.coordinates) {
                    checkCoords(f.geometry.coordinates);
                }
            }
        });

        const items = Object.values(provinceSummary);
        const totalItems = items.length;

        if (totalItems === 0) {
            alert('No painted regions found to export!');
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

        // Draw Map Shapes
        paintedFeatures.forEach(feat => {
            ctx.fillStyle = feat.color;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
            ctx.lineWidth = 1.4;

            const g = feat.geometry;
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
        ctx.fillText('🗺️ REGIONAL MAP LEGEND', mapWidth + 30, 52);

        ctx.fillStyle = '#94a3b8';
        ctx.font = '15px Inter, sans-serif';
        ctx.fillText(`${totalItems} Custom Regions & Capitals`, mapWidth + 30, 80);

        ctx.strokeStyle = '#334155';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mapWidth + 30, 98);
        ctx.lineTo(canvasWidth - 30, 98);
        ctx.stroke();

        // Render Items in Multi-Column Grid
        const startY = 135;
        items.forEach((item, idx) => {
            const colIdx = Math.floor(idx / rowsCount);
            const rowIdx = idx % rowsCount;

            const xPos = mapWidth + 30 + colIdx * colWidth;
            const yPos = startY + rowIdx * rowHeight;

            if (yPos > canvasHeight - 30) return;

            // Swatch chip
            ctx.fillStyle = item.color;
            ctx.fillRect(xPos, yPos - 16, 20, 20);
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.2;
            ctx.strokeRect(xPos, yPos - 16, 20, 20);

            // Region / Province Name
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 15px Inter, sans-serif';
            const nameText = item.name.length > 22 ? item.name.substring(0, 20) + '..' : item.name;
            ctx.fillText(nameText, xPos + 28, yPos - 2);

            // Capital Name
            ctx.fillStyle = '#f59e0b';
            ctx.font = '12px Inter, sans-serif';
            const capText = item.capital && item.capital !== 'N/A' ? `⭐ ${item.capital}` : `${item.count} units`;
            const capTrunc = capText.length > 26 ? capText.substring(0, 24) + '..' : capText;
            ctx.fillText(capTrunc, xPos + 28, yPos + 14);
        });

        // Trigger PNG Download
        const imgURI = canvas.toDataURL('image/png');
        const dlAnchor = document.createElement('a');
        dlAnchor.setAttribute('href', imgURI);
        dlAnchor.setAttribute('download', 'regional_custom_provinces_map.png');
        document.body.appendChild(dlAnchor);
        dlAnchor.click();
        dlAnchor.remove();
    });
</script>

</body>
</html>
"""

    out_file = r'c:\Users\ADMIN\Desktop\Geopolitico\scratch\regional_division_painter.html'
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    frontend_out = r'c:\Users\ADMIN\Desktop\Geopolitico\frontend\regional_division_painter.html'
    with open(frontend_out, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Successfully generated HTML map view at:\n  1. {out_file}\n  2. {frontend_out}")

if __name__ == '__main__':
    main()
