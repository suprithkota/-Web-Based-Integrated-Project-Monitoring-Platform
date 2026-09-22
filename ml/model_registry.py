"""
Central Model Registry for ProjectPulse AI.
Loads, manages, and executes all 7 ML models:
1. Random Forest (Existing Primary Regressor)
2. XGBoost (Regressor & Classifier)
3. LightGBM (Regressor & Classifier)
4. Logistic Regression (Interpretable Classifier)
5. Support Vector Machine (SVC Classifier)
6. K-Means (Unsupervised Clustering)
7. Isolation Forest (Anomaly Detection)
"""

import sys
from pathlib import Path
import numpy as np
import joblib

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / 'ml' / 'models'

# Cluster Archetypes
CLUSTER_PROFILES = {
    0: {
        'label': 'On-Track & High Health',
        'archetype': 'Delivery Optimized',
        'description': 'Projects exhibiting high physical delivery, on-time milestones, and low cost/schedule deviation.'
    },
    1: {
        'label': 'Schedule-Constrained',
        'archetype': 'Milestone Slippage',
        'description': 'Projects experiencing schedule slippage and delayed milestones, while cost escalation remains contained.'
    },
    2: {
        'label': 'Cost-Escalated',
        'archetype': 'Financial Strain',
        'description': 'Projects with notable budget revision and expenditure-progress divergence, requiring fiscal auditing.'
    },
    3: {
        'label': 'Critical Bottlenecked',
        'archetype': 'Multi-Factor Distress',
        'description': 'Complex projects hindered by simultaneous statutory clearance delays, contractor distress, and schedule lag.'
    }
}

