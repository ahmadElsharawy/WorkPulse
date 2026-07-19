import os
import sqlite3
import random
import json
from datetime import datetime, timedelta
from flask import g, current_app
from faker import Faker
from .extensions import bcrypt

def get_user_preferences(user_id):
    db = get_db()
    row = db.execute('SELECT * FROM user_preferences WHERE user_id = ?', (user_id,)).fetchone()
    if not row:
        try:
            db.execute('INSERT INTO user_preferences (user_id, lang, filters) VALUES (?, ?, ?)', (user_id, 'ar', '{}'))
            db.commit()
        except sqlite3.IntegrityError:
            pass
        return {'user_id': user_id, 'lang': 'ar', 'filters': {}}
    
    filters = {}
    if row['filters']:
        try:
            filters = json.loads(row['filters'])
        except Exception:
            filters = {}
    return {
        'user_id': row['user_id'],
        'lang': row['lang'] or 'ar',
        'filters': filters
    }

def save_user_preferences(user_id, lang=None, filters=None):
    db = get_db()
    pref = get_user_preferences(user_id)
    new_lang = lang if lang is not None else pref['lang']
    new_filters = pref['filters']
    if filters is not None:
        for page_key, page_val in filters.items():
            new_filters[page_key] = page_val
            
    db.execute('''
        INSERT OR REPLACE INTO user_preferences (user_id, lang, filters)
        VALUES (?, ?, ?)
    ''', (user_id, new_lang, json.dumps(new_filters)))
    db.commit()


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def _ensure_column_exists(db, table, column, col_type):
    """Safely ensure column exists in sqlite table without erroring if present."""
    cursor = db.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

