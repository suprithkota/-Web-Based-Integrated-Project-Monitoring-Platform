import os
import sys
import csv
from datetime import datetime, date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app
from database import db
from database.models import (
    User, Project, Milestone, ProjectHistory, Alert, RiskPrediction,
    Contractor, ContractorBranch, MaterialSupplier, ProjectMaterial,
    MaterialQualityTest, ProjectDelayRecord, ProjectFinancialRecord,
    ProjectLifecycleEvent, PostConstructionRecord, ProjectSubcontractor,
    DepartmentHierarchy, SiteInspectionRecord, PublicComplaint,
    DocumentEvidence, DataSourceConfig, DataSyncLog, DataVersionHistory,
    DataConflictRecord
)
from services.risk_service import update_project_risk
from services.alert_service import evaluate_and_generate_alerts

DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_TEMPLATES = [
    # --- MoRTH (Roads) ---
    {
        "code": "PRJ-0001",
        "name": "Delhi-Amritsar-Katra Expressway Package-04",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "National Highways Authority of India",
        "sector": "Roads",
        "state": "Punjab",
        "location": "Jalandhar - Amritsar Section",
        "agency": "NHAI",
        "approved_cost": 4850.0,
        "revised_cost": 5920.0,
        "expenditure": 3480.0,
        "physical_progress": 52.0,
        "planned_progress": 78.0,
        "delay_days": 240,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "In Progress",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 31.3260, "lng": 75.5762
    },
    {
        "code": "PRJ-0002",
        "name": "Bengaluru-Chennai Expressway Section II",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "National Highways Authority of India",
        "sector": "Roads",
        "state": "Karnataka",
        "location": "Malur - Bangarpet Segment",
        "agency": "NHAI",
        "approved_cost": 3420.0,
        "revised_cost": 3450.0,
        "expenditure": 2890.0,
        "physical_progress": 84.0,
        "planned_progress": 86.0,
        "delay_days": 15,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 12.9850, "lng": 77.9390
    },
    {
        "code": "PRJ-0003",
        "name": "Varanasi-Ranchi-Kolkata Economic Corridor PKG-7",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "National Highways Authority of India",
        "sector": "Roads",
        "state": "Bihar",
        "location": "Sasaram - Gaya Border",
        "agency": "NHAI",
        "approved_cost": 6100.0,
        "revised_cost": 7950.0,
        "expenditure": 5300.0,
        "physical_progress": 48.0,
        "planned_progress": 82.0,
        "delay_days": 380,
        "milestones_total": 6,
        "milestones_completed": 1,
        "milestones_delayed": 5,
        "contractor_status": "Critical",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "Pending",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 24.7914, "lng": 85.0002
    },
    {
        "code": "PRJ-0004",
        "name": "Ahmedabad-Dholera Expressway Link",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "National Highways Authority of India",
        "sector": "Roads",
        "state": "Gujarat",
        "location": "Sarkhej - Dholera SIR",
        "agency": "NHAI",
        "approved_cost": 2980.0,
        "revised_cost": 3050.0,
        "expenditure": 1950.0,
        "physical_progress": 66.0,
        "planned_progress": 70.0,
        "delay_days": 40,
        "milestones_total": 4,
        "milestones_completed": 2,
        "milestones_delayed": 1,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 22.2475, "lng": 72.1963
    },
    {
        "code": "PRJ-0005",
        "name": "Raipur-Visakhapatnam Greenfield Corridor PKG-3",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "National Highways Authority of India",
        "sector": "Roads",
        "state": "Odisha",
        "location": "Nabarangpur - Koraput Section",
        "agency": "NHAI",
        "approved_cost": 4120.0,
        "revised_cost": 4680.0,
        "expenditure": 2600.0,
        "physical_progress": 55.0,
        "planned_progress": 68.0,
        "delay_days": 110,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 2,
        "contractor_status": "Delayed",
        "land_acquisition_status": "In Progress",
        "environmental_clearance_status": "Delayed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 18.8135, "lng": 82.7118
    },
    {
        "code": "PRJ-0006",
        "name": "Zojila Tunnel Construction Project",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "NHIDCL",
        "sector": "Roads",
        "state": "Jammu & Kashmir",
        "location": "Baltal - Minamarg",
        "agency": "NHIDCL",
        "approved_cost": 6800.0,
        "revised_cost": 7200.0,
        "expenditure": 4600.0,
        "physical_progress": 62.0,
        "planned_progress": 72.0,
        "delay_days": 130,
        "milestones_total": 5,
        "milestones_completed": 3,
        "milestones_delayed": 2,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 34.2885, "lng": 75.4673
    },
    {
        "code": "PRJ-0007",
        "name": "Hyderabad Regional Ring Road Northern Arc",
        "ministry": "Ministry of Road Transport & Highways",
        "department": "NHAI / State R&B",
        "sector": "Roads",
        "state": "Telangana",
        "location": "Sangareddy - Toopran - Choutuppal",
        "agency": "NHAI",
        "approved_cost": 5400.0,
        "revised_cost": 6200.0,
        "expenditure": 2100.0,
        "physical_progress": 36.0,
        "planned_progress": 58.0,
        "delay_days": 190,
        "milestones_total": 5,
        "milestones_completed": 1,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "In Progress",
        "utility_shifting_status": "Delayed",
        "project_status": "Ongoing",
        "lat": 17.6180, "lng": 78.4800
    },

    # --- Ministry of Railways (MoR) ---
    {
        "code": "PRJ-0008",
        "name": "Mumbai-Ahmedabad High Speed Rail (Bullet Train)",
        "ministry": "Ministry of Railways",
        "department": "NHSRCL",
        "sector": "Railways",
        "state": "Maharashtra",
        "location": "Bandra-Kurla to Surat",
        "agency": "NHSRCL",
        "approved_cost": 108000.0,
        "revised_cost": 125000.0,
        "expenditure": 72000.0,
        "physical_progress": 58.0,
        "planned_progress": 79.0,
        "delay_days": 320,
        "milestones_total": 8,
        "milestones_completed": 4,
        "milestones_delayed": 4,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Delayed",
        "project_status": "Ongoing",
        "lat": 19.0600, "lng": 72.8656
    },
    {
        "code": "PRJ-0009",
        "name": "Eastern Dedicated Freight Corridor (EDFC)",
        "ministry": "Ministry of Railways",
        "department": "DFCCIL",
        "sector": "Railways",
        "state": "Uttar Pradesh",
        "location": "Sonnagar - Dadri Section",
        "agency": "DFCCIL",
        "approved_cost": 30358.0,
        "revised_cost": 31200.0,
        "expenditure": 29800.0,
        "physical_progress": 94.0,
        "planned_progress": 96.0,
        "delay_days": 20,
        "milestones_total": 6,
        "milestones_completed": 5,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 28.5355, "lng": 77.5500
    },
    {
        "code": "PRJ-0010",
        "name": "Western Dedicated Freight Corridor (WDFC) Phase 2",
        "ministry": "Ministry of Railways",
        "department": "DFCCIL",
        "sector": "Railways",
        "state": "Rajasthan",
        "location": "Rewari - Palanpur Segment",
        "agency": "DFCCIL",
        "approved_cost": 51100.0,
        "revised_cost": 54800.0,
        "expenditure": 44200.0,
        "physical_progress": 81.0,
        "planned_progress": 87.0,
        "delay_days": 75,
        "milestones_total": 6,
        "milestones_completed": 4,
        "milestones_delayed": 1,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 26.9124, "lng": 75.7873
    },
    {
        "code": "PRJ-0011",
        "name": "Rishikesh-Karanprayag New Broad Gauge Rail Link",
        "ministry": "Ministry of Railways",
        "department": "RVNL",
        "sector": "Railways",
        "state": "Uttarakhand",
        "location": "Rishikesh - Karnaprayag",
        "agency": "Rail Vikas Nigam Ltd",
        "approved_cost": 16216.0,
        "revised_cost": 21800.0,
        "expenditure": 13900.0,
        "physical_progress": 59.0,
        "planned_progress": 84.0,
        "delay_days": 290,
        "milestones_total": 7,
        "milestones_completed": 3,
        "milestones_delayed": 4,
        "contractor_status": "Delayed",
        "land_acquisition_status": "In Progress",
        "environmental_clearance_status": "Delayed",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 30.0869, "lng": 78.2676
    },
    {
        "code": "PRJ-0012",
        "name": "Bairabi-Sairang New Railway Line",
        "ministry": "Ministry of Railways",
        "department": "Northeast Frontier Railway",
        "sector": "Railways",
        "state": "Assam",
        "location": "Bairabi - Sairang Corridor",
        "agency": "NFR",
        "approved_cost": 5021.0,
        "revised_cost": 7450.0,
        "expenditure": 5100.0,
        "physical_progress": 51.0,
        "planned_progress": 78.0,
        "delay_days": 340,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "Pending",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 24.1840, "lng": 92.6500
    },
    {
        "code": "PRJ-0013",
        "name": "Kazipet-Vijayawada 3rd Railway Line & Electrification",
        "ministry": "Ministry of Railways",
        "department": "South Central Railway",
        "sector": "Railways",
        "state": "Andhra Pradesh",
        "location": "Vijayawada - Kazipet Section",
        "agency": "SCR",
        "approved_cost": 2180.0,
        "revised_cost": 2240.0,
        "expenditure": 1650.0,
        "physical_progress": 72.0,
        "planned_progress": 75.0,
        "delay_days": 30,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 16.5062, "lng": 80.6480
    },

    # --- Ministry of Housing & Urban Affairs (Metro & Urban) ---
    {
        "code": "PRJ-0014",
        "name": "Bangalore Metro Rail Phase 2A (Silk Board - KR Puram)",
        "ministry": "Ministry of Housing & Urban Affairs",
        "department": "Urban Transit",
        "sector": "Metro",
        "state": "Karnataka",
        "location": "Outer Ring Road, Bengaluru",
        "agency": "BMRCL",
        "approved_cost": 5994.0,
        "revised_cost": 6420.0,
        "expenditure": 3850.0,
        "physical_progress": 61.0,
        "planned_progress": 76.0,
        "delay_days": 140,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 2,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Delayed",
        "project_status": "Ongoing",
        "lat": 12.9166, "lng": 77.6238
    },
    {
        "code": "PRJ-0015",
        "name": "Patna Metro Rail Project Phase 1",
        "ministry": "Ministry of Housing & Urban Affairs",
        "department": "Urban Mass Transit",
        "sector": "Metro",
        "state": "Bihar",
        "location": "Danapur - Mithapur - Khemnichak",
        "agency": "DMRC / PMRCL",
        "approved_cost": 13365.0,
        "revised_cost": 15800.0,
        "expenditure": 6200.0,
        "physical_progress": 42.0,
        "planned_progress": 68.0,
        "delay_days": 260,
        "milestones_total": 6,
        "milestones_completed": 2,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 25.5941, "lng": 85.1376
    },
    {
        "code": "PRJ-0016",
        "name": "Pune Metro Rail Project Phase 1 Extension",
        "ministry": "Ministry of Housing & Urban Affairs",
        "department": "Maha Metro",
        "sector": "Metro",
        "state": "Maharashtra",
        "location": "Swargate - Katraj Corridor",
        "agency": "Maha Metro",
        "approved_cost": 2954.0,
        "revised_cost": 2980.0,
        "expenditure": 1820.0,
        "physical_progress": 70.0,
        "planned_progress": 72.0,
        "delay_days": 15,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 18.5204, "lng": 73.8567
    },
    {
        "code": "PRJ-0017",
        "name": "Bhopal Metro Rail Orange Line",
        "ministry": "Ministry of Housing & Urban Affairs",
        "department": "MPMRCL",
        "sector": "Metro",
        "state": "Madhya Pradesh",
        "location": "Karond Circle - AIIMS",
        "agency": "MPMRCL",
        "approved_cost": 6941.0,
        "revised_cost": 7250.0,
        "expenditure": 4200.0,
        "physical_progress": 58.0,
        "planned_progress": 69.0,
        "delay_days": 85,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 2,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "In Progress",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 23.2599, "lng": 77.4126
    },
    {
        "code": "PRJ-0018",
        "name": "Agra Metro Rail Project Priority Corridor",
        "ministry": "Ministry of Housing & Urban Affairs",
        "department": "UPMRC",
        "sector": "Metro",
        "state": "Uttar Pradesh",
        "location": "Taj East Gate - Jama Masjid",
        "agency": "UPMRC",
        "approved_cost": 8379.0,
        "revised_cost": 8410.0,
        "expenditure": 7100.0,
        "physical_progress": 89.0,
        "planned_progress": 91.0,
        "delay_days": 10,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 27.1767, "lng": 78.0081
    },

    # --- Ministry of Power (MoP) ---
    {
        "code": "PRJ-0019",
        "name": "Subansiri Lower Hydroelectric Project (2000 MW)",
        "ministry": "Ministry of Power",
        "department": "NHPC",
        "sector": "Power",
        "state": "Assam",
        "location": "Gerukamukh, Dhemaji",
        "agency": "NHPC Ltd",
        "approved_cost": 6285.0,
        "revised_cost": 21247.0,
        "expenditure": 18900.0,
        "physical_progress": 88.0,
        "planned_progress": 95.0,
        "delay_days": 490,
        "milestones_total": 7,
        "milestones_completed": 4,
        "milestones_delayed": 3,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Delayed",
        "lat": 27.5500, "lng": 94.2600
    },
    {
        "code": "PRJ-0020",
        "name": "Pakal Dul Hydroelectric Project (1000 MW)",
        "ministry": "Ministry of Power",
        "department": "CVPPPL",
        "sector": "Power",
        "state": "Jammu & Kashmir",
        "location": "Drangdhuran, Kishtwar",
        "agency": "Chenab Valley Power Projects",
        "approved_cost": 8112.0,
        "revised_cost": 9950.0,
        "expenditure": 5200.0,
        "physical_progress": 52.0,
        "planned_progress": 72.0,
        "delay_days": 210,
        "milestones_total": 6,
        "milestones_completed": 2,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "In Progress",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Delayed",
        "lat": 33.3100, "lng": 75.7600
    },
    {
        "code": "PRJ-0021",
        "name": "Inter-State Transmission System Green Energy Corridor II",
        "ministry": "Ministry of Power",
        "department": "POWERGRID",
        "sector": "Power",
        "state": "Rajasthan",
        "location": "Bhadla - Fatehgarh Evacuation Grid",
        "agency": "PGCIL",
        "approved_cost": 4650.0,
        "revised_cost": 4700.0,
        "expenditure": 3800.0,
        "physical_progress": 83.0,
        "planned_progress": 85.0,
        "delay_days": 20,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 27.5300, "lng": 71.9100
    },
    {
        "code": "PRJ-0022",
        "name": "North Karanpura Super Thermal Power Project (3x660 MW)",
        "ministry": "Ministry of Power",
        "department": "NTPC",
        "sector": "Power",
        "state": "Jharkhand",
        "location": "Tandwa, Chatra",
        "agency": "NTPC Ltd",
        "approved_cost": 14366.0,
        "revised_cost": 16900.0,
        "expenditure": 15200.0,
        "physical_progress": 91.0,
        "planned_progress": 94.0,
        "delay_days": 65,
        "milestones_total": 6,
        "milestones_completed": 5,
        "milestones_delayed": 1,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 23.8500, "lng": 85.0300
    },
    {
        "code": "PRJ-0023",
        "name": "Bhadradri Thermal Power Station Aux Grid",
        "ministry": "Ministry of Power",
        "department": "TSGENCO",
        "sector": "Power",
        "state": "Telangana",
        "location": "Manuguru, Kothagudem",
        "agency": "TSGENCO",
        "approved_cost": 7290.0,
        "revised_cost": 7400.0,
        "expenditure": 6800.0,
        "physical_progress": 95.0,
        "planned_progress": 96.0,
        "delay_days": 10,
        "milestones_total": 4,
        "milestones_completed": 4,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 17.9800, "lng": 80.7500
    },

    # --- Ministry of Ports, Shipping & Waterways (MoPSW) ---
    {
        "code": "PRJ-0024",
        "name": "Vadhavan Mega Deep Sea Port Development",
        "ministry": "Ministry of Ports, Shipping & Waterways",
        "department": "JNPA",
        "sector": "Ports",
        "state": "Maharashtra",
        "location": "Dahanu, Palghar",
        "agency": "Vadhavan Port Project Ltd",
        "approved_cost": 76220.0,
        "revised_cost": 78500.0,
        "expenditure": 11200.0,
        "physical_progress": 18.0,
        "planned_progress": 32.0,
        "delay_days": 180,
        "milestones_total": 6,
        "milestones_completed": 1,
        "milestones_delayed": 3,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "In Progress",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 19.9800, "lng": 72.6800
    },
    {
        "code": "PRJ-0025",
        "name": "International Container Transhipment Terminal Galathea Bay",
        "ministry": "Ministry of Ports, Shipping & Waterways",
        "department": "SMPK / Andaman Admin",
        "sector": "Ports",
        "state": "Tamil Nadu",
        "location": "Great Nicobar / Coastal Access",
        "agency": "IPA",
        "approved_cost": 44000.0,
        "revised_cost": 45100.0,
        "expenditure": 4200.0,
        "physical_progress": 14.0,
        "planned_progress": 25.0,
        "delay_days": 150,
        "milestones_total": 5,
        "milestones_completed": 1,
        "milestones_delayed": 2,
        "contractor_status": "Delayed",
        "land_acquisition_status": "In Progress",
        "environmental_clearance_status": "Delayed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 13.0827, "lng": 80.2707
    },
    {
        "code": "PRJ-0026",
        "name": "Paradip Port Western Dock Modernization",
        "ministry": "Ministry of Ports, Shipping & Waterways",
        "department": "Paradip Port Authority",
        "sector": "Ports",
        "state": "Odisha",
        "location": "Paradip Western Basin",
        "agency": "PPA",
        "approved_cost": 3004.0,
        "revised_cost": 3040.0,
        "expenditure": 2450.0,
        "physical_progress": 78.0,
        "planned_progress": 80.0,
        "delay_days": 15,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 20.3164, "lng": 86.6114
    },
    {
        "code": "PRJ-0027",
        "name": "Cochin Shipyard International Ship Repair Facility (ISRF)",
        "ministry": "Ministry of Ports, Shipping & Waterways",
        "department": "Cochin Shipyard",
        "sector": "Ports",
        "state": "Kerala",
        "location": "Willingdon Island, Kochi",
        "agency": "CSL",
        "approved_cost": 2799.0,
        "revised_cost": 2850.0,
        "expenditure": 2650.0,
        "physical_progress": 92.0,
        "planned_progress": 94.0,
        "delay_days": 10,
        "milestones_total": 4,
        "milestones_completed": 4,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 9.9674, "lng": 76.2711
    },

    # --- Ministry of Jal Shakti (Water & Irrigation) ---
    {
        "code": "PRJ-0028",
        "name": "Polavaram National Multi-Purpose Irrigation Project",
        "ministry": "Ministry of Jal Shakti",
        "department": "PPA / Water Resources",
        "sector": "Water",
        "state": "Andhra Pradesh",
        "location": "Godavari Basin, Eluru",
        "agency": "Polavaram Project Authority",
        "approved_cost": 29027.0,
        "revised_cost": 55548.0,
        "expenditure": 34500.0,
        "physical_progress": 54.0,
        "planned_progress": 85.0,
        "delay_days": 540,
        "milestones_total": 8,
        "milestones_completed": 3,
        "milestones_delayed": 5,
        "contractor_status": "Critical",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "In Progress",
        "utility_shifting_status": "Delayed",
        "project_status": "Delayed",
        "lat": 17.2500, "lng": 81.6500
    },
    {
        "code": "PRJ-0029",
        "name": "Ken-Betwa River Interlinking National Project",
        "ministry": "Ministry of Jal Shakti",
        "department": "NWDA",
        "sector": "Water",
        "state": "Madhya Pradesh",
        "location": "Daudhan Dam, Chhatarpur & Panna",
        "agency": "Ken-Betwa Link Project Authority",
        "approved_cost": 44605.0,
        "revised_cost": 47200.0,
        "expenditure": 9800.0,
        "physical_progress": 26.0,
        "planned_progress": 42.0,
        "delay_days": 190,
        "milestones_total": 6,
        "milestones_completed": 1,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Delayed",
        "environmental_clearance_status": "Delayed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 24.6300, "lng": 79.8800
    },
    {
        "code": "PRJ-0030",
        "name": "Jal Jeevan Mission Regional Water Grid - Zone IV",
        "ministry": "Ministry of Jal Shakti",
        "department": "Drinking Water & Sanitation",
        "sector": "Water",
        "state": "Rajasthan",
        "location": "Barmer - Jaisalmer Rural Grid",
        "agency": "PHED Rajasthan",
        "approved_cost": 3850.0,
        "revised_cost": 3920.0,
        "expenditure": 3100.0,
        "physical_progress": 82.0,
        "planned_progress": 84.0,
        "delay_days": 25,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 26.9157, "lng": 70.9083
    },
    {
        "code": "PRJ-0031",
        "name": "Namami Gange STP & Sewerage Network Kanpur Phase II",
        "ministry": "Ministry of Jal Shakti",
        "department": "NMCG",
        "sector": "Water",
        "state": "Uttar Pradesh",
        "location": "Jajmau & Sisamau Nala Interception",
        "agency": "UP Jal Nigam",
        "approved_cost": 1620.0,
        "revised_cost": 1640.0,
        "expenditure": 1350.0,
        "physical_progress": 86.0,
        "planned_progress": 89.0,
        "delay_days": 18,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 26.4499, "lng": 80.3319
    },

    # --- Ministry of Petroleum & Natural Gas (Energy) ---
    {
        "code": "PRJ-0032",
        "name": "Jagdishpur-Haldia-Bokaro-Dhamra Gas Pipeline (JHBDPL)",
        "ministry": "Ministry of Petroleum & Natural Gas",
        "department": "GAIL",
        "sector": "Energy",
        "state": "West Bengal",
        "location": "Durgapur - Haldia Section",
        "agency": "GAIL (India) Ltd",
        "approved_cost": 12940.0,
        "revised_cost": 13800.0,
        "expenditure": 11800.0,
        "physical_progress": 87.0,
        "planned_progress": 92.0,
        "delay_days": 60,
        "milestones_total": 5,
        "milestones_completed": 4,
        "milestones_delayed": 1,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 22.0667, "lng": 88.0667
    },
    {
        "code": "PRJ-0033",
        "name": "Barmer Petroleum Refinery & Petrochemical Complex",
        "ministry": "Ministry of Petroleum & Natural Gas",
        "department": "HRRL",
        "sector": "Energy",
        "state": "Rajasthan",
        "location": "Pachpadra, Barmer",
        "agency": "HPCL Rajasthan Refinery Ltd",
        "approved_cost": 43129.0,
        "revised_cost": 72937.0,
        "expenditure": 49000.0,
        "physical_progress": 74.0,
        "planned_progress": 89.0,
        "delay_days": 310,
        "milestones_total": 7,
        "milestones_completed": 4,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Delayed",
        "lat": 25.9200, "lng": 72.2500
    },
    {
        "code": "PRJ-0034",
        "name": "Numaligarh Refinery Expansion (3 to 9 MMTPA)",
        "ministry": "Ministry of Petroleum & Natural Gas",
        "department": "NRL",
        "sector": "Energy",
        "state": "Assam",
        "location": "Golaghat District",
        "agency": "Numaligarh Refinery Ltd",
        "approved_cost": 28026.0,
        "revised_cost": 29500.0,
        "expenditure": 18400.0,
        "physical_progress": 64.0,
        "planned_progress": 72.0,
        "delay_days": 90,
        "milestones_total": 5,
        "milestones_completed": 3,
        "milestones_delayed": 1,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 26.5800, "lng": 93.7500
    },

    # --- Ministry of Civil Aviation (MoCA) ---
    {
        "code": "PRJ-0035",
        "name": "Noida International Airport (Jewar) Phase 1",
        "ministry": "Ministry of Civil Aviation",
        "department": "YIAPL",
        "sector": "Airports",
        "state": "Uttar Pradesh",
        "location": "Jewar, Gautam Buddha Nagar",
        "agency": "Yamuna International Airport Pvt Ltd",
        "approved_cost": 10056.0,
        "revised_cost": 10600.0,
        "expenditure": 8900.0,
        "physical_progress": 89.0,
        "planned_progress": 94.0,
        "delay_days": 45,
        "milestones_total": 5,
        "milestones_completed": 4,
        "milestones_delayed": 1,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 28.1800, "lng": 77.6200
    },
    {
        "code": "PRJ-0036",
        "name": "Navi Mumbai International Airport Phase 1",
        "ministry": "Ministry of Civil Aviation",
        "department": "NMIAL / Adani",
        "sector": "Airports",
        "state": "Maharashtra",
        "location": "Ulwe - Panvel, Navi Mumbai",
        "agency": "CIDCO / NMIAL",
        "approved_cost": 16700.0,
        "revised_cost": 19600.0,
        "expenditure": 14200.0,
        "physical_progress": 78.0,
        "planned_progress": 88.0,
        "delay_days": 160,
        "milestones_total": 6,
        "milestones_completed": 4,
        "milestones_delayed": 2,
        "contractor_status": "Minor Delay",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 18.9900, "lng": 73.0700
    },
    {
        "code": "PRJ-0037",
        "name": "Bhogapuram International Greenfield Airport",
        "ministry": "Ministry of Civil Aviation",
        "department": "GMR Visakhapatnam",
        "sector": "Airports",
        "state": "Andhra Pradesh",
        "location": "Bhogapuram, Vizianagaram",
        "agency": "GMR Group / APADCL",
        "approved_cost": 4592.0,
        "revised_cost": 4650.0,
        "expenditure": 1900.0,
        "physical_progress": 46.0,
        "planned_progress": 52.0,
        "delay_days": 35,
        "milestones_total": 4,
        "milestones_completed": 2,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "In Progress",
        "project_status": "Ongoing",
        "lat": 18.0034, "lng": 83.4925
    },

    # --- Ministry of Communications (Telecommunications) ---
    {
        "code": "PRJ-0038",
        "name": "BharatNet Phase III Optical Fiber Rural Connectivity",
        "ministry": "Ministry of Communications",
        "department": "DoT / BBNL",
        "sector": "Telecommunications",
        "state": "Madhya Pradesh",
        "location": "Bundelkhand & Malwa Gram Panchayats",
        "agency": "BSNL / BBNL",
        "approved_cost": 13950.0,
        "revised_cost": 16200.0,
        "expenditure": 9400.0,
        "physical_progress": 62.0,
        "planned_progress": 81.0,
        "delay_days": 180,
        "milestones_total": 5,
        "milestones_completed": 2,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "In Progress",
        "utility_shifting_status": "Delayed",
        "project_status": "Ongoing",
        "lat": 23.8300, "lng": 78.7300
    },
    {
        "code": "PRJ-0039",
        "name": "BharatNet Phase II High-Speed Connectivity - Telangana",
        "ministry": "Ministry of Communications",
        "department": "T-Fiber",
        "sector": "Telecommunications",
        "state": "Telangana",
        "location": "33 Districts Rural Hubs",
        "agency": "T-Fiber Corp",
        "approved_cost": 5500.0,
        "revised_cost": 5580.0,
        "expenditure": 4600.0,
        "physical_progress": 89.0,
        "planned_progress": 91.0,
        "delay_days": 15,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 17.3850, "lng": 78.4867
    },

    # --- Ministry of Coal (MoC) ---
    {
        "code": "PRJ-0040",
        "name": "Talcher Coal Gasification Plant",
        "ministry": "Ministry of Coal",
        "department": "TFL / CIL",
        "sector": "Energy",
        "state": "Odisha",
        "location": "Talcher, Angul",
        "agency": "Talcher Fertilizers Ltd",
        "approved_cost": 13277.0,
        "revised_cost": 15850.0,
        "expenditure": 9100.0,
        "physical_progress": 61.0,
        "planned_progress": 82.0,
        "delay_days": 260,
        "milestones_total": 6,
        "milestones_completed": 3,
        "milestones_delayed": 3,
        "contractor_status": "Delayed",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Delayed",
        "utility_shifting_status": "In Progress",
        "project_status": "Delayed",
        "lat": 20.9500, "lng": 85.2200
    },
    {
        "code": "PRJ-0041",
        "name": "Magadh & Amrapali Coal Evacuation Rail Corridor",
        "ministry": "Ministry of Coal",
        "department": "CCL",
        "sector": "Energy",
        "state": "Jharkhand",
        "location": "Tandwa, Chatra District",
        "agency": "Central Coalfields Ltd",
        "approved_cost": 2150.0,
        "revised_cost": 2180.0,
        "expenditure": 1850.0,
        "physical_progress": 84.0,
        "planned_progress": 86.0,
        "delay_days": 20,
        "milestones_total": 4,
        "milestones_completed": 3,
        "milestones_delayed": 0,
        "contractor_status": "On Track",
        "land_acquisition_status": "Completed",
        "environmental_clearance_status": "Completed",
        "utility_shifting_status": "Completed",
        "project_status": "Ongoing",
        "lat": 23.9500, "lng": 84.9500
    }
]

