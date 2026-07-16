let map;
let beforeLayer = null;
let realisticLayer = null;
let optimisticLayer = null;
let currentMode = "optimistic"; // "before", "realistic", or "optimistic"
let boundaryOverlayLayer = null;
let markerOverlayLayer = null;

function initMap() {
    // Center map roughly on Eurasia/Mediterranean region initially
    map = L.map("map", {
        zoomControl: false,
        attributionControl: true
    }).setView([35.0, 30.0], 3);

    // Add standard Zoom control to the bottom right
    L.control.zoom({
        position: 'bottomright'
    }).addTo(map);

    // CartoDB Dark Matter tiles
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);
}

function renderScenarioMaps(
    geojsonBefore, geojsonRealistic, geojsonOptimistic,
    territoriesBefore, territoriesRealistic, territoriesOptimistic
) {
    // Clear old layers
    if (beforeLayer) map.removeLayer(beforeLayer);
    if (realisticLayer) map.removeLayer(realisticLayer);
    if (optimisticLayer) map.removeLayer(optimisticLayer);

    const styleFeature = (feature) => {
        const status = (feature.properties.status || 'direct_control').toLowerCase();
        const isVassal = status === 'vassal';
        const isTributary = status === 'tributary';
        const isDependency = isVassal || isTributary;
        
        const finalColor = getTerritoryColor(feature.properties.name, feature.properties.color || '#d4a853');

        return {
            fillColor: finalColor,
            weight: isDependency ? 1 : 1.5,
            opacity: 0.8,
            color: isDependency ? 'rgba(255, 255, 255, 0.6)' : 'rgba(255, 255, 255, 0.4)',
            fillOpacity: isTributary ? 0.2 : (isVassal ? 0.3 : 0.55),
            dashArray: isTributary ? '2, 6' : (isVassal ? '4, 4' : null),
            className: 'interactive-polygon'
        };
    };

    const onEachFeature = (feature, layer) => {
        // Highlight on hover
        layer.on({
            mouseover: (e) => {
                const l = e.target;
                l.setStyle({
                    fillOpacity: 0.8,
                    weight: 2.5,
                    color: 'rgba(255, 255, 255, 0.8)'
                });
                l.bringToFront();
            },
            mouseout: (e) => {
                layer.setStyle(styleFeature(feature));
            }
        });

        // Detailed popup info
        const props = feature.properties;
        const capitalStr = props.capital ? `<p><strong>Capital:</strong> ${props.capital}</p>` : '';
        const popStr = props.population ? `<p><strong>Population Est:</strong> ${props.population}</p>` : '';
        
        const popupContent = `
            <div class="map-popup">
                <h3>${props.name}</h3>
                ${capitalStr}
                ${popStr}
                <hr style="margin: 8px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.15);" />
                <p class="popup-desc">${props.description || 'No description available.'}</p>
            </div>
        `;
        layer.bindPopup(popupContent, {
            className: 'custom-map-popup'
        });
    };

    // Create Leaflet geoJSON layers
    beforeLayer = L.geoJSON(geojsonBefore, {
        style: styleFeature,
        onEachFeature: onEachFeature
    });

    realisticLayer = L.geoJSON(geojsonRealistic, {
        style: styleFeature,
        onEachFeature: onEachFeature
    });

    optimisticLayer = L.geoJSON(geojsonOptimistic, {
        style: styleFeature,
        onEachFeature: onEachFeature
    });

    // Update active map layers and legend
    updateMapLayers();
    syncActiveLegendAndSummary();

    // Auto fit map boundary to focus area
    const activeLayer = getActiveLayer();
    if (activeLayer && activeLayer.getBounds().isValid()) {
        map.fitBounds(activeLayer.getBounds(), { padding: [50, 50] });
    }
}

function getActiveLayer() {
    if (currentMode === "before") return beforeLayer;
    if (currentMode === "realistic") return realisticLayer;
    if (currentMode === "rivers") return realisticLayer;
    return optimisticLayer;
}

function updateMapLayers() {
    if (!map) return;
    
    if (beforeLayer) map.removeLayer(beforeLayer);
    if (realisticLayer) map.removeLayer(realisticLayer);
    if (optimisticLayer) map.removeLayer(optimisticLayer);
    if (boundaryOverlayLayer) {
        map.removeLayer(boundaryOverlayLayer);
        boundaryOverlayLayer = null;
    }
    if (markerOverlayLayer) {
        map.removeLayer(markerOverlayLayer);
        markerOverlayLayer = null;
    }

    const activeLayer = getActiveLayer();
    if (activeLayer) {
        activeLayer.addTo(map);
    }

    // Only show natural boundary overlays when the user is in "rivers" (Natural Borders) view mode
    if (currentMode === "rivers") {
        const data = window.activeScenarioData;
        
        // 1. Draw River/Land Boundary Overlay
        if (data && data.osm_boundary_geometry && data.osm_boundary_geometry.length > 0) {
            const lines = [];
            for (const path of data.osm_boundary_geometry) {
                const latlngs = path.map(pt => [pt[1], pt[0]]);
                const line = L.polyline(latlngs, {
                    color: '#00d2ff', // glowing cyan
                    weight: 4,       // thin, clean, permanent line
                    opacity: 0.95,   // permanently visible
                    interactive: true
                });
                lines.push(line);
            }
            boundaryOverlayLayer = L.featureGroup(lines);
            boundaryOverlayLayer.addTo(map);
            boundaryOverlayLayer.bringToFront();
            boundaryOverlayLayer.bindPopup(`<strong>🌊 ${data.osm_boundary_name || 'Natural Boundary'}</strong><br/>Geographic partition boundary line retrieved from offline GIS database.`);
        }
    }
}

