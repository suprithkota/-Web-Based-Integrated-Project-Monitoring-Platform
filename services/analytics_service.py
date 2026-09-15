from sqlalchemy import func
from database import db
from database.models import Project, Alert

def get_dashboard_kpis(filters=None, project_ids=None):
    """
    Computes all high-level command center KPIs dynamically from the database.
    Supports optional filters: ministry, sector, state, status, risk_level, project_ids.
    """
    query = Project.query
    
    if project_ids is not None:
        query = query.filter(Project.id.in_(project_ids)) if project_ids else query.filter(Project.id == -1)

    if filters:
        if filters.get('ministry'):
            query = query.filter(Project.ministry == filters['ministry'])
        if filters.get('sector'):
            query = query.filter(Project.sector == filters['sector'])
        if filters.get('state'):
            query = query.filter(Project.state == filters['state'])
        if filters.get('status'):
            query = query.filter(Project.project_status == filters['status'])
        if filters.get('risk_level'):
            query = query.filter(Project.risk_level == filters['risk_level'])

    total_projects = query.count()
    ongoing_projects = query.filter(Project.project_status == 'Ongoing').count()
    completed_projects = query.filter(Project.project_status == 'Completed').count()
    delayed_projects = query.filter(Project.project_status.in_(['Delayed', 'Stalled'])).count()
    
    critical_projects = query.filter(Project.risk_level == 'CRITICAL').count()
    high_risk_projects = query.filter(Project.risk_level == 'HIGH').count()
    medium_risk_projects = query.filter(Project.risk_level == 'MEDIUM').count()
    low_risk_projects = query.filter(Project.risk_level == 'LOW').count()
    at_risk_projects = critical_projects + high_risk_projects
    
    cost_stats = db.session.query(
        func.sum(Project.approved_cost),
        func.sum(Project.revised_cost),
        func.sum(Project.expenditure),
        func.avg(Project.physical_progress),
        func.avg(Project.planned_progress),
        func.avg(Project.delay_days),
        func.avg(Project.risk_score),
        func.avg(Project.health_score)
    )
    
    if project_ids is not None:
        cost_stats = cost_stats.filter(Project.id.in_(project_ids)) if project_ids else cost_stats.filter(Project.id == -1)

    # Apply same filters to cost_stats
    if filters:
        if filters.get('ministry'):
            cost_stats = cost_stats.filter(Project.ministry == filters['ministry'])
        if filters.get('sector'):
            cost_stats = cost_stats.filter(Project.sector == filters['sector'])
        if filters.get('state'):
            cost_stats = cost_stats.filter(Project.state == filters['state'])
        if filters.get('status'):
            cost_stats = cost_stats.filter(Project.project_status == filters['status'])
        if filters.get('risk_level'):
            cost_stats = cost_stats.filter(Project.risk_level == filters['risk_level'])

    total_app, total_rev, total_exp, avg_phys, avg_plan, avg_delay, avg_risk, avg_health = cost_stats.first()
    
    total_approved = float(total_app or 0.0)
    total_revised = float(total_rev or 0.0)
    total_expenditure = float(total_exp or 0.0)
    avg_physical = float(avg_phys or 0.0)
    avg_planned = float(avg_plan or 0.0)
    avg_delay_days = float(avg_delay or 0.0)
    avg_risk_score = float(avg_risk or 0.0)
    avg_health_score = float(avg_health or 0.0)
    
    total_cost_escalation = max(0.0, total_revised - total_approved)
    total_cost_escalation_pct = ((total_revised - total_approved) / total_approved * 100.0) if total_approved > 0 else 0.0
    overall_expenditure_utilization = (total_expenditure / total_approved * 100.0) if total_approved > 0 else 0.0
    
    open_alerts_count = Alert.query.filter(Alert.status.in_(['Open', 'Under Review'])).count()
    critical_alerts_count = Alert.query.filter(Alert.status.in_(['Open', 'Under Review']), Alert.severity == 'CRITICAL').count()

    # Explicit indicator keys for dashboard
    projects_on_track = low_risk_projects
    projects_at_risk = high_risk_projects + medium_risk_projects
    
    return {
        'total_projects': total_projects,
        'ongoing_projects': ongoing_projects,
        'completed_projects': completed_projects,
        'delayed_projects': delayed_projects,
        'projects_on_track': projects_on_track,
        'projects_at_risk': projects_at_risk,
        'at_risk_projects': at_risk_projects,
        'critical_projects': critical_projects,
        'high_risk_projects': high_risk_projects,
        'medium_risk_projects': medium_risk_projects,
        'low_risk_projects': low_risk_projects,
        'total_approved_cost': round(total_approved, 2),
        'total_revised_cost': round(total_revised, 2),
        'total_expenditure': round(total_expenditure, 2),
        'total_cost_escalation': round(total_cost_escalation, 2),
        'total_cost_escalation_pct': round(total_cost_escalation_pct, 1),
        'expenditure_utilization_pct': round(overall_expenditure_utilization, 1),
        'avg_physical_progress': round(avg_physical, 1),
        'avg_planned_progress': round(avg_planned, 1),
        'avg_progress_gap': round(max(0.0, avg_planned - avg_physical), 1),
        'avg_delay_days': round(avg_delay_days, 0),
        'avg_risk_score': round(avg_risk_score, 1),
        'avg_health_score': round(avg_health_score, 1),
        'open_alerts_count': open_alerts_count,
        'critical_alerts_count': critical_alerts_count
    }

