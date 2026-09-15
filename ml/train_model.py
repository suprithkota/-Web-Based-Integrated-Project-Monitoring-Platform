import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import joblib

from ml.preprocessing import extract_features_from_dict

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / 'ml' / 'models'

def generate_synthetic_training_data(n_samples=1000, random_seed=42):
    """
    Generates a calibrated synthetic dataset reflecting standard infrastructure monitoring
    patterns to train the ML regression engine.
    """
    np.random.seed(random_seed)
    
    X = []
    y = []
    
    contractor_options = ['On Track', 'Minor Delay', 'Delayed', 'Critical']
    status_options = ['Completed', 'In Progress', 'Delayed', 'Pending']
    
    for _ in range(n_samples):
        # Generate realistic project feature variations
        approved_cost = float(np.random.uniform(100.0, 15000.0))
        cost_esc_mult = np.random.choice([1.0, 1.05, 1.15, 1.25, 1.45], p=[0.45, 0.25, 0.15, 0.10, 0.05])
        revised_cost = float(approved_cost * cost_esc_mult)
        
        planned_prog = float(np.random.uniform(15.0, 95.0))
        # Actual progress depends on risk conditions
        gap = float(np.random.choice([0.0, 5.0, 15.0, 30.0], p=[0.4, 0.3, 0.2, 0.1]) + np.random.uniform(-2.0, 5.0))
        gap = max(0.0, min(planned_prog - 5.0, gap))
        physical_prog = max(5.0, min(100.0, planned_prog - gap))
        
        budget_util = min(100.0, (physical_prog + np.random.uniform(-5.0, 25.0)))
        expenditure = float(approved_cost * (budget_util / 100.0))
        
        milestones_total = int(np.random.choice([4, 6, 8, 10]))
        milestones_delayed = int(min(milestones_total, np.random.choice([0, 1, 2, 4, 6], p=[0.45, 0.25, 0.15, 0.10, 0.05])))
        
        delay_days = int(np.random.choice([0, 45, 120, 280, 450], p=[0.40, 0.25, 0.15, 0.12, 0.08]))
        contractor = np.random.choice(contractor_options, p=[0.55, 0.25, 0.15, 0.05])
        land = np.random.choice(status_options, p=[0.50, 0.30, 0.15, 0.05])
        env = np.random.choice(status_options, p=[0.60, 0.25, 0.10, 0.05])
        utility = np.random.choice(status_options, p=[0.55, 0.25, 0.15, 0.05])
        
        p_dict = {
            'approved_cost': approved_cost,
            'revised_cost': revised_cost,
            'expenditure': expenditure,
            'physical_progress': physical_prog,
            'planned_progress': planned_prog,
            'milestones_total': milestones_total,
            'milestones_delayed': milestones_delayed,
            'delay_days': delay_days,
            'contractor_status': contractor,
            'land_acquisition_status': land,
            'environmental_clearance_status': env,
            'utility_shifting_status': utility
        }
        
        feat_vec, raw = extract_features_from_dict(p_dict)
        
        # Ground-truth risk formula with realistic random noise
        # 0 to 100 scale
        risk_ground_truth = (
            0.28 * min(100.0, raw['progress_gap'] * 2.8) +
            0.22 * (raw['milestone_delay_ratio'] * 100.0) +
            0.20 * min(100.0, raw['cost_escalation'] * 3.0) +
            0.15 * min(100.0, (raw['delay_days'] / 240.0) * 100.0) +
            0.15 * ((raw['contractor_risk'] + raw['land_risk'] + raw['env_risk'] + raw['utility_risk']) / 4.0 * 100.0)
        )
        # add slight sensor/reporting noise
        noise = np.random.normal(0, 2.5)
        risk_ground_truth = max(3.0, min(98.0, risk_ground_truth + noise))
        
        X.append(feat_vec)
        y.append(risk_ground_truth)
        
    return np.array(X), np.array(y)

def train_and_export_model():
    """
    Trains the Random Forest model and saves it to disk.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    X, y = generate_synthetic_training_data(n_samples=1200)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=8,
        min_samples_split=4,
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    output_file = MODEL_DIR / 'risk_engine.joblib'
    joblib.dump(model, output_file)
    
    print(f"Model successfully trained.")
    print(f"Artifact saved to: {output_file}")
    print(f"Test Evaluation: MSE = {mse:.3f}, R2 Score = {r2:.3f}")
    return model, mse, r2

if __name__ == '__main__':
    train_and_export_model()
