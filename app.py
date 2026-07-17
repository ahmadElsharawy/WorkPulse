# app.py
import os, json
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, g, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['DATABASE'] = os.path.join(app.instance_path, 'database.db')

os.makedirs(app.instance_path, exist_ok=True)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

bcrypt = Bcrypt(app)
import random, re
from faker import Faker
@app.template_filter('datetimeformat')
def datetimeformat(value):
    if not value:
        return ""
    try:
        if len(value) >= 16 and value[10] == ' ' and value[13] == ':':
            return value[:16]
        if 'T' in value:
            parts = value.split('T')
            date_part = parts[0]
            time_part = parts[1].split('.')[0]
            time_part = ':'.join(time_part.split(':')[:2])
            return f"{date_part} {time_part}"
        return value
    except Exception:
        return value

@app.template_filter('format_duration')
def format_duration(task):
    try:
        duration = task['running_duration']
        if duration is None:
            duration = 0
    except Exception:
        duration = 0
        
    try:
        status = task['status']
        last_started_at = task['last_started_at']
    except Exception:
        status = None
        last_started_at = None
        
    if status == 'Running' and last_started_at:
        try:
            started_dt = datetime.fromisoformat(last_started_at)
            elapsed = (datetime.utcnow() - started_dt).total_seconds()
            duration += max(0, int(elapsed))
        except Exception:
            pass
            
    hours = duration // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
        
    return " ".join(parts)

@app.template_filter('total_seconds')
def total_seconds(task):
    try:
        duration = task['running_duration']
        if duration is None:
            duration = 0
    except Exception:
        duration = 0
        
    try:
        status = task['status']
        last_started_at = task['last_started_at']
    except Exception:
        status = None
        last_started_at = None
        
    if status == 'Running' and last_started_at:
        try:
            started_dt = datetime.fromisoformat(last_started_at)
            elapsed = (datetime.utcnow() - started_dt).total_seconds()
            duration += max(0, int(elapsed))
        except Exception:
            pass
    return duration

