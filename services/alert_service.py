from datetime import datetime
from database import db
from database.models import Project, Alert
from services.recommendation_service import generate_project_recommendations

def evaluate_and_generate_alerts(project):
    """
    Evaluates project parameters against early warning thresholds.
    Generates or updates early warning alerts in the database.
    """
    alerts_created = []
    
    physical = float(project.physical_progress or 0.0)
    planned = float(project.planned_progress or 0.0)
    gap = max(0.0, planned - physical)
    
    approved = float(project.approved_cost or 1.0)
    revised = float(project.revised_cost or approved)
    cost_esc = ((revised - approved) / approved * 100.0) if approved > 0 else 0.0
    
    exp = float(project.expenditure or 0.0)
    spend_pct = (exp / approved * 100.0) if approved > 0 else 0.0
    
    recs = generate_project_recommendations(project.to_dict())
    top_rec = recs[0]['detail'] if recs else "Maintain active monitoring."
    
    # Check existing open/under-review alerts to avoid spamming duplicates
    existing_open_triggers = {
        a.trigger: a for a in Alert.query.filter_by(project_id=project.id).filter(Alert.status.in_(['Open', 'Under Review'])).all()
    }
    
    # 1. Critical Delay / Progress Gap Alert
    if gap >= 20.0 or project.delay_days >= 180:
        sev = 'CRITICAL' if gap >= 28.0 or project.delay_days >= 300 else 'HIGH'
        trigger = 'SEVERE_PROGRESS_SLIPPAGE'
        
        if trigger not in existing_open_triggers:
            alert = Alert(
                project_id=project.id,
                severity=sev,
                title=f"Severe Schedule Slippage Detected ({gap:.1f}% Gap, {project.delay_days}d Delay)",
                description=f"Actual physical progress ({physical:.1f}%) is lagging behind planned target ({planned:.1f}%) with {project.delay_days} cumulative delay days.",
                trigger=trigger,
                probability=project.delay_probability or 80.0,
                contributing_factors=f"Progress Gap: {gap:.1f}%, Delay Days: {project.delay_days}, Contractor: {project.contractor_status}",
                recommendation=top_rec,
                status='Open'
            )
            db.session.add(alert)
            alerts_created.append(alert)
            
    # 2. Cost Escalation Alert
    if cost_esc >= 15.0:
        sev = 'CRITICAL' if cost_esc >= 25.0 else 'HIGH'
        trigger = 'HIGH_COST_ESCALATION'
        
        if trigger not in existing_open_triggers:
            alert = Alert(
                project_id=project.id,
                severity=sev,
                title=f"Budget Revision Escalation (+{cost_esc:.1f}%)",
                description=f"Project revised outlay is ₹{revised:,.2f} Cr against approved ₹{approved:,.2f} Cr, reflecting a {cost_esc:.1f}% cost escalation.",
                trigger=trigger,
                probability=project.cost_overrun_probability or 75.0,
                contributing_factors=f"Cost Escalation: +{cost_esc:.1f}%, Approved: ₹{approved:.0f} Cr, Revised: ₹{revised:.0f} Cr",
                recommendation="Convene Standing Committee on Cost Overruns to review root drivers of revised financial outlay.",
                status='Open'
            )
            db.session.add(alert)
            alerts_created.append(alert)

    # 3. Expenditure vs Progress Mismatch
    if (spend_pct - physical) >= 25.0 and physical < 60.0:
        trigger = 'EXPENDITURE_PROGRESS_MISMATCH'
        if trigger not in existing_open_triggers:
            alert = Alert(
                project_id=project.id,
                severity='HIGH',
                title="Expenditure-to-Progress Divergence",
                description=f"Financial disbursement has reached {spend_pct:.1f}% while physical delivery stands at only {physical:.1f}% ({spend_pct - physical:.1f}% gap).",
                trigger=trigger,
                probability=70.0,
                contributing_factors=f"Disbursement: {spend_pct:.1f}%, Physical: {physical:.1f}%",
                recommendation="Audit advance disbursements and correlate upcoming contractor invoices against verified physical inspection records.",
                status='Open'
            )
            db.session.add(alert)
            alerts_created.append(alert)

    # 4. Critical Pre-construction Bottleneck (Land / Clearances)
    if project.land_acquisition_status in ['Delayed', 'Pending'] or project.environmental_clearance_status in ['Delayed', 'Pending']:
        trigger = 'PRE_CONSTRUCTION_STALL'
        if trigger not in existing_open_triggers:
            factors = []
            if project.land_acquisition_status in ['Delayed', 'Pending']:
                factors.append(f"Land Acquisition ({project.land_acquisition_status})")
            if project.environmental_clearance_status in ['Delayed', 'Pending']:
                factors.append(f"Environmental Clearance ({project.environmental_clearance_status})")
                
            alert = Alert(
                project_id=project.id,
                severity='MEDIUM' if project.risk_level != 'CRITICAL' else 'HIGH',
                title="Statutory Clearance & Right-of-Way Impasse",
                description=f"Key pre-construction dependencies remain unfulfilled: {', '.join(factors)}.",
                trigger=trigger,
                probability=65.0,
                contributing_factors=", ".join(factors),
                recommendation="Engage State Nodal Department and Ministry steering committee for fast-track statutory resolution.",
                status='Open'
            )
            db.session.add(alert)
            alerts_created.append(alert)

    # 5. Milestone Cascade Alert
    if project.milestones_delayed >= 3:
        trigger = 'MULTIPLE_MILESTONE_DELAYS'
        if trigger not in existing_open_triggers:
            alert = Alert(
                project_id=project.id,
                severity='HIGH',
                title=f"Multiple Milestone Failures ({project.milestones_delayed} Delayed)",
                description=f"{project.milestones_delayed} out of {project.milestones_total} milestones have breached scheduled delivery deadlines.",
                trigger=trigger,
                probability=project.delay_probability or 80.0,
                contributing_factors=f"Milestones Delayed: {project.milestones_delayed} of {project.milestones_total}",
                recommendation="Initiate critical-path re-baselining with key executing agencies to prevent project delivery date collapse.",
                status='Open'
            )
            db.session.add(alert)
            alerts_created.append(alert)

    return alerts_created

def generate_alerts_for_all():
    projects = Project.query.all()
    total_new = 0
    for p in projects:
        created = evaluate_and_generate_alerts(p)
        total_new += len(created)
    db.session.commit()
    return total_new

def update_alert_status(alert_id, new_status, user_name="Officer", notes=""):
    alert = db.session.get(Alert, alert_id)
    if not alert:
        return None
        
    alert.status = new_status
    if notes:
        existing_notes = alert.notes or ""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        alert.notes = f"{existing_notes}\n[{timestamp}] {user_name} ({new_status}): {notes}".strip()
        
    if new_status == 'Resolved':
        alert.resolved_at = datetime.utcnow()
        alert.resolved_by = user_name
    elif new_status == 'Open':
        alert.resolved_at = None
        alert.resolved_by = ''
        
    db.session.commit()
    return alert
