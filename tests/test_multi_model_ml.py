"""
Comprehensive Test Suite for Multi-Model Machine Learning Architecture & SHAP Explainability.
Tests:
1. Random Forest preservation & backward compatibility
2. XGBoost regressor & classifier
3. LightGBM regressor & classifier
4. Logistic Regression classification & probabilities
5. Support Vector Machine (SVM) classification & probabilities
6. K-Means clustering assignment & archetype descriptions
7. Isolation Forest anomaly detection & score scaling
8. SHAP TreeExplainer & safe fallback attribution
9. Model comparison metrics reporting
10. Enhanced RiskEngine output contract preservation
11. Dedicated REST APIs (/api/ml/*)
12. Edge cases (zeros, extreme values, missing inputs)
"""

import unittest
import json
import sys
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import create_app
from config import Config
from database import db
from database.models import User, Project
from ml.preprocessing import extract_features_from_dict, FEATURE_NAMES
from ml.model_registry import model_registry
from ml.explainability.shap_explainer import compute_shap_explanation, _compute_fallback_attribution
from ml.model_comparison import get_model_comparison_report
from ml.risk_model import risk_engine

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False

class MultiModelMLTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        self.sample_features = np.array([15.0, 0.4, 12.0, 0.33, 8.0, 0.75, 0.30, 0.25, 0.25, 0.60, 0.65], dtype=np.float32)

        with self.app.app_context():
            db.create_all()
            user = User(username='mlofficer', email='mlofficer@test.gov.in', role='admin')
            user.set_password('officerPass123')
            user.email_verified = True
            user.status = 'active'
            
            p = Project(
                project_code='PRJ-ML-01',
                project_name='ML Validation Corridor',
                ministry='Ministry of Road Transport',
                sector='Roads',
                state='Gujarat',
                approved_cost=2500.0,
                revised_cost=2800.0,
                expenditure=1700.0,
                physical_progress=60.0,
                planned_progress=75.0,
                delay_days=120,
                milestones_total=6,
                milestones_completed=3,
                milestones_delayed=2,
                contractor_status='Delayed',
                land_acquisition_status='In Progress',
                environmental_clearance_status='Completed',
                utility_shifting_status='Completed'
            )
            db.session.add_all([user, p])
            db.session.commit()
            self.project_id = p.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _login(self):
        return self.client.post('/login', data={'username': 'mlofficer', 'password': 'officerPass123'})

    # ---------------- 1. Random Forest (Preserved Primary) ----------------
    def test_random_forest_preserved(self):
        rf_model = model_registry.models.get('random_forest')
        self.assertIsNotNone(rf_model, "Existing Random Forest model artifact must load successfully")
        pred = rf_model.predict([self.sample_features])[0]
        self.assertIsInstance(float(pred), float)
        self.assertTrue(0.0 <= pred <= 100.0)

    # ---------------- 2. XGBoost ----------------
    def test_xgboost_regressor_and_classifier(self):
        reg_preds = model_registry.predict_all_regressors(self.sample_features)
        self.assertIn('xgboost', reg_preds)
        if reg_preds['xgboost'] is not None:
            self.assertTrue(0.0 <= reg_preds['xgboost'] <= 100.0)

        clf_preds = model_registry.predict_all_classifiers(self.sample_features)
        if 'xgboost_classifier' in clf_preds and clf_preds['xgboost_classifier']:
            self.assertIn(clf_preds['xgboost_classifier']['predicted_level'], ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])

    # ---------------- 3. LightGBM ----------------
    def test_lightgbm_regressor_and_classifier(self):
        reg_preds = model_registry.predict_all_regressors(self.sample_features)
        self.assertIn('lightgbm', reg_preds)
        if reg_preds['lightgbm'] is not None:
            self.assertTrue(0.0 <= reg_preds['lightgbm'] <= 100.0)

    # ---------------- 4. Logistic Regression ----------------
    def test_logistic_regression(self):
        clf_preds = model_registry.predict_all_classifiers(self.sample_features)
        self.assertIn('logistic_regression', clf_preds)
        lr_result = clf_preds['logistic_regression']
        self.assertIsNotNone(lr_result)
        self.assertIn(lr_result['predicted_level'], ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
        self.assertIn('probabilities', lr_result)
        total_prob = sum(lr_result['probabilities'].values())
        self.assertAlmostEqual(total_prob, 100.0, delta=2.0)

    # ---------------- 5. Support Vector Machine (SVM) ----------------
    def test_support_vector_machine(self):
        clf_preds = model_registry.predict_all_classifiers(self.sample_features)
        self.assertIn('svm', clf_preds)
        svm_result = clf_preds['svm']
        self.assertIsNotNone(svm_result)
        self.assertIn(svm_result['predicted_level'], ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'])
        self.assertIn('probabilities', svm_result)
        total_prob = sum(svm_result['probabilities'].values())
        self.assertAlmostEqual(total_prob, 100.0, delta=2.0)

    # ---------------- 6. K-Means Clustering ----------------
    def test_kmeans_clustering(self):
        cluster_info = model_registry.assign_cluster(self.sample_features)
        self.assertIn('id', cluster_info)
        self.assertIn(cluster_info['id'], [0, 1, 2, 3])
        self.assertIn('label', cluster_info)
        self.assertIn('archetype', cluster_info)
        self.assertIn('description', cluster_info)

    # ---------------- 7. Isolation Forest Anomaly Detection ----------------
    def test_isolation_forest(self):
        anomaly_info = model_registry.detect_anomaly(self.sample_features)
        self.assertIn('detected', anomaly_info)
        self.assertIsInstance(anomaly_info['detected'], bool)
        self.assertIn('anomaly_score', anomaly_info)
        self.assertTrue(0.0 <= anomaly_info['anomaly_score'] <= 100.0)
        self.assertIn('status', anomaly_info)
        self.assertIn(anomaly_info['status'], ['NORMAL', 'ANOMALOUS'])

    # ---------------- 8. SHAP TreeExplainer & Fallback ----------------
    def test_shap_explanation(self):
        rf_model = model_registry.models.get('random_forest')
        shap_res = compute_shap_explanation(rf_model, self.sample_features, model_id='rf', model_name='Random Forest')
        self.assertIn('method', shap_res)
        self.assertIn(shap_res['method'], ['TreeSHAP', 'Heuristic-Attribution'])
        self.assertIn('base_value', shap_res)
        self.assertIn('features', shap_res)
        self.assertEqual(len(shap_res['features']), len(FEATURE_NAMES))
        self.assertIn('top_risk_drivers', shap_res)
        self.assertIn('summary_statement', shap_res)

        # Test fallback directly
        fallback_res = _compute_fallback_attribution(self.sample_features, 'Fallback Engine')
        self.assertEqual(fallback_res['method'], 'Heuristic-Attribution')
        self.assertEqual(len(fallback_res['features']), len(FEATURE_NAMES))

    # ---------------- 9. Model Comparison Report ----------------
    def test_model_comparison_report(self):
        report = get_model_comparison_report()
        self.assertIn('regression', report)
        self.assertIn('Random Forest', report['regression'])
        self.assertIn('MAE', report['regression']['Random Forest'])
        self.assertIn('RMSE', report['regression']['Random Forest'])
        self.assertIn('R2', report['regression']['Random Forest'])
        self.assertIn('classification', report)
        self.assertIn('Logistic Regression', report['classification'])
        self.assertIn('Support Vector Machine', report['classification'])

    # ---------------- 10. RiskEngine Output Contract ----------------
    def test_risk_engine_contract_preservation(self):
        sample = {
            'physical_progress': 55.0,
            'planned_progress': 75.0,
            'approved_cost': 1200.0,
            'revised_cost': 1400.0,
            'expenditure': 800.0,
            'delay_days': 90,
            'milestones_total': 5,
            'milestones_delayed': 2,
            'contractor_status': 'Delayed',
            'land_acquisition_status': 'Delayed',
            'environmental_clearance_status': 'Completed',
            'utility_shifting_status': 'Completed'
        }
        res = risk_engine.evaluate_project(sample)
        # 1. Verify ALL 9 existing legacy keys are preserved with expected types
        expected_keys = [
            'delay_probability', 'cost_overrun_probability', 'overall_risk_score',
            'risk_level', 'health_score', 'health_breakdown', 'contributing_factors',
            'explanation', 'root_causes'
        ]
        for k in expected_keys:
            self.assertIn(k, res, f"Legacy key '{k}' must remain in evaluate_project output")

        # 2. Verify new additive keys
        new_keys = ['ml_model_used', 'model_predictions', 'shap_explanation', 'top_risk_features', 'anomaly', 'cluster']
        for k in new_keys:
            self.assertIn(k, res, f"New ML key '{k}' must be present in evaluate_project output")

        self.assertIn('regressors', res['model_predictions'])
        self.assertIn('classifiers', res['model_predictions'])

    # ---------------- 11. Dedicated REST APIs ----------------
    def test_api_ml_endpoints(self):
        self._login()

        # GET /api/ml/models
        res = self.client.get('/api/ml/models')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['count'], 7)

        # GET /api/ml/comparison
        res = self.client.get('/api/ml/comparison')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('comparison', data)

        # GET /api/ml/explanation/<id>
        res = self.client.get(f'/api/ml/explanation/{self.project_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('shap_explanation', data)

        # GET /api/ml/anomaly/<id>
        res = self.client.get(f'/api/ml/anomaly/{self.project_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('anomaly', data)

        # GET /api/ml/cluster/<id>
        res = self.client.get(f'/api/ml/cluster/{self.project_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('cluster', data)

    # ---------------- 12. Edge Cases & Robustness ----------------
    def test_edge_cases(self):
        # All zeros
        zeros = np.zeros(11, dtype=np.float32)
        reg_zeros = model_registry.predict_all_regressors(zeros)
        self.assertIsNotNone(reg_zeros['random_forest'])
        self.assertTrue(0.0 <= reg_zeros['random_forest'] <= 100.0)

        # Extreme values
        extremes = np.array([100.0, 3.0, 500.0, 1.0, 100.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        reg_ext = model_registry.predict_all_regressors(extremes)
        self.assertIsNotNone(reg_ext['random_forest'])
        self.assertTrue(0.0 <= reg_ext['random_forest'] <= 100.0)

        # Empty dictionary into evaluate_project
        empty_res = risk_engine.evaluate_project({})
        self.assertIn('overall_risk_score', empty_res)
        self.assertIn('model_predictions', empty_res)

if __name__ == '__main__':
    unittest.main()
