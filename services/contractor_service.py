import json
from datetime import datetime, date
from sqlalchemy import func
from database import db
from database.models import (
    Contractor, ContractorBranch, Project, MaterialSupplier,
    ProjectMaterial, MaterialQualityTest, ProjectDelayRecord,
    ProjectFinancialRecord, ProjectLifecycleEvent, PostConstructionRecord,
    ProjectSubcontractor, PublicComplaint, DocumentEvidence
)

class ContractorService:
    """
    Contractor & Construction Company Intelligence Service.
    Enforces Section 25 (Fairness & Data Rule): Presents verified factual records,
    empirical measurements, and laboratory findings without subjective judgments.
    """

    @staticmethod
    def calculate_contractor_metrics(contractor):
        """
        Computes factual performance and operational records for a given contractor.
        """
        projects = contractor.projects.all() if hasattr(contractor.projects, 'all') else Project.query.filter_by(contractor_id=contractor.id).all()
        
        # 1. Project Delivery Statistics
        total_projects = len(projects)
        completed_projects = [p for p in projects if p.project_status == 'Completed']
        ongoing_projects = [p for p in projects if p.project_status == 'Ongoing']
        delayed_projects = [p for p in projects if p.project_status == 'Delayed']
        pending_projects = [p for p in projects if p.project_status in ['Not started', 'Suspended', 'Stalled', 'Awaiting approval', 'Awaiting funding', 'Under legal dispute']]
        
        completed_on_schedule = sum(1 for p in completed_projects if (p.delay_days or 0) <= 0)
        completed_late = sum(1 for p in completed_projects if (p.delay_days or 0) > 0)
        on_schedule_rate = round((completed_on_schedule / len(completed_projects) * 100.0), 1) if completed_projects else 0.0

        # 2. Financial & Budget Performance (Crores INR)
        total_contract_value = sum((p.contract_value or p.approved_cost or 0.0) for p in projects)
        total_original_budget = sum((p.original_budget or p.approved_cost or 0.0) for p in projects)
        total_final_cost = sum((p.final_cost or p.revised_cost or 0.0) for p in projects)
        total_expenditure = sum((p.expenditure or 0.0) for p in projects)
        
        total_cost_variance = round(total_final_cost - total_original_budget, 2)
        total_cost_variance_pct = round(((total_cost_variance / total_original_budget) * 100.0), 1) if total_original_budget > 0 else 0.0
        
        projects_within_budget = sum(1 for p in projects if p.cost_variance <= 0)
        projects_with_cost_variation = sum(1 for p in projects if p.cost_variance > 0)

        # 3. Material Quality & Laboratory Testing Performance
        project_ids = [p.id for p in projects]
        materials = ProjectMaterial.query.filter(ProjectMaterial.project_id.in_(project_ids)).all() if project_ids else []
        material_ids = [m.id for m in materials]
        
        tests = MaterialQualityTest.query.filter(MaterialQualityTest.material_id.in_(material_ids)).all() if material_ids else []
        tests_total = len(tests)
        tests_passed = sum(1 for t in tests if t.status == 'PASS')
        tests_failed = sum(1 for t in tests if t.status == 'FAIL')
        tests_conditional = sum(1 for t in tests if t.status == 'CONDITIONAL')
        test_pass_rate = round((tests_passed / tests_total * 100.0), 1) if tests_total > 0 else 100.0

        # 4. Post-Construction & Defect Monitoring
        post_records = PostConstructionRecord.query.filter(PostConstructionRecord.project_id.in_(project_ids)).all() if project_ids else []
        defects_total = len(post_records)
        no_defects_count = sum(1 for r in post_records if r.quality_status == 'No significant defects reported')
        minor_defects_count = sum(1 for r in post_records if r.quality_status == 'Minor defects reported')
        major_defects_count = sum(1 for r in post_records if r.quality_status == 'Major defects identified')
        repairs_completed_count = sum(1 for r in post_records if r.quality_status in ['Repairs completed', 'Repair completed'])
        under_investigation_count = sum(1 for r in post_records if r.quality_status == 'Defects under investigation')

        # 5. Delay Category Analysis across 8 standard categories
        delay_records = ProjectDelayRecord.query.filter(ProjectDelayRecord.project_id.in_(project_ids)).all() if project_ids else []
        delay_categories = {
            'Administrative': 0,
            'Financial': 0,
            'Land / Legal': 0,
            'Technical': 0,
            'Contractor / Execution': 0,
            'Material': 0,
            'Environmental': 0,
            'Other': 0
        }
        delay_days_by_cat = {cat: 0 for cat in delay_categories}
        for d in delay_records:
            cat = d.delay_category if d.delay_category in delay_categories else 'Other'
            delay_categories[cat] += 1
            delay_days_by_cat[cat] += (d.affected_days or 0)

        # 6. Public Complaints and Grievances
        complaints = PublicComplaint.query.filter(
            (PublicComplaint.contractor_id == contractor.id) | 
            (PublicComplaint.project_id.in_(project_ids) if project_ids else False)
        ).all()
        complaints_total = len(complaints)
        complaints_resolved = sum(1 for c in complaints if c.status in ['Resolved', 'Closed'])
        complaints_open = sum(1 for c in complaints if c.status not in ['Resolved', 'Closed', 'Rejected with Reason'])

        # 7. Document & Evidence Count
        docs_count = DocumentEvidence.query.filter(
            (DocumentEvidence.contractor_id == contractor.id) | 
            (DocumentEvidence.project_id.in_(project_ids) if project_ids else False)
        ).count()

        return {
            'total_projects': total_projects,
            'completed_projects_count': len(completed_projects),
            'completed_projects': len(completed_projects),
            'ongoing_projects_count': len(ongoing_projects),
            'ongoing_projects': len(ongoing_projects),
            'delayed_projects_count': len(delayed_projects),
            'delayed_projects': len(delayed_projects),
            'pending_projects_count': len(pending_projects),
            'pending_projects': len(pending_projects),
            'completed_on_schedule': completed_on_schedule,
            'completed_late': completed_late,
            'on_schedule_rate': on_schedule_rate,
            'total_contract_value': round(total_contract_value, 2),
            'total_original_budget': round(total_original_budget, 2),
            'total_final_cost': round(total_final_cost, 2),
            'total_expenditure': round(total_expenditure, 2),
            'total_cost_variance': total_cost_variance,
            'cost_variance': total_cost_variance,
            'total_cost_variance_pct': total_cost_variance_pct,
            'cost_variance_pct': total_cost_variance_pct,
            'projects_within_budget': projects_within_budget,
            'projects_with_cost_variation': projects_with_cost_variation,
            'tests_total': tests_total,
            'total_quality_tests': tests_total,
            'tests_passed': tests_passed,
            'tests_failed': tests_failed,
            'tests_conditional': tests_conditional,
            'test_pass_rate': test_pass_rate,
            'quality_pass_rate': test_pass_rate,
            'avg_delay_days': round(sum((p.delay_days or 0) for p in projects) / len(projects), 1) if projects else 0.0,
            'materials_count': len(materials),
            'defects_total': defects_total,
            'no_defects_count': no_defects_count,
            'minor_defects_count': minor_defects_count,
            'major_defects_count': major_defects_count,
            'repairs_completed_count': repairs_completed_count,
            'under_investigation_count': under_investigation_count,
            'delay_categories_count': delay_categories,
            'delay_days_by_cat': delay_days_by_cat,
            'complaints_total': complaints_total,
            'complaints_resolved': complaints_resolved,
            'complaints_open': complaints_open,
            'docs_count': docs_count,
            'branches_count': len(contractor.branches)
        }

    @staticmethod
    def get_all_contractors_summary(filters=None):
        """
        Retrieves all contractors matching optional filters and annotates with factual summary metrics.
        """
        filters = filters or {}
        query = Contractor.query

        if filters.get('search'):
            term = f"%{filters['search'].strip()}%"
            query = query.filter(
                (Contractor.name.ilike(term)) |
                (Contractor.registration_number.ilike(term)) |
                (Contractor.contractor_code.ilike(term)) |
                (Contractor.headquarters.ilike(term))
            )

        if filters.get('company_type'):
            query = query.filter(Contractor.company_type == filters['company_type'])

        if filters.get('contractor_class'):
            query = query.filter(Contractor.contractor_class == filters['contractor_class'])

        if filters.get('status'):
            query = query.filter(Contractor.registration_status == filters['status'])

        contractors = query.order_by(Contractor.name.asc()).all()
        results = []
        for c in contractors:
            metrics = ContractorService.calculate_contractor_metrics(c)
            c_dict = c.to_dict()
            c_dict.update(metrics)
            c_dict['metrics'] = metrics
            results.append(c_dict)

        return results

    @staticmethod
    def get_contractor_intelligence_dashboard_stats():
        """
        Aggregates system-wide statistics across all contractors, projects, and materials.
        """
        total_contractors = Contractor.query.count()
        total_companies = Contractor.query.filter_by(registration_status='Active').count()
        total_projects = Project.query.count()
        completed_projects = Project.query.filter_by(project_status='Completed').count()
        ongoing_projects = Project.query.filter_by(project_status='Ongoing').count()
        delayed_projects = Project.query.filter_by(project_status='Delayed').count()
        pending_projects = Project.query.filter(Project.project_status.in_([
            'Not started', 'Suspended', 'Stalled', 'Awaiting approval', 'Awaiting funding', 'Under legal dispute'
        ])).count()

        total_approved_value = db.session.query(func.coalesce(func.sum(Project.approved_cost), 0.0)).scalar() or 0.0
        total_expenditure = db.session.query(func.coalesce(func.sum(Project.expenditure), 0.0)).scalar() or 0.0

        # Quality test pass rates
        total_tests = MaterialQualityTest.query.count()
        passed_tests = MaterialQualityTest.query.filter_by(status='PASS').count()
        failed_tests = MaterialQualityTest.query.filter_by(status='FAIL').count()
        quality_pass_rate = round((passed_tests / total_tests * 100.0), 1) if total_tests > 0 else 100.0

        # Cost variations count
        projects_with_cost_var = Project.query.filter(Project.revised_cost > Project.approved_cost).count()
        projects_with_quality_issues = db.session.query(func.count(func.distinct(MaterialQualityTest.project_id))).filter(MaterialQualityTest.status == 'FAIL').scalar() or 0
        open_complaints = PublicComplaint.query.filter(~PublicComplaint.status.in_(['Resolved', 'Closed', 'Rejected with Reason'])).count()

        # Delay reasons breakdown across system
        delay_counts_raw = db.session.query(
            ProjectDelayRecord.delay_category, func.count(ProjectDelayRecord.id), func.coalesce(func.sum(ProjectDelayRecord.affected_days), 0)
        ).group_by(ProjectDelayRecord.delay_category).all()
        
        delay_breakdown = {}
        delay_category_distribution = {
            'Administrative': 0,
            'Financial': 0,
            'Land / Legal': 0,
            'Technical': 0,
            'Contractor / Execution': 0,
            'Material': 0,
            'Environmental': 0,
            'Other': 0
        }
        for cat, cnt, days in delay_counts_raw:
            delay_breakdown[cat] = {'count': cnt, 'affected_days': days}
            if cat in delay_category_distribution:
                delay_category_distribution[cat] = cnt
            else:
                delay_category_distribution['Other'] += cnt

        # Sector distribution
        sectors_raw = db.session.query(Project.sector, func.count(Project.id)).group_by(Project.sector).all()
        sector_dist = {s: cnt for s, cnt in sectors_raw}

        # On-schedule calculation
        completed_on_schedule = Project.query.filter(Project.project_status == 'Completed', (Project.delay_days == 0) | (Project.delay_days == None)).count()
        on_schedule_rate = round((completed_on_schedule / completed_projects * 100.0), 1) if completed_projects > 0 else 100.0

        # Cost variance system-wide
        total_revised = db.session.query(func.coalesce(func.sum(Project.revised_cost), 0.0)).scalar() or 0.0
        total_cost_variance = round(total_revised - total_approved_value, 2)
        total_cost_variance_pct = round((total_cost_variance / total_approved_value * 100.0), 1) if total_approved_value > 0 else 0.0

        # Delay averages
        total_delay_days = db.session.query(func.coalesce(func.sum(Project.delay_days), 0)).scalar() or 0
        delayed_projects_count = Project.query.filter((Project.delay_days > 0) | (Project.project_status == 'Delayed')).count()
        avg_delay_days = round(total_delay_days / delayed_projects_count, 1) if delayed_projects_count > 0 else 0

        post_construction_audits = PostConstructionRecord.query.count()

        return {
            'total_contractors': total_contractors,
            'total_companies': total_companies,
            'total_projects': total_projects,
            'total_projects_handled': total_projects,
            'completed_projects': completed_projects,
            'ongoing_projects': ongoing_projects,
            'delayed_projects': delayed_projects,
            'pending_projects': pending_projects,
            'total_approved_value': round(total_approved_value, 2),
            'total_contract_value': round(total_approved_value, 2),
            'total_expenditure': round(total_expenditure, 2),
            'total_cost_variance': total_cost_variance,
            'total_cost_variance_pct': total_cost_variance_pct,
            'total_delay_days': total_delay_days,
            'avg_delay_days': avg_delay_days,
            'on_schedule_rate': on_schedule_rate,
            'total_tests': total_tests,
            'total_quality_tests': total_tests,
            'passed_tests': passed_tests,
            'passed_quality_tests': passed_tests,
            'failed_tests': failed_tests,
            'failed_quality_tests': failed_tests,
            'quality_pass_rate': quality_pass_rate,
            'material_pass_rate': quality_pass_rate,
            'post_construction_audits': post_construction_audits,
            'projects_with_cost_variation': projects_with_cost_var,
            'projects_with_quality_issues': projects_with_quality_issues,
            'open_complaints': open_complaints,
            'delay_breakdown': delay_breakdown,
            'delay_category_distribution': delay_category_distribution,
            'sector_dist': sector_dist
        }

    @staticmethod
    def generate_contractor_ai_summary(contractor):
        """
        Produces a strictly factual summary of the contractor's empirical track record.
        Strictly prohibits subjective or evaluative conclusions.
        """
        metrics = ContractorService.calculate_contractor_metrics(contractor)
        
        narrative_parts = [
            f"**{contractor.name}** ({contractor.company_type}) is registered under license **{contractor.contractor_license_number or 'N/A'}** (Reg: `{contractor.registration_number}`) with registered class **{contractor.contractor_class}**.",
            f"Established in {contractor.year_established} ({contractor.years_of_experience} years in operation) with headquarters in {contractor.headquarters} and {metrics['branches_count']} registered operational branches.",
            f"The verified database records a portfolio of **{metrics['total_projects']} projects** ({metrics['completed_projects_count']} completed, {metrics['ongoing_projects_count']} ongoing, {metrics['delayed_projects_count']} delayed, {metrics['pending_projects_count']} pending).",
        ]

        if metrics['completed_projects_count'] > 0:
            narrative_parts.append(
                f"Of the completed projects, **{metrics['completed_on_schedule']} completed within planned schedule** and **{metrics['completed_late']} completed after planned schedule** ({metrics['on_schedule_rate']}% on-time completion rate)."
            )

        narrative_parts.append(
            f"Total approved contract outlay is **₹{metrics['total_contract_value']:,.2f} Cr** with cumulative expenditure of **₹{metrics['total_expenditure']:,.2f} Cr**. Cost variation stands at **{metrics['total_cost_variance_pct']:+.1f}%** across monitored projects ({metrics['projects_within_budget']} delivered within original approved budget, {metrics['projects_with_cost_variation']} with sanctioned variation orders)."
        )

        narrative_parts.append(
            f"Material quality testing records show **{metrics['tests_passed']} passed** and **{metrics['tests_failed']} failed** out of {metrics['tests_total']} certified laboratory tests ({metrics['test_pass_rate']}% pass rate) across standard BIS specifications."
        )

        top_delays = [f"{cat} ({cnt} events, {metrics['delay_days_by_cat'][cat]} days)" for cat, cnt in metrics['delay_categories_count'].items() if cnt > 0]
        if top_delays:
            narrative_parts.append(
                f"Documented project delay categories include: {', '.join(top_delays)}."
            )

        narrative_parts.append(
            f"Post-construction monitoring records show {metrics['no_defects_count']} inspections with no significant defects, {metrics['minor_defects_count']} minor defects, and {metrics['repairs_completed_count']} completed repairs during the Defect Liability Period (DLP)."
        )

        narrative_parts.append(
            f"Public citizen grievance tracking records {metrics['complaints_total']} submitted reports ({metrics['complaints_resolved']} resolved through verified site inspection, {metrics['complaints_open']} currently under review). *Notice: Citizen reports represent submitted concerns and are distinguished from verified technical inspection findings.*"
        )

        return {
            'text': "\n\n".join(narrative_parts),
            'generated_at': datetime.utcnow().isoformat(),
            'status': 'verified',
            'fairness_standard': 'Section 25 Verified Empirical Standard'
        }

    @classmethod
    def get_contractor_dashboard_stats(cls):
        """
        Alias for get_contractor_intelligence_dashboard_stats.
        """
        return cls.get_contractor_intelligence_dashboard_stats()

    @classmethod
    def get_top_performing_contractors(cls, limit=5):
        """
        Returns top contractors ranked by on-schedule completion and quality metrics.
        """
        contractors = cls.get_all_contractors_summary()
        contractors.sort(key=lambda c: (c.get('on_schedule_rate', 0), c.get('test_pass_rate', 0)), reverse=True)
        return contractors[:limit]
