# app.py
import os
import sqlite3
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, flash
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
        
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (ahmed['id'], proj_a['id'] if proj_a else None, 'Task One', 'First sample task', 'Pause', now, 0, ahmed['id']))
        db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                   (ahmed['id'], proj_a['id'] if proj_a else None, 'Task Two', 'Second sample task', 'Finish', now, 7200, badr['id']))
        
    db.commit()

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
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY t.created_at DESC"
    
    tasks = db.execute(query, params).fetchall()
    
    # Fetch options for filters
    employees_list = db.execute("SELECT id, full_name, username FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
    projects_list = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
    creators_list = db.execute("SELECT DISTINCT u.id, u.full_name, u.username FROM users u JOIN tasks t ON t.creator_id = u.id ORDER BY u.full_name").fetchall()
    
    return render_template(
        'hr.html', 
        tasks=tasks,
        employees_list=employees_list,
        projects_list=projects_list,
        creators_list=creators_list,
        selected_employees=selected_employees,
        selected_projects=selected_projects,
        selected_statuses=selected_statuses,
        created_from=created_from,
        created_to=created_to,
        selected_creators=selected_creators
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

@app.route('/hr/projects/delete/<int:project_id>', methods=['POST'])
@role_required('HR')
def delete_project(project_id):
    db = get_db()
    db.execute('UPDATE tasks SET project_id = NULL WHERE project_id = ?', (project_id,))
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
                
            flash('Employee added.', 'success')
            return redirect(url_for('hr_employees'))
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'danger')
            
    # List all current employees to be chosen as managers
    employees = db.execute("SELECT * FROM users WHERE role = 'Employee'").fetchall()
    return render_template('add_employee.html', employees=employees)

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
            
    return render_template('edit_employee.html', user=user, employees=employees, current_managers=current_managers)

@app.route('/hr/delete/<int:user_id>', methods=['POST'])
@role_required('HR')
def delete_employee(user_id):
    db = get_db()
    db.execute('DELETE FROM employee_managers WHERE employee_id = ? OR manager_id = ?', (user_id, user_id))
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
    tasks = db.execute('''
        SELECT t.*, u.full_name AS creator_name, p.name AS project_name
        FROM tasks t
        LEFT JOIN users u ON t.creator_id = u.id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE t.employee_id = ?
    ''', (current_user.id,)).fetchall()
    # List employees managed by the current employee
    subordinates = db.execute('''
        SELECT u.* FROM users u
        JOIN employee_managers em ON u.id = em.employee_id
        WHERE em.manager_id = ?
    ''', (current_user.id,)).fetchall()
    
    subordinate_tasks = db.execute('''
        SELECT t.*, u.full_name AS employee_name, p.name AS project_name
        FROM tasks t
        JOIN users u ON t.employee_id = u.id
        JOIN employee_managers em ON u.id = em.employee_id
        LEFT JOIN projects p ON t.project_id = p.id
        WHERE em.manager_id = ?
        ORDER BY t.created_at DESC
    ''', (current_user.id,)).fetchall()
    
    return render_template('employee.html', tasks=tasks, subordinates=subordinates, subordinate_tasks=subordinate_tasks)

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
    ''', (sub_id,)).fetchall()
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
    projects = db.execute('SELECT * FROM projects').fetchall()
    return render_template('add_subordinate_task.html', subordinate=subordinate, projects=projects)

# ---------- Init ----------
if __name__ == '__main__':
    with app.app_context():
        init_db()
        seed_data()
    app.run(host='127.0.0.1', port=5000, debug=True)
