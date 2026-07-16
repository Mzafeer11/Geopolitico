// Main application controller
let currentSessionId = null;

document.addEventListener("DOMContentLoaded", () => {
    // 1. Initialize core layers
    initMap();
    initTabs();
    
    // 2. Bind UI listeners
    bindEvents();
});

function bindEvents() {
    const simulateBtn = document.getElementById("simulate-btn");
    const backBtn = document.getElementById("back-btn");
    const presetCards = document.querySelectorAll(".preset-card");
    const modeBeforeBtn = document.getElementById("mode-before");
    const modeRealisticBtn = document.getElementById("mode-realistic");
    const modeOptimisticBtn = document.getElementById("mode-optimistic");
    const modeRiversBtn = document.getElementById("mode-rivers");
    const submitValidationBtn = document.getElementById("submit-validation-btn");

    if (submitValidationBtn) {
        submitValidationBtn.addEventListener("click", () => {
            const selections = {};
            const cards = document.querySelectorAll(".validation-anomaly-card");
            let missing = false;
            
            cards.forEach(card => {
                const anomalyId = card.dataset.id;
                const checkedRadio = card.querySelector(`input[name="opt-${anomalyId}"]:checked`);
                if (checkedRadio) {
                    selections[anomalyId] = checkedRadio.value;
                } else {
                    missing = true;
                }
            });
            
            if (missing) {
                showToast("Please resolve all geopolitical anomalies before proceeding.", "error");
                return;
            }
            
            showPanel("loading-section");
            document.getElementById("active-agent-display").innerText = "Applying verification border decisions...";
            document.getElementById("progress-details-display").innerText = "Regenerating final maps and boundaries...";
            
            fetch("/api/simulate/verify", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    selections: selections
                })
            })
            .then(res => {
                if (!res.ok) throw new Error("Failed to verify boundaries");
                return res.json();
            })
            .then(data => {
                showToast("Verifying border changes...", "success");
                pollJobStatus(data.job_id);
            })
            .catch(err => {
                console.error(err);
                showToast(err.message, "error");
                showPanel("validation-choice-section");
            });
        });
    }

    simulateBtn.addEventListener("click", () => {
        const scenario = document.getElementById("scenario-input").value.stripOrEmpty();
        
        if (!scenario) {
            showToast("Please enter a 'what-if' scenario description.", "error");
            return;
        }
        
        startSimulation(scenario);
    });

    backBtn.addEventListener("click", () => {
        showPanel("input-section");
    });

    // Preset clicks auto fill and start
    presetCards.forEach(card => {
        card.addEventListener("click", () => {
            const scenario = card.getAttribute("data-scenario");
            document.getElementById("scenario-input").value = scenario;
            startSimulation(scenario);
        });
    });

    // Map toggles
    modeBeforeBtn.addEventListener("click", () => {
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => btn.classList.remove("active"));
        modeBeforeBtn.classList.add("active");
        setMapMode("before");
    });

    modeRealisticBtn.addEventListener("click", () => {
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => btn.classList.remove("active"));
        modeRealisticBtn.classList.add("active");
        setMapMode("realistic");
    });

    modeOptimisticBtn.addEventListener("click", () => {
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => btn.classList.remove("active"));
        modeOptimisticBtn.classList.add("active");
        setMapMode("optimistic");
    });

    modeRiversBtn.addEventListener("click", () => {
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => btn.classList.remove("active"));
        modeRiversBtn.classList.add("active");
        setMapMode("rivers");
    });
}

// Strip whitespaces helper
String.prototype.stripOrEmpty = function() {
    return this ? this.replace(/^\s+|\s+$/g, '') : '';
};

let pollInterval = null;

