# Geopolitico — "What If?" Geopolitical Scenario Simulator

An interactive alternate history simulator powered by a **CrewAI multi-agent pipeline** and **GitHub Models API** (via your student pack), visualized on an interactive dark-themed map.

---

## Key Features

1. **Fully Custom Scenarios**: Type any "what-if" alternate history question (e.g. *What if Muslims won the Battle of Tours?*, *What if the Chenab Formula was accepted in 1947?*, *What if Muslims were 60% of British India?*).
2. **Anti-Hallucination Agent Pipeline**:
   - **Historian**: Searches Wikipedia and real sources to establish accurate historical baseline constraints.
   - **Geopolitical Analyst**: Simulates realistic geopolitical border changes and timelines based on logistics/geography.
   - **Fact-Checker**: Validates claims, checks coordinate sanity, and removes speculative hallucinations.
   - **Cartographer**: Converts semantic descriptions into precise geographic instructions.
3. **Sub-Region Polygon Clipping**: Supports partial country divisions (e.g., "Southern Spain", "France south of Tours", "West of the Chenab River") using geographic coordinate division and landmark geocoding (Nominatim).
4. **Dynamic Before/After Map**: Shows actual historical borders vs. simulated alternate history borders using custom-drawn leaflet layers.

---

## Setup Instructions

### 1. Requirements

Ensure you have Python 3.10+ installed. Install the Python dependencies:

```bash
pip install -r backend/requirements.txt
```

### 2. Configure GITHUB_TOKEN

Create a `.env` file at the root of the project:

```bash
copy .env.example .env
```

Open `.env` and paste your GitHub token (Student Developer Pack token):
```env
GITHUB_TOKEN=ghp_your_token_here
```

*Note: The token can also be pasted directly in the frontend interface during usage, which will override the environment variable.*

### 3. Download World Boundaries GeoJSON

Run the download script to retrieve and optimize the Natural Earth 110m countries GeoJSON boundary building blocks:

```bash
python backend/tools/download_data.py
```

### 4. Run the Application

Start the FastAPI backend server using Uvicorn:

```bash
python -m uvicorn backend.main:app --reload
```

Open your browser and navigate to:
```
http://localhost:8000
```

---

## How Polygon Clipping Works

When the alternate history simulation outputs partial regions (e.g. "Iberia south of Toledo"), the Cartographer agent emits a structured instruction:
1. Geocode landmark "Toledo, Spain" via Nominatim API -> obtains Latitude (39.86°N).
2. Look up the polygon representing Spain from the Natural Earth GeoJSON boundaries.
3. Clip Spain at 39.86°N latitude line.
4. Separate the polygon and keep the southern portion.
5. Merge the clipped portion with adjacent territories (e.g., Umayyad Caliphate) using Shapely polygon operations.
