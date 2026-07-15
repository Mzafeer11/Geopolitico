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
                displayResults(job.result);
            } else if (job.status === "failed") {
                clearInterval(pollInterval);
                showToast(`Simulation failed: ${job.error}`, "error");
                showPanel("input-section");
            }
        })
        .catch(err => {
            console.error(err);
            clearInterval(pollInterval);
            showToast("Error polling job status.", "error");
            showPanel("input-section");
        });
    }, 2000);
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
    
    typeWriter(contextEl, result.historical_context || "", 10, () => {
        typeWriter(actualEl, result.what_actually_happened || "", 10, () => {
            typeWriter(alternateEl, result.alternate_outcome || "", 10);
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
