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
    const modeProvincesBtn = document.getElementById("mode-provinces");
    const modeRealisticBtn = document.getElementById("mode-realistic");
    const modeOptimisticBtn = document.getElementById("mode-optimistic");
    const modeDistrictsBtn = document.getElementById("mode-districts");
    const modeAuditBtn = document.getElementById("mode-audit");
    const modeRiversBtn = document.getElementById("mode-rivers");
    const submitValidationBtn = document.getElementById("submit-validation-btn");

    const allModeBtns = [modeBeforeBtn, modeProvincesBtn, modeRealisticBtn, modeOptimisticBtn, modeDistrictsBtn, modeAuditBtn, modeRiversBtn].filter(Boolean);

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
        allModeBtns.forEach(btn => btn.classList.remove("active"));
        modeBeforeBtn.classList.add("active");
        setMapMode("before");
    });

    if (modeProvincesBtn) {
        modeProvincesBtn.addEventListener("click", () => {
            allModeBtns.forEach(btn => btn.classList.remove("active"));
            modeProvincesBtn.classList.add("active");
            setMapMode("provinces");
        });
    }

    modeRealisticBtn.addEventListener("click", () => {
        allModeBtns.forEach(btn => btn.classList.remove("active"));
        modeRealisticBtn.classList.add("active");
        setMapMode("realistic");
    });

    modeOptimisticBtn.addEventListener("click", () => {
        allModeBtns.forEach(btn => btn.classList.remove("active"));
        modeOptimisticBtn.classList.add("active");
        setMapMode("optimistic");
    });

    if (modeDistrictsBtn) {
        modeDistrictsBtn.addEventListener("click", () => {
            allModeBtns.forEach(btn => btn.classList.remove("active"));
            modeDistrictsBtn.classList.add("active");
            setMapMode("districts");
        });
    }

    if (modeAuditBtn) {
        modeAuditBtn.addEventListener("click", () => {
            allModeBtns.forEach(btn => btn.classList.remove("active"));
            modeAuditBtn.classList.add("active");
            setMapMode("audit");
        });
    }

    if (modeRiversBtn) {
        modeRiversBtn.addEventListener("click", () => {
            allModeBtns.forEach(btn => btn.classList.remove("active"));
            modeRiversBtn.classList.add("active");
            setMapMode("rivers");
        });
    }
}

// Strip whitespaces helper
String.prototype.stripOrEmpty = function () {
    return this ? this.replace(/^\s+|\s+$/g, '') : '';
};

let pollInterval = null;

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

const DEFAULT_STAGES = [
    { id: "guardrail", name: "Stage 1: Refinement of Prompt", detail: "Analyzing counterfactual prompt and verifying historical context...", status: "active" },
    { id: "planner", name: "Stage 2: Scenario Classification & Planning", detail: "Identifying base year, belligerents, and geopolitical mode...", status: "pending" },
    { id: "baseline_gis", name: "Stage 3: Historical Baselines & Natural Boundaries", detail: "Querying Cliopatria & resolving natural river/mountain vectors...", status: "pending" },
    { id: "simulation", name: "Stage 4: Geopolitical Simulation Execution", detail: "Computing territorial transfers, corridors, and demographic shifts...", status: "pending" },
    { id: "compilation", name: "Stage 5: Cartographic Compilation & Narrative", detail: "Assembling GeoJSON feature collections and synthesizing timeline...", status: "pending" },
    { id: "audit", name: "Stage 6: Continuity & Enclave Audit", detail: "Verifying territorial continuity, enclave detection, and final audit...", status: "pending" }
];

function initLoadingProgressUI(scenario) {
    const badgeEl = document.getElementById("active-stage-badge");
    const agentEl = document.getElementById("active-agent-display");
    const detailsEl = document.getElementById("progress-details-display");
    const stagesListEl = document.getElementById("stages-list");
    const logContentEl = document.getElementById("live-log-content");

    if (badgeEl) badgeEl.innerText = "Stage 1 of 6";
    if (agentEl) agentEl.innerText = "Stage 1: Refinement of Prompt";
    if (detailsEl) detailsEl.innerText = "Analyzing counterfactual prompt and verifying historical context...";

    if (stagesListEl) {
        stagesListEl.innerHTML = DEFAULT_STAGES.map(st => `
            <div class="stage-item stage-${st.status}">
                <span class="stage-status-icon">${st.status === 'active' ? '⏳' : '○'}</span>
                <div class="stage-info">
                    <span class="stage-name">${escapeHtml(st.name)}</span>
                    <span class="stage-desc">${escapeHtml(st.detail)}</span>
                </div>
            </div>
        `).join("");
    }

    if (logContentEl) {
        logContentEl.innerHTML = `<div class="log-line log-system">[SYSTEM] Initializing simulation for: "${escapeHtml(scenario.slice(0, 60))}..."</div>`;
    }
}

