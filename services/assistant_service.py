import re
import os
import json
from sqlalchemy import func
from database import db
from database.models import Project, Alert
from ml.predictor import predict_project_risk

class ProjectAssistantService:
    """
    AI Project Intelligence Assistant.
    Retrieves real facts from the database first, eliminating hallucinations.
    Uses rule-based deterministic response synthesis with optional LLM API fallback.
    """
    
    def process_query(self, query_text, authorized_project_ids=None):
        query_clean = query_text.strip().lower()

        # 1. Explicit Project Code Inquiry (e.g. "Why is PRJ-0003 high risk?")
        code_match = re.search(r'PRJ-\d+', query_text, re.IGNORECASE)
        if code_match:
            code = code_match.group(0).upper()
            p = Project.query.filter(Project.project_code.ilike(f"%{code}%")).first()
            if p:
                if authorized_project_ids is not None and p.id not in authorized_project_ids:
                    return f"### Access Restricted\n\nUnder current RBAC governance, your account is not authorized to access intelligence records for project **{p.project_code}** ({p.project_name})."
                return self._explain_project(p, query_text)
            
        # 2. Intent: Highest delay risk projects
        if any(w in query_clean for w in ['highest delay', 'delay risk', 'most delayed', 'time overrun', 'schedule overrun']):
            return self._get_highest_delay_projects(authorized_project_ids)
            
        # 3. Intent: Highest cost overrun risk / cost escalation > X%
        if any(w in query_clean for w in ['cost escalation', 'cost overrun', 'budget escalation', 'budget overrun', 'escalation above']):
            pct_match = re.search(r'(\d+)%', query_clean)
            min_pct = float(pct_match.group(1)) if pct_match else 15.0
            return self._get_cost_escalation_projects(min_pct, authorized_project_ids)
            
        # 4. Intent: Ministry with most critical projects
        if 'ministry' in query_clean and any(w in query_clean for w in ['most critical', 'highest risk', 'maximum', 'worst', 'critical', 'delay']):
            return self._get_ministry_risk_comparison(authorized_project_ids)
            
        # 5. Intent: Sector comparison / highest risk sector
        if 'sector' in query_clean and any(w in query_clean for w in ['highest risk', 'average risk', 'critical', 'most']):
            return self._get_sector_risk_comparison(authorized_project_ids)

        # 6. Intent: Critical projects count / status summary
        if any(w in query_clean for w in ['how many critical', 'critical count', 'at risk count', 'currently critical', 'critical status', 'total critical', 'list critical']):
            return self._get_critical_projects_summary(authorized_project_ids)
            
        # 7. Intent: Low physical progress but high expenditure / mismatch
        if any(w in query_clean for w in ['low progress', 'high expenditure', 'mismatch', 'spending fast', 'divergence']):
            return self._get_mismatch_projects(authorized_project_ids)
            
        # 8. General project count or summary
        if any(w in query_clean for w in ['overview', 'summary', 'status', 'total projects', 'health']):
            return self._get_general_overview(authorized_project_ids)
            
        # 9. Fallback project name match (with stopword filtering)
        project_match = self._find_matching_project(query_text, authorized_project_ids)
        if project_match:
            return self._explain_project(project_match, query_text)

        # 10. Fallback helpful guide with suggestions
        return self._get_fallback_guidance(query_text)

    def _find_matching_project(self, query_text, authorized_project_ids=None):
        STOPWORDS = {'project', 'projects', 'corridor', 'package', 'national', 'highway', 'railway', 'phase', 'section', 'development', 'which', 'what', 'where', 'there', 'about', 'state'}
        query = Project.query
        if authorized_project_ids is not None:
            query = query.filter(Project.id.in_(authorized_project_ids))
        projects = query.all()
        q_lower = query_text.lower()
        for p in projects:
            words = [w for w in re.findall(r'\b[a-z]{4,}\b', p.project_name.lower()) if w not in STOPWORDS]
            if words and any(w in q_lower for w in words):
                return p
        return None

    def _explain_project(self, project, original_query):
        eval_result = predict_project_risk(project)
        gap = project.progress_gap
        cost_esc = project.cost_escalation
        
        reasons = []
        if gap > 10:
            reasons.append(f"Actual physical progress is **{project.physical_progress}%** versus planned **{project.planned_progress}%** ({gap}% lag).")
        if project.milestones_delayed > 0:
            reasons.append(f"**{project.milestones_delayed} of {project.milestones_total} milestones** have slipped past schedule.")
        if cost_esc > 5:
            reasons.append(f"Revised outlay (₹{project.revised_cost:,.0f} Cr) is **{cost_esc:.1f}% higher** than original approved cost (₹{project.approved_cost:,.0f} Cr).")
        if project.delay_days > 30:
            reasons.append(f"Cumulative schedule slippage has reached **{project.delay_days} days**.")
        if project.contractor_status in ['Delayed', 'Critical']:
            reasons.append(f"Contractor execution status is flagged as **{project.contractor_status}**.")
        if project.land_acquisition_status in ['Delayed', 'Pending']:
            reasons.append(f"Land acquisition remains **{project.land_acquisition_status}**.")
        if project.environmental_clearance_status in ['Delayed', 'Pending']:
            reasons.append(f"Environmental clearances are **{project.environmental_clearance_status}**.")
            
        if not reasons:
            reasons.append("Project progress, expenditure, and milestone completion are tracking close to baseline projections.")

        response = f"""### Project Intelligence Report: **{project.project_name}** ({project.project_code})

**Ministry**: {project.ministry} | **Sector**: {project.sector} | **State**: {project.state}  
**Overall Risk Score**: **{project.risk_score}/100** ({project.risk_level} Risk)  
**Project Health Score**: **{project.health_score}/100**  
**Delay Probability**: **{project.delay_probability:.1f}%** | **Cost Overrun Probability**: **{project.cost_overrun_probability:.1f}%**

#### Key Contributing Factors:
""" + "\n".join([f"- {r}" for r in reasons]) + f"""

#### Recommended Monitoring Action:
{eval_result['explanation']}

*Data Source: Database Project Record. Analytical estimate for decision support.*
"""
        return response

    def _get_highest_delay_projects(self, authorized_project_ids=None):
        query = Project.query
        if authorized_project_ids is not None:
            query = query.filter(Project.id.in_(authorized_project_ids))
        projects = query.order_by(Project.delay_probability.desc()).limit(5).all()
        if not projects:
            return "No projects found within your authorized project scope."
        lines = []
        for i, p in enumerate(projects, 1):
            lines.append(
                f"{i}. **{p.project_name}** (`{p.project_code}`)\n"
                f"   - State: {p.state} | Sector: {p.sector}\n"
                f"   - **Estimated Delay Probability: {p.delay_probability:.1f}%** | Delay Days: {p.delay_days}d\n"
                f"   - Progress: {p.physical_progress}% (Target: {p.planned_progress}%) | Milestones Delayed: {p.milestones_delayed}"
            )
            
        return "### Projects with Highest Estimated Delay Risk\n\n" + "\n\n".join(lines) + "\n\n*Note: High delay risk is driven by execution gaps, critical-path milestone slippage, and statutory bottleneck indicators.*"

    def _get_cost_escalation_projects(self, min_pct=15.0, authorized_project_ids=None):
        query = Project.query
        if authorized_project_ids is not None:
            query = query.filter(Project.id.in_(authorized_project_ids))
        projects = query.all()
        escalated = [p for p in projects if p.cost_escalation >= min_pct]
        escalated.sort(key=lambda x: x.cost_escalation, reverse=True)
        top5 = escalated[:5]
        
        if not top5:
            return f"No projects currently have cost escalation exceeding {min_pct}%."
            
        lines = []
        for i, p in enumerate(top5, 1):
            diff = p.revised_cost - p.approved_cost
            lines.append(
                f"{i}. **{p.project_name}** (`{p.project_code}`)\n"
                f"   - Ministry: {p.ministry}\n"
                f"   - **Cost Escalation: +{p.cost_escalation:.1f}%** (+₹{diff:,.1f} Cr)\n"
                f"   - Approved: ₹{p.approved_cost:,.1f} Cr ➔ Revised: ₹{p.revised_cost:,.1f} Cr\n"
                f"   - Cost Overrun Risk: **{p.cost_overrun_probability:.1f}%**"
            )
            
        return f"### Projects with Cost Escalation ≥ {min_pct}%\n\n" + "\n\n".join(lines)

    def _get_critical_projects_summary(self, authorized_project_ids=None):
        base_q = Project.query
        if authorized_project_ids is not None:
            base_q = base_q.filter(Project.id.in_(authorized_project_ids))
        total = base_q.count()
        if total == 0:
            return "No projects found within your authorized project scope."
        critical_count = base_q.filter_by(risk_level='CRITICAL').count()
        high_count = base_q.filter_by(risk_level='HIGH').count()
        medium_count = base_q.filter_by(risk_level='MEDIUM').count()
        low_count = base_q.filter_by(risk_level='LOW').count()
        
        critical_projects = base_q.filter_by(risk_level='CRITICAL').limit(4).all()
        sample_crit = ", ".join([f"**{p.project_name}** (`{p.project_code}`)" for p in critical_projects]) or "None"
        
        return f"""### Current Project Health & Risk Distribution

Across all **{total} monitored infrastructure projects** in your scope:

- 🔴 **CRITICAL Risk**: **{critical_count} projects** ({(critical_count/total*100):.1f}%)
- 🟠 **HIGH Risk**: **{high_count} projects** ({(high_count/total*100):.1f}%)
- 🟡 **MEDIUM Risk**: **{medium_count} projects** ({(medium_count/total*100):.1f}%)
- 🟢 **LOW Risk**: **{low_count} projects** ({(low_count/total*100):.1f}%)

**Immediate Critical Attention Required**:
{sample_crit}

Use the **Early Warning Center** to review open red-flag alerts and dispatch intervention recommendations.
"""

    def _get_ministry_risk_comparison(self, authorized_project_ids=None):
        q = db.session.query(
            Project.ministry,
            func.count(Project.id),
            func.avg(Project.risk_score),
            func.sum(db.case((Project.risk_level == 'CRITICAL', 1), else_=0))
        )
        if authorized_project_ids is not None:
            q = q.filter(Project.id.in_(authorized_project_ids))
        stats = q.group_by(Project.ministry).order_by(func.sum(db.case((Project.risk_level == 'CRITICAL', 1), else_=0)).desc()).all()
        
        if not stats:
            return "No ministry statistics available for your authorized projects."
        lines = []
        for m, total, avg_risk, crit in stats[:5]:
            lines.append(f"- **{m}**: **{crit or 0} Critical projects** out of {total} total (Average Risk: {(avg_risk or 0):.1f}/100)")
            
        return "### Ministry Risk & Critical Project Analysis\n\n" + "\n".join(lines)

    def _get_sector_risk_comparison(self, authorized_project_ids=None):
        q = db.session.query(
            Project.sector,
            func.count(Project.id),
            func.avg(Project.risk_score)
        )
        if authorized_project_ids is not None:
            q = q.filter(Project.id.in_(authorized_project_ids))
        stats = q.group_by(Project.sector).order_by(func.avg(Project.risk_score).desc()).all()
        
        if not stats:
            return "No sector statistics available for your authorized projects."
        lines = []
        for s, total, avg_risk in stats[:6]:
            lines.append(f"- **{s}**: Average Risk Score **{(avg_risk or 0):.1f}/100** ({total} monitored projects)")
            
        return "### Sector Risk Ranking (Highest Average Risk First)\n\n" + "\n".join(lines)

    def _get_mismatch_projects(self, authorized_project_ids=None):
        query = Project.query
        if authorized_project_ids is not None:
            query = query.filter(Project.id.in_(authorized_project_ids))
        all_p = query.all()
        mismatched = []
        for p in all_p:
            spend_pct = p.budget_utilization
            if (spend_pct - p.physical_progress) >= 20.0 and p.physical_progress < 60.0:
                mismatched.append((p, spend_pct - p.physical_progress))
                
        mismatched.sort(key=lambda x: x[1], reverse=True)
        top = mismatched[:5]
        
        if not top:
            return "No projects currently display a high expenditure-to-physical progress divergence."
            
        lines = []
        for i, (p, diff) in enumerate(top, 1):
            lines.append(
                f"{i}. **{p.project_name}** (`{p.project_code}`)\n"
                f"   - Budget Spent: **{p.budget_utilization:.1f}%** | Physical Progress: **{p.physical_progress:.1f}%**\n"
                f"   - **Divergence Gap: {diff:.1f}% points** (Approved: ₹{p.approved_cost:,.0f} Cr, Spent: ₹{p.expenditure:,.0f} Cr)\n"
                f"   - Risk Level: **{p.risk_level}**"
            )
            
        return "### Projects with Significant Expenditure-Progress Divergence\n\n" + "\n\n".join(lines)

    def _get_general_overview(self, authorized_project_ids=None):
        q = Project.query
        if authorized_project_ids is not None:
            q = q.filter(Project.id.in_(authorized_project_ids))
        total = q.count()
        app_cost_q = db.session.query(func.sum(Project.approved_cost))
        exp_q = db.session.query(func.sum(Project.expenditure))
        avg_phys_q = db.session.query(func.avg(Project.physical_progress))
        if authorized_project_ids is not None:
            app_cost_q = app_cost_q.filter(Project.id.in_(authorized_project_ids))
            exp_q = exp_q.filter(Project.id.in_(authorized_project_ids))
            avg_phys_q = avg_phys_q.filter(Project.id.in_(authorized_project_ids))

        app_cost = app_cost_q.scalar() or 0.0
        exp = exp_q.scalar() or 0.0
        avg_phys = avg_phys_q.scalar() or 0.0
        utilization = (exp / app_cost * 100) if app_cost > 0 else 0.0
        
        return f"""### ProjectPulse AI System Overview

- **Total Monitored Projects**: {total}
- **Total Approved Capital Outlay**: ₹{app_cost:,.2f} Cr
- **Cumulative Expenditure**: ₹{exp:,.2f} Cr ({utilization:.1f}% utilization)
- **Average Physical Progress**: {avg_phys:.1f}%

You can ask me specific questions such as:
1. *"Which projects have the highest delay risk?"*
2. *"Which ministry has the most critical projects?"*
3. *"Why is PRJ-0001 high risk?"*
4. *"Which projects have cost escalation above 20%?"*
5. *"Show projects with low physical progress but high expenditure."*
"""

    def _get_fallback_guidance(self, query):
        return f"""I analyzed your question: *"{query}"*.

As a database-grounded Project Intelligence Assistant, I can answer queries about infrastructure monitoring data, risks, and forecasts. Try asking:

- 🕒 *"Which projects have the highest delay risk?"*
- 💰 *"Which projects have cost escalation above 20%?"*
- 🏛 *"Which ministry has the most critical projects?"*
- ⚠️ *"How many projects are currently critical?"*
- 🔍 *"Why is PRJ-0003 high risk?"* (or enter any Project Code / Name)
- 📉 *"Show projects with low physical progress but high expenditure"*
"""

assistant_service = ProjectAssistantService()
