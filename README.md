# FoodLink AI — AI-Powered Surplus Food Redistribution Platform

> **Turning Surplus into Support**  
> *Developed for College Hackathon (4-Developer Team End-to-End Prototype)*  
> *Geographic Region: Chandigarh & Mohali Tricity Area*

---

## 1. Project Overview

**FoodLink AI** addresses urban food wastage by connecting institutional donors (college canteens, restaurant kitchens, hostel messes, banquet caterers) with nearby recipient organizations (community kitchens, food shelters, orphanages, family relief NGOs).

Unlike basic static CRUD apps, FoodLink AI is a complete, working logistics platform featuring:
1. **Rule-Based Food Safety Risk Screening Engine** with category-specific shelf-life thresholds and temperature danger zone screening.
2. **AI Smart Matching Engine** utilizing a 5-factor weighted scoring algorithm with hard constraint filters and multi-recipient allocation support.
3. **Statistical Demand Forecasting** using weighted historical moving averages, projected 7-day curves, and Google Gemini natural language interpretation.
4. **OSRM Road Route Optimization** using real OpenStreetMap road driving data, stop sequencing permutations, and collection deadline alerts.
5. **Interactive Operations Dashboard** with live Leaflet.js mapping, Chart.js analytics, and Gemini AI operations briefings.

---

## 2. Technology Stack