# ---------- Database helpers ----------

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    # Users table: roles are HR or Employee
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            position TEXT
        )
    ''')
    # Join table for many-to-many employee-manager relationship (both roles are Employee)
    db.execute('''
        CREATE TABLE IF NOT EXISTS employee_managers (
            employee_id INTEGER NOT NULL,
            manager_id INTEGER NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id),
            FOREIGN KEY(manager_id) REFERENCES users(id),
            PRIMARY KEY (employee_id, manager_id)
        )
    ''')
    # Join table for many-to-many employee-project relationship
    db.execute('''
        CREATE TABLE IF NOT EXISTS employee_projects (
            employee_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            PRIMARY KEY (employee_id, project_id)
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
    # Tasks table: directly assigned/owned by the employee, created by creator_id
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
            FOREIGN KEY(employee_id) REFERENCES users(id),
            FOREIGN KEY(creator_id) REFERENCES users(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )
    ''')
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
    
    # Employees (who can also be managers)
    ahmed_pwd = bcrypt.generate_password_hash('123').decode('utf-8')
    db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
               ('Ahmed', 'ahmed', ahmed_pwd, 'Employee', 'Software Engineer'))
    
    badr_pwd = bcrypt.generate_password_hash('123').decode('utf-8')
    db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
               ('Badr', 'badr', badr_pwd, 'Employee', 'Team Lead'))
    
    # Ahmed has Badr as manager
    ahmed = db.execute('SELECT id FROM users WHERE username = ?', ('ahmed',)).fetchone()
    badr = db.execute('SELECT id FROM users WHERE username = ?', ('badr',)).fetchone()
    if ahmed and badr:
        db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)', (ahmed['id'], badr['id']))
        
        # Assign Ahmed to Project Alpha
        if proj_a:
            db.execute('INSERT OR IGNORE INTO employee_projects (employee_id, project_id) VALUES (?,?)', (ahmed['id'], proj_a['id']))
            
        # Assign Badr to Project Alpha and Beta
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
    """Populate the SQLite database with mock projects, employees, and tasks."""
    db = get_db()
    # Clear existing data
    db.execute('DELETE FROM tasks')
    db.execute('DELETE FROM employee_managers')
    db.execute('DELETE FROM employee_projects')
    db.execute('DELETE FROM users WHERE role = "Employee"')
    db.execute('DELETE FROM projects')
    db.commit()

    fake = Faker()
    # Create projects
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

    # Create employees
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

    # Assign managers (up to 2 per employee)
    for emp_id in employee_ids:
        possible_mgrs = [mid for mid in employee_ids if mid != emp_id]
        mgrs = random.sample(possible_mgrs, k=random.randint(0, 2))
        for mgr in mgrs:
            db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)',
                       (emp_id, mgr))
    db.commit()

    # Assign projects to employees (1 to 5 random projects)
    for emp_id in employee_ids:
        emp_projects = random.sample(project_ids, k=random.randint(1, 5))
        for p_id in emp_projects:
            db.execute('INSERT INTO employee_projects (employee_id, project_id) VALUES (?,?)', (emp_id, p_id))
    db.commit()

    # Create tasks
    now = datetime.utcnow()
    for emp_id in employee_ids:
        # Fetch assigned projects
        rows = db.execute('SELECT project_id FROM employee_projects WHERE employee_id = ?', (emp_id,)).fetchall()
        emp_project_ids = [r['project_id'] for r in rows]
        if not emp_project_ids:
            emp_project_ids = project_ids
            
        # Generate a realistic workload per employee (50‑150 completed tasks)
        num_tasks = random.randint(50, 150)
        for _ in range(num_tasks):
            project_id = random.choice(emp_project_ids)
            # Distribute tasks over the last 6‑12 months
            days_ago = random.randint(180, 365)
            created_at = now - timedelta(days=days_ago,
                                         hours=random.randint(0, 23),
                                         minutes=random.randint(0, 59))
            created_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
            # Random duration between 0.5h and 8h
            duration = random.randint(1800, 28800)
            status = 'Completed'
            db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                       (emp_id, project_id, 'Task', 'Generated task', status, created_str, duration, emp_id))
    db.commit()
    return {'projects': len(project_ids), 'employees': len(employee_ids), 'tasks_generated': 'variable'}

# ---------- Manager helpers ----------

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

# ---------- User model ----------
class User(UserMixin):
    def __init__(self, id_, username, role, full_name=None):
        self.id = id_
        self.username = username
        self.role = role
        self.full_name = full_name

    @staticmethod
    def get(user_id):
        row = get_db().execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['role'], row['full_name'])
        return None

    @staticmethod
    def find_by_username(username):
        row = get_db().execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['role'], row['full_name'])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# ---------- Role helper ----------
def role_required(*roles):
    def decorator(f):
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied for your role.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        wrapped.__name__ = f.__name__
        return wrapped
    return decorator

# ---------- Routes ----------
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'HR':
            return redirect(url_for('hr_dashboard'))
        elif current_user.role == 'Employee':
            return redirect(url_for('employee_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        row = get_db().execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if row and bcrypt.check_password_hash(row['password_hash'], password):
            user = User(row['id'], row['username'], row['role'], row['full_name'])
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('index'))
        flash('Invalid credentials.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html')
            
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        
        if row and bcrypt.check_password_hash(row['password_hash'], current_password):
            new_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
            db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, current_user.id))
            db.commit()
            flash('Password changed successfully.', 'success')
            return redirect(url_for('index'))
        else:
            flash('Incorrect current password.', 'danger')
            
    return render_template('change_password.html')

# ----- HR Dashboard & User Management -----
@app.route('/hr')
@role_required('HR')
def hr_dashboard():
    db = get_db()
    total_employees = db.execute("SELECT COUNT(*) FROM users WHERE role = 'Employee'").fetchone()[0]
    # Fetch employee task summary
    # Prepare filters
    selected_sum_employees = [int(x) for x in request.args.getlist('sum_employees') if x.isdigit()]
    selected_sum_statuses = request.args.getlist('sum_statuses')  # values: Running, Pause, Finish, Not Work
    
    summary_query = '''
        SELECT u.id, u.full_name AS employee_name,
            SUM(CASE WHEN t.status = 'Running' THEN 1 ELSE 0 END) AS running_cnt,
            SUM(CASE WHEN t.status = 'Pause' THEN 1 ELSE 0 END) AS pause_cnt,
            SUM(CASE WHEN t.status = 'Finish' THEN 1 ELSE 0 END) AS finish_cnt
        FROM users u
        LEFT JOIN tasks t ON u.id = t.employee_id
        WHERE u.role = 'Employee'
    '''
    summary_params = []
    if selected_sum_employees:
        placeholders = ','.join('?' for _ in selected_sum_employees)
        summary_query += f" AND u.id IN ({placeholders})"
        summary_params.extend(selected_sum_employees)
    # Date range filters for summary (apply to task creation date)
    created_from = request.args.get('summary_created_from', '').strip()
    created_to = request.args.get('summary_created_to', '').strip()
    if created_from:
        summary_query += " AND t.created_at >= ?"
        summary_params.append(f"{created_from} 00:00")
    if created_to:
        summary_query += " AND t.created_at <= ?"
        summary_params.append(f"{created_to} 23:59")
    summary_query += " GROUP BY u.id"
    employee_summaries = db.execute(summary_query, summary_params).fetchall()
    # Convert to list of dicts with counts
    summaries = []
    for row in employee_summaries:
        total = (row['running_cnt'] or 0) + (row['pause_cnt'] or 0) + (row['finish_cnt'] or 0)
        # Apply status filter if any
        include = True
        if selected_sum_statuses:
            # For each selected status, check if employee has count>0 (except Not Work)
            status_match = False
            for status in selected_sum_statuses:
                if status == 'Running' and (row['running_cnt'] or 0) > 0:
                    status_match = True
                if status == 'Pause' and (row['pause_cnt'] or 0) > 0:
                    status_match = True
                if status == 'Finish' and (row['finish_cnt'] or 0) > 0:
                    status_match = True
                if status == 'Not Work' and (row['running_cnt'] or 0) == 0:
                    status_match = True
            include = status_match
        if include:
            summaries.append({
                'employee_id': row['id'],
                'employee_name': row['employee_name'],
                'running_cnt': row['running_cnt'] or 0,
                'pause_cnt': row['pause_cnt'] or 0,
                'finish_cnt': row['finish_cnt'] or 0,
                'total': total
            })
    # Fetch employee options for filter UI
    employees_list = db.execute("SELECT id, full_name FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
    total_projects = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    active_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Running'").fetchone()[0]
    return render_template(
        'hr.html',
        total_employees=total_employees,
        total_projects=total_projects,
        active_tasks=active_tasks,
        summaries=summaries,
        employees_list=employees_list,
        selected_sum_employees=selected_sum_employees,
        selected_sum_statuses=selected_sum_statuses
    )


@app.route('/hr/tracking')
@role_required('HR')
def hr_tracking():
    db = get_db()
    
    # Get filter inputs
    selected_employees = [int(x) for x in request.args.getlist('employees') if x.isdigit()]
    selected_projects = []
    for x in request.args.getlist('projects'):
        if x == 'none':
            selected_projects.append('none')
        elif x.isdigit():
            selected_projects.append(int(x))
            
    selected_statuses = request.args.getlist('statuses')
    created_from = request.args.get('created_from', '').strip()
    created_to = request.args.get('created_to', '').strip()
    selected_creators = [int(x) for x in request.args.getlist('creators') if x.isdigit()]
    
    # Build query
    query = '''
        SELECT t.*, u.full_name AS employee_name, creator.full_name AS creator_name, p.name AS project_name
        FROM tasks t
        JOIN users u ON t.employee_id = u.id
        LEFT JOIN users creator ON t.creator_id = creator.id
        LEFT JOIN projects p ON t.project_id = p.id
    '''
    
    conditions = []
    params = []
    
    if selected_employees:
        placeholders = ','.join('?' for _ in selected_employees)
        conditions.append(f"t.employee_id IN ({placeholders})")
        params.extend(selected_employees)
        
    if selected_projects:
        proj_conds = []
        has_none = False
        val_projs = []
        for p in selected_projects:
            if p == 'none':
                has_none = True
            else:
                val_projs.append(p)
        if val_projs:
            placeholders = ','.join('?' for _ in val_projs)
            proj_conds.append(f"t.project_id IN ({placeholders})")
            params.extend(val_projs)
        if has_none:
            proj_conds.append("t.project_id IS NULL")
        if proj_conds:
            conditions.append(f"({' OR '.join(proj_conds)})")
            
    if selected_statuses:
        placeholders = ','.join('?' for _ in selected_statuses)
        conditions.append(f"t.status IN ({placeholders})")
        params.extend(selected_statuses)
        
    if created_from:
        conditions.append("t.created_at >= ?")
        params.append(f"{created_from} 00:00")
        
    if created_to:
        conditions.append("t.created_at <= ?")
        params.append(f"{created_to} 23:59")
        
    if selected_creators:
        placeholders = ','.join('?' for _ in selected_creators)
        conditions.append(f"t.creator_id IN ({placeholders})")
        params.extend(selected_creators)
        
    # Count total tasks first
    count_query = '''
        SELECT COUNT(*)
        FROM tasks t
        JOIN users u ON t.employee_id = u.id
        LEFT JOIN users creator ON t.creator_id = creator.id
        LEFT JOIN projects p ON t.project_id = p.id
    '''
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    total_tasks = db.execute(count_query, params).fetchone()[0]

    # Get page and per_page
    page = request.args.get('page', 1, type=int)
    per_page = 50
    total_pages = (total_tasks + per_page - 1) // per_page if total_tasks > 0 else 1
    page = max(1, min(page, total_pages))

    # Paginate query
    query += " LIMIT ? OFFSET ?"
    tasks_params = list(params) + [per_page, (page - 1) * per_page]
    tasks = db.execute(query, tasks_params).fetchall()
    
    # Helper to construct pagination URLs preserving multi-value filters
    def get_page_url(page_num):
        import urllib.parse
        params_list = []
        for key, values in request.args.lists():
            if key == 'page':
                continue
            for val in values:
                params_list.append((key, val))
        params_list.append(('page', str(page_num)))
        return url_for('hr_tracking') + '?' + urllib.parse.urlencode(params_list)

    # Fetch options for filters
    employees_list = db.execute("SELECT id, full_name, username FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
    projects_list = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    creators_list = db.execute("SELECT DISTINCT u.id, u.full_name, u.username FROM users u JOIN tasks t ON t.creator_id = u.id ORDER BY u.full_name").fetchall()
    
    showing_from = (page - 1) * per_page + 1 if total_tasks > 0 else 0
    showing_to = min(page * per_page, total_tasks)
    start_page = max(1, page - 2)
    end_page = min(total_pages, page + 2)
    page_range = list(range(start_page, end_page + 1))

    return render_template(
        'hr_tracking.html', 
        tasks=tasks,
        employees_list=employees_list,
        projects_list=projects_list,
        creators_list=creators_list,
        selected_employees=selected_employees,
        selected_projects=selected_projects,
        selected_statuses=selected_statuses,
        created_from=created_from,
        created_to=created_to,
        selected_creators=selected_creators,
        page=page,
        total_pages=total_pages,
        total_tasks=total_tasks,
        page_url=get_page_url,
        showing_from=showing_from,
        showing_to=showing_to,
        page_range=page_range
    )

@app.route('/hr/employees')
@role_required('HR')
def hr_employees():
    db = get_db()
    users = db.execute('SELECT * FROM users WHERE role != ?', ('HR',)).fetchall()
    return render_template('hr_employees.html', users=users)

@app.route('/hr/projects')
@role_required('HR')
def hr_projects():
    db = get_db()
    projects = db.execute('SELECT * FROM projects').fetchall()
    return render_template('hr_projects.html', projects=projects)

@app.route('/hr/projects/add', methods=['POST'])
@role_required('HR')
def add_project():
    name = request.form.get('name')
    client = request.form.get('client')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    if name and client:
        db = get_db()
        try:
            db.execute('INSERT INTO projects (name, client, start_date, end_date) VALUES (?,?,?,?)',
                       (name, client, start_date or None, end_date or None))
            db.commit()
            flash('Project added successfully.', 'success')
        except sqlite3.IntegrityError:
            flash('Project name already exists.', 'danger')
    else:
        flash('Project name and Client are required.', 'danger')
    return redirect(url_for('hr_projects'))

@app.route('/hr/projects/edit/<int:project_id>', methods=['GET', 'POST'])
@role_required('HR')
def edit_project(project_id):
    db = get_db()
    project = db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('hr_projects'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        client = request.form.get('client')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        if name and client:
            try:
                db.execute('UPDATE projects SET name = ?, client = ?, start_date = ?, end_date = ? WHERE id = ?',
                           (name, client, start_date or None, end_date or None, project_id))
                db.commit()
                flash('Project updated successfully.', 'success')
                return redirect(url_for('hr_projects'))
            except sqlite3.IntegrityError:
                flash('Project name already exists.', 'danger')
        else:
            flash('Project name and Client are required.', 'danger')
            
    return render_template('edit_project.html', project=project)
# ----- HR Reporting -----

from io import BytesIO
import pandas as pd
from flask import send_file, jsonify

def _fetch_tasks_for_employee_report(employee_id, date_from, date_to, project_ids=None):
    """Return list of dicts with task data for employee report.
    Excludes running tasks and filters by creation date.
    """
    db = get_db()
    params = [employee_id, f"{date_from} 00:00", f"{date_to} 23:59"]
    query = '''
        SELECT t.id, t.created_at, t.running_duration, p.id as project_id, p.name as project_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE t.employee_id = ?
          AND t.status != 'Running'
          AND datetime(t.created_at) BETWEEN ? AND ?
    '''
    if project_ids:
        placeholders = ','.join('?' for _ in project_ids)
        query += f" AND p.id IN ({placeholders})"
        params.extend(project_ids)
    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]

def _fetch_tasks_for_project_report(project_id, date_from, date_to, employee_ids=None):
    """Return list of dicts with task data for project report.
    If project_id is None, include all projects.
    """
    db = get_db()
    params = [f"{date_from} 00:00", f"{date_to} 23:59"]
    query = '''
        SELECT t.id, t.created_at, t.running_duration, u.id as employee_id, u.full_name as employee_name, p.id as project_id, p.name as project_name
        FROM tasks t
        JOIN users u ON t.employee_id = u.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.status != 'Running'
          AND datetime(t.created_at) BETWEEN ? AND ?
    '''
    if project_id is not None:
        query += " AND p.id = ?"
        params.append(project_id)
    if employee_ids:
        placeholders = ','.join('?' for _ in employee_ids)
        query += f" AND u.id IN ({placeholders})"
        params.extend(employee_ids)
    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]

def _apply_excel_formatting(workbook):
    """Apply required formatting to both worksheets using openpyxl.
    """
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    header_fill = PatternFill(start_color='FFC000', end_color='FFC000', fill_type='solid')
    bold_font = Font(bold=True)
    thin = Side(style='thin')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for ws in workbook.worksheets:
        ws.freeze_panes = ws['A2']
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font = bold_font
            cell.fill = header_fill
            cell.border = border
            cell.alignment = Alignment(horizontal='center')
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.border = border
                if isinstance(cell.value, (int, float)):
                    cell.number_format = numbers.FORMAT_NUMBER_00
        for col in ws.columns:
            max_len = max((len(str(cell.value)) for cell in col if cell.value), default=0)
            ws.column_dimensions[col[0].column_letter].width = max_len + 2
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=1):
            if str(row[0].value).lower() == 'total':
                for c in ws[row[0].row]:
                    c.font = bold_font
        last_col = ws.max_column
        for r in range(2, ws.max_row + 1):
            ws.cell(row=r, column=last_col).font = bold_font
        ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE

def _generate_employee_excel(rows, employee_name, date_from, date_to, generated_by):
    """Create Excel workbook for employee report.
    Returns a BytesIO object.
    """
    if not rows:
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            pd.DataFrame([{'Message': 'No data found for selected filters.'}]).to_excel(writer, index=False, sheet_name='Details')
            pd.DataFrame([{'Message': 'No data found for selected filters.'}]).to_excel(writer, index=False, sheet_name='Summary')
        out.seek(0)
        return out
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['created_at']).dt.date
    df['hours'] = df['running_duration'] / 3600.0
    pivot = pd.pivot_table(df, index='date', columns='project_name', values='hours', aggfunc='sum', fill_value=0)
    pivot = pivot.sort_index()
    pivot['Total'] = pivot.sum(axis=1)
    total_row = pivot.sum(axis=0)
    total_row.name = 'Total'
    details_df = pd.concat([pivot, pd.DataFrame([total_row])])
    # Compute per‑project totals (exclude the 'Total' column and the total row)
    per_project = pivot.iloc[:-1][pivot.columns.drop('Total')].sum()
    # Round to two decimals for display consistency
    per_project = per_project.round(2)
    summary_df = pd.DataFrame({
        'Project': per_project.index,
        'Total Hours': per_project.values
    })
    # Grand total should be the sum of the displayed project totals
    grand_total = per_project.sum().round(2)
    summary_df = pd.concat([summary_df, pd.DataFrame({'Project': ['Grand Total'], 'Total Hours': [grand_total]})], ignore_index=True)
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        details_df.to_excel(writer, sheet_name='Details')
        ws = writer.book.create_sheet('Summary')
        info = {
            'Report Type': 'Employee Report',
            'Employee': employee_name,
            'Date From': date_from,
            'Date To': date_to,
            'Generated By': generated_by,
            'Generated On': pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        r = 1
        for k, v in info.items():
            ws.cell(row=r, column=1, value=k)
            ws.cell(row=r, column=2, value=v)
            r += 1
        table_start = r + 1
        ws.cell(row=table_start, column=1, value='Project')
        ws.cell(row=table_start, column=2, value='Total Hours')
        for i, rec in enumerate(summary_df.itertuples(index=False), start=1):
            ws.cell(row=table_start + i, column=1, value=rec.Project)
            ws.cell(row=table_start + i, column=2, value=rec[1])
        _apply_excel_formatting(writer.book)
    out.seek(0)
    return out

def _generate_project_excel(rows, project_name, date_from, date_to, generated_by):
    """Create Excel workbook for project report.
    Mirrors employee version but pivots on employee.
    """
    if not rows:
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            pd.DataFrame([{'Message': 'No data found for selected filters.'}]).to_excel(writer, index=False, sheet_name='Details')
            pd.DataFrame([{'Message': 'No data found for selected filters.'}]).to_excel(writer, index=False, sheet_name='Summary')
        out.seek(0)
        return out
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['created_at']).dt.date
    df['hours'] = df['running_duration'] / 3600.0
    pivot = pd.pivot_table(df, index='date', columns='employee_name', values='hours', aggfunc='sum', fill_value=0)
    pivot = pivot.sort_index()
    pivot['Total'] = pivot.sum(axis=1)
    total_row = pivot.sum(axis=0)
    total_row.name = 'Total'
    details_df = pd.concat([pivot, pd.DataFrame([total_row])])
    # Compute per‑employee totals (exclude the 'Total' column and the total row)
    per_employee = pivot.iloc[:-1][pivot.columns.drop('Total')].sum()
    per_employee = per_employee.round(2)
    summary_df = pd.DataFrame({
        'Employee': per_employee.index,
        'Total Hours': per_employee.values
    })
    # Grand total is sum of displayed employee totals
    grand_total = per_employee.sum().round(2)
    summary_df = pd.concat([summary_df, pd.DataFrame({'Employee': ['Grand Total'], 'Total Hours': [grand_total]})], ignore_index=True)
    summary_df = pd.concat([summary_df, pd.DataFrame({'Employee': ['Grand Total'], 'Total Hours': [total_row['Total']]})], ignore_index=True)
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        details_df.to_excel(writer, sheet_name='Details')
        ws = writer.book.create_sheet('Summary')
        info = {
            'Report Type': 'Project Report',
            'Project': project_name if project_name else 'All Projects',
            'Date From': date_from,
            'Date To': date_to,
            'Generated By': generated_by,
            'Generated On': pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        r = 1
        for k, v in info.items():
            ws.cell(row=r, column=1, value=k)
            ws.cell(row=r, column=2, value=v)
            r += 1
        table_start = r + 1
        ws.cell(row=table_start, column=1, value='Employee')
        ws.cell(row=table_start, column=2, value='Total Hours')
        for i, rec in enumerate(summary_df.itertuples(index=False), start=1):
            ws.cell(row=table_start + i, column=1, value=rec.Employee)
            ws.cell(row=table_start + i, column=2, value=rec[1])
        _apply_excel_formatting(writer.book)
    out.seek(0)
    return out

# ----- HR Reporting Routes -----

@app.route('/hr/reports')
@role_required('HR')
def hr_reports_page():
    db = get_db()
    employees = db.execute("SELECT id, full_name FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
    projects = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    return render_template('hr_reports.html', employees=employees, projects=projects)

@app.route('/hr/export', methods=['POST'])
@role_required('HR')
def hr_export():
    payload = request.get_json()
    if not payload:
        return jsonify({'error': 'Invalid request'}), 400
    report_type = payload.get('type')
    date_from = payload.get('date_from')
    date_to = payload.get('date_to')
    if not report_type or not date_from or not date_to:
        return jsonify({'error': 'Missing required parameters'}), 400
    generated_by = current_user.full_name or current_user.username
    if report_type == 'employee':
        employee_id = payload.get('employee_id')
        if not employee_id:
            return jsonify({'error': 'Employee ID required'}), 400
        emp = get_db().execute('SELECT full_name FROM users WHERE id = ?', (employee_id,)).fetchone()
        if not emp:
            return jsonify({'error': 'Employee not found'}), 404
        rows = _fetch_tasks_for_employee_report(employee_id, date_from, date_to, payload.get('project_ids'))
        excel_io = _generate_employee_excel(rows, emp['full_name'], date_from, date_to, generated_by)
        sanitized_name = re.sub(r'[^A-Za-z0-9]+', '_', emp['full_name']).strip('_')
        filename = f"{sanitized_name}_{date_from}_{date_to}.xlsx"
    elif report_type == 'project':
        project_id = payload.get('project_id')
        project_name = None
        if project_id:
            proj = get_db().execute('SELECT name FROM projects WHERE id = ?', (project_id,)).fetchone()
            if not proj:
                return jsonify({'error': 'Project not found'}), 404
            project_name = proj['name']
        rows = _fetch_tasks_for_project_report(project_id, date_from, date_to)
        excel_io = _generate_project_excel(rows, project_name, date_from, date_to, generated_by)
        if project_name:
            sanitized_proj = re.sub(r'[^A-Za-z0-9]+', '_', project_name).strip('_')
        else:
            sanitized_proj = 'all_projects'
        filename = f"{sanitized_proj}_{date_from}_{date_to}.xlsx"
    else:
        return jsonify({'error': 'Invalid report type'}), 400
    return send_file(
        excel_io,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/hr/seed', methods=['POST'])
@role_required('HR')
def hr_seed():
    summary = seed_mock_data()
    return jsonify({'message': 'Database seeded', 'summary': summary}), 200

@app.route('/hr/projects/delete/<int:project_id>', methods=['POST'])
@role_required('HR')
def delete_project(project_id):
    db = get_db()
    db.execute('UPDATE tasks SET project_id = NULL WHERE project_id = ?', (project_id,))
    db.execute('DELETE FROM employee_projects WHERE project_id = ?', (project_id,))
    db.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    db.commit()
    flash('Project deleted.', 'info')
    return redirect(url_for('hr_projects'))

@app.route('/hr/add', methods=['GET', 'POST'])
@role_required('HR')
def add_employee():
    db = get_db()
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        password = request.form['password']
        position = request.form.get('position', '')
        manager_usernames = request.form.getlist('managers')
        project_ids = request.form.getlist('projects')
        role = 'Employee'
        pwd_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        
        try:
            db.execute('INSERT INTO users (full_name, username, password_hash, role, position) VALUES (?,?,?,?,?)',
                       (full_name, username, pwd_hash, role, position))
            db.commit()
            
            employee_row = db.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
            if employee_row:
                employee_id = employee_row['id']
                manager_ids = []
                for mgr_name in manager_usernames:
                    mgr_row = db.execute('SELECT id FROM users WHERE username = ?', (mgr_name,)).fetchone()
                    if mgr_row:
                        manager_ids.append(mgr_row['id'])
                set_manager_ids(employee_id, manager_ids)
                
                for p_id in project_ids:
                    db.execute('INSERT INTO employee_projects (employee_id, project_id) VALUES (?,?)', (employee_id, int(p_id)))
                db.commit()
                
            flash('Employee added.', 'success')
            return redirect(url_for('hr_employees'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
            
    # List all current employees to be chosen as managers
    employees = db.execute("SELECT * FROM users WHERE role = 'Employee'").fetchall()
    projects = db.execute("SELECT * FROM projects ORDER BY name").fetchall()
    return render_template('add_employee.html', employees=employees, projects=projects)

@app.route('/hr/edit/<int:user_id>', methods=['GET', 'POST'])
@role_required('HR')
def edit_employee(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('hr_employees'))
    
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        position = request.form.get('position', '')
        password = request.form.get('password', '').strip()
        manager_usernames = request.form.getlist('managers')
        project_ids = request.form.getlist('projects')
        
        try:
            if password:
                pwd_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                db.execute('UPDATE users SET full_name = ?, username = ?, password_hash = ?, position = ? WHERE id = ?',
                           (full_name, username, pwd_hash, position, user_id))
            else:
                db.execute('UPDATE users SET full_name = ?, username = ?, position = ? WHERE id = ?',
                           (full_name, username, position, user_id))
            db.commit()
            
            manager_ids = []
            for mgr_name in manager_usernames:
                mgr_row = db.execute('SELECT id FROM users WHERE username = ?', (mgr_name,)).fetchone()
                if mgr_row:
                    manager_ids.append(mgr_row['id'])
            set_manager_ids(user_id, manager_ids)
            
            db.execute('DELETE FROM employee_projects WHERE employee_id = ?', (user_id,))
            for p_id in project_ids:
                db.execute('INSERT INTO employee_projects (employee_id, project_id) VALUES (?,?)', (user_id, int(p_id)))
            db.commit()
            
            flash('Employee updated.', 'success')
            return redirect(url_for('hr_employees'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
            
    # List other employees to be chosen as managers
    employees = db.execute("SELECT * FROM users WHERE role = 'Employee' AND id != ?", (user_id,)).fetchall()
    current_mgr_ids = get_manager_ids(user_id)
    current_managers = []
    for mid in current_mgr_ids:
        r = db.execute('SELECT username FROM users WHERE id = ?', (mid,)).fetchone()
        if r:
            current_managers.append(r['username'])
            
    projects = db.execute("SELECT * FROM projects ORDER BY name").fetchall()
    current_proj_rows = db.execute("SELECT project_id FROM employee_projects WHERE employee_id = ?", (user_id,)).fetchall()
    current_project_ids = [r['project_id'] for r in current_proj_rows]
            
    return render_template('edit_employee.html', user=user, employees=employees, current_managers=current_managers, projects=projects, current_project_ids=current_project_ids)

@app.route('/hr/delete/<int:user_id>', methods=['POST'])
@role_required('HR')
def delete_employee(user_id):
    db = get_db()
    db.execute('DELETE FROM employee_managers WHERE employee_id = ? OR manager_id = ?', (user_id, user_id))
    db.execute('DELETE FROM employee_projects WHERE employee_id = ?', (user_id,))
    db.execute('DELETE FROM tasks WHERE employee_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash('Employee deleted.', 'info')
    return redirect(url_for('hr_employees'))

# ----- Employee Dashboard & Tasks -----
@app.route('/employee')
@role_required('Employee')
def employee_dashboard():
    db = get_db()
    
    # ------------------ My Tasks Filters ------------------
    selected_projects = []
    for x in request.args.getlist('projects'):
        if x == 'none':
            selected_projects.append('none')
        elif x.isdigit():
            selected_projects.append(int(x))
            
    selected_statuses = request.args.getlist('statuses')
    created_from = request.args.get('created_from', '').strip()
    created_to = request.args.get('created_to', '').strip()
    selected_creators = [int(x) for x in request.args.getlist('creators') if x.isdigit()]
    
    # ------------------ Subordinate Tasks Filters ------------------
    selected_sub_employees = [int(x) for x in request.args.getlist('sub_employees') if x.isdigit()]
    selected_sub_projects = []
    for x in request.args.getlist('sub_projects'):
        if x == 'none':
            selected_sub_projects.append('none')
        elif x.isdigit():
            selected_sub_projects.append(int(x))
            
    selected_sub_statuses = request.args.getlist('sub_statuses')
    sub_created_from = request.args.get('sub_created_from', '').strip()
    sub_created_to = request.args.get('sub_created_to', '').strip()
    selected_sub_creators = [int(x) for x in request.args.getlist('sub_creators') if x.isdigit()]
    
    # Build query for employee's own tasks
    query = '''
        SELECT t.*, u.full_name AS creator_name, p.name AS project_name
        FROM tasks t
        LEFT JOIN users u ON t.creator_id = u.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.employee_id = ?
    '''
    params = [current_user.id]
    
    if selected_projects:
        proj_conds = []
        has_none = False
        val_projs = []
        for p in selected_projects:
            if p == 'none':
                has_none = True
            else:
                val_projs.append(p)
        if val_projs:
            placeholders = ','.join('?' for _ in val_projs)
            proj_conds.append(f"t.project_id IN ({placeholders})")
            params.extend(val_projs)
        if has_none:
            proj_conds.append("t.project_id IS NULL")
        if proj_conds:
            query += f" AND ({' OR '.join(proj_conds)})"
            
    if selected_statuses:
        placeholders = ','.join('?' for _ in selected_statuses)
        query += f" AND t.status IN ({placeholders})"
        params.extend(selected_statuses)
        
    if created_from:
        query += " AND t.created_at >= ?"
        params.append(f"{created_from} 00:00")
        
    if created_to:
        query += " AND t.created_at <= ?"
        params.append(f"{created_to} 23:59")
        
    if selected_creators:
        placeholders = ','.join('?' for _ in selected_creators)
        query += f" AND t.creator_id IN ({placeholders})"
        params.extend(selected_creators)
        
    query += " ORDER BY t.created_at DESC"
    
    tasks = db.execute(query, params).fetchall()
    
    # List employees managed by the current employee
    subordinates = db.execute('''
        SELECT u.* FROM users u
        JOIN employee_managers em ON u.id = em.employee_id
        WHERE em.manager_id = ?
    ''', (current_user.id,)).fetchall()
    
    # Build query for subordinate tasks live tracking
    sub_query = '''
        SELECT t.*, u.full_name AS employee_name, creator.full_name AS creator_name, p.name AS project_name
        FROM tasks t
        JOIN users u ON t.employee_id = u.id
        JOIN employee_managers em ON u.id = em.employee_id
        LEFT JOIN users creator ON t.creator_id = creator.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE em.manager_id = ?
          AND EXISTS (
              SELECT 1 FROM employee_projects ep1
              WHERE ep1.employee_id = t.employee_id AND ep1.project_id = t.project_id
          )
          AND EXISTS (
              SELECT 1 FROM employee_projects ep2
              WHERE ep2.employee_id = ? AND ep2.project_id = t.project_id
          )
    '''
    sub_params = [current_user.id, current_user.id]
    
    if selected_sub_employees:
        placeholders = ','.join('?' for _ in selected_sub_employees)
        sub_query += f" AND t.employee_id IN ({placeholders})"
        sub_params.extend(selected_sub_employees)
        
    if selected_sub_projects:
        proj_conds = []
        has_none = False
        val_projs = []
        for p in selected_sub_projects:
            if p == 'none':
                has_none = True
            else:
                val_projs.append(p)
        if val_projs:
            placeholders = ','.join('?' for _ in val_projs)
            proj_conds.append(f"t.project_id IN ({placeholders})")
            sub_params.extend(val_projs)
        if has_none:
            proj_conds.append("t.project_id IS NULL")
        if proj_conds:
            sub_query += f" AND ({' OR '.join(proj_conds)})"
            
    if selected_sub_statuses:
        placeholders = ','.join('?' for _ in selected_sub_statuses)
        sub_query += f" AND t.status IN ({placeholders})"
        sub_params.extend(selected_sub_statuses)
        
    if sub_created_from:
        sub_query += " AND t.created_at >= ?"
        sub_params.append(f"{sub_created_from} 00:00")
        
    if sub_created_to:
        sub_query += " AND t.created_at <= ?"
        sub_params.append(f"{sub_created_to} 23:59")
        
    if selected_sub_creators:
        placeholders = ','.join('?' for _ in selected_sub_creators)
        sub_query += f" AND t.creator_id IN ({placeholders})"
        sub_params.extend(selected_sub_creators)
        
    sub_query += " ORDER BY t.created_at DESC"
    
    subordinate_tasks = db.execute(sub_query, sub_params).fetchall()
    
    # Fetch options for filters specifically for this employee's tasks (restricted to assigned projects)
    projects_list = db.execute('''
        SELECT p.id, p.name FROM projects p
        JOIN employee_projects ep ON p.id = ep.project_id
        WHERE ep.employee_id = ?
        ORDER BY p.name
    ''', (current_user.id,)).fetchall()
    if not projects_list:
        projects_list = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    creators_list = db.execute('''
        SELECT DISTINCT u.id, u.full_name, u.username 
        FROM users u 
        JOIN tasks t ON t.creator_id = u.id 
        WHERE t.employee_id = ? 
        ORDER BY u.full_name
    ''', (current_user.id,)).fetchall()
    
    # Fetch options for filters specifically for subordinate tasks
    sub_creators_list = db.execute('''
        SELECT DISTINCT creator.id, creator.full_name, creator.username
        FROM users creator
        JOIN tasks t ON t.creator_id = creator.id
        JOIN employee_managers em ON t.employee_id = em.employee_id
        WHERE em.manager_id = ?
        ORDER BY creator.full_name
    ''', (current_user.id,)).fetchall()
    
    return render_template(
        'employee.html', 
        tasks=tasks, 
        subordinates=subordinates, 
        subordinate_tasks=subordinate_tasks,
        projects_list=projects_list,
        creators_list=creators_list,
        selected_projects=selected_projects,
        selected_statuses=selected_statuses,
        created_from=created_from,
        created_to=created_to,
        selected_creators=selected_creators,
        
        sub_creators_list=sub_creators_list,
        selected_sub_employees=selected_sub_employees,
        selected_sub_projects=selected_sub_projects,
        selected_sub_statuses=selected_sub_statuses,
        sub_created_from=sub_created_from,
        sub_created_to=sub_created_to,
        selected_sub_creators=selected_sub_creators
    )

@app.route('/employee/add', methods=['GET', 'POST'])
@role_required('Employee')
def add_task():
    db = get_db()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        project_id = int(request.form['project_id'])
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (current_user.id, project_id, title, description, 'Pause', now, 0, current_user.id))
        db.commit()
        flash('Task added.', 'success')
        return redirect(url_for('employee_dashboard'))
    projects = db.execute('''
        SELECT p.* FROM projects p
        JOIN employee_projects ep ON p.id = ep.project_id
        WHERE ep.employee_id = ?
        ORDER BY p.name
    ''', (current_user.id,)).fetchall()
    if not projects:
        projects = db.execute('SELECT * FROM projects').fetchall()
    return render_template('add_task.html', projects=projects)

@app.route('/employee/edit/<int:task_id>', methods=['GET', 'POST'])
@role_required('Employee')
def edit_task(task_id):
    db = get_db()
    task = db.execute('SELECT * FROM tasks WHERE id = ? AND employee_id = ?', (task_id, current_user.id)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('employee_dashboard'))
    if task['creator_id'] != current_user.id:
        flash('You cannot edit tasks assigned by your manager.', 'danger')
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        new_status = request.form['status']
        project_id = int(request.form['project_id'])
        
        old_status = task['status']
        old_running_duration = task['running_duration'] or 0
        old_last_started_at = task['last_started_at']
        
        new_running_duration = old_running_duration
        new_last_started_at = old_last_started_at
        now_utc = datetime.utcnow()
        
        # Status change logic
        if old_status == 'Running' and new_status != 'Running':
            if old_last_started_at:
                try:
                    started_dt = datetime.fromisoformat(old_last_started_at)
                    elapsed = (now_utc - started_dt).total_seconds()
                    new_running_duration = old_running_duration + max(0, int(elapsed))
                except Exception:
                    pass
            new_last_started_at = None
        elif old_status != 'Running' and new_status == 'Running':
            new_last_started_at = now_utc.isoformat()
            
        db.execute('''
            UPDATE tasks 
            SET title = ?, description = ?, status = ?, running_duration = ?, last_started_at = ?, project_id = ?
            WHERE id = ? AND employee_id = ?
        ''', (title, description, new_status, new_running_duration, new_last_started_at, project_id, task_id, current_user.id))
        db.commit()
        flash('Task updated.', 'success')
        return redirect(url_for('employee_dashboard'))
        
    projects = db.execute('''
        SELECT p.* FROM projects p
        JOIN employee_projects ep ON p.id = ep.project_id
        WHERE ep.employee_id = ?
        ORDER BY p.name
    ''', (current_user.id,)).fetchall()
    if not projects:
        projects = db.execute('SELECT * FROM projects').fetchall()
    return render_template('edit_task.html', task=task, projects=projects)

@app.route('/employee/task/<int:task_id>/update_status', methods=['POST'])
@role_required('Employee')
def update_task_status(task_id):
    db = get_db()
    task = db.execute('SELECT status, running_duration, last_started_at FROM tasks WHERE id = ? AND employee_id = ?', (task_id, current_user.id)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('employee_dashboard'))
    new_status = request.form.get('status')
    valid_statuses = ['Running', 'Pause', 'Finish']
    if new_status in valid_statuses:
        old_status = task['status']
        old_running_duration = task['running_duration'] or 0
        old_last_started_at = task['last_started_at']
        
        new_running_duration = old_running_duration
        new_last_started_at = old_last_started_at
        now_utc = datetime.utcnow()
        
        # Status change logic
        if old_status == 'Running' and new_status != 'Running':
            if old_last_started_at:
                try:
                    started_dt = datetime.fromisoformat(old_last_started_at)
                    elapsed = (now_utc - started_dt).total_seconds()
                    new_running_duration = old_running_duration + max(0, int(elapsed))
                except Exception:
                    pass
            new_last_started_at = None
        elif old_status != 'Running' and new_status == 'Running':
            new_last_started_at = now_utc.isoformat()
            
        db.execute('''
            UPDATE tasks 
            SET status = ?, running_duration = ?, last_started_at = ?
            WHERE id = ? AND employee_id = ?
        ''', (new_status, new_running_duration, new_last_started_at, task_id, current_user.id))
        db.commit()
        flash('Task status updated.', 'success')
    else:
        flash('Invalid status.', 'danger')
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/delete/<int:task_id>', methods=['POST'])
@role_required('Employee')
def delete_task(task_id):
    db = get_db()
    task = db.execute('SELECT creator_id, employee_id FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        flash('Task not found.', 'danger')
        return redirect(url_for('employee_dashboard'))
    if task['creator_id'] != current_user.id:
        flash('You can only delete tasks created by you.', 'danger')
        return redirect(url_for('employee_dashboard'))
    db.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    db.commit()
    flash('Task deleted.', 'success')
    if task['employee_id'] != current_user.id:
        return redirect(url_for('view_subordinate_tasks', sub_id=task['employee_id']))
    return redirect(url_for('employee_dashboard'))

@app.route('/employee/subordinates')
@role_required('Employee')
def view_subordinates():
    db = get_db()
    subordinates = db.execute('''
        SELECT u.* FROM users u
        JOIN employee_managers em ON u.id = em.employee_id
        WHERE em.manager_id = ?
    ''', (current_user.id,)).fetchall()
    return render_template('subordinates.html', subordinates=subordinates)

# ----- Subordinate Tasks -----
@app.route('/employee/subordinate/<int:sub_id>/tasks')
@role_required('Employee')
def view_subordinate_tasks(sub_id):
    db = get_db()
    link = db.execute('SELECT 1 FROM employee_managers WHERE employee_id = ? AND manager_id = ?', (sub_id, current_user.id)).fetchone()
    if not link:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    subordinate = db.execute('SELECT * FROM users WHERE id = ?', (sub_id,)).fetchone()
    tasks = db.execute('''
        SELECT t.*, u.full_name AS creator_name, p.name AS project_name
        FROM tasks t
        LEFT JOIN users u ON t.creator_id = u.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.employee_id = ?
          AND EXISTS (
              SELECT 1 FROM employee_projects ep1
              WHERE ep1.employee_id = t.employee_id AND ep1.project_id = t.project_id
          )
          AND EXISTS (
              SELECT 1 FROM employee_projects ep2
              WHERE ep2.employee_id = ? AND ep2.project_id = t.project_id
          )
    ''', (sub_id, current_user.id)).fetchall()
    return render_template('subordinate_tasks.html', subordinate=subordinate, tasks=tasks)

@app.route('/employee/subordinate/<int:sub_id>/tasks/add', methods=['GET', 'POST'])
@role_required('Employee')
def add_subordinate_task(sub_id):
    db = get_db()
    link = db.execute('SELECT 1 FROM employee_managers WHERE employee_id = ? AND manager_id = ?', (sub_id, current_user.id)).fetchone()
    if not link:
        flash('Access denied.', 'danger')
        return redirect(url_for('employee_dashboard'))
    subordinate = db.execute('SELECT * FROM users WHERE id = ?', (sub_id,)).fetchone()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        project_id = int(request.form['project_id'])
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (sub_id, project_id, title, description, 'Pause', now, 0, current_user.id))
        db.commit()
        flash('Task assigned to employee.', 'success')
        return redirect(url_for('view_subordinate_tasks', sub_id=sub_id))
    projects = db.execute('''
        SELECT p.* FROM projects p
        JOIN employee_projects ep_sub ON p.id = ep_sub.project_id
        JOIN employee_projects ep_mgr ON p.id = ep_mgr.project_id
        WHERE ep_sub.employee_id = ? AND ep_mgr.employee_id = ?
        ORDER BY p.name
    ''', (sub_id, current_user.id)).fetchall()
    if not projects:
        projects = db.execute('''
            SELECT p.* FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            WHERE ep.employee_id = ?
            ORDER BY p.name
        ''', (sub_id,)).fetchall()
    if not projects:
        projects = db.execute('SELECT * FROM projects').fetchall()
    return render_template('add_subordinate_task.html', subordinate=subordinate, projects=projects)

# ---------- Init ----------
if __name__ == '__main__':
    with app.app_context():
        init_db()
        seed_data()
    app.run(host='0.0.0.0', port=5000, debug=True)
