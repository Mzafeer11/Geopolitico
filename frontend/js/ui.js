// UI helpers and animations

function showPanel(panelId) {
    const panels = document.querySelectorAll(".panel-card");
    panels.forEach(p => p.classList.remove("active"));
    
    const target = document.getElementById(panelId);
    if (target) {
        target.classList.add("active");
    }
}

// Typewriter effect helper
function typeWriter(element, text, speed = 15, callback = null) {
    if (!element) return;
    
    // Clear element contents
    element.innerHTML = "";
    
    let i = 0;
    function type() {
        if (i < text.length) {
            // Support simple newlines formatting
            if (text.charAt(i) === '\n') {
                element.innerHTML += '<br/>';
            } else {
                element.innerHTML += text.charAt(i);
            }
            i++;
            setTimeout(type, speed);
        } else if (callback) {
            callback();
        }
    }
    type();
}

// Toast notification helper
function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerText = message;
    
    container.appendChild(toast);
    
    // Auto remove after animations finish (~5s total)
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// Handle Results Tab Navigation
function initTabs() {
    const tabButtons = document.querySelectorAll(".tab-btn");
    tabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            
            const contents = document.querySelectorAll(".tab-content");
            contents.forEach(c => c.classList.remove("active"));
            
            const targetId = btn.getAttribute("data-tab");
            const targetContent = document.getElementById(targetId);
            if (targetContent) {
                targetContent.classList.add("active");
            }
        });
    });
}

// Helper to update timelines and bullet points
function populateList(elementId, items, className = "") {
    const list = document.getElementById(elementId);
    if (!list) return;
    list.innerHTML = "";
    
    if (!items || items.length === 0) {
        list.innerHTML = `<li class="muted">No data available.</li>`;
        return;
    }
    
    items.forEach(item => {
        const li = document.createElement("li");
        if (className) li.className = className;
        
        if (typeof item === 'string') {
            // Check if it's a URL link for sources
            if (item.startsWith("http://") || item.startsWith("https://")) {
                li.innerHTML = `<a href="${item}" target="_blank" rel="noopener noreferrer">${item}</a>`;
            } else {
                li.innerText = item;
            }
        } else if (item.year !== undefined && item.event !== undefined) {
            // It's a timeline event
            li.innerHTML = `
                <div class="timeline-year">${item.year}</div>
                <div class="timeline-desc">${item.event}</div>
            `;
        }
        list.appendChild(li);
    });
}