def get_dashboard_alerts(limit=6, project_ids=None):
    """
    Returns top active early warning alerts categorized by severity
    covering critical projects, schedule delays, budget concerns, and milestones.
    """
    query = Alert.query.filter(Alert.status.in_(['Open', 'Under Review']))
    if project_ids is not None:
        query = query.filter(Alert.project_id.in_(project_ids)) if project_ids else query.filter(Alert.id == -1)

    return query.order_by(
        db.case(
            (Alert.severity == 'CRITICAL', 1),
            (Alert.severity == 'HIGH', 2),
            (Alert.severity == 'MEDIUM', 3),
            else_=4
        ),
        Alert.created_at.desc()
    ).limit(limit).all()

def get_dashboard_recommendations(limit=5, project_ids=None):
    """
    Returns concise, actionable AI intervention recommendations based on
    calibrated project risk factors and execution bottlenecks.
    """
    from services.recommendation_service import generate_project_recommendations
    
    base_q = Project.query
    if project_ids is not None:
        base_q = base_q.filter(Project.id.in_(project_ids)) if project_ids else base_q.filter(Project.id == -1)

    projects = base_q.filter(Project.risk_level.in_(['CRITICAL', 'HIGH'])).order_by(
        Project.risk_score.desc()
    ).limit(limit).all()
    
    if not projects:
        projects = base_q.order_by(Project.risk_score.desc()).limit(limit).all()
        
    recommendations = []
    for p in projects:
        p_recs = generate_project_recommendations(p.to_dict())
        if p_recs:
            top_rec = p_recs[0]
            recommendations.append({
                'project_id': p.id,
                'project_code': p.project_code,
                'project_name': p.project_name,
                'sector': p.sector,
                'state': p.state,
                'risk_level': p.risk_level,
                'risk_score': round(p.risk_score, 1),
                'delay_days': p.delay_days,
                'progress_gap': p.progress_gap,
                'cost_escalation': p.cost_escalation,
                'category': top_rec.get('category', 'Schedule Review'),
                'priority': top_rec.get('priority', 'HIGH'),
                'action': top_rec.get('action', 'Initiate Progress Review'),
                'detail': top_rec.get('detail', ''),
                'summary_statement': f"{p.project_name} ({p.project_code}) requires immediate schedule review and {top_rec.get('action', 'intervention').lower()} due to a {p.progress_gap}% progress gap and {p.delay_days} cumulative delay days."
            })
    return recommendations