# Function to dynamically generate remaining projects to reach 62 total realistic records
def generate_expanded_projects():
    projects = list(PROJECT_TEMPLATES)
    
    extra_templates = [
        # Sector, Ministry, States list, base approved cost
        ("Roads", "Ministry of Road Transport & Highways", ["Maharashtra", "Tamil Nadu", "Haryana", "Telangana", "West Bengal", "Bihar"], 2400.0),
        ("Railways", "Ministry of Railways", ["Uttar Pradesh", "Odisha", "Gujarat", "Andhra Pradesh", "Karnataka"], 3800.0),
        ("Metro", "Ministry of Housing & Urban Affairs", ["Delhi", "Maharashtra", "Tamil Nadu", "Kerala"], 5200.0),
        ("Power", "Ministry of Power", ["Madhya Pradesh", "Rajasthan", "Telangana", "Gujarat"], 4500.0),
        ("Water", "Ministry of Jal Shakti", ["Bihar", "Uttar Pradesh", "Odisha", "Karnataka"], 1800.0),
        ("Airports", "Ministry of Civil Aviation", ["Assam", "Punjab", "Gujarat", "Kerala"], 2200.0),
        ("Ports", "Ministry of Ports, Shipping & Waterways", ["Andhra Pradesh", "Gujarat", "Maharashtra", "Tamil Nadu"], 3500.0)
    ]
    
    current_idx = len(projects) + 1
    
    # Target distribution: we want 62 projects
    while len(projects) < 62:
        sec, min_name, states, base_cost = extra_templates[len(projects) % len(extra_templates)]
        st = states[len(projects) % len(states)]
        
        # Determine archetype condition: 0=Low, 1=Medium, 2=High, 3=Critical
        archetype = len(projects) % 4
        
        if archetype == 0:  # Low risk
            cost_mult = 1.02
            planned_p = 75.0
            actual_p = 73.0
            del_days = 10
            m_del = 0
            c_stat = "On Track"
            l_stat = "Completed"
            e_stat = "Completed"
            u_stat = "Completed"
            p_status = "Ongoing"
        elif archetype == 1: # Medium risk
            cost_mult = 1.07
            planned_p = 68.0
            actual_p = 59.0
            del_days = 70
            m_del = 1
            c_stat = "Minor Delay"
            l_stat = "In Progress"
            e_stat = "Completed"
            u_stat = "In Progress"
            p_status = "Ongoing"
        elif archetype == 2: # High risk
            cost_mult = 1.22
            planned_p = 82.0
            actual_p = 58.0
            del_days = 220
            m_del = 3
            c_stat = "Delayed"
            l_stat = "Delayed"
            e_stat = "In Progress"
            u_stat = "Delayed"
            p_status = "Delayed"
        else: # Critical risk
            cost_mult = 1.38
            planned_p = 90.0
            actual_p = 49.0
            del_days = 410
            m_del = 5
            c_stat = "Critical"
            l_stat = "Delayed"
            e_stat = "Pending"
            u_stat = "Delayed"
            p_status = "Delayed"
            
        app_cost = base_cost + ((len(projects) * 137) % 3500)
        rev_cost = round(app_cost * cost_mult, 1)
        spend = round(app_cost * ((actual_p + 4.0) / 100.0), 1)
        
        code = f"PRJ-{current_idx:04d}"
        name = f"{st} {sec} Infrastructure Development Package-{len(projects) - 30}"
        
        # Coordinate heuristics based on state
        state_coords = {
            'Maharashtra': (19.75, 75.71), 'Tamil Nadu': (11.12, 78.65), 'Haryana': (29.05, 76.08),
            'Telangana': (17.87, 78.10), 'West Bengal': (22.98, 87.85), 'Bihar': (25.09, 85.31),
            'Uttar Pradesh': (26.84, 80.94), 'Odisha': (20.95, 85.09), 'Gujarat': (22.25, 71.19),
            'Andhra Pradesh': (15.91, 79.74), 'Karnataka': (15.31, 75.71), 'Delhi': (28.70, 77.10),
            'Kerala': (10.85, 76.27), 'Madhya Pradesh': (22.97, 78.65), 'Rajasthan': (27.02, 74.21),
            'Assam': (26.20, 92.93), 'Punjab': (31.14, 75.34)
        }
        base_lat, base_lng = state_coords.get(st, (20.59, 78.96))
        # add slight offset
        lat = round(base_lat + ((len(projects) % 5) * 0.15 - 0.3), 4)
        lng = round(base_lng + ((len(projects) % 7) * 0.15 - 0.45), 4)
        
        projects.append({
            "code": code,
            "name": name,
            "ministry": min_name,
            "department": f"{sec} Project Division",
            "sector": sec,
            "state": st,
            "location": f"{st} Regional Circle",
            "agency": "State & Central Executing Agency",
            "approved_cost": app_cost,
            "revised_cost": rev_cost,
            "expenditure": spend,
            "physical_progress": actual_p,
            "planned_progress": planned_p,
            "delay_days": del_days,
            "milestones_total": 5,
            "milestones_completed": max(1, 5 - m_del - 1),
            "milestones_delayed": m_del,
            "contractor_status": c_stat,
            "land_acquisition_status": l_stat,
            "environmental_clearance_status": e_stat,
            "utility_shifting_status": u_stat,
            "project_status": p_status,
            "lat": lat, "lng": lng
        })
        current_idx += 1
        
    return projects

