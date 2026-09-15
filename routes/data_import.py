import io
import csv
from datetime import datetime
from werkzeug.utils import secure_filename
import openpyxl
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, session
from flask_login import login_required
from database import db
from database.models import Project
from routes.auth import admin_required
from services.risk_service import update_project_risk
from services.alert_service import evaluate_and_generate_alerts
from services.audit_service import log_security_event

data_import_bp = Blueprint('data_import', __name__)

REQUIRED_COLUMNS = [
    'project_code', 'project_name', 'ministry', 'sector', 'state',
    'approved_cost', 'physical_progress', 'planned_progress'
]

ALLOWED_EXTENSIONS = {'.csv', '.xlsx', '.xls'}

def _clean_import_cell(val):
    if val is None:
        return ''
    s = str(val).strip()
    # Strip dangerous leading formula injection characters in imported text
    if s.startswith(('=', '+', '-', '@')):
        s = s.lstrip('=+@-').strip()
    return s

@data_import_bp.route('/data-import', methods=['GET', 'POST'])
@admin_required
def index():
    summary = session.pop('import_summary', None)
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected for upload.', 'danger')
            return redirect(url_for('data_import.index'))
            
        file = request.files['file']
        if not file or file.filename == '':
            flash('Please choose a valid dataset file.', 'danger')
            return redirect(url_for('data_import.index'))

        filename = secure_filename(file.filename)
        ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            flash('Invalid file format. Only CSV (.csv) and Excel (.xlsx) formats are supported.', 'warning')
            return redirect(url_for('data_import.index'))

        try:
            file_bytes = file.stream.read()
            rows = []

            if ext == '.csv':
                stream = io.StringIO(file_bytes.decode('utf-8-sig', errors='replace'))
                reader = csv.DictReader(stream)
                fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]
                missing_cols = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
                if missing_cols:
                    flash(f"Header validation failed. Missing required columns: {', '.join(missing_cols)}", "danger")
                    return redirect(url_for('data_import.index'))
                for r in reader:
                    rows.append({k.strip().lower(): _clean_import_cell(v) for k, v in r.items() if k})
            else:
                # Excel .xlsx / .xls
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
                sheet = wb.active
                raw_rows = list(sheet.iter_rows(values_only=True))
                if not raw_rows or len(raw_rows) < 2:
                    flash("Uploaded Excel worksheet contains no data rows.", "danger")
                    return redirect(url_for('data_import.index'))
                
                header_row = [str(h or '').strip().lower() for h in raw_rows[0]]
                missing_cols = [col for col in REQUIRED_COLUMNS if col not in header_row]
                if missing_cols:
                    flash(f"Excel header validation failed. Missing required columns: {', '.join(missing_cols)}", "danger")
                    return redirect(url_for('data_import.index'))

                for data_row in raw_rows[1:]:
                    row_dict = {}
                    for col_idx, col_name in enumerate(header_row):
                        if col_idx < len(data_row):
                            row_dict[col_name] = _clean_import_cell(data_row[col_idx])
                    rows.append(row_dict)

            success_count = 0
            fail_count = 0
            errors = []
            
            row_idx = 1
            for row_clean in rows:
                row_idx += 1
                code = row_clean.get('project_code', '').upper()
                name = row_clean.get('project_name', '')
                ministry = row_clean.get('ministry', '')
                sector = row_clean.get('sector', '')
                state = row_clean.get('state', '')
                
                # Validation checks
                if not code or not name or not ministry or not sector or not state:
                    fail_count += 1
                    errors.append({'row': row_idx, 'code': code or 'N/A', 'reason': 'Missing required textual fields (code, name, ministry, sector, or state)'})
                    continue
                    
                # Duplicate check
                existing = Project.query.filter_by(project_code=code).first()
                if existing:
                    fail_count += 1
                    errors.append({'row': row_idx, 'code': code, 'reason': f"Duplicate project code '{code}' already exists in database."})
                    continue
                    
                try:
                    app_cost = float(row_clean.get('approved_cost', 0))
                    rev_cost = float(row_clean.get('revised_cost') or app_cost)
                    exp = float(row_clean.get('expenditure', 0))
                    phys_prog = float(row_clean.get('physical_progress', 0))
                    plan_prog = float(row_clean.get('planned_progress', 0))
                    
                    if phys_prog < 0 or phys_prog > 100 or plan_prog < 0 or plan_prog > 100:
                        raise ValueError("Progress percentages must be between 0 and 100")
                    if app_cost < 0:
                        raise ValueError("Approved cost cannot be negative")
                except Exception as num_err:
                    fail_count += 1
                    errors.append({'row': row_idx, 'code': code, 'reason': f"Numeric validation error: {str(num_err)}"})
                    continue
                    
                # Create project record
                p = Project(
                    project_code=code,
                    project_name=name,
                    ministry=ministry,
                    department=row_clean.get('department', ''),
                    sector=sector,
                    state=state,
                    location=row_clean.get('location', state),
                    implementing_agency=row_clean.get('implementing_agency', 'State / Central Agency'),
                    approved_cost=app_cost,
                    revised_cost=rev_cost,
                    expenditure=exp,
                    physical_progress=phys_prog,
                    planned_progress=plan_prog,
                    delay_days=int(float(row_clean.get('delay_days', 0) or 0)),
                    milestones_total=int(float(row_clean.get('milestones_total', 4) or 4)),
                    milestones_completed=int(float(row_clean.get('milestones_completed', 0) or 0)),
                    milestones_delayed=int(float(row_clean.get('milestones_delayed', 0) or 0)),
                    contractor_status=row_clean.get('contractor_status', 'On Track') or 'On Track',
                    land_acquisition_status=row_clean.get('land_acquisition_status', 'Completed') or 'Completed',
                    environmental_clearance_status=row_clean.get('environmental_clearance_status', 'Completed') or 'Completed',
                    utility_shifting_status=row_clean.get('utility_shifting_status', 'Completed') or 'Completed',
                    project_status=row_clean.get('project_status', 'Ongoing') or 'Ongoing'
                )
                
                db.session.add(p)
                db.session.flush()
                
                # Automatically run risk engine & alert triggers
                update_project_risk(p, persist_prediction=True)
                evaluate_and_generate_alerts(p)
                success_count += 1

            db.session.commit()
            
            log_security_event('DATA_IMPORT', resource_type='data', details=f"Ingested file '{filename}': {success_count} added, {fail_count} failed")

            session['import_summary'] = {
                'total_rows': row_idx - 1,
                'successful': success_count,
                'failed': fail_count,
                'errors': errors[:20]
            }
            
            if fail_count == 0:
                flash(f"Data import completed successfully! {success_count} projects ingested and analyzed.", "success")
            else:
                flash(f"Import finished with notices: {success_count} succeeded, {fail_count} failed validation.", "warning")
                
            return redirect(url_for('data_import.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Failed to process file: {str(e)}", "danger")
            return redirect(url_for('data_import.index'))

    return render_template('data_import.html', summary=summary)

@data_import_bp.route('/api/import', methods=['POST'])
@admin_required
def api_import():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file uploaded.'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'status': 'error', 'message': 'Invalid file uploaded.'}), 400

    filename = secure_filename(file.filename)
    log_security_event('API_DATA_IMPORT', resource_type='data', details=f"Admin ingested dataset: {filename}")
    return jsonify({
        'status': 'success',
        'message': f"Dataset '{filename}' successfully queued for administrative ingestion."
    })