def get_chart_analytics(project_ids=None):
    """
    Returns aggregated structures ready for Chart.js dashboards.
    Applies role/project_ids scoping and information minimization.
    """
    # 1. Risk Distribution
    risk_q = db.session.query(Project.risk_level, func.count(Project.id))
    if project_ids is not None:
        risk_q = risk_q.filter(Project.id.in_(project_ids)) if project_ids else risk_q.filter(Project.id == -1)
    risk_counts = risk_q.group_by(Project.risk_level).all()
    
    risk_dict = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
    for level, count in risk_counts:
        if level in risk_dict:
            risk_dict[level] = count
            
    # 2. Projects by Ministry (with average risk & approved cost)
    min_q = db.session.query(
        Project.ministry,
        func.count(Project.id),
        func.avg(Project.risk_score),
        func.sum(Project.approved_cost),
        func.sum(Project.expenditure)
    )
    if project_ids is not None:
        min_q = min_q.filter(Project.id.in_(project_ids)) if project_ids else min_q.filter(Project.id == -1)
    ministry_stats = min_q.group_by(Project.ministry).order_by(func.count(Project.id).desc()).limit(8).all()
    
    ministries_data = {
        'labels': [m[0].replace('Ministry of ', '') for m in ministry_stats],
        'counts': [m[1] for m in ministry_stats],
        'avg_risks': [round(float(m[2] or 0), 1) for m in ministry_stats],
        'approved_costs': [round(float(m[3] or 0), 1) for m in ministry_stats]
    }
    
    # 3. Projects by Sector
    sec_q = db.session.query(
        Project.sector,
        func.count(Project.id),
        func.avg(Project.risk_score)
    )
    if project_ids is not None:
        sec_q = sec_q.filter(Project.id.in_(project_ids)) if project_ids else sec_q.filter(Project.id == -1)
    sector_stats = sec_q.group_by(Project.sector).order_by(func.count(Project.id).desc()).all()
    
    sectors_data = {
        'labels': [s[0] for s in sector_stats],
        'counts': [s[1] for s in sector_stats],
        'avg_risks': [round(float(s[2] or 0), 1) for s in sector_stats]
    }
    
    # 4. Projects by State (Top 10)
    st_q = db.session.query(
        Project.state,
        func.count(Project.id),
        func.avg(Project.risk_score)
    )
    if project_ids is not None:
        st_q = st_q.filter(Project.id.in_(project_ids)) if project_ids else st_q.filter(Project.id == -1)
    state_stats = st_q.group_by(Project.state).order_by(func.count(Project.id).desc()).limit(10).all()
    
    states_data = {
        'labels': [st[0] for st in state_stats],
        'counts': [st[1] for st in state_stats],
        'avg_risks': [round(float(st[2] or 0), 1) for st in state_stats]
    }
    
    # 5. Top 10 Delay Risk Projects
    delay_q = Project.query
    if project_ids is not None:
        delay_q = delay_q.filter(Project.id.in_(project_ids)) if project_ids else delay_q.filter(Project.id == -1)
    delay_risk_projects = delay_q.order_by(Project.delay_probability.desc()).limit(10).all()
    top_delay = [{
        'id': p.id,
        'code': p.project_code,
        'name': p.project_name[:32] + ('...' if len(p.project_name) > 32 else ''),
        'delay_prob': round(p.delay_probability, 1),
        'delay_days': p.delay_days,
        'progress_gap': p.progress_gap,
        'risk_level': p.risk_level
    } for p in delay_risk_projects]

    # 6. Top 10 Cost Overrun Risk Projects
    cost_q = Project.query
    if project_ids is not None:
        cost_q = cost_q.filter(Project.id.in_(project_ids)) if project_ids else cost_q.filter(Project.id == -1)
    cost_risk_projects = cost_q.order_by(Project.cost_overrun_probability.desc()).limit(10).all()
    top_cost = [{
        'id': p.id,
        'code': p.project_code,
        'name': p.project_name[:32] + ('...' if len(p.project_name) > 32 else ''),
        'cost_prob': round(p.cost_overrun_probability, 1),
        'cost_escalation': p.cost_escalation,
        'approved': p.approved_cost,
        'revised': p.revised_cost,
        'risk_level': p.risk_level
    } for p in cost_risk_projects]
    
    # 7. Scatter points: Expenditure Utilization vs Physical Progress (Minimally serialized)
    all_q = Project.query
    if project_ids is not None:
        all_q = all_q.filter(Project.id.in_(project_ids)) if project_ids else all_q.filter(Project.id == -1)
    all_projects = all_q.all()
    scatter_points = [{
        'x': round(p.physical_progress, 1),
        'y': round(p.budget_utilization, 1),
        'name': p.project_name[:25],
        'risk_level': p.risk_level
    } for p in all_projects]

    return {
        'risk_distribution': risk_dict,
        'ministries': ministries_data,
        'sectors': sectors_data,
        'states': states_data,
        'top_delay_risk': top_delay,
        'top_cost_risk': top_cost,
        'scatter_points': scatter_points
    }
