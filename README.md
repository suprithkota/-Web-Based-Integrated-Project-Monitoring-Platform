# ProjectPulse AI — Intelligent Infrastructure Project Monitoring & Early Warning Platform

> **Smart India Hackathon (SIH26103)**  
> **Web-Based Integrated Project-Monitoring Platform**  
> *Tagline:* **Monitor. Predict. Explain. Act.**  
> *Core Value Proposition:* **«Existing monitoring systems show what is happening. Our platform predicts what is likely to happen next, explains why, and helps decision-makers identify where intervention may be required.»**

---

## 1. Executive Overview & Problem Statement

Large-scale national infrastructure projects (expressways, dedicated freight corridors, metro rail, hydroelectric dams, refineries, ports, and rural networks) represent trillions of rupees in capital expenditure. However, monitoring authorities historically face:
- **Lagging Indicator Blindspots:** Traditional systems highlight delays only *after* milestones have collapsed.
- **Cascading Cost Overruns:** Minor statutory or contractor bottlenecks compound into multi-crore budget revisions.
- **Information Overload:** Decision-makers receive voluminous progress tables without clear root causes or actionable priorities.

### Relationship to PAIMANA
India's existing monitoring platform **PAIMANA** (Project Assessment, Infrastructure Monitoring & Analytics for Nation-building) provides authoritative operational monitoring, milestone tracking, and expenditure data. 

**ProjectPulse AI is designed to complement PAIMANA, not replace it.** It ingests monitoring data and overlays a **predictive intelligence and early-intervention decision-support layer**.

---

## 2. Key Capabilities & Features

1. **Executive Command Center Dashboard:**
   - Real-time KPIs dynamically aggregated from database: Total Projects, Ongoing/Completed, At-Risk (High + Critical), Critical Projects count, Total Approved Capital Outlay, Cumulative Expenditure, and Average Physical Progress vs Planned Progress.
   - Interactive Chart.js visualizations: Portfolio Risk Distribution, Ministry Allocations & Risk Profiles, Sector Breakdown, and Expenditure Utilization vs Physical Progress Scatter plot.
   - Dynamic multi-parameter filtering by Ministry, Sector, State, Status, and Risk Level.

2. **Calibrated AI/ML Risk Engine:**
   - Scikit-learn Random Forest model trained on infrastructure execution patterns (`MSE: 16.41, R2: 0.88`).
   - Generates **Estimated Delay Probability (0–100%)** and **Cost Overrun Probability (0–100%)**.
   - Computes transparent **Overall Risk Score (0–100)** and categorizes projects:
     - `0–30`: 🟢 **LOW RISK**
     - `31–55`: 🟡 **MEDIUM RISK**
     - `56–75`: 🟠 **HIGH RISK**
     - `76–100`: 🔴 **CRITICAL RISK**
   - Decomposes project health into an explainable **Project Health Score (0–100)** with individual component scores: Schedule Health, Financial Health, Physical Progress, Milestone Health, and Risk Factors.

3. **Explainable AI & Root-Cause Attribution:**
   - Quantified percentage contributions for key risk drivers: Physical Progress Gap, Milestone Delays, Cost Escalation, Contractor Delay, Land Acquisition, Environmental Clearances, and Utility Relocation.
   - Generates natural-language diagnostic narrative explaining *why* the project is at risk.
   - Cautious, evidence-grounded **Root-Cause Analysis** identifying potential execution bottlenecks without speculation.

4. **Early Warning Center & Triage Workflow:**
   - Automated detection of red-flag conditions: Severe progress slippage, cost escalation exceeding 15%, milestone cascade failures, and expenditure-to-progress divergences.
   - Full triage lifecycle: `Open` ➔ `Under Review` ➔ `Resolved` with resolution timestamps and officer audit notes.

5. **Targeted Intervention Recommendation Engine:**
   - Context-aware action recommendations mapped directly to detected bottlenecks (e.g., escalating land acquisition with revenue authorities, contractor performance audits, fast-tracking forest clearances via PARIVESH, or re-baselining critical paths).

6. **Interactive What-If Scenario Simulator:**
   - Allows officers to stress-test projects by adjusting physical progress, delay days, milestone slippage, revised budget, contractor status, and statutory clearance conditions.
   - Live side-by-side comparison of baseline vs simulated risk score, delay probability, cost probability, and health score deltas with clear label: *«Scenario Simulation — Not an official forecast»*.

7. **Grounded AI Project Intelligence Assistant:**
   - Natural language conversational interface grounded directly in the live database (zero hallucinations).
   - Answers inquiries on highest delay risks, cost escalations, ministry risk rankings, and individual project root causes.
   - Runs out-of-the-box via deterministic rule-engine; supports optional external LLM API via `.env`.

