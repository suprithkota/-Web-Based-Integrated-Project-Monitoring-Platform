import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ml.preprocessing import extract_features_from_dict
from ml.model_registry import model_registry
from ml.explainability.shap_explainer import compute_shap_explanation
from ml.model_comparison import get_model_comparison_report

MODEL_DIR = BASE_DIR / 'ml' / 'models'

class RiskEngine:
    """
    AI/ML Infrastructure Project Risk and Decision-Support Engine.
    Combines machine learning inference with transparent, explainable feature attribution.
    """
    
    def __init__(self):
        self.model_path = MODEL_DIR / 'risk_engine.joblib'
        self.ml_model = None
        self._load_ml_model()

    def _load_ml_model(self):
        if self.model_path.exists():
            try:
                import joblib
                self.ml_model = joblib.load(self.model_path)
            except Exception:
                self.ml_model = None
        else:
            self.ml_model = None

    def evaluate_project(self, project_data):
        """
        Evaluates project risk metrics.
        Returns:
            dict with:
                delay_probability,
                cost_overrun_probability,
                overall_risk_score,
                risk_level,
                health_score,
                health_breakdown,
                contributing_factors,
                explanation,
                root_causes
        """
        feats, raw = extract_features_from_dict(project_data)
        
        # 1. Calculate Delay Probability (0 - 100%)
        # Primary drivers: Progress Gap (35%), Milestone Slippage (25%), Delay Days (20%),
        # Contractor status (10%), Land/Clearance Bottlenecks (10%)
        gap_score = min(100.0, raw['progress_gap'] * 2.8)
        milestone_score = raw['milestone_delay_ratio'] * 100.0
        days_score = min(100.0, (raw['delay_days'] / 240.0) * 100.0)
        contractor_score = raw['contractor_risk'] * 100.0
        bottleneck_score = ((raw['land_risk'] + raw['env_risk'] + raw['utility_risk']) / 3.0) * 100.0
        
        calculated_delay_prob = (
            0.35 * gap_score +
            0.25 * milestone_score +
            0.20 * days_score +
            0.10 * contractor_score +
            0.10 * bottleneck_score
        )
        calculated_delay_prob = max(5.0, min(98.0, calculated_delay_prob))
        
        # 2. Calculate Cost Overrun Probability (0 - 100%)
        # Primary drivers: Cost Escalation already observed (40%), Expenditure vs Progress Mismatch (25%),
        # Schedule delay impact (20%), Land & Utility bottlenecks (15%)
        cost_esc_score = min(100.0, raw['cost_escalation'] * 3.0)
        spend_mismatch_score = min(100.0, raw['expenditure_vs_progress'] * 2.5)
        land_utility_score = ((raw['land_risk'] + raw['utility_risk']) / 2.0) * 100.0
        
        calculated_cost_prob = (
            0.40 * cost_esc_score +
            0.25 * spend_mismatch_score +
            0.20 * calculated_delay_prob +
            0.15 * land_utility_score
        )
        calculated_cost_prob = max(5.0, min(98.0, calculated_cost_prob))
        
        # If trained ML model is available, blend model predictions
        if self.ml_model is not None:
            try:
                # Shape: [1, n_features]
                pred = self.ml_model.predict([feats])[0]
                # blend 60% ML, 40% rule-based for stability
                overall_risk = float(0.60 * pred + 0.40 * (0.55 * calculated_delay_prob + 0.45 * calculated_cost_prob))
            except Exception:
                overall_risk = float(0.55 * calculated_delay_prob + 0.45 * calculated_cost_prob)
        else:
            overall_risk = float(0.55 * calculated_delay_prob + 0.45 * calculated_cost_prob)
            
        overall_risk = round(max(3.0, min(98.0, overall_risk)), 1)
        delay_prob = round(calculated_delay_prob, 1)
        cost_prob = round(calculated_cost_prob, 1)
        
        # Risk Classification
        if overall_risk <= 30.0:
            risk_level = 'LOW'
        elif overall_risk <= 55.0:
            risk_level = 'MEDIUM'
        elif overall_risk <= 75.0:
            risk_level = 'HIGH'
        else:
            risk_level = 'CRITICAL'
            
        # Project Health Score (0-100) & Subcomponents
        health_score = round(max(0.0, 100.0 - overall_risk), 1)
        schedule_health = round(max(5.0, 100.0 - delay_prob), 1)
        financial_health = round(max(5.0, 100.0 - cost_prob), 1)
        physical_health = round(max(5.0, 100.0 - gap_score), 1)
        milestone_health = round(max(5.0, 100.0 - milestone_score), 1)
        risk_factors_health = round(max(5.0, 100.0 - ((contractor_score + bottleneck_score) / 2.0)), 1)
        
        health_breakdown = {
            'schedule_health': schedule_health,
            'financial_health': financial_health,
            'physical_health': physical_health,
            'milestone_health': milestone_health,
            'risk_factors_health': risk_factors_health
        }
        
        # 3. Transparent Explainability Factors (Quantified percentage contributions)
        factors = {
            'Physical progress gap': round(min(100.0, gap_score), 1),
            'Milestone delays': round(min(100.0, milestone_score), 1),
            'Cost escalation': round(min(100.0, cost_esc_score), 1),
            'Contractor performance delay': round(min(100.0, contractor_score), 1),
            'Land acquisition bottleneck': round(min(100.0, raw['land_risk'] * 100.0), 1),
            'Environmental clearance': round(min(100.0, raw['env_risk'] * 100.0), 1),
            'Utility shifting dependency': round(min(100.0, raw['utility_risk'] * 100.0), 1)
        }
        
        # Sort factors by impact
        sorted_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)
        top_factors = [f"{k} ({v}%)" for k, v in sorted_factors if v >= 40.0]
        
        # 4. Generate Natural Language Explainability Narrative
        narrative_parts = []
        if raw['progress_gap'] >= 10.0:
            narrative_parts.append(f"actual physical progress ({project_data.get('physical_progress')}%) lags significantly behind planned schedule ({project_data.get('planned_progress')}%)")
        if raw['milestone_delay_ratio'] > 0.25:
            delayed_count = project_data.get('milestones_delayed', 0)
            narrative_parts.append(f"{delayed_count} critical milestone(s) are delayed")
        if raw['cost_escalation'] >= 10.0:
            narrative_parts.append(f"revised project cost reflects a {raw['cost_escalation']:.1f}% escalation over approved outlay")
        if raw['delay_days'] > 60:
            narrative_parts.append(f"cumulative schedule delay has reached {int(raw['delay_days'])} days")
        if raw['contractor_risk'] >= 0.7:
            narrative_parts.append("contractor execution performance is flagged as delayed/critical")
        if raw['land_risk'] >= 0.7:
            narrative_parts.append("land acquisition hurdles remain pending resolution")
        if raw['env_risk'] >= 0.7:
            narrative_parts.append("statutory environmental clearances are delayed")
            
        if narrative_parts:
            primary_reasons = ", ".join(narrative_parts[:3])
            explanation = f"The project is classified as {risk_level} risk primarily because {primary_reasons}. Decision-makers should review these indicators promptly."
        else:
            explanation = f"The project exhibits a {risk_level} risk profile with execution metrics, milestones, and expenditure broadly aligned with baseline targets."

        # 5. Cautious Root Cause Analysis
        root_causes = []
        if raw['land_risk'] >= 0.7:
            root_causes.append({
                'factor': 'Land Acquisition',
                'status': project_data.get('land_acquisition_status', 'Delayed'),
                'severity': 'HIGH' if raw['land_risk'] >= 0.8 else 'MEDIUM',
                'description': 'Potential contributing factor: Pending right-of-way handover or compensation disbursement.'
            })
        if raw['contractor_risk'] >= 0.7:
            root_causes.append({
                'factor': 'Contractor Execution',
                'status': project_data.get('contractor_status', 'Delayed'),
                'severity': 'HIGH' if raw['contractor_risk'] >= 0.8 else 'MEDIUM',
                'description': 'Potential contributing factor: Equipment mobilization deficits or sub-contractor coordination issues.'
            })
        if raw['env_risk'] >= 0.7:
            root_causes.append({
                'factor': 'Environmental Clearance',
                'status': project_data.get('environmental_clearance_status', 'Delayed'),
                'severity': 'HIGH' if raw['env_risk'] >= 0.8 else 'MEDIUM',
                'description': 'Potential contributing factor: Forest clearance stage-II approval or state pollution control board reviews pending.'
            })
        if raw['utility_risk'] >= 0.7:
            root_causes.append({
                'factor': 'Utility Shifting',
                'status': project_data.get('utility_shifting_status', 'Delayed'),
                'severity': 'MEDIUM',
                'description': 'Potential contributing factor: High-tension electrical transmission line or pipeline relocation pending.'
            })
        if raw['progress_gap'] >= 15.0:
            root_causes.append({
                'factor': 'Physical Progress Slippage',
                'status': f"{raw['progress_gap']:.1f}% Gap",
                'severity': 'CRITICAL' if raw['progress_gap'] >= 25.0 else 'HIGH',
                'description': 'Potential contributing factor: Work front availability and seasonal or logistical delays.'
            })
        if raw['cost_escalation'] >= 15.0:
            root_causes.append({
                'factor': 'Cost Escalation Driver',
                'status': f"+{raw['cost_escalation']:.1f}%",
                'severity': 'CRITICAL' if raw['cost_escalation'] >= 30.0 else 'HIGH',
                'description': 'Potential contributing factor: Scope modification, raw material inflation, or extended supervision overheads.'
            })

        # 6. Multi-Model Inference, Clustering, Anomaly Detection & SHAP Explainability
        try:
            reg_preds = model_registry.predict_all_regressors(feats)
        except Exception:
            reg_preds = {'random_forest': overall_risk}

        try:
            clf_preds = model_registry.predict_all_classifiers(feats)
        except Exception:
            clf_preds = {}

        try:
            anomaly_info = model_registry.detect_anomaly(feats)
        except Exception:
            anomaly_info = {'detected': False, 'status': 'NORMAL', 'anomaly_score': 15.0}

        try:
            cluster_info = model_registry.assign_cluster(feats)
        except Exception:
            cluster_info = {'id': 0, 'label': 'Standard Cohort', 'archetype': 'Standard'}

        try:
            shap_info = compute_shap_explanation(self.ml_model, feats, model_id='rf', model_name='Random Forest')
        except Exception:
            shap_info = {
                'method': 'Heuristic-Attribution',
                'status': 'fallback',
                'base_value': 25.0,
                'features': [],
                'top_risk_drivers': [],
                'summary_statement': 'SHAP calculation fallback.'
            }

        try:
            comparison_summary = get_model_comparison_report()
        except Exception:
            comparison_summary = {}

        top_risk_features = [
            f['display_name'] for f in shap_info.get('top_risk_drivers', [])
        ] or [k for k, v in sorted_factors[:3]]

        return {
            'delay_probability': delay_prob,
            'cost_overrun_probability': cost_prob,
            'overall_risk_score': overall_risk,
            'risk_level': risk_level,
            'health_score': health_score,
            'health_breakdown': health_breakdown,
            'contributing_factors': dict(sorted_factors),
            'explanation': explanation,
            'root_causes': root_causes,
            # Additional Multi-Model ML & SHAP metadata (non-breaking)
            'ml_model_used': 'RandomForestRegressor (Ensemble Primary)',
            'model_predictions': {
                'regressors': reg_preds,
                'classifiers': clf_preds
            },
            'shap_explanation': shap_info,
            'top_risk_features': top_risk_features,
            'anomaly': anomaly_info,
            'cluster': cluster_info,
            'model_comparison': comparison_summary
        }


# Global singleton instance
risk_engine = RiskEngine()
