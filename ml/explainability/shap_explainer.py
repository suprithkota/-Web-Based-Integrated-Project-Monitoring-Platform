"""
SHAP Explainability Layer for ProjectPulse AI.
Computes local feature attributions using TreeSHAP for tree-based models,
with graceful fallback attribution if SHAP is unavailable or encounters errors.
"""

import numpy as np
from ml.preprocessing import FEATURE_NAMES

FEATURE_DISPLAY_NAMES = {
    'progress_gap': 'Physical Progress Gap',
    'delay_days_norm': 'Normalized Schedule Delay',
    'cost_escalation_pct': 'Cost Escalation %',
    'milestone_delay_ratio': 'Delayed Milestones Ratio',
    'expenditure_vs_progress_ratio': 'Spend vs Progress Mismatch',
    'contractor_risk_val': 'Contractor Execution Risk',
    'land_risk_val': 'Land Acquisition Bottleneck',
    'env_risk_val': 'Environmental Clearances',
    'utility_risk_val': 'Utility Shifting Dependency',
    'physical_progress_norm': 'Physical Delivery Level',
    'financial_progress_norm': 'Financial Progress Level'
}

# Cache for TreeExplainers to avoid re-building them on every prediction
_EXPLAINER_CACHE = {}

def get_tree_explainer(model, model_id='rf'):
    """
    Returns a cached TreeExplainer instance for the given tree model.
    """
    if model is None:
        return None
    if model_id in _EXPLAINER_CACHE:
        return _EXPLAINER_CACHE[model_id]
    
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        _EXPLAINER_CACHE[model_id] = explainer
        return explainer
    except Exception:
        return None

def compute_shap_explanation(model, feature_vector, model_id='rf', model_name='Random Forest'):
    """
    Computes SHAP feature attribution values for a single project feature vector.
    
    Args:
        model: Trained tree-based model (e.g. RandomForest, XGBoost, LightGBM)
        feature_vector: 1D numpy array of length 11
        model_id: Identifier string for caching
        model_name: Human readable model name for reporting
        
    Returns:
        dict containing:
            method: 'TreeSHAP' or 'Heuristic-Attribution'
            status: 'available' or 'fallback'
            model_name: string
            base_value: float (expected model baseline)
            features: list of dicts with feature name, display name, value, shap_value, impact
            top_risk_drivers: list of top features that increase risk
            top_mitigating_factors: list of top features that reduce risk
            summary_statement: human-readable explanation
    """
    vec = np.asarray(feature_vector, dtype=np.float32)
    if vec.ndim == 1:
        X = vec.reshape(1, -1)
    else:
        X = vec

    explainer = get_tree_explainer(model, model_id)
    
    if explainer is not None:
        try:
            exp = explainer(X)
            values = exp.values[0]
            base_val = float(np.mean(exp.base_values)) if hasattr(exp.base_values, '__len__') else float(exp.base_values)
            
            attributions = []
            for i, name in enumerate(FEATURE_NAMES):
                val = float(values[i])
                raw_val = float(X[0, i])
                disp_name = FEATURE_DISPLAY_NAMES.get(name, name)
                attributions.append({
                    'feature': name,
                    'display_name': disp_name,
                    'raw_value': round(raw_val, 3),
                    'shap_value': round(val, 2),
                    'absolute_impact': round(abs(val), 2),
                    'direction': 'INCREASES_RISK' if val > 0.05 else ('DECREASES_RISK' if val < -0.05 else 'NEUTRAL')
                })
                
            # Sort features by magnitude of absolute impact
            attributions_sorted = sorted(attributions, key=lambda x: x['absolute_impact'], reverse=True)
            
            risk_drivers = [f for f in attributions_sorted if f['shap_value'] > 0]
            mitigating = [f for f in attributions_sorted if f['shap_value'] < 0]
            
            # Format high-level narrative statement
            top_3_drivers = [f"{d['display_name']} (+{d['shap_value']:.1f} pts)" for d in risk_drivers[:3]]
            if top_3_drivers:
                summary = f"SHAP TreeExplainer identifies {', '.join(top_3_drivers)} as primary drivers elevating project risk."
            else:
                summary = "Project features are evenly balanced around baseline targets with no anomalous risk driver."
                
            return {
                'method': 'TreeSHAP',
                'status': 'available',
                'model_name': model_name,
                'base_value': round(base_val, 1),
                'features': attributions_sorted,
                'top_risk_drivers': risk_drivers[:4],
                'top_mitigating_factors': mitigating[:3],
                'summary_statement': summary
            }
        except Exception:
            # Fall back safely if SHAP computation errors
            pass

    # Safe Fallback Heuristic Attribution if SHAP is unavailable or errors
    return _compute_fallback_attribution(vec, model_name)

def _compute_fallback_attribution(feature_vector, model_name='Random Forest'):
    """
    Computes grounded linear attribution proxy when SHAP is unavailable.
    """
    vec = np.asarray(feature_vector).flatten()
    weights = {
        'progress_gap': 0.28,
        'milestone_delay_ratio': 0.22,
        'cost_escalation_pct': 0.20,
        'delay_days_norm': 0.15,
        'contractor_risk_val': 0.12,
        'land_risk_val': 0.10,
        'env_risk_val': 0.08,
        'utility_risk_val': 0.08,
        'expenditure_vs_progress_ratio': 0.10,
        'physical_progress_norm': -0.15,
        'financial_progress_norm': 0.05
    }
    
    attributions = []
    for i, name in enumerate(FEATURE_NAMES):
        raw_val = float(vec[i]) if i < len(vec) else 0.0
        w = weights.get(name, 0.05)
        approx_impact = raw_val * w * 10.0
        disp_name = FEATURE_DISPLAY_NAMES.get(name, name)
        attributions.append({
            'feature': name,
            'display_name': disp_name,
            'raw_value': round(raw_val, 3),
            'shap_value': round(approx_impact, 2),
            'absolute_impact': round(abs(approx_impact), 2),
            'direction': 'INCREASES_RISK' if approx_impact > 0.5 else ('DECREASES_RISK' if approx_impact < -0.5 else 'NEUTRAL')
        })
        
    attributions_sorted = sorted(attributions, key=lambda x: x['absolute_impact'], reverse=True)
    risk_drivers = [f for f in attributions_sorted if f['shap_value'] > 0]
    mitigating = [f for f in attributions_sorted if f['shap_value'] < 0]
    
    return {
        'method': 'Heuristic-Attribution',
        'status': 'fallback',
        'model_name': model_name,
        'base_value': 25.0,
        'features': attributions_sorted,
        'top_risk_drivers': risk_drivers[:4],
        'top_mitigating_factors': mitigating[:3],
        'summary_statement': "Explainability calculated via indicator sensitivity attribution."
    }