def init_db():
    """Initialize database tables and schema migrations."""
    db = get_db()

    # Users table
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            position TEXT,
            email TEXT,
            phone TEXT,
            employee_number TEXT,
            department TEXT,
            residence_permit_end_date TEXT,
            hire_date TEXT,
            termination_date TEXT,
            basic_salary REAL DEFAULT 0,
            total_salary REAL DEFAULT 0
        )
    ''')
    for col, ctype in [
        ('email', 'TEXT'),
        ('phone', 'TEXT'),
        ('employee_number', 'TEXT'),
        ('department', 'TEXT'),
        ('residence_permit_end_date', 'TEXT'),
        ('hire_date', 'TEXT'),
        ('termination_date', 'TEXT'),
        ('basic_salary', 'REAL DEFAULT 0'),
        ('total_salary', 'REAL DEFAULT 0'),
    ]:
        _ensure_column_exists(db, 'users', col, ctype)

    # Join table for employee-manager
    db.execute('''
        CREATE TABLE IF NOT EXISTS employee_managers (
            employee_id INTEGER NOT NULL,
            manager_id INTEGER NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id),
            FOREIGN KEY(manager_id) REFERENCES users(id),
            PRIMARY KEY (employee_id, manager_id)
        )
    ''')

    # Projects table
    db.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            client TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT
        )
    ''')

    # Join table for employee-project
    db.execute('''
        CREATE TABLE IF NOT EXISTS employee_projects (
            employee_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            allocated_hours INTEGER DEFAULT 0,
            FOREIGN KEY(employee_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            PRIMARY KEY (employee_id, project_id)
        )
    ''')
    _ensure_column_exists(db, 'employee_projects', 'allocated_hours', 'INTEGER DEFAULT 0')

    # Tasks table
    db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            running_duration INTEGER DEFAULT 0,
            last_started_at TEXT,
            creator_id INTEGER NOT NULL,
            approval_status TEXT DEFAULT "Draft",
            approval_comments TEXT,
            approver_id INTEGER,
            FOREIGN KEY(employee_id) REFERENCES users(id),
            FOREIGN KEY(creator_id) REFERENCES users(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
    for col, ctype in [
        ('approval_status', 'TEXT DEFAULT "Draft"'),
        ('approval_comments', 'TEXT'),
        ('approver_id', 'INTEGER'),
    ]:
        _ensure_column_exists(db, 'tasks', col, ctype)

    # User preferences
    db.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            lang TEXT,
            filters TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Leave Requests table
    db.execute('''
        CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            duration_days INTEGER NOT NULL DEFAULT 1,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending_managers',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            rejection_reason TEXT,
            FOREIGN KEY(employee_id) REFERENCES users(id)
        )
    ''')

    # Leave Request Approvals (Chain & Duration Tracking)
    db.execute('''
        CREATE TABLE IF NOT EXISTS leave_request_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leave_request_id INTEGER NOT NULL,
            approver_id INTEGER,
            approver_role TEXT NOT NULL,
            approval_order INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'waiting',
            assigned_at TEXT NOT NULL,
            action_at TEXT,
            response_time_seconds INTEGER DEFAULT 0,
            comments TEXT,
            FOREIGN KEY(leave_request_id) REFERENCES leave_requests(id) ON DELETE CASCADE,
            FOREIGN KEY(approver_id) REFERENCES users(id)
        )
    ''')

    # End of Service HR Adjustments & UAE Leave Types
    db.execute('''
        CREATE TABLE IF NOT EXISTS eos_settlement_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL UNIQUE,
            sick_leave_days REAL DEFAULT 0,
            parental_leave_days REAL DEFAULT 0,
            bereavement_leave_days REAL DEFAULT 0,
            study_leave_days REAL DEFAULT 0,
            hajj_leave_days REAL DEFAULT 0,
            other_leave_days REAL DEFAULT 0,
            additional_additions REAL DEFAULT 0,
            additional_deductions REAL DEFAULT 0,
            gratuity_days_deduction REAL DEFAULT 0,
            gratuity_days_deduction_reason TEXT,
            notes TEXT,
            updated_at TEXT,
            FOREIGN KEY(employee_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    try:
        db.execute('ALTER TABLE eos_settlement_adjustments ADD COLUMN gratuity_days_deduction REAL DEFAULT 0')
    except Exception:
        pass
    try:
        db.execute('ALTER TABLE eos_settlement_adjustments ADD COLUMN gratuity_days_deduction_reason TEXT')
    except Exception:
        pass
    db.commit()

    # Itemized Financial Adjustments with Reasons (Additions & Deductions)
    db.execute('''
        CREATE TABLE IF NOT EXISTS eos_financial_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            amount REAL NOT NULL,
            reason TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # Itemized Gratuity Day Adjustments with Reasons (Additions & Deductions)
    db.execute('''
        CREATE TABLE IF NOT EXISTS eos_gratuity_day_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            days_count REAL NOT NULL,
            reason TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    db.commit()
    db.commit()


def seed_data():
    db = get_db()
    if db.execute('SELECT 1 FROM users WHERE username = ?', ('hr',)).fetchone():
        return
    
    # HR User
    hr_pwd = bcrypt.generate_password_hash('123').decode('utf-8')
    db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
               ('HR User', 'hr', hr_pwd, 'HR', 'HR Manager'))
    
    # Projects
    db.execute('INSERT INTO projects (name, client, start_date, end_date) VALUES (?,?,?,?)', ('Project Alpha', 'Company A', '2026-01-01', '2026-12-31'))
    db.execute('INSERT INTO projects (name, client, start_date, end_date) VALUES (?,?,?,?)', ('Project Beta', 'Company B', '2026-06-01', '2026-11-30'))
    proj_a = db.execute('SELECT id FROM projects WHERE name = ?', ('Project Alpha',)).fetchone()
    proj_b = db.execute('SELECT id FROM projects WHERE name = ?', ('Project Beta',)).fetchone()
    
    # Employees
    ahmed_pwd = bcrypt.generate_password_hash('123').decode('utf-8')
    db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
               ('Ahmed', 'ahmed', ahmed_pwd, 'Employee', 'Software Engineer'))
    
    badr_pwd = bcrypt.generate_password_hash('123').decode('utf-8')
    db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
               ('Badr', 'badr', badr_pwd, 'Employee', 'Team Lead'))
    
    ahmed = db.execute('SELECT id FROM users WHERE username = ?', ('ahmed',)).fetchone()
    badr = db.execute('SELECT id FROM users WHERE username = ?', ('badr',)).fetchone()
    
    if ahmed and badr:
        db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)', (ahmed['id'], badr['id']))
        
        if proj_a:
            db.execute('INSERT OR IGNORE INTO employee_projects (employee_id, project_id) VALUES (?,?)', (ahmed['id'], proj_a['id']))
        if proj_a:
            db.execute('INSERT OR IGNORE INTO employee_projects (employee_id, project_id) VALUES (?,?)', (badr['id'], proj_a['id']))
        if proj_b:
            db.execute('INSERT OR IGNORE INTO employee_projects (employee_id, project_id) VALUES (?,?)', (badr['id'], proj_b['id']))
            
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (ahmed['id'], proj_a['id'] if proj_a else None, 'Task One', 'First sample task', 'Pause', now, 0, ahmed['id']))
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (ahmed['id'], proj_a['id'] if proj_a else None, 'Task Two', 'Second sample task', 'Finish', now, 7200, badr['id']))
        
    db.commit()

def seed_mock_data():
    db = get_db()
    db.execute('DELETE FROM tasks')
    db.execute('DELETE FROM employee_managers')
    db.execute('DELETE FROM employee_projects')
    db.execute('DELETE FROM users WHERE role = "Employee"')
    db.execute('DELETE FROM projects')
    db.commit()

    fake = Faker()
    project_ids = []
    for _ in range(30):
        name = fake.company() + " Project"
        client = fake.company()
        start_date = fake.date_between(start_date='-180d')
        end_date = fake.date_between(start_date=start_date, end_date='+180d')
        cursor = db.execute('INSERT INTO projects (name, client, start_date, end_date) VALUES (?,?,?,?)',
                       (name, client, start_date.isoformat(), end_date.isoformat()))
        project_ids.append(cursor.lastrowid)
    db.commit()

    employee_ids = []
    default_pwd = bcrypt.generate_password_hash('password123').decode('utf-8')
    for _ in range(50):
        full_name = fake.name()
        username = fake.user_name()
        position = fake.job()
        cursor = db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
                    (full_name, username, default_pwd, 'Employee', position))
        employee_ids.append(cursor.lastrowid)
    db.commit()

    for emp_id in employee_ids:
        possible_mgrs = [mid for mid in employee_ids if mid != emp_id]
        mgrs = random.sample(possible_mgrs, k=random.randint(0, 2))
        for mgr in mgrs:
            db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)',
                       (emp_id, mgr))
    db.commit()

    for emp_id in employee_ids:
        emp_projects = random.sample(project_ids, k=random.randint(1, 5))
        for p_id in emp_projects:
            allocated = random.choice([0, 10, 20, 45, 75, 120, 160])
            db.execute('INSERT INTO employee_projects (employee_id, project_id, allocated_hours) VALUES (?,?,?)', (emp_id, p_id, allocated))
    db.commit()

    now = datetime.utcnow()
    total_tasks_created = 0
    for emp_id in employee_ids:
        rows = db.execute('SELECT project_id, allocated_hours FROM employee_projects WHERE employee_id = ?', (emp_id,)).fetchall()
        for row in rows:
            p_id = row['project_id']
            allocated = row['allocated_hours']
            
            if allocated > 0:
                if random.random() < 0.3:
                    target_hours = allocated * random.uniform(1.05, 1.30)
                else:
                    target_hours = allocated * random.uniform(0.15, 0.85)
                target_seconds = int(target_hours * 3600)
            else:
                target_seconds = random.randint(5 * 3600, 60 * 3600)
                
            remaining_seconds = target_seconds
            while remaining_seconds > 0:
                duration = random.randint(3600, min(28800, remaining_seconds))
                if remaining_seconds - duration < 3600:
                    duration = remaining_seconds
                
                remaining_seconds -= duration
                
                days_ago = random.randint(1, 90)
                created_at = now - timedelta(days=days_ago,
                                             hours=random.randint(0, 23),
                                             minutes=random.randint(0, 59))
                created_str = created_at.strftime('%Y-%m-%d %H:%M')
                
                status = random.choice(['Finish', 'Pause', 'Running'])
                title = f"{fake.catch_phrase()} Task"
                desc = fake.sentence()
                
                last_started = None
                if status == 'Running':
                    last_started = (datetime.utcnow() - timedelta(minutes=random.randint(10, 180))).isoformat()
                    
                approval_status = 'Draft'
                approver_id = None
                if status == 'Finish':
                    approval_status = random.choice(['Approved', 'Submitted', 'Draft', 'Rejected'])
                    if approval_status in ['Submitted', 'Approved', 'Rejected']:
                        mgr_row = db.execute('SELECT manager_id FROM employee_managers WHERE employee_id = ?', (emp_id,)).fetchone()
                        if mgr_row:
                            approver_id = mgr_row['manager_id']
                            
                db.execute('''
                    INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id, last_started_at, approval_status, approver_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ''', (emp_id, p_id, title, desc, status, created_str, duration, emp_id, last_started, approval_status, approver_id))
                total_tasks_created += 1
    db.commit()
    return {'projects': len(project_ids), 'employees': len(employee_ids), 'tasks_generated': total_tasks_created}

def get_manager_ids(employee_id):
    db = get_db()
    rows = db.execute('SELECT manager_id FROM employee_managers WHERE employee_id = ?', (employee_id,)).fetchall()
    return [r['manager_id'] for r in rows]

def set_manager_ids(employee_id, manager_ids):
    db = get_db()
    db.execute('DELETE FROM employee_managers WHERE employee_id = ?', (employee_id,))
    for mid in manager_ids:
        db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)', (employee_id, mid))
    db.commit()


def get_pending_approvals_count(user):
    """Return count of submitted tasks pending approval for the given user."""
    if not user or not user.is_authenticated:
        return 0
    try:
        db = get_db()
        if user.is_hr:
            row = db.execute("SELECT COUNT(*) FROM tasks WHERE approval_status = 'Submitted'").fetchone()
        else:
            row = db.execute("SELECT COUNT(*) FROM tasks WHERE approver_id = ? AND approval_status = 'Submitted'", (user.id,)).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0


def get_pending_leave_requests_count(user):
    """Return count of leave requests pending approval for the given user (HR or Manager)."""
    if not user or not user.is_authenticated:
        return 0
    try:
        db = get_db()
        if getattr(user, 'is_hr', False) or user.role == 'HR':
            row = db.execute('''
                SELECT COUNT(*) FROM leave_request_approvals 
                WHERE approver_role = 'HR' AND status = 'pending'
            ''').fetchone()
        else:
            row = db.execute('''
                SELECT COUNT(*) FROM leave_request_approvals 
                WHERE approver_id = ? AND status = 'pending'
            ''', (user.id,)).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0