function startSimulation(scenario) {
    showPanel("loading-section");
    document.getElementById("active-agent-display").innerText = "Initializing Geopolitical Simulator...";
    document.getElementById("progress-details-display").innerText = "Analyzing counterfactual context...";
    
    // Clear old poll if any running
    if (pollInterval) clearInterval(pollInterval);
    
    // Call FastAPI API
    fetch("/api/simulate", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ scenario, token: "" })
    })

    .then(res => {
        if (!res.ok) {
            return res.json().then(err => { throw new Error(err.detail || "Server error starting simulation"); });
        }
        return res.json();
    })
    .then(data => {
        const jobId = data.job_id;
        showToast("Simulation job queued successfully.", "success");
        
        // Start polling status
        pollJobStatus(jobId);
    })
    .catch(err => {
        console.error(err);
        showToast(err.message, "error");
        showPanel("input-section");
    });
}

function pollJobStatus(jobId) {
    pollInterval = setInterval(() => {
        fetch(`/api/status/${jobId}`)
        .then(res => {
            if (!res.ok) throw new Error("Failed to check job progress status");
            return res.json();
        })
        .then(job => {
            // Update loading info
            document.getElementById("progress-details-display").innerText = job.progress || "Processing...";
            
            // Deduce active stage based on progress message
            if (job.progress.toLowerCase().includes("analyzing") || job.progress.toLowerCase().includes("context") || job.progress.toLowerCase().includes("planner")) {
                document.getElementById("active-agent-display").innerText = "🏛️ Planner Node: active";
            } else if (job.progress.toLowerCase().includes("locating") || job.progress.toLowerCase().includes("provinces") || job.progress.toLowerCase().includes("spatial")) {
                document.getElementById("active-agent-display").innerText = "🗺️ Spatial Processor: active";
            } else if (job.progress.toLowerCase().includes("applying") || job.progress.toLowerCase().includes("regenerating") || job.progress.toLowerCase().includes("demographic") || job.progress.toLowerCase().includes("conquest") || job.progress.toLowerCase().includes("executing")) {
                document.getElementById("active-agent-display").innerText = "🌍 Simulation Nodes: active";
            } else if (job.progress.toLowerCase().includes("compiling") || job.progress.toLowerCase().includes("map")) {
                document.getElementById("active-agent-display").innerText = "🎨 Cartographic Compiler: active";
            }
            
            if (job.status === "completed") {
                clearInterval(pollInterval);
                currentSessionId = job.session_id; // Store globally
                clearValidationHighlight();
                displayResults(job.result);
            } else if (job.status === "awaiting_verification") {
                clearInterval(pollInterval);
                currentSessionId = job.session_id; // Store globally
                displayResults(job.result);
                showPanel("validation-choice-section");
                displayValidationQuestions(job.questions);
            } else if (job.status === "failed") {
                clearInterval(pollInterval);
                clearValidationHighlight();
                showToast(`Simulation failed: ${job.error}`, "error");
                showPanel("input-section");
            }
        })
        .catch(err => {
            console.error(err);
            clearInterval(pollInterval);
            clearValidationHighlight();
            showToast("Error polling job status.", "error");
            showPanel("input-section");
        });
    }, 2000);
}

let validationHighlightLayer = null;

function showValidationHighlight(geojson, scenarioType) {
    if (validationHighlightLayer && map) {
        map.removeLayer(validationHighlightLayer);
        validationHighlightLayer = null;
    }
    if (!geojson || !geojson.features || geojson.features.length === 0 || !map) return;
    
    // Auto-switch Leaflet map tab to match the anomaly's target scenario
    if (scenarioType === "realistic") {
        const modeBeforeBtn = document.getElementById("mode-before");
        const modeRealisticBtn = document.getElementById("mode-realistic");
        const modeOptimisticBtn = document.getElementById("mode-optimistic");
        const modeRiversBtn = document.getElementById("mode-rivers");
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => { if (btn) btn.classList.remove("active"); });
        if (modeRealisticBtn) modeRealisticBtn.classList.add("active");
        setMapMode("realistic");
    } else if (scenarioType === "optimistic") {
        const modeBeforeBtn = document.getElementById("mode-before");
        const modeRealisticBtn = document.getElementById("mode-realistic");
        const modeOptimisticBtn = document.getElementById("mode-optimistic");
        const modeRiversBtn = document.getElementById("mode-rivers");
        [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => { if (btn) btn.classList.remove("active"); });
        if (modeOptimisticBtn) modeOptimisticBtn.classList.add("active");
        setMapMode("optimistic");
    }
    
    validationHighlightLayer = L.geoJSON(geojson, {
        style: (feature) => {
            const color = feature.properties.color || "#2ecc71";
            return {
                fillColor: color,
                weight: 3,
                opacity: 0.9,
                color: color,
                fillOpacity: 0.6,
                dashArray: "4, 4"
            };
        }
    }).addTo(map);
    
    try {
        const bounds = validationHighlightLayer.getBounds();
        if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [50, 50], maxZoom: 8 });
        }
    } catch(e) {
        console.error(e);
    }
}