class ModelRegistry:
    def __init__(self):
        self.model_dir = MODEL_DIR
        self.models = {}
        self._load_all_models()

    def _load_all_models(self):
        """Loads all serialized model artifacts from disk safely."""
        # 1. Random Forest (Existing Primary)
        rf_path = self.model_dir / 'risk_engine.joblib'
        self.models['random_forest'] = self._safe_load(rf_path)

        # 2. XGBoost Regressor / Classifier
        xgb_path = self.model_dir / 'xgboost_risk_model.joblib'
        self.models['xgboost'] = self._safe_load(xgb_path)

        # 3. LightGBM Regressor / Classifier
        lgb_path = self.model_dir / 'lightgbm_risk_model.joblib'
        self.models['lightgbm'] = self._safe_load(lgb_path)

        # 4. Logistic Regression
        lr_path = self.model_dir / 'logistic_regression_model.joblib'
        self.models['logistic_regression'] = self._safe_load(lr_path)

        # 5. Support Vector Machine (SVM)
        svm_path = self.model_dir / 'svm_model.joblib'
        self.models['svm'] = self._safe_load(svm_path)

        # 6. K-Means Clustering
        kmeans_path = self.model_dir / 'kmeans_model.joblib'
        self.models['kmeans'] = self._safe_load(kmeans_path)

        # 7. Isolation Forest Anomaly Detection
        iso_path = self.model_dir / 'isolation_forest_model.joblib'
        self.models['isolation_forest'] = self._safe_load(iso_path)

    def _safe_load(self, path):
        if path.exists():
            try:
                return joblib.load(path)
            except Exception as e:
                return None
        return None

    def reload(self):
        """Reloads all models from disk."""
        self._load_all_models()

    # ------------------ Supervised Regression ------------------

    def predict_all_regressors(self, feature_vector):
        """
        Runs all available regression models on the 11-element feature vector.
        Returns dictionary of predictions bounded between 0 and 100.
        """
        vec = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)
        predictions = {}

        # 1. Random Forest (Baseline)
        if self.models.get('random_forest') is not None:
            try:
                pred = float(self.models['random_forest'].predict(vec)[0])
                predictions['random_forest'] = round(max(0.0, min(100.0, pred)), 1)
            except Exception:
                predictions['random_forest'] = None
        else:
            predictions['random_forest'] = None

        # 2. XGBoost Regressor
        xgb_bundle = self.models.get('xgboost')
        if xgb_bundle is not None:
            try:
                regressor = xgb_bundle.get('regressor') if isinstance(xgb_bundle, dict) else xgb_bundle
                if regressor is not None:
                    pred = float(regressor.predict(vec)[0])
                    predictions['xgboost'] = round(max(0.0, min(100.0, pred)), 1)
            except Exception:
                predictions['xgboost'] = None
        else:
            predictions['xgboost'] = None

        # 3. LightGBM Regressor
        lgb_bundle = self.models.get('lightgbm')
        if lgb_bundle is not None:
            try:
                regressor = lgb_bundle.get('regressor') if isinstance(lgb_bundle, dict) else lgb_bundle
                if regressor is not None:
                    pred = float(regressor.predict(vec)[0])
                    predictions['lightgbm'] = round(max(0.0, min(100.0, pred)), 1)
            except Exception:
                predictions['lightgbm'] = None
        else:
            predictions['lightgbm'] = None

        return predictions

    # ------------------ Supervised Classification ------------------

    def predict_all_classifiers(self, feature_vector):
        """
        Runs classification models predicting Risk Level categories (LOW, MEDIUM, HIGH, CRITICAL).
        """
        vec = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)
        results = {}

        # 1. Logistic Regression
        lr_model = self.models.get('logistic_regression')
        if lr_model is not None:
            try:
                cat = str(lr_model.predict(vec)[0])
                probs = {}
                if hasattr(lr_model, 'predict_proba'):
                    prob_vals = lr_model.predict_proba(vec)[0]
                    classes = lr_model.classes_
                    probs = {str(c): round(float(p) * 100, 1) for c, p in zip(classes, prob_vals)}
                results['logistic_regression'] = {
                    'predicted_level': cat,
                    'probabilities': probs
                }
            except Exception:
                results['logistic_regression'] = None
        else:
            results['logistic_regression'] = None

        # 2. Support Vector Machine (SVC)
        svm_model = self.models.get('svm')
        if svm_model is not None:
            try:
                cat = str(svm_model.predict(vec)[0])
                probs = {}
                if hasattr(svm_model, 'predict_proba'):
                    prob_vals = svm_model.predict_proba(vec)[0]
                    classes = svm_model.classes_
                    probs = {str(c): round(float(p) * 100, 1) for c, p in zip(classes, prob_vals)}
                results['svm'] = {
                    'predicted_level': cat,
                    'probabilities': probs
                }
            except Exception:
                results['svm'] = None
        else:
            results['svm'] = None

        # 3. XGBoost Classifier (if present in bundle)
        xgb_bundle = self.models.get('xgboost')
        if isinstance(xgb_bundle, dict) and xgb_bundle.get('classifier') is not None:
            try:
                clf = xgb_bundle['classifier']
                label_encoder = xgb_bundle.get('label_encoder')
                raw_pred = clf.predict(vec)[0]
                cat = label_encoder.inverse_transform([raw_pred])[0] if label_encoder else str(raw_pred)
                results['xgboost_classifier'] = {'predicted_level': str(cat)}
            except Exception:
                results['xgboost_classifier'] = None

        return results

    # ------------------ Unsupervised Anomaly Detection ------------------

    def detect_anomaly(self, feature_vector):
        """
        Uses IsolationForest to detect atypical indicator combinations.
        Returns dict with anomaly flag, normalized anomaly score (0-100), and interpretation.
        """
        iso_model = self.models.get('isolation_forest')
        vec = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)

        if iso_model is None:
            return {
                'detected': False,
                'status': 'NORMAL',
                'anomaly_score': 15.0,
                'severity': 'LOW',
                'description': 'Anomaly detection engine not yet serialized.'
            }

        try:
            # predict: 1 = normal, -1 = anomaly
            raw_pred = int(iso_model.predict(vec)[0])
            is_anomaly = (raw_pred == -1)

            # decision_function: lower score = more anomalous
            # typically ranges from -0.5 to 0.5. We convert it to a 0-100 anomaly index
            score_raw = float(iso_model.decision_function(vec)[0])
            # normalize: negative scores mean anomalous
            # map range [-0.25, 0.25] -> [100.0, 0.0]
            normalized_score = round(max(0.0, min(100.0, (0.20 - score_raw) * 200.0)), 1)

            severity = 'HIGH' if normalized_score >= 70.0 else ('MEDIUM' if normalized_score >= 45.0 else 'LOW')

            if is_anomaly:
                desc = "Unusual combination of physical progress, cost utilization, and statutory bottleneck indicators detected."
            else:
                desc = "Project metrics align with standard infrastructure execution distributions."

            return {
                'detected': is_anomaly,
                'status': 'ANOMALOUS' if is_anomaly else 'NORMAL',
                'anomaly_score': normalized_score,
                'severity': severity,
                'description': desc
            }
        except Exception:
            return {
                'detected': False,
                'status': 'NORMAL',
                'anomaly_score': 20.0,
                'severity': 'LOW',
                'description': 'Anomaly model calculation unavailable.'
            }

    # ------------------ Unsupervised Clustering ------------------

    def assign_cluster(self, feature_vector):
        """
        Uses KMeans to cluster the project into an archetype cluster.
        Returns cluster ID (0-3), human-readable label, archetype, and description.
        """
        kmeans_model = self.models.get('kmeans')
        vec = np.asarray(feature_vector, dtype=np.float32).reshape(1, -1)

        if kmeans_model is None:
            return {
                'id': 0,
                'label': 'Standard Cohort',
                'archetype': 'Unassigned',
                'description': 'Clustering model not serialized.'
            }

        try:
            # Check if kmeans is wrapped in a pipeline or standalone
            if isinstance(kmeans_model, dict):
                scaler = kmeans_model.get('scaler')
                km = kmeans_model.get('model')
                X_scaled = scaler.transform(vec) if scaler else vec
                cid = int(km.predict(X_scaled)[0])
            elif hasattr(kmeans_model, 'predict'):
                cid = int(kmeans_model.predict(vec)[0])
            else:
                cid = 0

            profile = CLUSTER_PROFILES.get(cid, {
                'label': f'Cohort #{cid}',
                'archetype': 'Infrastructure Profile',
                'description': 'Project cluster cohort.'
            })

            return {
                'id': cid,
                'label': profile['label'],
                'archetype': profile['archetype'],
                'description': profile['description']
            }
        except Exception:
            return {
                'id': 0,
                'label': 'Cohort 0',
                'archetype': 'Standard Infrastructure',
                'description': 'Cluster assignment fallback.'
            }

    # ------------------ Operational Status ------------------

    def get_model_status(self):
        """Returns diagnostic status of all 7 models."""
        status = []
        model_specs = [
            ('Random Forest', 'random_forest', 'Regression (Continuous Risk Score)', 'ml/models/risk_engine.joblib'),
            ('XGBoost', 'xgboost', 'Regression & Classification', 'ml/models/xgboost_risk_model.joblib'),
            ('LightGBM', 'lightgbm', 'Regression & Classification', 'ml/models/lightgbm_risk_model.joblib'),
            ('Logistic Regression', 'logistic_regression', 'Classification (Risk Levels)', 'ml/models/logistic_regression_model.joblib'),
            ('Support Vector Machine', 'svm', 'Classification (SVC)', 'ml/models/svm_model.joblib'),
            ('K-Means Clustering', 'kmeans', 'Unsupervised Cohort Grouping', 'ml/models/kmeans_model.joblib'),
            ('Isolation Forest', 'isolation_forest', 'Unsupervised Anomaly Detection', 'ml/models/isolation_forest_model.joblib')
        ]

        for name, key, task, rel_path in model_specs:
            loaded = (self.models.get(key) is not None)
            file_exists = (BASE_DIR / rel_path).exists()
            status.append({
                'name': name,
                'key': key,
                'task': task,
                'file_path': rel_path,
                'file_exists': file_exists,
                'is_loaded': loaded,
                'status': 'OPERATIONAL' if loaded else ('ARTIFACT_READY' if file_exists else 'NOT_TRAINED')
            })

        return status

# Singleton Instance
model_registry = ModelRegistry()
