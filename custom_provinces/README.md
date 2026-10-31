# Custom Provinces & Regional Division Tools

This folder contains the visual interactive tools, configurations, and data artifacts for creating, previewing, and painting custom regional provinces and administrative divisions.

## Files & Datasets

- **`build_custom_provinces.py`**: Core builder script that parses GADM county/district polygons, dissolves territorial units into custom named provinces, calculates solid exterior hulls, and pinpoints assigned capitals.
- **`build_regional_map.py`**: Regional map builder that compiles sub-national features across Pakistan, India, Afghanistan, Iran, Tajikistan, China, Nepal, Myanmar, Bangladesh, and Bhutan into painted regional division layers.
- **`custom_province_painter.html`**: Interactive web tool for painting and previewing custom regional provinces with river basin layers (including the Sutlej River).
- **`regional_division_painter.html`**: Regional boundary painter allowing district selection and export of custom divisions.
- **`regional_governance_viewer.html`**: Explorer for regional governance hierarchy and territorial groupings.
- **`custom_provinces_preview.html`**: Leaflet preview tool for custom provinces and pinpointed capitals.
- **`habsburg_relationship_explorer.html`**: Visualizer for historical composite monarchies and vassal territories.
- **`custom_named_provinces_with_capitals.json`**: Compiled GeoJSON feature dataset of custom named provinces with assigned capitals.
- **`custom_macro_regions_config.json`**: Macro-regional configuration schema.
- **`custom_regional_painted_divisions.json`**: Serialized output of custom painted regional divisions.

