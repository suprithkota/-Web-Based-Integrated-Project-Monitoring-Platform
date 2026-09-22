"""
Comprehensive Multi-Model Training and Benchmarking Pipeline for ProjectPulse AI.
Trains and exports:
1. XGBoost (Regressor & Classifier)
2. LightGBM (Regressor & Classifier)
3. Logistic Regression (Pipeline with StandardScaler)
4. Support Vector Machine (Pipeline with StandardScaler & SVC(probability=True))
5. K-Means (Unsupervised Clustering with Scaler)
6. Isolation Forest (Unsupervised Anomaly Detection)
Also evaluates the existing Random Forest on the benchmark holdout set and saves
evaluated comparison metrics to model_comparison_metrics.json.

NOTE: This script DOES NOT modify or overwrite the existing ml/models/risk_engine.joblib.
"""

import os
import sys
import json
from pathlib import Path
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.svm import SVC
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score, precision_score, recall_score, f1_score
import joblib

from ml.train_model import generate_synthetic_training_data
from ml.model_comparison import save_model_comparison_report

MODEL_DIR = BASE_DIR / 'ml' / 'models'

def categorize_risk_scores(y):
    """Assigns standard risk categories based on continuous score."""
    cats = []
    for val in y:
        if val <= 30.0:
            cats.append('LOW')
        elif val <= 55.0:
            cats.append('MEDIUM')
        elif val <= 75.0:
            cats.append('HIGH')
        else:
            cats.append('CRITICAL')
    return np.array(cats)