function getTerritoryColor(name, defaultColor) {
    if (!name) return defaultColor;
    const n = name.toLowerCase();
    if (n.includes('india')) return '#fbbf24'; // saffron
    if (n.includes('pakistan')) return '#047857'; // emerald green
    if (n.includes('china')) return '#ef4444'; // red
    return defaultColor;
}

function updateLegend(territories) {
    const legendContainer = document.getElementById("legend-items");
    const legendPanel = document.getElementById("map-legend");
    
    legendContainer.innerHTML = "";
    
    if (!territories || territories.length === 0) {
        legendPanel.style.display = "none";
        return;
    }

    legendPanel.style.display = "block";
    territories.forEach(t => {
        const item = document.createElement("div");
        item.className = "legend-item";
        const finalColor = getTerritoryColor(t.name, t.color);
        item.innerHTML = `
            <div class="legend-color" style="background-color: ${finalColor}"></div>
            <span>${t.name}</span>
        `;
        legendContainer.appendChild(item);
    });
}

function syncActiveLegendAndSummary() {
    if (!window.activeScenarioData) return;

    const data = window.activeScenarioData;
    let territories = [];
    let summaryText = "";

    if (currentMode === "before") {
        territories = data.territories_before;
        summaryText = "Historical boundary in base year.";
    } else if (currentMode === "realistic") {
        territories = data.territories_after_realistic;
        summaryText = data.realistic_scenario_summary || "Realistic alternate boundary.";
    } else {
        territories = data.territories_after_optimistic;
        summaryText = data.optimistic_scenario_summary || "Optimistic alternate boundary (maximum extent).";
    }

    updateLegend(territories);

    // Update scenario summary card
    const summaryCard = document.getElementById("scenario-summary-card");
    const summaryTextEl = document.getElementById("scenario-summary-text");
    if (summaryCard && summaryTextEl) {
        summaryTextEl.innerText = summaryText;
        summaryCard.style.display = "block";
    }
}

function setMapMode(mode) {
    currentMode = mode;
    updateMapLayers();
    syncActiveLegendAndSummary();
    
    // Update narrative text to match the active map mode
    const alternateEl = document.getElementById("result-alternate");
    if (alternateEl && window.activeScenarioData) {
        const data = window.activeScenarioData;
        const alternateText = (mode === "realistic" || mode === "rivers") ? 
            (data.alternate_outcome_realistic || data.alternate_outcome || "") : 
            (data.alternate_outcome_optimistic || data.alternate_outcome || "");
        alternateEl.innerText = alternateText;
    }
}

// ─── Sandbox Mode Map Rendering ─────────────────────────────────────────────

let sandboxLayer = null;

function renderSandboxMap(geojsonData, territories) {
    // Clear existing sandbox and classic layers
    if (sandboxLayer) map.removeLayer(sandboxLayer);
    if (beforeLayer) map.removeLayer(beforeLayer);
    if (realisticLayer) map.removeLayer(realisticLayer);
    if (optimisticLayer) map.removeLayer(optimisticLayer);

    const styleFeature = (feature) => {
        const status = (feature.properties.status || 'direct_control').toLowerCase();
        const isVassal = status === 'vassal';
        const isTributary = status === 'tributary';
        const isDependency = isVassal || isTributary;

        return {
            fillColor: feature.properties.color || '#d4a853',
            weight: isDependency ? 1 : 1.5,
            opacity: 0.8,
            color: isDependency ? 'rgba(255, 255, 255, 0.6)' : 'rgba(255, 255, 255, 0.4)',
            fillOpacity: isTributary ? 0.2 : (isVassal ? 0.3 : 0.55),
            dashArray: isTributary ? '2, 6' : (isVassal ? '4, 4' : null),
            className: 'interactive-polygon'
        };
    };

    const onEachFeature = (feature, layer) => {
        layer.on({
            mouseover: (e) => {
                e.target.setStyle({ fillOpacity: 0.8, weight: 2.5, color: 'rgba(255, 255, 255, 0.8)' });
                e.target.bringToFront();
            },
            mouseout: (e) => { layer.setStyle(styleFeature(feature)); }
        });

        const props = feature.properties;
        const statusBadge = props.status ? `<span class="status-badge status-${props.status}">${props.status.replace('_', ' ')}</span>` : '';
        const popupContent = `
            <div class="map-popup">
                <h3>${props.name} ${statusBadge}</h3>
                ${props.capital ? `<p><strong>Capital:</strong> ${props.capital}</p>` : ''}
                <hr style="margin: 8px 0; border: 0; border-top: 1px solid rgba(255,255,255,0.15);" />
                <p class="popup-desc">${props.description || 'No description available.'}</p>
            </div>
        `;
        layer.bindPopup(popupContent, { className: 'custom-map-popup' });
    };

    sandboxLayer = L.geoJSON(geojsonData, {
        style: styleFeature,
        onEachFeature: onEachFeature
    });
    sandboxLayer.addTo(map);

    // Update legend
    updateLegend(territories);

    // Fit bounds
    if (sandboxLayer.getBounds().isValid()) {
        map.fitBounds(sandboxLayer.getBounds(), { padding: [50, 50] });
    }
}

