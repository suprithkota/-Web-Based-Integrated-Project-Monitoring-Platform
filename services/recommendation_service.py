def generate_project_recommendations(project_data):
    """
    Generates actionable, indicator-grounded intervention recommendations
    designed for government monitoring officers.
    Does NOT claim to be official executive orders.
    """
    recs = []
    
    physical_prog = float(project_data.get('physical_progress') or 0.0)
    planned_prog = float(project_data.get('planned_progress') or 0.0)
    gap = max(0.0, planned_prog - physical_prog)
    
    approved_cost = float(project_data.get('approved_cost') or 1.0)
    revised_cost = float(project_data.get('revised_cost') or approved_cost)
    cost_esc = ((revised_cost - approved_cost) / approved_cost * 100.0) if approved_cost > 0 else 0.0
    
    expenditure = float(project_data.get('expenditure') or 0.0)
    budget_util = (expenditure / approved_cost * 100.0) if approved_cost > 0 else 0.0
    
    delay_days = int(project_data.get('delay_days') or 0)
    milestones_delayed = int(project_data.get('milestones_delayed') or 0)
    
    contractor = str(project_data.get('contractor_status') or 'On Track').strip()
    land = str(project_data.get('land_acquisition_status') or 'Completed').strip()
    env = str(project_data.get('environmental_clearance_status') or 'Completed').strip()
    utility = str(project_data.get('utility_shifting_status') or 'Completed').strip()
    
    # 1. Land Acquisition Bottleneck
    if land in ['Delayed', 'Pending']:
        recs.append({
            'priority': 'HIGH',
            'category': 'Land Acquisition',
            'icon': 'fa-map-marked-alt',
            'action': 'Escalate Land Acquisition Dependencies',
            'detail': 'Convene inter-departmental review with district revenue authorities and state nodal officers to expedite pending right-of-way and compensation disbursement.'
        })
    elif land == 'In Progress':
        recs.append({
            'priority': 'MEDIUM',
            'category': 'Land Acquisition',
            'icon': 'fa-map-marked-alt',
            'action': 'Track Land Handover Milestones',
            'detail': 'Monitor remaining land parcel transfers closely to prevent civil works stoppage at key chainages.'
        })
        
    # 2. Contractor Execution
    if contractor in ['Delayed', 'Critical']:
        recs.append({
            'priority': 'CRITICAL' if contractor == 'Critical' else 'HIGH',
            'category': 'Contractor Oversight',
            'icon': 'fa-hard-hat',
            'action': 'Contractor Performance Audit & Recovery Schedule',
            'detail': 'Initiate performance review with EPC contractor management. Demand submission of catch-up schedule and examine machinery/manpower mobilization deficits.'
        })
    elif contractor == 'Minor Delay':
        recs.append({
            'priority': 'MEDIUM',
            'category': 'Contractor Oversight',
            'icon': 'fa-hard-hat',
            'action': 'Fortnightly Contractor Coordination',
            'detail': 'Increase coordination meetings to fortnightly intervals to prevent minor contractor slippages from compounding into critical path delays.'
        })
        
    # 3. Statutory Environmental Clearances
    if env in ['Delayed', 'Pending']:
        recs.append({
            'priority': 'HIGH',
            'category': 'Statutory Clearances',
            'icon': 'fa-tree',
            'action': 'Accelerate Environmental / Forest Clearances',
            'detail': 'Prioritize compliance submissions to Regional Forest Empowered Committee (REC) / State EIA Authority and track clearance milestones on PARIVESH portal.'
        })
        
    # 4. Utility Shifting
    if utility in ['Delayed', 'Pending']:
        recs.append({
            'priority': 'HIGH',
            'category': 'Utility Shifting',
            'icon': 'fa-bolt',
            'action': 'Joint Utility Relocation Taskforce',
            'detail': 'Convene coordination taskforce with State DISCOM, water boards, and telecom utilities to establish time-bound shifting schedules.'
        })
        
    # 5. Progress Slippage
    if gap >= 20.0:
        recs.append({
            'priority': 'CRITICAL',
            'category': 'Execution Monitoring',
            'icon': 'fa-tachometer-alt',
            'action': 'Intensive Weekly Monitoring & Work-Front Auditing',
            'detail': f"Physical progress is {gap:.1f}% behind planned schedule. Transition monitoring from monthly to weekly cycles and inspect work-front access barriers."
        })
    elif gap >= 10.0:
        recs.append({
            'priority': 'MEDIUM',
            'category': 'Execution Monitoring',
            'icon': 'fa-tachometer-alt',
            'action': 'Bottleneck Review on Active Packages',
            'detail': f"Physical progress gap stands at {gap:.1f}%. Review procurement pipelines and resource mobilization for active work packages."
        })
        
    # 6. Milestone Delays
    if milestones_delayed >= 3:
        recs.append({
            'priority': 'CRITICAL',
            'category': 'Milestone Governance',
            'icon': 'fa-flag-checkered',
            'action': 'Comprehensive Milestone Re-baselining Review',
            'detail': f"{milestones_delayed} milestones have missed their target dates. Re-examine critical path dependencies and establish enforceable revised milestones."
        })
    elif milestones_delayed >= 1:
        recs.append({
            'priority': 'MEDIUM',
            'category': 'Milestone Governance',
            'icon': 'fa-flag-checkered',
            'action': 'Target Delayed Milestone Recovery',
            'detail': 'Focus immediate project leadership oversight on recovering delayed milestones to avoid schedule cascade.'
        })
        
    # 7. Cost Escalation & Expenditure Mismatch
    if cost_esc >= 15.0:
        recs.append({
            'priority': 'HIGH',
            'category': 'Financial Governance',
            'icon': 'fa-file-invoice-dollar',
            'action': 'Detailed Expenditure & Variance Audit',
            'detail': f"Revised cost exceeds original budget by {cost_esc:.1f}%. Convene Standing Committee on Cost Overruns (SCCO) review to evaluate revision justifications."
        })
        
    if budget_util - physical_prog >= 20.0:
        recs.append({
            'priority': 'HIGH',
            'category': 'Financial Governance',
            'icon': 'fa-chart-pie',
            'action': 'Investigate Fund Utilization vs Physical Delivery',
            'detail': f"Expenditure ({budget_util:.1f}%) significantly outpaces physical completion ({physical_prog:.1f}%). Audit mobilization advances and billing milestones."
        })
        
    if not recs:
        recs.append({
            'priority': 'INFO',
            'category': 'Routine Oversight',
            'icon': 'fa-check-circle',
            'action': 'Maintain Standard Monitoring Rhythm',
            'detail': 'Project metrics are within acceptable operational tolerances. Maintain scheduled monthly reporting and regular milestone validation.'
        })
        
    return recs