def train_and_export_all_models():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating calibrated benchmark infrastructure dataset (1,500 samples)...")
    X, y = generate_synthetic_training_data(n_samples=1500, random_seed=42)
    y_cat = categorize_risk_scores(y)

    X_train, X_test, y_train, y_test, y_cat_train, y_cat_test = train_test_split(
        X, y, y_cat, test_size=0.2, random_state=42, stratify=y_cat
    )

    comparison_report = {
        "metadata": {
            "dataset": "Calibrated Infrastructure Project Telemetry (1,500 samples, 80/20 train/test split)",
            "evaluation_strategy": "Independent Holdout Test Set (Zero Data Leakage)",
            "total_samples": len(X),
            "test_samples": len(X_test)
        },
        "regression": {},
        "classification": {},
        "unsupervised": {}
    }

    # -------------------------------------------------------------
    # 1. EVALUATE EXISTING RANDOM FOREST (DO NOT RE-TRAIN OR OVERWRITE)
    # -------------------------------------------------------------
    rf_file = MODEL_DIR / 'risk_engine.joblib'
    if rf_file.exists():
        try:
            rf_model = joblib.load(rf_file)
            rf_pred = rf_model.predict(X_test)
            mae = float(mean_absolute_error(y_test, rf_pred))
            rmse = float(np.sqrt(mean_squared_error(y_test, rf_pred)))
            r2 = float(r2_score(y_test, rf_pred))
            comparison_report['regression']['Random Forest'] = {
                'task': 'Continuous Risk Score Prediction (0-100)',
                'MAE': round(mae, 3),
                'RMSE': round(rmse, 3),
                'R2': round(r2, 3),
                'primary_model': True,
                'status': 'OPERATIONAL',
                'artifact': 'ml/models/risk_engine.joblib'
            }
            print(f"[Random Forest (Existing)] MAE: {mae:.3f} | RMSE: {rmse:.3f} | R2: {r2:.3f}")
        except Exception as e:
            print(f"[Random Forest Evaluation Warning]: {e}")

    # -------------------------------------------------------------
    # 2. TRAIN & EXPORT XGBOOST (Regressor & Classifier)
    # -------------------------------------------------------------
    try:
        import xgboost as xgb
        print("\nTraining XGBoost models...")
        xgb_reg = xgb.XGBRegressor(
            n_estimators=120,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.85,
            colsample_bytree=0.85,
            random_state=42,
            n_jobs=-1
        )
        xgb_reg.fit(X_train, y_train)
        xgb_pred = xgb_reg.predict(X_test)

        mae = float(mean_absolute_error(y_test, xgb_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, xgb_pred)))
        r2 = float(r2_score(y_test, xgb_pred))

        comparison_report['regression']['XGBoost'] = {
            'task': 'Continuous Risk Score Prediction (0-100)',
            'MAE': round(mae, 3),
            'RMSE': round(rmse, 3),
            'R2': round(r2, 3),
            'primary_model': False,
            'status': 'OPERATIONAL',
            'artifact': 'ml/models/xgboost_risk_model.joblib'
        }
        print(f"[XGBoost Regressor] MAE: {mae:.3f} | RMSE: {rmse:.3f} | R2: {r2:.3f}")

        # XGBoost Classifier
        le = LabelEncoder()
        y_train_enc = le.fit_transform(y_cat_train)
        y_test_enc = le.transform(y_cat_test)

        xgb_clf = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
            n_jobs=-1,
            eval_metric='mlogloss'
        )
        xgb_clf.fit(X_train, y_train_enc)
        clf_pred = xgb_clf.predict(X_test)

        acc = float(accuracy_score(y_test_enc, clf_pred))
        prec = float(precision_score(y_test_enc, clf_pred, average='weighted', zero_division=0))
        rec = float(recall_score(y_test_enc, clf_pred, average='weighted', zero_division=0))
        f1 = float(f1_score(y_test_enc, clf_pred, average='weighted', zero_division=0))

        comparison_report['classification']['XGBoost Classifier'] = {
            'task': 'Risk Level Category (LOW, MEDIUM, HIGH, CRITICAL)',
            'accuracy': round(acc, 3),
            'precision': round(prec, 3),
            'recall': round(rec, 3),
            'f1_score': round(f1, 3),
            'type': 'Gradient Boosted Trees Classifier',
            'status': 'OPERATIONAL'
        }
        print(f"[XGBoost Classifier] Accuracy: {acc:.3f} | F1: {f1:.3f}")

        xgb_bundle = {
            'regressor': xgb_reg,
            'classifier': xgb_clf,
            'label_encoder': le
        }
        joblib.dump(xgb_bundle, MODEL_DIR / 'xgboost_risk_model.joblib')
    except Exception as e:
        print(f"[XGBoost Training Error]: {e}")

    # -------------------------------------------------------------
    # 3. TRAIN & EXPORT LIGHTGBM (Regressor & Classifier)
    # -------------------------------------------------------------
    try:
        import lightgbm as lgb
        print("\nTraining LightGBM models...")
        lgb_reg = lgb.LGBMRegressor(
            n_estimators=120,
            max_depth=6,
            learning_rate=0.08,
            num_leaves=31,
            random_state=42,
            verbose=-1
        )
        lgb_reg.fit(X_train, y_train)
        lgb_pred = lgb_reg.predict(X_test)

        mae = float(mean_absolute_error(y_test, lgb_pred))
        rmse = float(np.sqrt(mean_squared_error(y_test, lgb_pred)))
        r2 = float(r2_score(y_test, lgb_pred))

        comparison_report['regression']['LightGBM'] = {
            'task': 'Continuous Risk Score Prediction (0-100)',
            'MAE': round(mae, 3),
            'RMSE': round(rmse, 3),
            'R2': round(r2, 3),
            'primary_model': False,
            'status': 'OPERATIONAL',
            'artifact': 'ml/models/lightgbm_risk_model.joblib'
        }
        print(f"[LightGBM Regressor] MAE: {mae:.3f} | RMSE: {rmse:.3f} | R2: {r2:.3f}")

        lgb_clf = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            num_leaves=25,
            random_state=42,
            verbose=-1
        )
        lgb_clf.fit(X_train, y_cat_train)
        lgb_clf_pred = lgb_clf.predict(X_test)

        acc = float(accuracy_score(y_cat_test, lgb_clf_pred))
        prec = float(precision_score(y_cat_test, lgb_clf_pred, average='weighted', zero_division=0))
        rec = float(recall_score(y_cat_test, lgb_clf_pred, average='weighted', zero_division=0))
        f1 = float(f1_score(y_cat_test, lgb_clf_pred, average='weighted', zero_division=0))

        comparison_report['classification']['LightGBM Classifier'] = {
            'task': 'Risk Level Category (LOW, MEDIUM, HIGH, CRITICAL)',
            'accuracy': round(acc, 3),
            'precision': round(prec, 3),
            'recall': round(rec, 3),
            'f1_score': round(f1, 3),
            'type': 'LightGBM Decision Trees',
            'status': 'OPERATIONAL'
        }
        print(f"[LightGBM Classifier] Accuracy: {acc:.3f} | F1: {f1:.3f}")

        lgb_bundle = {
            'regressor': lgb_reg,
            'classifier': lgb_clf
        }
        joblib.dump(lgb_bundle, MODEL_DIR / 'lightgbm_risk_model.joblib')
    except Exception as e:
        print(f"[LightGBM Training Error]: {e}")

    # -------------------------------------------------------------
    # 4. TRAIN & EXPORT LOGISTIC REGRESSION
    # -------------------------------------------------------------
    print("\nTraining Logistic Regression Pipeline...")
    lr_pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', LogisticRegression(max_iter=1000, C=1.0, random_state=42))
    ])
    lr_pipe.fit(X_train, y_cat_train)
    lr_pred = lr_pipe.predict(X_test)

    acc = float(accuracy_score(y_cat_test, lr_pred))
    prec = float(precision_score(y_cat_test, lr_pred, average='weighted', zero_division=0))
    rec = float(recall_score(y_cat_test, lr_pred, average='weighted', zero_division=0))
    f1 = float(f1_score(y_cat_test, lr_pred, average='weighted', zero_division=0))

    comparison_report['classification']['Logistic Regression'] = {
        'task': 'Risk Level Category (LOW, MEDIUM, HIGH, CRITICAL)',
        'accuracy': round(acc, 3),
        'precision': round(prec, 3),
        'recall': round(rec, 3),
        'f1_score': round(f1, 3),
        'type': 'Linear Interpretable Classifier',
        'status': 'OPERATIONAL',
        'artifact': 'ml/models/logistic_regression_model.joblib'
    }
    print(f"[Logistic Regression] Accuracy: {acc:.3f} | F1: {f1:.3f}")
    joblib.dump(lr_pipe, MODEL_DIR / 'logistic_regression_model.joblib')

    # -------------------------------------------------------------
    # 5. TRAIN & EXPORT SUPPORT VECTOR MACHINE (SVM)
    # -------------------------------------------------------------
    print("\nTraining Support Vector Machine (SVC with RBF kernel)...")
    svm_pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('svc', SVC(C=1.5, kernel='rbf', probability=True, random_state=42))
    ])
    svm_pipe.fit(X_train, y_cat_train)
    svm_pred = svm_pipe.predict(X_test)

    acc = float(accuracy_score(y_cat_test, svm_pred))
    prec = float(precision_score(y_cat_test, svm_pred, average='weighted', zero_division=0))
    rec = float(recall_score(y_cat_test, svm_pred, average='weighted', zero_division=0))
    f1 = float(f1_score(y_cat_test, svm_pred, average='weighted', zero_division=0))

    comparison_report['classification']['Support Vector Machine'] = {
        'task': 'Risk Level Category (LOW, MEDIUM, HIGH, CRITICAL)',
        'accuracy': round(acc, 3),
        'precision': round(prec, 3),
        'recall': round(rec, 3),
        'f1_score': round(f1, 3),
        'type': 'Kernel Non-Linear Classifier (RBF)',
        'status': 'OPERATIONAL',
        'artifact': 'ml/models/svm_model.joblib'
    }
    print(f"[Support Vector Machine] Accuracy: {acc:.3f} | F1: {f1:.3f}")
    joblib.dump(svm_pipe, MODEL_DIR / 'svm_model.joblib')

    # -------------------------------------------------------------
    # 6. TRAIN & EXPORT K-MEANS CLUSTERING
    # -------------------------------------------------------------
    print("\nTraining K-Means Clustering (k=4)...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    kmeans.fit(X_scaled)

    kmeans_bundle = {
        'scaler': scaler,
        'model': kmeans,
        'inertia': float(kmeans.inertia_)
    }
    comparison_report['unsupervised']['K-Means Clustering'] = {
        'task': 'Risk Archetype Grouping',
        'k_clusters': 4,
        'inertia': round(float(kmeans.inertia_), 1),
        'status': 'OPERATIONAL',
        'artifact': 'ml/models/kmeans_model.joblib'
    }
    print(f"[K-Means Clustering] Inertia: {kmeans.inertia_:.1f}")
    joblib.dump(kmeans_bundle, MODEL_DIR / 'kmeans_model.joblib')

    # -------------------------------------------------------------
    # 7. TRAIN & EXPORT ISOLATION FOREST ANOMALY DETECTION
    # -------------------------------------------------------------
    print("\nTraining Isolation Forest (contamination=0.08)...")
    iso = IsolationForest(
        n_estimators=100,
        contamination=0.08,
        random_state=42,
        n_jobs=-1
    )
    iso.fit(X)

    comparison_report['unsupervised']['Isolation Forest'] = {
        'task': 'Indicator Anomaly Detection',
        'contamination': 0.08,
        'status': 'OPERATIONAL',
        'artifact': 'ml/models/isolation_forest_model.joblib'
    }
    print(f"[Isolation Forest] Fit complete on {len(X)} samples.")
    joblib.dump(iso, MODEL_DIR / 'isolation_forest_model.joblib')

    # -------------------------------------------------------------
    # 8. SAVE COMPARISON BENCHMARK REPORT
    # -------------------------------------------------------------
    save_model_comparison_report(comparison_report)
    print(f"\nAll models successfully trained and serialized to: {MODEL_DIR}")
    print(f"Benchmark comparison saved to: {MODEL_DIR / 'model_comparison_metrics.json'}")
    return comparison_report

if __name__ == '__main__':
    train_and_export_all_models()