8. **Geospatial Infrastructure Map:**
   - Interactive India map powered by Leaflet.js with risk-color-coded pins (Green, Yellow, Orange, Red) and interactive popup intelligence cards.

9. **Data Ingestion Engine:**
   - Admin CSV batch upload with schema validation, numeric range checks, duplicate project code rejection, and detailed error logging.

10. **Role-Based Access Control (RBAC):**
    - **Administrator:** Full CRUD, data ingestion, user management, and risk re-computation.
    - **Monitoring Officer:** View projects, risk intelligence, triage early warnings, run simulations, update project progress.
    - **Viewer / Observer:** Read-only access to dashboard, projects registry, and analytics.

---

## 3. End-to-End System Architecture

```
                       +--------------------------------------------------+
                       |   Data Ingestion Layer (Representative Dataset   |
                       |         / Batch CSV Upload / Future PAIMANA)     |
                       +-------------------------+------------------------+
                                                 |
                                                 v
                       +--------------------------------------------------+
                       |        Schema Validation & Preprocessing         |
                       |       (Feature Extraction & Normalization)       |
                       +-------------------------+------------------------+
                                                 |
                                                 v
                       +--------------------------------------------------+
                       |              AI/ML Risk Engine                   |
                       |  - Delay Probability (Random Forest Regression)  |
                       |  - Cost Overrun Probability                      |
                       |  - Project Health Score Decomposer (0-100)       |
                       |  - Transparent Feature Importance Attribution    |
                       +-------------------------+------------------------+
                                                 |
                      +--------------------------+--------------------------+
                      |                                                     |
                      v                                                     v
+------------------------------------------+    +------------------------------------------+
|       Early Warning Alert Engine         |    |   Intervention Recommendation Engine     |
| - Automated threshold trigger detection  |    | - Bottleneck-mapped action plans         |
| - Triage: Open -> Under Review -> Closed |    | - Inter-agency escalation guidance       |
+---------------------+--------------------+    +---------------------+--------------------+
                      |                                                     |
                      +--------------------------+--------------------------+
                                                 |
                                                 v
                       +--------------------------------------------------+
                       |     Government Officer Decision Support Hub      |
                       |  - Executive KPI Command Center                  |
                       |  - Searchable Projects Registry & Deep Intel     |
                       |  - What-If Scenario Simulator                    |
                       |  - Grounded AI Chat Assistant (Zero Hallucination)|
                       |  - Geospatial Leaflet Infrastructure Map         |
                       +--------------------------------------------------+
```

---

## 4. Technology Stack

- **Backend:** Python 3.11, Flask 3.1, Flask-SQLAlchemy 3.1, Flask-Login 0.6, Werkzeug
- **Database:** SQLite (local prototype; architecture ready for PostgreSQL via `DATABASE_URL`)
- **AI/ML:** Scikit-learn (RandomForestRegressor), Pandas, NumPy, Joblib
- **Frontend:** HTML5, CSS3, JavaScript (ES6+), Bootstrap 5.3, Chart.js 4.4, Leaflet.js 1.9, Font Awesome 6
- **Testing:** Python `unittest` suite (15 unit & integration tests)

---

## 5. Quick Start Installation Guide (Windows / PowerShell)

### Step 1: Open PowerShell in Project Directory
```powershell
cd c:\Users\supri\OneDrive\Desktop\sih
```

### Step 2: Create & Activate Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If PowerShell restricts execution scripts, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### Step 3: Install Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Train & Export ML Risk Model
```powershell
python ml/train_model.py
```
*Output: `Model successfully trained. Artifact saved to ml/models/risk_engine.joblib (MSE: 16.41, R2: 0.88)`*

### Step 5: Seed Representative Database (62 Projects + Users)
```powershell
python database/seed.py
```
*Output: Seeds 62 realistic projects across 10 Ministries, creates demo accounts, and exports `sample_projects.csv`.*

### Step 6: Run Flask Server
```powershell
python app.py
```
*Access in browser:* **`http://127.0.0.1:5000`**

---

## 6. Demo Accounts & Credentials

| Role | Username | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Monitoring Officer** *(Recommended for Demo)* | `officer` | `officer123` | View Intel, Triage Alerts, What-If Simulator, AI Assistant, Update Progress |
| **Administrator** | `admin` | `admin123` | Full Access: Add/Edit/Delete Projects, CSV Data Ingestion, System Settings |
| **Observer / Viewer** | `viewer` | `viewer123` | Read-only access to Dashboard, Projects Registry, and Deep Analytics |

*Tip: The login page includes 1-click autofill buttons for all three roles.*

---

## 7. SIH 5–7 Minute Demonstration Flow

1. **Sign In (0:00 - 0:30):**
   - Navigate to `http://127.0.0.1:5000/login`
   - Click the quick-fill button for **Monitoring Officer** (`officer` / `officer123`) and log in.