function updateLoadingProgressUI(job) {
    if (!job) return;

    const badgeEl = document.getElementById("active-stage-badge");
    const agentEl = document.getElementById("active-agent-display");
    const detailsEl = document.getElementById("progress-details-display");
    const stagesListEl = document.getElementById("stages-list");
    const logContentEl = document.getElementById("live-log-content");

    const stageIdx = job.stage_index || 1;
    const totalStages = job.total_stages || 6;
    if (badgeEl) badgeEl.innerText = `Stage ${stageIdx} of ${totalStages}`;
    if (agentEl) agentEl.innerText = job.current_stage || "Stage 1: Refinement of Prompt";
    if (detailsEl) detailsEl.innerText = job.stage_detail || job.progress || "Processing geopolitical simulation...";

    // Render pipeline checklist items
    const stages = (job.stages && job.stages.length > 0) ? job.stages : DEFAULT_STAGES;
    if (stagesListEl) {
        stagesListEl.innerHTML = stages.map(st => {
            let iconText = "○";
            if (st.status === "completed") iconText = "✓";
            else if (st.status === "active") iconText = "⏳";
            return `
                <div class="stage-item stage-${st.status}">
                    <span class="stage-status-icon">${iconText}</span>
                    <div class="stage-info">
                        <span class="stage-name">${escapeHtml(st.name)}</span>
                        <span class="stage-desc">${escapeHtml(st.detail || "")}</span>
                    </div>
                </div>
            `;
        }).join("");
    }

    // Render live log feed
    if (logContentEl && job.recent_logs && job.recent_logs.length > 0) {
        logContentEl.innerHTML = job.recent_logs.map(line => {
            let cls = "log-line";
            if (line.includes("[GUARDRAIL]") || line.includes("[STAGE") || line.includes("Refinement")) cls += " log-stage";
            else if (line.includes("[SYSTEM]") || line.includes("[SIMULATOR")) cls += " log-system";
            else if (line.includes("[OFFLINE GIS]") || line.includes("[CLIOPATRIA]") || line.includes("[RESOLVER]")) cls += " log-gis";
            else if (line.includes("[ERR]") || line.includes("failed")) cls += " log-err";
            return `<div class="${cls}">${escapeHtml(line)}</div>`;
        }).join("");
        logContentEl.scrollTop = logContentEl.scrollHeight;
    }
}

function startSimulation(scenario) {
    showPanel("loading-section");
    initLoadingProgressUI(scenario);

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

            // Start polling status with 1-second cadence
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
                // Update live stage checklist and logs
                updateLoadingProgressUI(job);

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
    }, 1000);
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
    } catch (e) {
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


function displayResults(result) {
    if (result && result.result && typeof result.result === "object" && (!result.title || result.result.title)) {
        result = result.result;
    }
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
    const modeProvincesBtn = document.getElementById("mode-provinces");
    const modeRealisticBtn = document.getElementById("mode-realistic");
    const modeOptimisticBtn = document.getElementById("mode-optimistic");
    const modeDistrictsBtn = document.getElementById("mode-districts");
    const modeAuditBtn = document.getElementById("mode-audit");
    const modeRiversBtn = document.getElementById("mode-rivers");

    [modeBeforeBtn, modeProvincesBtn, modeRealisticBtn, modeOptimisticBtn, modeDistrictsBtn, modeAuditBtn, modeRiversBtn].forEach(btn => { if (btn) btn.classList.remove("active"); });

    const sMode = result.scenario_mode || result.mode || result.pipeline || "";
    const isDemographic = (sMode === "demographic_shift");
    const isPartitionMode = (sMode === "proposal_partition" || (result.realistic_scenario_summary && result.realistic_scenario_summary.includes("partition agreement")));

    if (modeProvincesBtn) {
        if (!isDemographic && !isPartitionMode && result.geojson_provinces && result.geojson_provinces.features && result.geojson_provinces.features.length > 0) {
            modeProvincesBtn.style.display = "inline-block";
        } else {
            modeProvincesBtn.style.display = "none";
        }
    }

    if (modeDistrictsBtn) {
        if (result.geojson_districts && result.geojson_districts.features && result.geojson_districts.features.length > 0) {
            modeDistrictsBtn.style.display = "inline-block";
        } else {
            modeDistrictsBtn.style.display = "none";
        }
    }

    if (modeAuditBtn) {
        if (result.geojson_audit && result.geojson_audit.features && result.geojson_audit.features.length > 0) {
            modeAuditBtn.style.display = "inline-block";
        } else {
            modeAuditBtn.style.display = "none";
        }
    }

    // Toggle displaying Natural Borders button based on presence of boundary geometries
    const hasBoundaries = (result.osm_boundary_geometry && result.osm_boundary_geometry.length > 0);
    if (hasBoundaries && modeRiversBtn) {
        modeRiversBtn.style.display = "inline-block";
    } else if (modeRiversBtn) {
        modeRiversBtn.style.display = "none";
    }

    // Check if partition treaty mode
    if (isPartitionMode) {
        if (modeRealisticBtn) modeRealisticBtn.style.display = "none";
        if (modeOptimisticBtn) {
            modeOptimisticBtn.innerText = "After Treaty";
            modeOptimisticBtn.classList.add("active");
        }
        currentMode = "optimistic";
    } else {
        if (modeRealisticBtn) modeRealisticBtn.style.display = "inline-block";
        if (modeOptimisticBtn) {
            modeOptimisticBtn.innerText = "Optimistic";
            modeOptimisticBtn.classList.add("active");
        }
        currentMode = "optimistic";
    }

    // Draw elements on Leaflet Map
    renderScenarioMaps(
        result.geojson_before,
        result.geojson_provinces,
        result.geojson_after_realistic,
        result.geojson_after_optimistic,
        result.territories_before,
        result.territories_after_realistic,
        result.territories_after_optimistic,
        result.geojson_districts,
        result.geojson_audit
    );

    setMapMode(currentMode);
    setTimeout(() => {
        if (map) {
            map.invalidateSize();
            const activeLayer = getActiveLayer();
            if (activeLayer && activeLayer.getBounds().isValid()) {
                map.fitBounds(activeLayer.getBounds(), { padding: [50, 50] });
            }
        }
    }, 150);
}