* **Frontend:** HTML5, CSS3 (Modern SaaS design system, dark navy slate `#0f172a`, emerald accent `#10b981`), Vanilla JavaScript (ES6+ SPA architecture), [Leaflet.js](https://leafletjs.com/) for interactive mapping, [Chart.js](https://www.chartjs.org/) for data visualization.
* **Backend:** Python 3.10+, Flask REST API, Parameterized SQL with foreign key constraints.
* **Database:** SQLite 3 with ACID transactions, atomic allocation limits, and automatic schema initialization.
* **Routing Engine:** Open Source Routing Machine (OSRM) Table API & Route API (with automatic Haversine urban road-factor fallback).
* **Generative AI:** Official Google Gen AI Python SDK (`google-genai`). Optional integration—runs full deterministic logistics explanations if no API key is provided.

---

## 3. Core AI & Algorithmic Modules

### A. Smart Matching Engine (`backend/matching.py`)
Matches active surplus donations against recipient NGOs using a 5-factor weighted formula:
* **Distance Suitability (30%):** Proximity decay function $\max(0, 100 - (\text{dist\_km} \times 4.0))$ across the Tricity region.
* **Quantity Compatibility (25%):** Evaluates whether the donation fits the NGO's remaining daily capacity without causing food wastage.
* **Urgency & Time Suitability (20%):** Cross-references transit distance with time remaining before collection deadline.
* **Dietary Compatibility (15%):** Enforces strict dietary matching (e.g. Non-Veg food rejected for strict Vegetarian kitchens).
* **Capacity Headroom (10%):** Prioritizes recipients with sufficient capacity margin.
* **Hard Constraint Rejections:** Expired donations, temperature violations, dietary mismatches, or zero capacity automatically disqualify candidates before scoring.

### B. Demand Forecasting Engine (`backend/forecasting.py`)
Computes recipient meal requirements using a baseline weighted statistical formula:
$$\text{Prediction} = (0.5 \times \text{Historical Avg}) + (0.3 \times \text{Recent 7-Day Avg}) + (0.2 \times \text{Expected Baseline})$$
* Clearly identified as a baseline statistical moving average, not a black-box deep learning model.
* Generates 7-day forward projected values and trend detection (Increasing, Stable, Decreasing).
* Gemini interprets verified metrics into executive inventory recommendations.

### C. Route Optimization (`backend/routing.py`)
* Queries the OSRM Table API for real driving distance and duration matrices.
* Calculates stop sequencing (exact permutation for $\le 6$ stops; nearest neighbor for larger batches).
* Queries the OSRM Route API for GeoJSON polyline geometries rendered on Leaflet.
* Checks travel times against food safety collection deadlines and issues warnings.
* Provides graceful Haversine fallback (1.3x road winding factor) if OSRM is unreachable.

### D. Food Safety Risk Screening (`backend/food_safety.py`)
* Configurable category-dependent lifespan limits:
  * Cooked Meals (Hot-hold): 6 hours.
  * Cooked Meals (Danger Zone Room Temp): Strict 4-hour limit.
  * Cooked Meals (Chilled 0-4°C): 24 hours.
  * Perishable Dairy (Paneer/Milk): Max 12 hours under active refrigeration.
  * Bakery: 36 hours.
  * Raw Produce: 48 hours.
* Transparent screening notice: Assists logistical pre-screening; does not replace physical inspection.

---

## 4. Project Directory Structure

```
foodlink-ai/
├── app.py                     # Main Flask REST server & routes
├── config.py                  # Environment & algorithm configurations
├── database.py                # SQLite connection, schema DDL & transactions
├── requirements.txt           # Python dependency definitions
├── .env.example               # Environment variables template
├── .gitignore                 # Standard Python/SQLite gitignore
├── README.md                  # Comprehensive setup & project guide
│
├── backend/
│   ├── __init__.py
│   ├── matching.py            # AI Smart Matching & scoring engine
│   ├── forecasting.py         # Statistical demand forecasting
│   ├── routing.py             # OSRM road distance matrix & GeoJSON routing
│   ├── food_safety.py         # Category shelf-life & temperature rules
│   └── ai_service.py          # Google Gen AI SDK integration & fallback
│
├── templates/
│   └── index.html             # Single-Page SaaS Application (8 Views)
│
├── static/
│   ├── css/
│   │   └── style.css          # Clean modern SaaS styling & responsive grid
│   └── js/
│       ├── app.js             # SPA routing, modals, health checks
│       ├── dashboard.js       # KPI metrics, Chart.js graphs, management forms
│       └── map.js             # Leaflet.js map, markers, OSRM polylines
│
├── data/
│   └── seed_data.py           # Realistic Chandigarh-Mohali seed data
│
├── tests/
│   └── test_foodlink.py       # Automated unit & integration tests
│
└── instance/
    └── foodlink.db            # SQLite database file (auto-generated)
```

---

## 5. Quick Setup & Run Instructions

### Step 1: Clone or Navigate to the Project Folder
```bash
cd "C:\Users\Manish Kumar\.gemini\antigravity\scratch\foodlink-ai"
```

### Step 2: Install Python Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: (Optional) Configure Gemini API Key
Create a `.env` file in the project root:
```ini
FLASK_DEBUG=True
PORT=5000
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```
*(Note: If you leave `GEMINI_API_KEY` empty, FoodLink AI automatically uses its high-quality deterministic logistics rule engine without crashing.)*

### Step 4: Initialize and Seed the Database
```bash
python data/seed_data.py
```

### Step 5: Run Automated Tests
```bash
python tests/test_foodlink.py
```
*(All 8 test suites should report `OK`.)*

### Step 6: Start the Flask Application
```bash
python app.py
```

Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 6. Demonstration Workflow (Hackathon Presentation Guide)

1. **Dashboard Overview:** View live KPI metrics (Donors, Meals Available, Meals Allocated, Active NGOs), category distribution doughnut, and Gemini autonomous intelligence brief.
2. **Log Food Donation:** Go to *Food Donations* $\to$ Click *+ Log Surplus Food*. Notice how entering safe conditions (Hot-hold Cooked meal, deadline in 2.5 hours) passes screening, while choosing 8-hour room temp fails with specific microbial warnings.
3. **Execute AI Smart Matching:** Go to *AI Smart Matching* $\to$ Select the active donation $\to$ Click *Run AI Matching Algorithm*. Review the top-ranked NGO, 5-factor breakdown bars, and Gemini explanation.
4. **Propose & Accept Allocation:** Click *Propose Allocation* for 80 meals. Observe the transaction commit. Then click *Accept Batch* on the dashboard to confirm delivery and update NGO capacity.
5. **Demand Forecasting:** Go to *Demand Forecast* $\to$ Select an NGO (e.g. *Annapurna Seva Kitchen*). Observe the historical 14-day line chart, 7-day projected curve, and statistical baseline formula explanation.
6. **OSRM Route Optimization:** Go to *Route Optimization* $\to$ Click *Load Active Allocation Stops* $\to$ Click *Optimize Delivery Route*. Watch Leaflet render the OpenStreetMap driving route polyline across Chandigarh and Mohali with stop sequence ETAs!

---

## 7. REST API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health telemetry, DB connection & Gemini status |
| `GET` | `/api/dashboard` | Main metrics, urgent alerts & recent allocations |
| `POST`| `/api/seed` | Reset DB with fresh Chandigarh-Mohali demo data |
| `GET`/`POST` | `/api/donors` | List or register food donors |
| `GET`/`POST` | `/api/ngos` | List or register recipient NGOs |
| `GET`/`POST` | `/api/donations`| List or submit food donations (with safety validation) |
| `GET` | `/api/donations/<id>`| Full donation detail and current allocations |
| `POST`| `/api/match/<id>` | Run 5-factor AI matching and Gemini explanation |
| `POST`| `/api/allocations` | Transaction-safe meal allocation |
| `POST`| `/api/allocations/<id>/accept`| Recipient NGO accepts allocation |
| `GET` | `/api/forecast/<ngo_id>` | Statistical demand forecast + chart series |
| `POST`| `/api/route` | OSRM road matrix, stop ordering & GeoJSON polyline |
| `POST`| `/api/ai-insights` | Executive redistribution intelligence briefing |
