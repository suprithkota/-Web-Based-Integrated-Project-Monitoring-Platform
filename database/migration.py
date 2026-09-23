import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def ensure_database_schema(db_path="instance/project_monitoring.db"):
    db_file = Path(db_path)
    if not db_file.is_absolute():
        db_file = BASE_DIR / db_file
    if not db_file.exists():
        return

    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1]: row for row in cursor.fetchall()}

        new_columns = [
            ("organization", "VARCHAR(150) DEFAULT ''"),
            ("email_verified", "BOOLEAN DEFAULT 0 NOT NULL"),
            ("status", "VARCHAR(32) DEFAULT 'pending_verification' NOT NULL"),
            ("verification_token", "VARCHAR(128)"),
            ("verification_token_expires_at", "DATETIME"),
            ("reset_token", "VARCHAR(128)"),
            ("reset_token_expires_at", "DATETIME"),
            ("phone_number", "VARCHAR(20) DEFAULT ''"),
            ("sms_code", "VARCHAR(16)"),
            ("sms_code_expires_at", "DATETIME"),
            ("last_resend_at", "DATETIME"),
            ("resend_count", "INTEGER DEFAULT 0"),
            ("failed_login_attempts", "INTEGER DEFAULT 0"),
            ("locked_until", "DATETIME")
        ]

        for col_name, col_def in new_columns:
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

        cursor.execute('''
            UPDATE users
            SET email_verified = 1, status = 'active'
            WHERE role = 'admin' OR username IN ('admin', 'officer', 'viewer')
        ''')

        cursor.execute('''
            UPDATE users SET phone_number = '+91 98765 43210' WHERE username = 'admin' AND (phone_number IS NULL OR phone_number = '')
        ''')
        cursor.execute('''
            UPDATE users SET phone_number = '+91 98765 43211' WHERE username = 'officer' AND (phone_number IS NULL OR phone_number = '')
        ''')
        cursor.execute('''
            UPDATE users SET phone_number = '+91 98765 43212' WHERE username = 'viewer' AND (phone_number IS NULL OR phone_number = '')
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS security_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username VARCHAR(64),
                action VARCHAR(100) NOT NULL,
                resource_type VARCHAR(50),
                resource_id VARCHAR(50),
                details TEXT,
                ip_address VARCHAR(64),
                user_agent VARCHAR(255),
                status VARCHAR(20) DEFAULT 'SUCCESS' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON security_audit_logs (action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON security_audit_logs (created_at)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                can_edit BOOLEAN DEFAULT 1 NOT NULL,
                role_scope VARCHAR(50) DEFAULT 'Monitoring Officer',
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                UNIQUE(user_id, project_id)
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_assignment_user_id ON project_assignments (user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_assignment_project_id ON project_assignments (project_id)")

        # Seed initial project assignments for officer if none exist
        cursor.execute("SELECT id FROM users WHERE username = 'officer' OR role = 'officer' LIMIT 1")
        officer_row = cursor.fetchone()
        if officer_row:
            officer_id = officer_row[0]
            cursor.execute("SELECT COUNT(*) FROM project_assignments WHERE user_id = ?", (officer_id,))
            if cursor.fetchone()[0] == 0:
                # Assign the first 3 projects to officer (leaving project 4+ unassigned to test object authorization boundaries)
                cursor.execute("SELECT id FROM projects ORDER BY id ASC LIMIT 3")
                project_rows = cursor.fetchall()
                for pr in project_rows:
                    cursor.execute('''
                        INSERT OR IGNORE INTO project_assignments (user_id, project_id, can_edit, role_scope)
                        VALUES (?, ?, 1, 'Monitoring Officer')
                    ''', (officer_id, pr[0]))

        # Add user columns if missing
        user_new_cols = [
            ("technical_designation", "VARCHAR(50) DEFAULT 'Monitoring Officer'"),
            ("jurisdiction", "VARCHAR(150) DEFAULT ''")
        ]
        for col_name, col_def in user_new_cols:
            if col_name not in columns:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")

        # Add project columns if missing
        cursor.execute("PRAGMA table_info(projects)")
        proj_columns = {row[1]: row for row in cursor.fetchall()}
        new_proj_columns = [
            ("contractor_id", "INTEGER REFERENCES contractors(id) ON DELETE SET NULL"),
            ("original_budget", "FLOAT DEFAULT 0.0"),
            ("final_cost", "FLOAT DEFAULT 0.0"),
            ("contract_value", "FLOAT DEFAULT 0.0"),
            ("planned_duration_months", "INTEGER DEFAULT 0"),
            ("actual_duration_months", "INTEGER DEFAULT 0"),
            ("completion_certificate_ref", "VARCHAR(100) DEFAULT ''"),
            ("completion_certificate_date", "DATE"),
            ("documented_delay_reason", "TEXT DEFAULT ''"),
            ("responsible_stakeholder", "VARCHAR(200) DEFAULT ''"),
            ("latest_govt_inspection", "TEXT DEFAULT ''"),
            ("latest_contractor_update", "TEXT DEFAULT ''"),
            ("corrective_action", "TEXT DEFAULT ''"),
            ("expected_restart_date", "DATE"),
            ("current_construction_stage", "VARCHAR(100) DEFAULT ''"),
            ("current_site_status", "VARCHAR(255) DEFAULT ''"),
            ("reported_issues", "TEXT DEFAULT '{}'"),
            ("data_source", "VARCHAR(200) DEFAULT 'Official Department Project Record'"),
            ("source_timestamp", "DATETIME"),
            ("sync_timestamp", "DATETIME"),
            ("verification_status", "VARCHAR(50) DEFAULT 'Verified'")
        ]
        for col_name, col_def in new_proj_columns:
            if col_name not in proj_columns:
                cursor.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_def}")

        # Create all new tables using CREATE TABLE IF NOT EXISTS
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contractors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL,
                contractor_code VARCHAR(64) UNIQUE NOT NULL,
                registration_number VARCHAR(100) UNIQUE NOT NULL,
                contractor_license_number VARCHAR(100) DEFAULT '',
                company_type VARCHAR(100) DEFAULT 'Private Limited',
                owner_representative VARCHAR(200) DEFAULT '',
                year_established INTEGER DEFAULT 2000,
                years_of_experience INTEGER DEFAULT 24,
                headquarters VARCHAR(200) DEFAULT '',
                contact_email VARCHAR(120) DEFAULT '',
                contact_phone VARCHAR(50) DEFAULT '',
                address TEXT DEFAULT '',
                website VARCHAR(255) DEFAULT '',
                govt_registration_details TEXT DEFAULT '',
                license_validity_date DATE,
                registration_status VARCHAR(50) DEFAULT 'Active',
                contractor_class VARCHAR(50) DEFAULT 'Class 1 / Class A',
                areas_of_specialization TEXT DEFAULT '[]',
                sectors_served TEXT DEFAULT '[]',
                certifications TEXT DEFAULT '[]',
                data_source VARCHAR(200) DEFAULT 'Central / State Contractor Registry',
                source_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sync_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                verification_status VARCHAR(50) DEFAULT 'Verified',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contractors_name ON contractors (name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_contractors_reg ON contractors (registration_number)")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contractor_branches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contractor_id INTEGER NOT NULL REFERENCES contractors(id) ON DELETE CASCADE,
                branch_name VARCHAR(200) NOT NULL,
                location VARCHAR(200) NOT NULL,
                branch_manager VARCHAR(150) DEFAULT '',
                contact_email VARCHAR(120) DEFAULT '',
                contact_phone VARCHAR(50) DEFAULT '',
                address TEXT DEFAULT '',
                registration_info VARCHAR(200) DEFAULT '',
                workforce_count INTEGER DEFAULT 0,
                equipment_summary TEXT DEFAULT '',
                departments_served TEXT DEFAULT '[]',
                local_suppliers TEXT DEFAULT '[]',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS material_suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) UNIQUE NOT NULL,
                registration_number VARCHAR(100) DEFAULT '',
                category VARCHAR(100) DEFAULT '',
                contact_person VARCHAR(150) DEFAULT '',
                phone VARCHAR(50) DEFAULT '',
                email VARCHAR(120) DEFAULT '',
                address TEXT DEFAULT '',
                city VARCHAR(100) DEFAULT '',
                state VARCHAR(100) DEFAULT '',
                certifications TEXT DEFAULT '',
                delivery_delay_records INTEGER DEFAULT 0,
                data_source VARCHAR(200) DEFAULT 'Official Supplier Register',
                verification_status VARCHAR(50) DEFAULT 'Verified',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
                supplier_id INTEGER REFERENCES material_suppliers(id) ON DELETE SET NULL,
                material_name VARCHAR(200) NOT NULL,
                material_category VARCHAR(100) NOT NULL,
                brand_manufacturer VARCHAR(150) DEFAULT '',
                batch_number VARCHAR(100) DEFAULT '',
                quantity FLOAT DEFAULT 0.0,
                unit VARCHAR(50) DEFAULT 'MT',
                delivery_date DATE,
                source_location VARCHAR(200) DEFAULT '',
                purchase_order_ref VARCHAR(100) DEFAULT '',
                invoice_ref VARCHAR(100) DEFAULT '',
                required_specification TEXT DEFAULT '',
                actual_specification TEXT DEFAULT '',
                approval_status VARCHAR(50) DEFAULT 'Approved',
                quality_certification_status VARCHAR(100) DEFAULT 'Pending Test',
                quality_certificate_ref VARCHAR(150) DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute("PRAGMA table_info(project_materials)")
        pm_columns = {row[1]: row for row in cursor.fetchall()}
        if "quality_certification_status" not in pm_columns and pm_columns:
            cursor.execute("ALTER TABLE project_materials ADD COLUMN quality_certification_status VARCHAR(100) DEFAULT 'Pending Test'")
            cursor.execute("UPDATE project_materials SET quality_certification_status = 'BIS Certified' WHERE approval_status = 'Approved'")


        cursor.execute('''
            CREATE TABLE IF NOT EXISTS material_quality_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_id INTEGER NOT NULL REFERENCES project_materials(id) ON DELETE CASCADE,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                test_name VARCHAR(200) NOT NULL,
                required_standard VARCHAR(150) DEFAULT '',
                manufacturer_spec TEXT DEFAULT '',
                dept_specification TEXT DEFAULT '',
                test_standard VARCHAR(150) DEFAULT '',
                test_date DATE,
                testing_laboratory VARCHAR(200) DEFAULT 'NABL Accredited Lab',
                test_result_value VARCHAR(200) DEFAULT '',
                status VARCHAR(30) DEFAULT 'PASS',
                inspector_name VARCHAR(150) DEFAULT '',
                inspector_designation VARCHAR(150) DEFAULT 'Quality Assurance Engineer',
                quality_certificate_ref VARCHAR(150) DEFAULT '',
                sample_info TEXT DEFAULT '',
                rejection_information TEXT DEFAULT '',
                replacement_information TEXT DEFAULT '',
                verified_at DATETIME,
                verified_by VARCHAR(100) DEFAULT ''
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_delay_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
                delay_category VARCHAR(50) NOT NULL,
                delay_description TEXT NOT NULL,
                start_date DATE,
                end_date DATE,
                affected_days INTEGER DEFAULT 0,
                evidence_document_ref VARCHAR(200) DEFAULT '',
                official_source VARCHAR(200) DEFAULT '',
                responsible_authority VARCHAR(200) DEFAULT '',
                officer_remarks TEXT DEFAULT '',
                corrective_action TEXT DEFAULT '',
                verification_status VARCHAR(50) DEFAULT 'Verified',
                recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_financial_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                record_type VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                reference_no VARCHAR(100) DEFAULT '',
                approved_amount FLOAT DEFAULT 0.0,
                actual_expenditure FLOAT DEFAULT 0.0,
                sanction_date DATE,
                sanctioning_authority VARCHAR(150) DEFAULT '',
                notes TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_lifecycle_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                stage_name VARCHAR(150) NOT NULL,
                planned_date DATE,
                actual_date DATE,
                status VARCHAR(50) DEFAULT 'Completed',
                delay_days INTEGER DEFAULT 0,
                remarks TEXT DEFAULT '',
                sequence_order INTEGER DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS post_construction_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
                inspection_date DATE,
                inspector_name VARCHAR(150) DEFAULT '',
                warranty_dlp_expiry DATE,
                quality_status VARCHAR(50) DEFAULT 'No significant defects reported',
                structural_condition VARCHAR(100) DEFAULT 'Good',
                road_condition VARCHAR(100) DEFAULT 'Satisfactory',
                building_condition VARCHAR(100) DEFAULT 'Good',
                cracks_observed TEXT DEFAULT 'None',
                water_leakage_status TEXT DEFAULT 'None',
                corrosion_settlement_status TEXT DEFAULT 'None',
                drainage_status TEXT DEFAULT 'Operational',
                verified_findings TEXT DEFAULT '',
                repair_history TEXT DEFAULT '',
                defect_reports TEXT DEFAULT '',
                maintenance_requirements TEXT DEFAULT ''
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_subcontractors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                contractor_id INTEGER NOT NULL REFERENCES contractors(id) ON DELETE CASCADE,
                subcontractor_name VARCHAR(255) NOT NULL,
                registration_number VARCHAR(100) DEFAULT '',
                scope_of_work VARCHAR(255) DEFAULT '',
                contract_value FLOAT DEFAULT 0.0,
                performance_status VARCHAR(50) DEFAULT 'Satisfactory'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS department_hierarchies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_name VARCHAR(150) NOT NULL,
                region_circle VARCHAR(150) DEFAULT '',
                district VARCHAR(100) DEFAULT '',
                division VARCHAR(150) DEFAULT '',
                chief_engineer VARCHAR(150) DEFAULT '',
                superintending_engineer VARCHAR(150) DEFAULT '',
                executive_engineer VARCHAR(150) DEFAULT '',
                assistant_exec_engineer VARCHAR(150) DEFAULT '',
                assistant_engineer VARCHAR(150) DEFAULT '',
                junior_engineer VARCHAR(150) DEFAULT '',
                official_routing_email VARCHAR(120) DEFAULT ''
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS site_inspection_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                officer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                officer_name VARCHAR(120) DEFAULT '',
                officer_designation VARCHAR(50) DEFAULT 'Junior Engineer',
                inspection_date DATE NOT NULL,
                stage_inspected VARCHAR(150) DEFAULT '',
                work_completed_percentage FLOAT DEFAULT 0.0,
                measurements_recorded TEXT DEFAULT '',
                gps_latitude FLOAT,
                gps_longitude FLOAT,
                photos_json TEXT DEFAULT '[]',
                verification_status VARCHAR(50) DEFAULT 'Pending EE Review',
                reviewed_by VARCHAR(120) DEFAULT '',
                reviewed_at DATETIME,
                review_remarks TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS public_complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_code VARCHAR(50) UNIQUE NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
                location VARCHAR(255) NOT NULL,
                gps_lat FLOAT,
                gps_lng FLOAT,
                category VARCHAR(100) NOT NULL,
                description TEXT NOT NULL,
                complainant_name VARCHAR(120) DEFAULT 'Citizen',
                complainant_contact VARCHAR(100) DEFAULT '',
                evidence_file_path VARCHAR(255) DEFAULT '',
                status VARCHAR(50) DEFAULT 'Submitted',
                routed_department VARCHAR(150) DEFAULT '',
                assigned_officer VARCHAR(150) DEFAULT '',
                official_response TEXT DEFAULT '',
                inspection_finding_ref TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS document_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_code VARCHAR(64) UNIQUE NOT NULL,
                project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                contractor_id INTEGER REFERENCES contractors(id) ON DELETE SET NULL,
                material_id INTEGER REFERENCES project_materials(id) ON DELETE SET NULL,
                doc_type VARCHAR(100) NOT NULL,
                title VARCHAR(255) NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                file_size_bytes INTEGER DEFAULT 0,
                mime_type VARCHAR(100) DEFAULT 'application/pdf',
                source_agency VARCHAR(200) DEFAULT '',
                document_version VARCHAR(20) DEFAULT 'v1.0',
                verification_status VARCHAR(50) DEFAULT 'Verified',
                tamper_hash VARCHAR(64) DEFAULT '',
                uploaded_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_source_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name VARCHAR(200) UNIQUE NOT NULL,
                department VARCHAR(150) DEFAULT '',
                source_type VARCHAR(50) DEFAULT 'API',
                endpoint_url VARCHAR(500) DEFAULT '',
                auth_method VARCHAR(50) DEFAULT 'None',
                encrypted_auth_secret VARCHAR(255) DEFAULT '',
                sync_method VARCHAR(50) DEFAULT 'Polling',
                sync_frequency VARCHAR(50) DEFAULT '1 hour',
                source_priority INTEGER DEFAULT 1,
                connection_status VARCHAR(50) DEFAULT 'Connected',
                last_successful_sync DATETIME,
                next_scheduled_sync DATETIME,
                records_imported INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_rejected INTEGER DEFAULT 0,
                last_error_message TEXT DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_sync_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sync_id VARCHAR(64) UNIQUE NOT NULL,
                source_id INTEGER REFERENCES data_source_configs(id) ON DELETE SET NULL,
                source_name VARCHAR(200) DEFAULT '',
                trigger_type VARCHAR(50) DEFAULT 'Scheduled',
                request_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                response_time_ms INTEGER DEFAULT 0,
                records_received INTEGER DEFAULT 0,
                records_inserted INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_rejected INTEGER DEFAULT 0,
                validation_failures INTEGER DEFAULT 0,
                error_details TEXT DEFAULT '',
                status VARCHAR(20) DEFAULT 'SUCCESS',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_version_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER NOT NULL,
                field_name VARCHAR(100) NOT NULL,
                previous_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                source_name VARCHAR(200) DEFAULT '',
                source_timestamp DATETIME,
                sync_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                verification_status VARCHAR(50) DEFAULT 'Verified',
                changed_by VARCHAR(100) DEFAULT 'Sync Engine',
                reason TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_conflict_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER NOT NULL,
                field_name VARCHAR(100) NOT NULL,
                source_a_name VARCHAR(200) NOT NULL,
                source_a_value TEXT NOT NULL,
                source_a_timestamp DATETIME,
                source_b_name VARCHAR(200) NOT NULL,
                source_b_value TEXT NOT NULL,
                source_b_timestamp DATETIME,
                status VARCHAR(50) DEFAULT 'Unresolved',
                resolved_value TEXT DEFAULT '',
                resolved_by VARCHAR(100) DEFAULT '',
                resolved_at DATETIME,
                notes TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration check: {e}")