function clearValidationHighlight() {
    if (validationHighlightLayer && map) {
        map.removeLayer(validationHighlightLayer);
        validationHighlightLayer = null;
    }
}

function displayValidationQuestions(questions) {
    const container = document.getElementById("validation-questions-container");
    container.innerHTML = "";
    
    questions.forEach(q => {
        const card = document.createElement("div");
        card.className = "validation-anomaly-card";
        card.dataset.id = q.id;
        card.style.background = "rgba(255,255,255,0.03)";
        card.style.border = "1px solid rgba(255,255,255,0.1)";
        card.style.borderRadius = "8px";
        card.style.padding = "15px";
        card.style.marginBottom = "15px";
        
        const typeLabel = q.scenario_type === "realistic" ? "🔍 Realistic Anomaly" : "⚡ Optimistic Anomaly";
        const typeColor = q.scenario_type === "realistic" ? "#fbbf24" : "#2ecc71";
        
        const header = document.createElement("h4");
        header.style.color = typeColor;
        header.style.fontSize = "11px";
        header.style.fontWeight = "700";
        header.style.textTransform = "uppercase";
        header.style.marginBottom = "5px";
        header.innerText = typeLabel;
        card.appendChild(header);
        
        const desc = document.createElement("p");
        desc.style.fontSize = "12px";
        desc.style.marginBottom = "15px";
        desc.style.color = "#e2e8f0";
        desc.innerText = q.issue_description;
        card.appendChild(desc);
        
        // Option 1 Container (Addition - Green)
        const opt1Group = document.createElement("div");
        opt1Group.style.marginBottom = "10px";
        opt1Group.style.padding = "8px 12px";
        opt1Group.style.border = "1px dashed rgba(46, 204, 113, 0.3)";
        opt1Group.style.borderRadius = "6px";
        opt1Group.style.cursor = "pointer";
        opt1Group.style.background = "rgba(46, 204, 113, 0.03)";
        opt1Group.className = "anomaly-option-row";
        
        const radio1 = document.createElement("input");
        radio1.type = "radio";
        radio1.name = `opt-${q.id}`;
        radio1.value = "option_1";
        radio1.id = `opt1-${q.id}`;
        radio1.style.marginRight = "8px";
        
        const label1 = document.createElement("label");
        label1.htmlFor = `opt1-${q.id}`;
        label1.style.fontSize = "12px";
        label1.style.color = "#fff";
        label1.style.cursor = "pointer";
        label1.innerText = `Option 1 (Land Bridge): ${q.option_1.description}`;
        
        opt1Group.appendChild(radio1);
        opt1Group.appendChild(label1);
        
        // Option 2 Container (Subtraction - Red)
        const opt2Group = document.createElement("div");
        opt2Group.style.padding = "8px 12px";
        opt2Group.style.border = "1px dashed rgba(239, 68, 68, 0.3)";
        opt2Group.style.borderRadius = "6px";
        opt2Group.style.cursor = "pointer";
        opt2Group.style.background = "rgba(239, 68, 68, 0.03)";
        opt2Group.className = "anomaly-option-row";
        
        const radio2 = document.createElement("input");
        radio2.type = "radio";
        radio2.name = `opt-${q.id}`;
        radio2.value = "option_2";
        radio2.id = `opt2-${q.id}`;
        radio2.style.marginRight = "8px";
        
        const label2 = document.createElement("label");
        label2.htmlFor = `opt2-${q.id}`;
        label2.style.fontSize = "12px";
        label2.style.color = "#fff";
        label2.style.cursor = "pointer";
        label2.innerText = `Option 2 (Withdraw): ${q.option_2.description}`;
        
        opt2Group.appendChild(radio2);
        opt2Group.appendChild(label2);
        
        // Hover listeners for highlights
        opt1Group.addEventListener("mouseenter", () => showValidationHighlight(q.option_1_geojson, q.scenario_type));
        opt1Group.addEventListener("mouseleave", () => {
            const checked = card.querySelector(`input[name="opt-${q.id}"]:checked`);
            if (checked && checked.value === "option_1") {
                showValidationHighlight(q.option_1_geojson, q.scenario_type);
            } else if (checked && checked.value === "option_2") {
                showValidationHighlight(q.option_2_geojson, q.scenario_type);
            } else {
                clearValidationHighlight();
            }
        });
        opt1Group.addEventListener("click", () => {
            radio1.checked = true;
            showValidationHighlight(q.option_1_geojson, q.scenario_type);
        });
        
        opt2Group.addEventListener("mouseenter", () => showValidationHighlight(q.option_2_geojson, q.scenario_type));
        opt2Group.addEventListener("mouseleave", () => {
            const checked = card.querySelector(`input[name="opt-${q.id}"]:checked`);
            if (checked && checked.value === "option_2") {
                showValidationHighlight(q.option_2_geojson, q.scenario_type);
            } else if (checked && checked.value === "option_1") {
                showValidationHighlight(q.option_1_geojson, q.scenario_type);
            } else {
                clearValidationHighlight();
            }
        });
        opt2Group.addEventListener("click", () => {
            radio2.checked = true;
            showValidationHighlight(q.option_2_geojson, q.scenario_type);
        });
        
        card.appendChild(opt1Group);
        card.appendChild(opt2Group);
        container.appendChild(card);
    });
}