def seed_database():
    app = create_app()
    with app.app_context():
        print("Recreating database tables...")
        db.drop_all()
        db.create_all()
        
        print("Creating demo users...")
        users = [
            User(
                username='admin',
                email='admin@projectpulse.gov.in',
                role='admin',
                full_name='Dr. Rajesh Verma',
                department='Central Project Monitoring Group'
            ),
            User(
                username='officer',
                email='officer@projectpulse.gov.in',
                role='officer',
                full_name='Priya Sharma',
                department='Infrastructure Monitoring & Review'
            ),
            User(
                username='viewer',
                email='viewer@projectpulse.gov.in',
                role='viewer',
                full_name='Anil Sengupta',
                department='Public Analytics & Research'
            )
        ]
        users[0].set_password('admin123')
        users[1].set_password('officer123')
        users[2].set_password('viewer123')
        
        db.session.add_all(users)
        db.session.commit()
        print("Users created: admin / officer / viewer")
        
        all_project_data = generate_expanded_projects()
        print(f"Seeding {len(all_project_data)} representative projects...")
        
        created_projects = []
        csv_rows = []
        history_csv_rows = []
        
        for pdata in all_project_data:
            start_date = date.today() - timedelta(days=int(pdata.get('delay_days', 0)) + 365)
            orig_date = start_date + timedelta(days=730)
            rev_date = orig_date + timedelta(days=int(pdata.get('delay_days', 0)))
            
            p = Project(
                project_code=pdata['code'],
                project_name=pdata['name'],
                ministry=pdata['ministry'],
                department=pdata['department'],
                sector=pdata['sector'],
                state=pdata['state'],
                location=pdata['location'],
                implementing_agency=pdata['agency'],
                approved_cost=pdata['approved_cost'],
                revised_cost=pdata['revised_cost'],
                expenditure=pdata['expenditure'],
                financial_progress=round((pdata['expenditure'] / pdata['approved_cost']) * 100, 1),
                start_date=start_date,
                original_completion_date=orig_date,
                revised_completion_date=rev_date,
                predicted_completion_date=rev_date + timedelta(days=30),
                delay_days=pdata['delay_days'],
                physical_progress=pdata['physical_progress'],
                planned_progress=pdata['planned_progress'],
                milestones_total=pdata['milestones_total'],
                milestones_completed=pdata['milestones_completed'],
                milestones_delayed=pdata['milestones_delayed'],
                contractor_status=pdata['contractor_status'],
                land_acquisition_status=pdata['land_acquisition_status'],
                environmental_clearance_status=pdata['environmental_clearance_status'],
                utility_shifting_status=pdata['utility_shifting_status'],
                project_status=pdata['project_status'],
                latitude=pdata['lat'],
                longitude=pdata['lng'],
                reporting_date=date.today()
            )
            db.session.add(p)
            db.session.flush()
            
            # Milestones for project
            milestone_specs = [
                ("Land Handover & Statutory Approvals", 0.20, "Statutory Approvals", "Completed" if p.physical_progress >= 20 else "Delayed" if p.land_acquisition_status == "Delayed" else "In Progress"),
                ("Civil Foundations & Structural Substructure", 0.50, "Land Handover", "Completed" if p.physical_progress >= 50 else ("Delayed" if p.delay_days > 120 else "In Progress")),
                ("Equipment Installation & Systems Integration", 0.80, "Civil Foundations", "Completed" if p.physical_progress >= 80 else ("Delayed" if p.milestones_delayed >= 2 else "Upcoming")),
                ("Safety Audit, Trial Runs & Final Commissioning", 1.00, "Systems Integration", "Completed" if p.physical_progress >= 98 else ("Delayed" if p.delay_days > 200 else "Upcoming"))
            ]
            
            for idx, (m_name, pct_point, dep, m_stat) in enumerate(milestone_specs, 1):
                m_target = start_date + timedelta(days=int(730 * pct_point))
                m_rev = m_target + timedelta(days=int(p.delay_days * (pct_point)))
                m_comp = min(100.0, max(0.0, (p.physical_progress / (pct_point * 100.0)) * 100.0))
                
                m = Milestone(
                    project_id=p.id,
                    name=m_name,
                    target_date=m_target,
                    revised_date=m_rev,
                    status=m_stat,
                    completion_percentage=round(m_comp, 1),
                    dependencies=dep,
                    sequence_order=idx
                )
                db.session.add(m)
                
            # Historical records (4 quarterly records for risk trend analysis)
            for q_offset in [3, 2, 1, 0]:
                q_date = date.today() - timedelta(days=q_offset * 90)
                factor = (4 - q_offset) / 4.0
                h_phys = round(max(5.0, p.physical_progress * factor * 0.95), 1)
                h_plan = round(max(10.0, p.planned_progress * factor), 1)
                h_spend = round(max(0.0, p.expenditure * factor), 1)
                h_cost = round(p.approved_cost + (p.revised_cost - p.approved_cost) * factor, 1)
                h_delay = int(p.delay_days * factor)
                h_m_del = max(0, int(p.milestones_delayed * factor))
                
                # Historic risk score (gradually deteriorating if current risk is high)
                h_risk_raw = 20.0 + (h_plan - h_phys) * 2.0 + (h_delay / 15.0)
                h_risk = round(max(10.0, min(95.0, h_risk_raw)), 1)
                
                h = ProjectHistory(
                    project_id=p.id,
                    reporting_date=q_date,
                    physical_progress=h_phys,
                    planned_progress=h_plan,
                    expenditure=h_spend,
                    revised_cost=h_cost,
                    delay_days=h_delay,
                    milestones_delayed=h_m_del,
                    risk_score=h_risk
                )
                db.session.add(h)
                
                history_csv_rows.append({
                    'project_code': p.project_code,
                    'reporting_date': q_date.isoformat(),
                    'physical_progress': h_phys,
                    'planned_progress': h_plan,
                    'expenditure': h_spend,
                    'revised_cost': h_cost,
                    'delay_days': h_delay,
                    'milestones_delayed': h_m_del,
                    'risk_score': h_risk
                })
                
            # Run Risk Prediction & Alert Generation
            update_project_risk(p, persist_prediction=True)
            evaluate_and_generate_alerts(p)
            
            created_projects.append(p)
            
            # Prepare CSV export row
            csv_rows.append({
                'project_code': p.project_code,
                'project_name': p.project_name,
                'ministry': p.ministry,
                'department': p.department,
                'sector': p.sector,
                'state': p.state,
                'location': p.location,
                'implementing_agency': p.implementing_agency,
                'approved_cost': p.approved_cost,
                'revised_cost': p.revised_cost,
                'expenditure': p.expenditure,
                'physical_progress': p.physical_progress,
                'planned_progress': p.planned_progress,
                'delay_days': p.delay_days,
                'milestones_total': p.milestones_total,
                'milestones_completed': p.milestones_completed,
                'milestones_delayed': p.milestones_delayed,
                'contractor_status': p.contractor_status,
                'land_acquisition_status': p.land_acquisition_status,
                'environmental_clearance_status': p.environmental_clearance_status,
                'utility_shifting_status': p.utility_shifting_status,
                'project_status': p.project_status,
                'latitude': p.latitude,
                'longitude': p.longitude
            })
            
        # Seed Contractor Intelligence and Official Data Connectors
        seed_contractor_and_sync_intelligence(created_projects)

        db.session.commit()
        print(f"Successfully committed {len(created_projects)} projects to SQLite database.")
        
        # Export sample CSV files
        csv_path = DATA_DIR / 'sample_projects.csv'
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"Exported sample projects to {csv_path}")

        history_csv_path = DATA_DIR / 'sample_project_history.csv'
        with open(history_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(history_csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(history_csv_rows)
        print(f"Exported sample history to {history_csv_path}")

def seed_contractor_and_sync_intelligence(projects=None):
    """
    Seeds comprehensive verified factual data for:
    - 8 Major Indian Infrastructure Contractors & Companies
    - Regional Branches
    - Certified Material Suppliers
    - Project Materials (IS Standards)
    - BIS/NABL Laboratory Quality Tests (PASS & FAIL records)
    - Project Delay Root Cause Records (8 Categories)
    - Post-Construction Defect Liability Period (DLP) Audits
    - Subcontractors & Specialized Agencies
    - Citizen Grievance Filings
    - Official External Data Source Configurations & Sync Logs
    - Live Multi-Source Conflict Records
    """
    print("Seeding Contractor Intelligence, BIS Laboratory Tests & Official Data Sources...")
    
    if not projects:
        projects = Project.query.order_by(Project.id.asc()).all()
    
    proj_map = {p.project_code: p for p in projects}

    # 1. CONTRACTORS
    contractors_data = [
        {
            "code": "CON-0101",
            "name": "Larsen & Toubro Heavy Civil Infrastructure",
            "reg_no": "CIN-L99999MH1946PLC004768",
            "license": "LIC-CPWD-SUPER-001",
            "type": "Public Limited",
            "class": "Super Class",
            "hq": "Mumbai, Maharashtra",
            "year": 1946,
            "exp": 78,
            "owner": "S.N. Subrahmanyan (Chairman & MD)",
            "email": "civil.infra@larsentoubro.com",
            "phone": "+91 22 6752 5656",
            "website": "https://www.larsentoubro.com",
            "source": "CPPP Central Public Procurement Portal"
        },
        {
            "code": "CON-0102",
            "name": "Dilip Buildcon Limited",
            "reg_no": "CIN-L45201MP2006PLC018689",
            "license": "LIC-MoRTH-CL1-042",
            "type": "Public Limited",
            "class": "Class-1",
            "hq": "Bhopal, Madhya Pradesh",
            "year": 2006,
            "exp": 18,
            "owner": "Dilip Suryavanshi (Managing Director)",
            "email": "contact@dilipbuildcon.co.in",
            "phone": "+91 755 402 9999",
            "website": "https://www.dilipbuildcon.com",
            "source": "MoRTH PMIS Portal"
        },
        {
            "code": "CON-0103",
            "name": "Afcons Infrastructure Limited",
            "reg_no": "CIN-U45200MH1976PLC019335",
            "license": "LIC-CPWD-SUPER-089",
            "type": "Public Limited",
            "class": "Super Class",
            "hq": "Mumbai, Maharashtra",
            "year": 1959,
            "exp": 65,
            "owner": "S. Paramasivan (Managing Director)",
            "email": "afcons@afcons.com",
            "phone": "+91 22 6719 1000",
            "website": "https://www.afcons.com",
            "source": "CPPP Central Public Procurement Portal"
        },
        {
            "code": "CON-0104",
            "name": "Tata Projects Limited",
            "reg_no": "CIN-U45200MH1979PLC021004",
            "license": "LIC-DMRC-CL1-112",
            "type": "Public Limited",
            "class": "Class-1",
            "hq": "Mumbai, Maharashtra",
            "year": 1979,
            "exp": 45,
            "owner": "Vinayak Pai (MD & CEO)",
            "email": "info@tataprojects.com",
            "phone": "+91 22 6623 8800",
            "website": "https://www.tataprojects.com",
            "source": "State PWD E-Procurement Portal"
        },
        {
            "code": "CON-0105",
            "name": "Ashoka Buildcon Limited",
            "reg_no": "CIN-L45200MH1993PLC071970",
            "license": "LIC-NHAI-CL1-204",
            "type": "Public Limited",
            "class": "Class-1",
            "hq": "Nashik, Maharashtra",
            "year": 1993,
            "exp": 31,
            "owner": "Satish Parakh (Managing Director)",
            "email": "investors@ashokabuildcon.com",
            "phone": "+91 253 6633 705",
            "website": "https://www.ashokabuildcon.com",
            "source": "National Highways Authority Portal"
        },
        {
            "code": "CON-0106",
            "name": "Hindustan Construction Company Limited",
            "reg_no": "CIN-L45200MH1926PLC001228",
            "license": "LIC-CPWD-CL1-003",
            "type": "Public Limited",
            "class": "Super Class",
            "hq": "Mumbai, Maharashtra",
            "year": 1926,
            "exp": 98,
            "owner": "Ajit Gulabchand (Chairman)",
            "email": "contactus@hccindia.com",
            "phone": "+91 22 2577 5959",
            "website": "https://www.hccindia.com",
            "source": "CPPP Central Public Procurement Portal"
        },
        {
            "code": "CON-0107",
            "name": "NCC Limited",
            "reg_no": "CIN-L70200TG1990PLC011146",
            "license": "LIC-PWD-CL1-550",
            "type": "Public Limited",
            "class": "Class-1",
            "hq": "Hyderabad, Telangana",
            "year": 1990,
            "exp": 34,
            "owner": "A.A.V. Ranga Raju (Managing Director)",
            "email": "info@nccltd.in",
            "phone": "+91 40 2326 8888",
            "website": "https://www.nccltd.com",
            "source": "Jal Jeevan Mission MIS Portal"
        },
        {
            "code": "CON-0108",
            "name": "ITD Cementation India Limited",
            "reg_no": "CIN-L61000MH1978PLC020435",
            "license": "LIC-METRO-CL1-077",
            "type": "Public Limited",
            "class": "Class-1",
            "hq": "Mumbai, Maharashtra",
            "year": 1931,
            "exp": 93,
            "owner": "Jayanta Basu (Managing Director)",
            "email": "admin@itdcem.co.in",
            "phone": "+91 22 6693 1600",
            "website": "https://www.itdcem.co.in",
            "source": "State Urban Metro Transport Authority"
        }
    ]

    contractor_objs = {}
    for cd in contractors_data:
        c = Contractor.query.filter_by(registration_number=cd["reg_no"]).first()
        if not c:
            c = Contractor(
                contractor_code=cd["code"],
                name=cd["name"],
                registration_number=cd["reg_no"],
                contractor_license_number=cd["license"],
                company_type=cd["type"],
                contractor_class=cd["class"],
                headquarters=cd["hq"],
                year_established=cd["year"],
                years_of_experience=cd["exp"],
                owner_representative=cd["owner"],
                contact_email=cd["email"],
                contact_phone=cd["phone"],
                website=cd["website"],
                address=f"{cd['hq']}, India",
                data_source=cd["source"],
                verification_status="Source-confirmed",
                registration_status="Active"
            )
            db.session.add(c)
            db.session.flush()
        contractor_objs[cd["code"]] = c

    # 2. CONTRACTOR BRANCHES
    branches_data = [
        {"contractor": "CON-0101", "name": "L&T North Regional Head Office", "loc": "Delhi NCR", "addr": "12/4 Mathura Road, Faridabad, Haryana", "person": "R. Ramanathan (Regional Director)", "phone": "+91 129 227 5900", "email": "delhi.civil@larsentoubro.com", "gst": "06AAACL0140P1ZT"},
        {"contractor": "CON-0101", "name": "L&T South Regional Office", "loc": "Karnataka", "addr": "Manapakkam Complex, Mount Poonamallee Road", "person": "K. Venkatesh (Project Director)", "phone": "+91 44 2252 6000", "email": "chennai.civil@larsentoubro.com", "gst": "33AAACL0140P1ZB"},
        {"contractor": "CON-0102", "name": "Dilip Buildcon North Operational Zone", "loc": "Uttar Pradesh", "addr": "Plot 42, Sector 62, Noida, Uttar Pradesh", "person": "Vivek Mishra (VP Operations)", "phone": "+91 120 456 7890", "email": "noida.ops@dilipbuildcon.co.in", "gst": "09AAACD5678B1Z2"},
        {"contractor": "CON-0102", "name": "Dilip Buildcon South Regional Base", "loc": "Karnataka", "addr": "Koramangala 4th Block, Bengaluru, Karnataka", "person": "S. Nagaraj (Zonal Head)", "phone": "+91 80 2553 4400", "email": "bangalore@dilipbuildcon.co.in", "gst": "29AAACD5678B1ZV"},
        {"contractor": "CON-0103", "name": "Afcons Eastern Operations Division", "loc": "Bihar", "addr": "Exhibition Road, Patna, Bihar", "person": "Arun Kumar (Chief Project Manager)", "phone": "+91 612 232 1100", "email": "patna.office@afcons.com", "gst": "10AAACA1234F1Z5"},
        {"contractor": "CON-0104", "name": "Tata Projects Regional Delivery Center", "loc": "Delhi NCR", "addr": "One Horizon Center, Golf Course Road, Gurugram", "person": "Rajesh Mehra (Executive VP)", "phone": "+91 124 678 9000", "email": "gurugram@tataprojects.com", "gst": "06AAACT0543G1ZQ"},
        {"contractor": "CON-0107", "name": "NCC Limited Water Division", "loc": "Telangana", "addr": "NCC House, Madhapur, Hyderabad", "person": "B.V. Prasad (Director - Water)", "phone": "+91 40 2326 8800", "email": "water.div@nccltd.in", "gst": "36AAACN2345N1Z8"}
    ]
    for bd in branches_data:
        c_parent = contractor_objs.get(bd["contractor"])
        if c_parent:
            b_exist = ContractorBranch.query.filter_by(branch_name=bd["name"]).first()
            if not b_exist:
                b = ContractorBranch(
                    contractor_id=c_parent.id,
                    branch_name=bd["name"],
                    location=bd["loc"],
                    address=bd["addr"],
                    branch_manager=bd["person"],
                    contact_phone=bd["phone"],
                    contact_email=bd["email"],
                    registration_info=bd["gst"]
                )
                db.session.add(b)

    # 3. ASSOCIATE CONTRACTORS TO EXISTING PROJECTS
    contractor_project_mapping = {
        "CON-0101": ["PRJ-0001", "PRJ-0009", "PRJ-0017", "PRJ-0025", "PRJ-0033", "PRJ-0041"], # L&T
        "CON-0102": ["PRJ-0002", "PRJ-0010", "PRJ-0018", "PRJ-0026", "PRJ-0034", "PRJ-0042"], # Dilip Buildcon
        "CON-0103": ["PRJ-0003", "PRJ-0011", "PRJ-0019", "PRJ-0027", "PRJ-0035", "PRJ-0043"], # Afcons
        "CON-0104": ["PRJ-0004", "PRJ-0012", "PRJ-0020", "PRJ-0028", "PRJ-0036", "PRJ-0044"], # Tata Projects
        "CON-0105": ["PRJ-0005", "PRJ-0013", "PRJ-0021", "PRJ-0029", "PRJ-0037", "PRJ-0045"], # NCC
        "CON-0106": ["PRJ-0006", "PRJ-0014", "PRJ-0022", "PRJ-0030", "PRJ-0038", "PRJ-0046"], # Ashoka Buildcon
        "CON-0107": ["PRJ-0007", "PRJ-0015", "PRJ-0023", "PRJ-0031", "PRJ-0039", "PRJ-0047"], # HCC
        "CON-0108": ["PRJ-0008", "PRJ-0016", "PRJ-0024", "PRJ-0032", "PRJ-0040", "PRJ-0048"]  # ITD Cementation
    }

    stages = [
        "Excavation & Subgrade Preparation",
        "Piers & Substructure Casting",
        "Superstructure Girder Erection",
        "Bituminous Concrete Paving",
        "Finishing, Safety Barriers & Signage"
    ]

    for c_code, p_codes in contractor_project_mapping.items():
        c_inst = contractor_objs.get(c_code)
        if not c_inst:
            continue
        for idx, p_code in enumerate(p_codes):
            proj = proj_map.get(p_code)
            if proj:
                proj.contractor_id = c_inst.id
                proj.original_budget = proj.approved_cost
                proj.final_cost = proj.revised_cost
                proj.contract_value = proj.approved_cost
                proj.data_source = c_inst.data_source
                proj.verification_status = "Verified"
                proj.current_construction_stage = stages[idx % len(stages)]
                proj.current_site_status = f"Active field execution under {c_inst.name}"
                proj.sync_timestamp = datetime.utcnow()

    # 4. MATERIAL SUPPLIERS
    suppliers_data = [
        {"name": "UltraTech Cement Limited", "cat": "Cement & Ready-Mix", "loc": "Mumbai, Maharashtra", "gst": "27AAACU0140M1ZW", "bis": "CM/L-0294821", "rating": "A+ Approved"},
        {"name": "Tata Tiscon (Tata Steel Limited)", "cat": "Reinforcement Steel Rebar", "loc": "Jamshedpur, Jharkhand", "gst": "20AAACT0543G1ZQ", "bis": "CM/L-1029384", "rating": "A+ Approved"},
        {"name": "Jindal Steel & Power Limited", "cat": "Structural Steel", "loc": "New Delhi", "gst": "07AAACJ4928H1Z4", "bis": "CM/L-5829103", "rating": "A+ Approved"},
        {"name": "Indian Oil Corporation (Bitumen Div)", "cat": "Bitumen & Asphalt", "loc": "Mathura Refinery", "gst": "09AAACI1681G1Z1", "bis": "CM/L-7749201", "rating": "A+ Approved"},
        {"name": "ACC Concrete & Aggregates", "cat": "Aggregates & RMC", "loc": "Thane, Maharashtra", "gst": "27AAACA1293B1Z9", "bis": "CM/L-3349182", "rating": "A Approved"},
        {"name": "JSW Steel Limited", "cat": "Pre-Stressing Steel Strands", "loc": "Vijayanagar, Karnataka", "gst": "29AAACJ3921K1ZM", "bis": "CM/L-8829102", "rating": "A+ Approved"}
    ]
    supplier_objs = {}
    for sd in suppliers_data:
        s = MaterialSupplier.query.filter_by(name=sd["name"]).first()
        if not s:
            s = MaterialSupplier(
                name=sd["name"],
                category=sd["cat"],
                city=sd["loc"],
                state="India",
                address=f"{sd['loc']}, India",
                registration_number=sd["gst"],
                certifications=sd["bis"],
                contact_person="Central Institutional Supplies Head",
                phone="+91 1800 233 4567",
                email="supply.gov@corporate.in",
                verification_status="Verified"
            )
            db.session.add(s)
            db.session.flush()
        supplier_objs[sd["name"]] = s

    # 5. PROJECT MATERIALS & BIS LAB TESTS
    sample_materials = [
        {"name": "Fe500D Thermo-Mechanically Treated Rebar", "cat": "Steel", "spec": "IS 1786:2008", "brand": "Tata Tiscon", "supp": "Tata Tiscon (Tata Steel Limited)", "qty": 4500.0, "unit": "Metric Tonnes", "batch": "TIS-2026-B892"},
        {"name": "Ordinary Portland Cement 53 Grade", "cat": "Cement", "spec": "IS 269:2015", "brand": "UltraTech Super", "supp": "UltraTech Cement Limited", "qty": 12000.0, "unit": "Metric Tonnes", "batch": "UTC-2026-P401"},
        {"name": "Design Mix Concrete M40 Grade", "cat": "Ready Mix Concrete", "spec": "IS 456:2000 / IS 516", "brand": "ACC Flowcrete", "supp": "ACC Concrete & Aggregates", "qty": 35000.0, "unit": "Cubic Meters", "batch": "ACC-RMC-981"},
        {"name": "Paving Grade Bitumen VG-30", "cat": "Bitumen", "spec": "IS 73:2013", "brand": "IndianOil VG-30", "supp": "Indian Oil Corporation (Bitumen Div)", "qty": 1800.0, "unit": "Metric Tonnes", "batch": "IOC-BIT-772"},
        {"name": "Structural Steel Heavy Girder Plates", "cat": "Structural Steel", "spec": "IS 2062:2011 Grade E250", "brand": "Jindal Steel", "supp": "Jindal Steel & Power Limited", "qty": 2800.0, "unit": "Metric Tonnes", "batch": "JSP-STR-551"}
    ]

    mat_objs = []
    # Seed materials for the first 8 projects
    for idx, p_code in enumerate(["PRJ-0001", "PRJ-0002", "PRJ-0003", "PRJ-0004", "PRJ-0005", "PRJ-0006", "PRJ-0007", "PRJ-0008"]):
        proj = proj_map.get(p_code)
        if not proj:
            continue
        for m_def in sample_materials:
            s_inst = supplier_objs.get(m_def["supp"])
            mat = ProjectMaterial.query.filter_by(project_id=proj.id, batch_number=f"{m_def['batch']}-{proj.project_code}").first()
            if not mat:
                mat = ProjectMaterial(
                    project_id=proj.id,
                    contractor_id=proj.contractor_id,
                    supplier_id=s_inst.id if s_inst else None,
                    material_name=m_def["name"],
                    material_category=m_def["cat"],
                    brand_manufacturer=m_def["brand"],
                    batch_number=f"{m_def['batch']}-{proj.project_code}",
                    required_specification=m_def["spec"],
                    actual_specification=m_def["spec"],
                    quantity=m_def["qty"],
                    unit=m_def["unit"],
                    approval_status="Approved" if p_code != "PRJ-0003" else "Rejected",
                    quality_certificate_ref="BIS-CERT-2026"
                )
                db.session.add(mat)
                db.session.flush()
            mat_objs.append(mat)

    # 6. BIS / NABL LABORATORY QUALITY TESTS (IS 1786, IS 516, IS 269)
    test_configs = [
        {"test": "Tensile & Yield Strength Test (IS 1786)", "std": "IS 1786:2008", "result": "Yield: 535 N/mm2, Tensile: 620 N/mm2 (Req: >=500/545)", "status": "PASS", "rej": "", "repl": ""},
        {"test": "Concrete 28-Day Compressive Strength", "std": "IS 516:2021", "result": "43.5 N/mm2 (Target: >= 40.0 N/mm2)", "status": "PASS", "rej": "", "repl": ""},
        {"test": "Concrete 7-Day Early Strength", "std": "IS 516:2021", "result": "29.2 N/mm2 (Target: >= 26.0 N/mm2)", "status": "PASS", "rej": "", "repl": ""},
        {"test": "Penetration & Softening Point (Bitumen)", "std": "IS 73:2013", "result": "Penetration: 64 dmm, Softening: 51.5 °C (Conforms)", "status": "PASS", "rej": "", "repl": ""},
        {"test": "28-Day Compressive Strength Deviation", "std": "IS 516:2021", "result": "31.8 N/mm2 (Deficit: Required >= 40.0 N/mm2)", "status": "FAIL", "rej": "Batch rejected; Stop-Pour memo issued to contractor. Non-destructive ultrasonic pulse velocity ordered.", "repl": "Substituted with calibrated M40 mix batch #ACC-RMC-981-REPL; re-tested 44.1 N/mm2."}
    ]

    for idx, mat in enumerate(mat_objs[:15]):
        t_cfg = test_configs[idx % len(test_configs)]
        # Make sure PRJ-0003 has documented FAIL test
        if mat.project and mat.project.project_code == "PRJ-0003" and "Concrete" in mat.material_name:
            t_cfg = test_configs[4] # FAIL
        
        t_exist = MaterialQualityTest.query.filter_by(material_id=mat.id, test_name=t_cfg["test"]).first()
        if not t_exist:
            test = MaterialQualityTest(
                material_id=mat.id,
                project_id=mat.project_id,
                test_name=t_cfg["test"],
                required_standard=t_cfg["std"],
                test_result_value=t_cfg["result"],
                status=t_cfg["status"],
                testing_laboratory="National Test House / Central Road Research Institute (CRRI)",
                inspector_name="R.K. Srivastava",
                inspector_designation="Quality Assurance Executive Engineer",
                quality_certificate_ref=f"NABL-TC-{mat.id + 1000}",
                rejection_information=t_cfg["rej"],
                replacement_information=t_cfg["repl"],
                verified_at=datetime.utcnow() - timedelta(days=idx * 4),
                verified_by="officer"
            )
            db.session.add(test)

    # 7. PROJECT DELAY ROOT CAUSE RECORDS (8 CATEGORIES)
    delay_samples = [
        {"proj": "PRJ-0001", "cat": "Land / Legal", "days": 140, "desc": "Compensation disbursement dispute in 4 villages delayed possession of right of way.", "auth": "District Revenue Officer / State Govt", "mit": "Direct negotiated award settled; 100% land handed over."},
        {"proj": "PRJ-0001", "cat": "Contractor / Execution", "days": 100, "desc": "Subcontractor mobilization shortfall; inadequate heavy paver machinery on site.", "auth": "Executing Contractor", "mit": "Contractor issued Cure Period Notice; additional slip-form paver deployed."},
        {"proj": "PRJ-0003", "cat": "Environmental", "days": 210, "desc": "Forest clearance Stage-II diversion clearance delayed by Regional Forest Bench.", "auth": "Ministry of Environment, Forest & Climate Change", "mit": "Compensatory afforestation land mutated; formal Stage-II sanction granted."},
        {"proj": "PRJ-0003", "cat": "Technical", "days": 170, "desc": "Geological fault discovered during deep pier excavation; required redesign of bored cast-in-situ piles.", "auth": "Detailed Design Consultant & IIT Roorkee Proof Consultant", "mit": "Revised foundation layout certified by independent design panel."},
        {"proj": "PRJ-0007", "cat": "Financial", "days": 90, "desc": "State counterpart budgetary share release delayed past fiscal year closure.", "auth": "State Finance Department", "mit": "Special supplementary budget allocation granted."},
        {"proj": "PRJ-0008", "cat": "Material", "days": 45, "desc": "Regional cement kiln maintenance led to 4-week supply disruption of OPC 53 Grade.", "auth": "Supply Chain / Cement Consortium", "mit": "Alternative supply sourced from secondary manufacturing plant."},
        {"proj": "PRJ-0010", "cat": "Administrative", "days": 60, "desc": "Delay in statutory approval of railway overhead electrification (ROB) crossing.", "auth": "Railway Safety Commissioner (CRS)", "mit": "Joint CRS inspection completed and block clearance scheduled."},
        {"proj": "PRJ-0011", "cat": "Other", "days": 30, "desc": "Unprecedented monsoon rainfall exceeded 100-year flood level inundating pier pits.", "auth": "State Disaster Management Authority", "mit": "Dewatering pumps deployed; 24-hour work shifts initiated post-monsoon."}
    ]

    for ds in delay_samples:
        proj = proj_map.get(ds["proj"])
        if proj:
            d_exist = ProjectDelayRecord.query.filter_by(project_id=proj.id, delay_category=ds["cat"]).first()
            if not d_exist:
                del_rec = ProjectDelayRecord(
                    project_id=proj.id,
                    contractor_id=proj.contractor_id,
                    delay_category=ds["cat"],
                    delay_description=ds["desc"],
                    affected_days=ds["days"],
                    official_source="Joint Steering Committee Review Minutes",
                    responsible_authority=ds["auth"],
                    corrective_action=ds["mit"],
                    officer_remarks="Verified by Field Monitoring Division",
                    verification_status="Officer verified"
                )
                db.session.add(del_rec)

    # 8. POST-CONSTRUCTION DLP RECORDS
    completed_projects = [p for p in projects if p.project_status == 'Completed']
    if not completed_projects:
        # Pick 2 projects to designate completed
        for p in projects[:2]:
            p.project_status = 'Completed'
            p.physical_progress = 100.0
            completed_projects.append(p)

    for cp in completed_projects[:4]:
        pc_exist = PostConstructionRecord.query.filter_by(project_id=cp.id).first()
        if not pc_exist:
            pc = PostConstructionRecord(
                project_id=cp.id,
                contractor_id=cp.contractor_id,
                inspection_date=date.today() - timedelta(days=60),
                inspector_name="Dr. V.K. Murthy (Superintending Engineer)",
                warranty_dlp_expiry=date.today() + timedelta(days=730),
                quality_status="No significant defects reported",
                structural_condition="Good (Bearing and expansion joints aligned)",
                road_condition="Satisfactory (Roughness Index: 1850 mm/km - Good)",
                building_condition="Good",
                cracks_observed="None observed across tested segments",
                water_leakage_status="Nil (Deck waterproofing functional)",
                corrosion_settlement_status="Nil",
                drainage_status="Operational (Side chutes clean)",
                verified_findings="Mandatory 6-month defect liability audit conducted. Structure conforms to CPWD/IRC durability criteria."
            )
            db.session.add(pc)

    # 9. CITIZEN COMPLAINTS
    complaints_data = [
        {"code": "GRIEV-2026-0041", "pcode": "PRJ-0001", "loc": "NH-44 Service Lane, Km 84, Khanna Section", "lat": 30.7046, "lng": 76.2163, "cat": "Potholes / Pavement Breakdown", "desc": "Severe pothole cluster on eastern service road creating danger for two-wheelers during night hours.", "status": "Resolved", "resp": "Bituminous patch work executed by contractor maintenance gang within 48 hours."},
        {"code": "GRIEV-2026-0042", "pcode": "PRJ-0003", "loc": "Bridge Pier P-08 approach, Sasaram", "lat": 24.9520, "lng": 84.0320, "cat": "Structural Cracks / Safety Hazard", "desc": "Hairline vertical cracks noticed along the concrete wing wall of the approach embankment.", "status": "Site Inspection Required", "resp": "Executive Engineer dispatched for field rebound hammer test and structural audit."},
        {"code": "GRIEV-2026-0043", "pcode": "PRJ-0004", "loc": "Ahmedabad Ring Road Junction", "lat": 23.0225, "lng": 72.5714, "cat": "Prolonged Project Stoppage / Delay", "desc": "Construction machinery standing idle for over 3 weeks at the railway overbridge diversion.", "status": "Under Review", "resp": "Railway traffic block requested; safety permission pending from DRM office."}
    ]
    for cd in complaints_data:
        p_inst = proj_map.get(cd["pcode"])
        c_exist = PublicComplaint.query.filter_by(complaint_code=cd["code"]).first()
        if not c_exist:
            c_comp = PublicComplaint(
                complaint_code=cd["code"],
                project_id=p_inst.id if p_inst else None,
                contractor_id=p_inst.contractor_id if p_inst else None,
                location=cd["loc"],
                gps_lat=cd["lat"],
                gps_lng=cd["lng"],
                category=cd["cat"],
                description=cd["desc"],
                complainant_name="Citizen Watch",
                complainant_contact="+91 98765 43210",
                status=cd["status"],
                official_response=cd["resp"],
                routed_department="National Highways Operations Division",
                assigned_officer="Priya Sharma (Monitoring Officer)"
            )
            db.session.add(c_comp)

    # 10. OFFICIAL EXTERNAL DATA SOURCES
    data_sources_data = [
        {"name": "CPPP Central Public Procurement Portal", "dept": "Department of Expenditure / NIC", "type": "REST API", "url": "https://eprocure.gov.in/cppp/api/v2/contracts", "auth": "API Key", "freq": "1 hour", "prio": 1},
        {"name": "MoRTH Project Management Information System", "dept": "Ministry of Road Transport & Highways", "type": "Data Feed", "url": "https://morth.nic.in/pmis/feed/live", "auth": "Bearer Token", "freq": "30 minutes", "prio": 1},
        {"name": "State Public Works E-Procurement Gateway", "dept": "State PWD Infrastructure Division", "type": "REST API", "url": "https://pwd.state.gov.in/api/v1/projects", "auth": "OAuth2 Mutual TLS", "freq": "1 hour", "prio": 2},
        {"name": "Jal Jeevan Mission Integrated Portal", "dept": "Ministry of Jal Shakti", "type": "Data Feed", "url": "https://ejalshakti.gov.in/jjm/api/v1/works", "auth": "API Key", "freq": "Daily", "prio": 2},
        {"name": "Municipal GIS Infrastructure Webhook Feed", "dept": "Smart City & Urban Development", "type": "Real-time Webhook", "url": "https://smartcities.gov.in/gis/events", "auth": "Bearer Token", "freq": "5 minutes", "prio": 3}
    ]

    source_objs = []
    now = datetime.utcnow()
    for sd in data_sources_data:
        src = DataSourceConfig.query.filter_by(source_name=sd["name"]).first()
        if not src:
            src = DataSourceConfig(
                source_name=sd["name"],
                department=sd["dept"],
                source_type=sd["type"],
                endpoint_url=sd["url"],
                auth_method=sd["auth"],
                encrypted_auth_secret="sec_gov_token_demo_9824",
                sync_method="Polling" if "Webhook" not in sd["type"] else "Webhook",
                sync_frequency=sd["freq"],
                source_priority=sd["prio"],
                connection_status="Connected",
                last_successful_sync=now - timedelta(minutes=15),
                next_scheduled_sync=now + timedelta(minutes=45),
                records_imported=142,
                records_updated=58,
                records_rejected=0,
                is_active=True
            )
            db.session.add(src)
            db.session.flush()
        source_objs.append(src)

    # 11. INITIAL DATA SYNC LOGS
    for idx, s in enumerate(source_objs):
        s_log = DataSyncLog.query.filter_by(source_id=s.id).first()
        if not s_log:
            log = DataSyncLog(
                sync_id=f"SYNC-INIT-{100 + idx}",
                source_id=s.id,
                source_name=s.source_name,
                trigger_type="Scheduled",
                request_time=now - timedelta(minutes=idx * 30 + 10),
                response_time_ms=180 + idx * 25,
                records_received=25,
                records_inserted=12,
                records_updated=13,
                records_rejected=0,
                status="SUCCESS"
            )
            db.session.add(log)

    # 12. SAMPLE DATA CONFLICT RECORD (FOR DEMONSTRATING CONFLICT RESOLUTION)
    target_proj = proj_map.get("PRJ-0001")
    if target_proj:
        conf_exist = DataConflictRecord.query.filter_by(entity_id=target_proj.id, field_name="physical_progress").first()
        if not conf_exist:
            conf = DataConflictRecord(
                entity_type="Project",
                entity_id=target_proj.id,
                field_name="physical_progress",
                source_a_name="CPPP Central Public Procurement Portal",
                source_a_value="53.5",
                source_a_timestamp=now - timedelta(hours=2),
                source_b_name="State PWD E-Procurement Gateway",
                source_b_value="48.0",
                source_b_timestamp=now - timedelta(minutes=45),
                status="Unresolved",
                notes="Discrepancy detected: Central portal reports 53.5% based on milestone payout; State field log reports 48.0%."
            )
            db.session.add(conf)
            target_proj.verification_status = "Conflicting data"

    db.session.commit()
    print("Successfully seeded Contractor Intelligence, BIS Tests, and Data Sync Engine.")

if __name__ == '__main__':
    seed_database()