2. **Executive Command Center (0:30 - 1:30):**
   - Point out dynamic KPIs (Total Projects: 62, Approved Outlay vs Expenditure, Portfolio Health Index: ~60/100).
   - Show interactive Chart.js charts: Risk Distribution doughnut, Ministry Allocations, and Progress vs Spend Scatter plot.
   - Emphasize: *All statistics are computed dynamically from the database.*
3. **Filter Critical Projects (1:30 - 2:15):**
   - Click the red **«Filter Critical Projects»** link on the KPI card.
   - Notice the Projects Registry filters to show only Critical risk projects with progress gaps, delay days, and badges.
4. **Project Deep Intelligence & Explainability (2:15 - 3:30):**
   - Select **PRJ-0003** (*Varanasi-Ranchi-Kolkata Economic Corridor PKG-7*) or **PRJ-0001** (*Delhi-Amritsar-Katra Expressway*).
   - Inspect the **Health Score Gauge (38/100)**, **Delay Risk (88%)**, and **Cost Overrun Risk (78%)**.
   - Highlight the **Explainable AI section**: Show quantified contributing factor bars (Progress Gap: 95%, Milestone Delays: 83%, Contractor Status: 75%).
   - Show the **Root-Cause Analysis** and **Recommended Interventions** (Inter-departmental escalation, contractor recovery schedule).
5. **Early Warning Center & Triage (3:30 - 4:15):**
   - Open **Early Warnings** in the sidebar (notice badge count).
   - Demonstrate alert details: Severity, Trigger (`SEVERE_PROGRESS_SLIPPAGE`), Probability, and Recommendations.
   - Update an alert status from `Open` to `Under Review` with an officer note.
6. **What-If Scenario Simulator (4:15 - 5:15):**
   - Navigate to **What-If Simulator**.
   - Move the **Physical Progress slider** from 48% down to 35%, and increase **Delay Days** to 450.
   - Click **«Compute Simulated Impact»**.
   - Show the side-by-side delta: Risk index rises (`DETERIORATING +Risk`), health score drops, and sensitivity narrative updates.
   - Note the prominent disclaimer: *«Scenario Simulation — Not an official forecast»*.
7. **AI Project Intelligence Assistant (5:15 - 6:00):**
   - Navigate to **AI Assistant**.
   - Click the suggestion chip: *«Which projects have the highest delay risk?»*
   - Click *«Why is PRJ-0003 high risk?»*
   - Emphasize: *The assistant is grounded directly in the database, eliminating hallucinated statistics.*
8. **Geospatial Map & Conclusion (6:00 - 6:30):**
   - Open **Geospatial Map** to showcase India-wide infrastructure pins color-coded by risk.
   - Conclude with the core takeaway: **Monitor ➔ Predict ➔ Explain ➔ Alert ➔ Act.**

---

## 8. REST API Documentation

All endpoints return JSON and are secured via session-based authentication:

| Method | Endpoint | Description | Access |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/dashboard` | Returns aggregated KPI metrics and chart datasets | Logged in |
| `GET` | `/api/projects` | Returns array of all monitored projects | Logged in |
| `GET` | `/api/projects/<id>` | Returns detailed project data, risk evaluation & recs | Logged in |
| `GET` | `/api/risk/<id>` | Returns ML delay prob, cost prob, and health breakdown | Logged in |
| `GET` | `/api/alerts` | Returns list of early warning alerts (supports `?status=`) | Logged in |
| `POST` | `/api/alerts/<id>/resolve` | Marks an alert as Resolved with officer notes | Officer/Admin |
| `POST` | `/api/simulate` | Computes simulated risk delta from modified parameters | Logged in |
| `POST` | `/api/assistant` | Submits natural-language query to grounded AI engine | Logged in |
| `GET` | `/api/map-data` | Returns project geographic coordinates and risk status | Logged in |

---

## 9. Automated Testing Suite

To run the full automated test suite:
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

Test coverage includes:
- `test_auth.py`: Authentication, session persistence, role-based protection.
- `test_projects.py`: Project retrieval, detail page, REST API payload verification.
- `test_risk.py`: Preprocessing, feature vector dimensions, low vs critical risk calibration.
- `test_alerts.py`: Automatic threshold evaluation, alert creation, triage status transition.
- `test_api.py`: REST endpoints (`/api/dashboard`, `/api/simulate`, `/api/assistant`, `/api/map-data`).

---

## 10. Data-Source & Predictive Disclaimer

- **Representative Demo Dataset:** All 62 infrastructure project records in this prototype are realistic synthetic representations based on public domain infrastructure patterns across India's Central Ministries. They are not official government records.
- **Predictive Analytics:** Predictions, health scores, and risk classifications generated by this prototype are analytical estimates intended strictly for decision-support and academic demonstration; they do not represent official government forecasts or sanctions.