function renderQuestion(q, container) {
    const group = document.createElement("div");
    group.className = "input-group";
    group.style.marginBottom = "12px";
    
    const label = document.createElement("label");
    label.innerText = q.question;
    label.style.display = "block";
    label.style.marginBottom = "5px";
    label.style.fontSize = "11px";
    group.appendChild(label);
    
    const select = document.createElement("select");
    select.id = `q-${q.id}`;
    select.style.width = "100%";
    select.style.padding = "8px 10px";
    select.style.background = "rgba(255,255,255,0.06)";
    select.style.border = "1px solid rgba(255,255,255,0.12)";
    select.style.borderRadius = "4px";
    select.style.color = "#fff";
    select.style.fontSize = "12px";
    
    q.options.forEach(opt => {
        const option = document.createElement("option");
        option.value = opt;
        option.innerText = opt;
        option.style.background = "#161c2d";
        select.appendChild(option);
    });
    
    group.appendChild(select);
    container.appendChild(group);
}

// Bind Refinement panel triggers
document.addEventListener("DOMContentLoaded", () => {
    const refineBtn = document.getElementById("refine-btn");
    const refinementInput = document.getElementById("refinement-input");
    
    if (refineBtn && refinementInput) {
        refineBtn.addEventListener("click", () => {
            const message = refinementInput.value.trim();
            if (!message) {
                showToast("Please enter refinement instructions.", "error");
                return;
            }
            if (!currentSessionId) {
                showToast("No active simulation session available to refine.", "error");
                return;
            }
            
            refinementInput.value = "";
            showPanel("loading-section");
            document.getElementById("active-agent-display").innerText = "Applying refinement feedback...";
            document.getElementById("progress-details-display").innerText = "Generating adjusted geopolitical scenario maps...";
            
            fetch("/api/interactive/step", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    message: message,
                    token: ""
                })
            })
            .then(res => {
                if (!res.ok) throw new Error("Refinement request failed");
                return res.json();
            })
            .then(data => {
                showToast("Refinement submitted.", "success");
                pollJobStatus(data.job_id);
            })
            .catch(err => {
                console.error(err);
                showToast(err.message, "error");
                showPanel("results-section");
            });
        });
        
        refinementInput.addEventListener("keypress", (e) => {
            if (e.key === "Enter") {
                refineBtn.click();
            }
        });
    }
});


