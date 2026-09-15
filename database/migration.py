import sqlite3
from pathlib import Path

def ensure_database_schema(db_path="instance/project_monitoring.db"):
    db_file = Path(db_path)
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

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration check: {e}")