function displayResults(result) {
    // Cache result globally for map mode switches
    window.activeScenarioData = result;
    
    showPanel("results-section");
    showToast("Simulation completed successfully!", "success");
    
    // Fill text metrics
    document.getElementById("result-title").innerText = result.title || "Simulation Result";
    document.getElementById("result-base-year").innerText = result.base_year || "-";
    
    const confidencePercent = result.confidence_score ? `${Math.round(result.confidence_score * 100)}%` : "-";
    document.getElementById("result-confidence").innerText = confidencePercent;
    
    // Load narrative tab by default
    document.querySelector(".tab-btn[data-tab='tab-narrative']").click();
    
    // Animating narrative elements using typewriter effect sequentially
    const contextEl = document.getElementById("result-context");
    const actualEl = document.getElementById("result-actual");
    const alternateEl = document.getElementById("result-alternate");
    
    const alternateText = (currentMode === "realistic" || currentMode === "rivers") ? 
        (result.alternate_outcome_realistic || result.alternate_outcome || "") : 
        (result.alternate_outcome_optimistic || result.alternate_outcome || "");
        
    typeWriter(contextEl, result.historical_context || "", 10, () => {
        typeWriter(actualEl, result.what_actually_happened || "", 10, () => {
            typeWriter(alternateEl, alternateText, 10);
        });
    });
    
    // Fill timeline, border changes, butterfly effects, and sources list
    populateList("result-timeline-list", result.timeline);
    
    // Format list structures showing both scenarios
    const changes = [];
    if (result.territories_after_realistic) {
        result.territories_after_realistic.forEach(t => {
            changes.push(`[Realistic] ${t.name}: ${t.description}`);
        });
    }
    if (result.territories_after_optimistic) {
        result.territories_after_optimistic.forEach(t => {
            changes.push(`[Optimistic] ${t.name}: ${t.description}`);
        });
    }
    populateList("result-changes-list", changes);
    
    populateList("result-effects-list", result.butterfly_effects);
    populateList("result-sources-list", result.sources || []);
    
    // Set map default mode: alternate after (optimistic)
    const modeBeforeBtn = document.getElementById("mode-before");
    const modeRealisticBtn = document.getElementById("mode-realistic");
    const modeOptimisticBtn = document.getElementById("mode-optimistic");
    const modeRiversBtn = document.getElementById("mode-rivers");
    [modeBeforeBtn, modeRealisticBtn, modeOptimisticBtn, modeRiversBtn].forEach(btn => btn.classList.remove("active"));
    
    // Toggle displaying Natural Borders button based on presence of boundary geometries
    const hasBoundaries = (result.osm_boundary_geometry && result.osm_boundary_geometry.length > 0);
    if (hasBoundaries) {
        modeRiversBtn.style.display = "inline-block";
    } else {
        modeRiversBtn.style.display = "none";
    }
    
    // Check if partition treaty mode
    const isPartition = (result.realistic_scenario_summary && result.realistic_scenario_summary.includes("partition agreement"));
    if (isPartition) {
        modeRealisticBtn.style.display = "none";
        modeOptimisticBtn.innerText = "After Treaty";
        modeOptimisticBtn.classList.add("active");
        currentMode = "optimistic";
    } else {
        modeRealisticBtn.style.display = "inline-block";
        modeOptimisticBtn.innerText = "Optimistic";
        modeOptimisticBtn.classList.add("active");
        currentMode = "optimistic";
    }
    
    // Draw elements on Leaflet Map
    renderScenarioMaps(
        result.geojson_before,
        result.geojson_after_realistic,
        result.geojson_after_optimistic,
        result.territories_before,
        result.territories_after_realistic,
        result.territories_after_optimistic
    );
}
