import sqlite3
import urllib.parse
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from workpulse.decorators import role_required
from workpulse.database import get_db, get_manager_ids, set_manager_ids, seed_mock_data, get_user_preferences, save_user_preferences
from workpulse.extensions import bcrypt

def register_hr_routes(app):
    @app.route('/hr')
    @role_required('HR')
    def hr_dashboard():
        db = get_db()
        
        total_employees = db.execute("SELECT COUNT(*) FROM users WHERE role = 'Employee'").fetchone()[0]
        total_projects = db.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        active_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Running'").fetchone()[0]
        
        proj_dist = db.execute('''
            SELECT p.name, COALESCE(SUM(t.running_duration), 0) AS total_duration
            FROM projects p
            LEFT JOIN tasks t ON p.id = t.project_id
            GROUP BY p.id
            HAVING total_duration > 0
        ''').fetchall()
        hr_chart_projects_labels = [r['name'] for r in proj_dist]
        hr_chart_projects_data = [round(r['total_duration'] / 3600.0, 2) for r in proj_dist]
        
        top_emp = db.execute('''
            SELECT u.full_name, COALESCE(SUM(t.running_duration), 0) AS total_duration
            FROM users u
            JOIN tasks t ON u.id = t.employee_id
            WHERE u.role != 'HR'
            GROUP BY u.id
            HAVING total_duration > 0
            ORDER BY total_duration DESC
            LIMIT 5
        ''').fetchall()
        hr_chart_employees_labels = [r['full_name'] for r in top_emp]
        hr_chart_employees_data = [round(r['total_duration'] / 3600.0, 2) for r in top_emp]
        
        return render_template(
            'hr/hr.html',
            total_employees=total_employees,
            total_projects=total_projects,
            active_tasks=active_tasks,
            hr_chart_projects_labels=hr_chart_projects_labels,
            hr_chart_projects_data=hr_chart_projects_data,
            hr_chart_employees_labels=hr_chart_employees_labels,
            hr_chart_employees_data=hr_chart_employees_data
        )

    @app.route('/hr/employees')
    @role_required('HR')
    def hr_employees():
        db = get_db()
        users = db.execute('SELECT * FROM users WHERE role != ?', ('HR',)).fetchall()
        return render_template('hr/hr_employees.html', users=users)

    @app.route('/hr/projects')
    @role_required('HR')
    def hr_projects():
        db = get_db()
        projects = db.execute('SELECT * FROM projects').fetchall()
        employees = db.execute('SELECT id, full_name, username FROM users WHERE role != "HR" ORDER BY full_name').fetchall()
        return render_template('hr/hr_projects.html', projects=projects, employees=employees)

    @app.route('/hr/employees/<int:user_id>')
    @role_required('HR')
    def hr_employee_detail(user_id):
        db = get_db()
        employee = db.execute('SELECT * FROM users WHERE id = ? AND role != ?', (user_id, 'HR')).fetchone()
        if not employee:
            flash('Employee not found.', 'danger')
            return redirect(url_for('hr_employees'))
            
        projects = db.execute('''
            SELECT p.id, p.name, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
            WHERE ep.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (user_id,)).fetchall()
        
        project_details = []
        for p in projects:
            allocated = p['allocated_hours']
            worked_hours = p['worked_seconds'] / 3600.0
            remaining = allocated - worked_hours if allocated > 0 else 0
            project_details.append({
                'id': p['id'],
                'name': p['name'],
                'allocated_hours': allocated,
                'worked_hours': worked_hours,
                'remaining_hours': remaining
            })
            
        return render_template('hr/hr_employee_detail.html', employee=employee, projects=project_details)

    @app.route('/hr/projects/<int:project_id>')
    @role_required('HR')
    def hr_project_detail(project_id):
        db = get_db()
        project = db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        if not project:
            flash('Project not found.', 'danger')
            return redirect(url_for('hr_projects'))
            
        employees = db.execute('''
            SELECT u.id, u.full_name, u.username, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM users u
            JOIN employee_projects ep ON u.id = ep.employee_id
            LEFT JOIN tasks t ON ep.project_id = t.project_id AND t.employee_id = u.id
            WHERE ep.project_id = ?
            GROUP BY u.id
            ORDER BY u.full_name
        ''', (project_id,)).fetchall()
        
        employee_details = []
        for emp in employees:
            allocated = emp['allocated_hours']
            worked_hours = emp['worked_seconds'] / 3600.0
            remaining = allocated - worked_hours if allocated > 0 else 0
            employee_details.append({
                'id': emp['id'],
                'full_name': emp['full_name'],
                'username': emp['username'],
                'allocated_hours': allocated,
                'worked_hours': worked_hours,
                'remaining_hours': remaining
            })
            
        return render_template('hr/hr_project_detail.html', project=project, employees=employee_details)

    @app.route('/hr/employees/<int:user_id>/print')
    @role_required('HR')
    def hr_employee_detail_print(user_id):
        db = get_db()
        employee = db.execute('SELECT * FROM users WHERE id = ? AND role != ?', (user_id, 'HR')).fetchone()
        if not employee:
            flash('Employee not found.', 'danger')
            return redirect(url_for('hr_employees'))
            
        projects = db.execute('''
            SELECT p.id, p.name, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
            WHERE ep.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (user_id,)).fetchall()
        
        project_details = []
        for p in projects:
            allocated = p['allocated_hours']
            worked_hours = p['worked_seconds'] / 3600.0
            remaining = allocated - worked_hours if allocated > 0 else 0
            project_details.append({
                'id': p['id'],
                'name': p['name'],
                'allocated_hours': allocated,
                'worked_hours': worked_hours,
                'remaining_hours': remaining
            })
            
        return render_template('print/print_employee_detail.html', employee=employee, projects=project_details, generated_by=current_user.full_name or current_user.username, generated_on=datetime.now().strftime('%Y-%m-%d %H:%M'))

    @app.route('/api/v1/employees/<int:user_id>/pdf')
    @role_required('HR')
    def api_download_employee_pdf(user_id):
        return redirect(url_for('hr_employee_detail_print', user_id=user_id))

    @app.route('/hr/projects/<int:project_id>/print')
    @role_required('HR')
    def hr_project_detail_print(project_id):
        db = get_db()
        project = db.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        if not project:
            flash('Project not found.', 'danger')
            return redirect(url_for('hr_projects'))
            
        employees = db.execute('''
            SELECT u.id, u.full_name, u.username, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM users u
            JOIN employee_projects ep ON u.id = ep.employee_id
            LEFT JOIN tasks t ON ep.project_id = t.project_id AND t.employee_id = u.id
            WHERE ep.project_id = ?
            GROUP BY u.id
            ORDER BY u.full_name
        ''', (project_id,)).fetchall()
        
        employee_details = []
        for emp in employees:
            allocated = emp['allocated_hours']
            worked_hours = emp['worked_seconds'] / 3600.0
            remaining = allocated - worked_hours if allocated > 0 else 0
            employee_details.append({
                'id': emp['id'],
                'full_name': emp['full_name'],
                'username': emp['username'],
                'allocated_hours': allocated,
                'worked_hours': worked_hours,
                'remaining_hours': remaining
            })
            
        return render_template('print/print_project_detail.html', project=project, employees=employee_details, generated_by=current_user.full_name or current_user.username, generated_on=datetime.now().strftime('%Y-%m-%d %H:%M'))

    @app.route('/hr/projects/add', methods=['POST'])
    @role_required('HR')
    def add_project():
        name = request.form.get('name')
        client = request.form.get('client')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        employee_ids = request.form.getlist('employee_ids')
        if name and client:
            db = get_db()
            try:
                cursor = db.execute('INSERT INTO projects (name, client, start_date, end_date) VALUES (?,?,?,?)',
                           (name, client, start_date or None, end_date or None))
                project_id = cursor.lastrowid
                for emp_id in employee_ids:
                    db.execute('INSERT OR IGNORE INTO employee_projects (employee_id, project_id, allocated_hours) VALUES (?,?,0)',
                               (int(emp_id), project_id))
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
            employee_ids = request.form.getlist('employee_ids')
            if name and client:
                try:
                    db.execute('UPDATE projects SET name = ?, client = ?, start_date = ?, end_date = ? WHERE id = ?',
                               (name, client, start_date or None, end_date or None, project_id))
                    
                    db.execute('DELETE FROM employee_projects WHERE project_id = ?', (project_id,))
                    for emp_id in employee_ids:
                        db.execute('INSERT INTO employee_projects (employee_id, project_id, allocated_hours) VALUES (?, ?, 100)',
                                   (int(emp_id), project_id))
                    db.commit()
                    flash('Project updated successfully.', 'success')
                    return redirect(url_for('hr_projects'))
                except sqlite3.IntegrityError:
                    flash('Project name already exists.', 'danger')
            else:
                flash('Project name and Client are required.', 'danger')
                
        employees = db.execute("SELECT id, full_name, username FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
        assigned = db.execute("SELECT employee_id FROM employee_projects WHERE project_id = ?", (project_id,)).fetchall()
        assigned_ids = [r['employee_id'] for r in assigned]
                
        return render_template('hr/edit_project.html', project=project, employees=employees, assigned_ids=assigned_ids)

    @app.route('/hr/add', methods=['GET', 'POST'])
    @role_required('HR')
    def add_employee():
        db = get_db()
        if request.method == 'POST':
            full_name = request.form['full_name']
            username = request.form['username']
            password = request.form['password']
            position = request.form.get('position', '')
            email = request.form.get('email', '')
            phone = request.form.get('phone', '')
            employee_number = request.form.get('employee_number', '')
            department = request.form.get('department', '')
            residence_permit_end_date = request.form.get('residence_permit_end_date', '')
            hire_date = request.form.get('hire_date', '')
            manager_usernames = request.form.getlist('managers')
            subordinate_usernames = request.form.getlist('subordinates')
            project_ids = request.form.getlist('projects')
            role = 'Employee'
            pwd_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            
            try:
                db.execute('INSERT INTO users (full_name, username, password_hash, role, position, email, phone, employee_number, department, residence_permit_end_date, hire_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (full_name, username, pwd_hash, role, position, email, phone, employee_number, department, residence_permit_end_date, hire_date))
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
                    
                    for sub_name in subordinate_usernames:
                        sub_row = db.execute('SELECT id FROM users WHERE username = ?', (sub_name,)).fetchone()
                        if sub_row:
                            db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)', (sub_row['id'], employee_id))
                    
                    for p_id in project_ids:
                        hours_val = request.form.get(f'allocated_hours_{p_id}', '0').strip()
                        hours = int(hours_val) if hours_val.isdigit() else 0
                        db.execute('INSERT INTO employee_projects (employee_id, project_id, allocated_hours) VALUES (?,?,?)', (employee_id, int(p_id), hours))
                    db.commit()
                    
                flash('Employee added.', 'success')
                return redirect(url_for('hr_employees'))
            except sqlite3.IntegrityError:
                flash('Username already exists.', 'danger')
                
        employees = db.execute("SELECT * FROM users WHERE role = 'Employee'").fetchall()
        projects = db.execute("SELECT * FROM projects ORDER BY name").fetchall()
        return render_template('hr/add_employee.html', employees=employees, projects=projects)

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
            email = request.form.get('email', '')
            phone = request.form.get('phone', '')
            employee_number = request.form.get('employee_number', '')
            department = request.form.get('department', '')
            residence_permit_end_date = request.form.get('residence_permit_end_date', '')
            hire_date = request.form.get('hire_date', '')
            manager_usernames = request.form.getlist('managers')
            subordinate_usernames = request.form.getlist('subordinates')
            project_ids = request.form.getlist('projects')
            
            try:
                if password:
                    pwd_hash = bcrypt.generate_password_hash(password).decode('utf-8')
                    db.execute('UPDATE users SET full_name = ?, username = ?, password_hash = ?, position = ?, email = ?, phone = ?, employee_number = ?, department = ?, residence_permit_end_date = ?, hire_date = ? WHERE id = ?',
                               (full_name, username, pwd_hash, position, email, phone, employee_number, department, residence_permit_end_date, hire_date, user_id))
                else:
                    db.execute('UPDATE users SET full_name = ?, username = ?, position = ?, email = ?, phone = ?, employee_number = ?, department = ?, residence_permit_end_date = ?, hire_date = ? WHERE id = ?',
                               (full_name, username, position, email, phone, employee_number, department, residence_permit_end_date, hire_date, user_id))
                db.commit()
                
                manager_ids = []
                for mgr_name in manager_usernames:
                    mgr_row = db.execute('SELECT id FROM users WHERE username = ?', (mgr_name,)).fetchone()
                    if mgr_row:
                        manager_ids.append(mgr_row['id'])
                set_manager_ids(user_id, manager_ids)
                
                db.execute('DELETE FROM employee_managers WHERE manager_id = ?', (user_id,))
                for sub_name in subordinate_usernames:
                    sub_row = db.execute('SELECT id FROM users WHERE username = ?', (sub_name,)).fetchone()
                    if sub_row:
                        db.execute('INSERT INTO employee_managers (employee_id, manager_id) VALUES (?,?)', (sub_row['id'], user_id))
                
                db.execute('DELETE FROM employee_projects WHERE employee_id = ?', (user_id,))
                for p_id in project_ids:
                    hours_val = request.form.get(f'allocated_hours_{p_id}', '0').strip()
                    hours = int(hours_val) if hours_val.isdigit() else 0
                    db.execute('INSERT INTO employee_projects (employee_id, project_id, allocated_hours) VALUES (?,?,?)', (user_id, int(p_id), hours))
                db.commit()
                
                flash('Employee updated.', 'success')
                return redirect(url_for('hr_employees'))
            except sqlite3.IntegrityError:
                flash('Username already exists.', 'danger')
                
        employees = db.execute("SELECT * FROM users WHERE role = 'Employee' AND id != ?", (user_id,)).fetchall()
        current_mgr_ids = get_manager_ids(user_id)
        current_managers = []
        for mid in current_mgr_ids:
            r = db.execute('SELECT username FROM users WHERE id = ?', (mid,)).fetchone()
            if r:
                current_managers.append(r['username'])
                
        sub_rows = db.execute('''
            SELECT u.username 
            FROM users u
            JOIN employee_managers em ON u.id = em.employee_id
            WHERE em.manager_id = ?
        ''', (user_id,)).fetchall()
        current_subordinates = [r['username'] for r in sub_rows]
                
        projects = db.execute("SELECT * FROM projects ORDER BY name").fetchall()
        current_proj_rows = db.execute("SELECT project_id, allocated_hours FROM employee_projects WHERE employee_id = ?", (user_id,)).fetchall()
        current_project_ids = [r['project_id'] for r in current_proj_rows]
        project_allocations = {r['project_id']: r['allocated_hours'] for r in current_proj_rows}
                
        return render_template('hr/edit_employee.html', user=user, employees=employees, current_managers=current_managers, current_subordinates=current_subordinates, projects=projects, current_project_ids=current_project_ids, project_allocations=project_allocations)

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

    @app.route('/hr/projects/delete/<int:project_id>', methods=['POST'])
    @role_required('HR')
    def delete_project(project_id):
        db = get_db()
        db.execute('DELETE FROM employee_projects WHERE project_id = ?', (project_id,))
        db.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
        db.execute('DELETE FROM projects WHERE id = ?', (project_id,))
        db.commit()
        flash('Project deleted.', 'info')
        return redirect(url_for('hr_projects'))

    @app.route('/hr/tracking')
    @role_required('HR')
    def hr_tracking():
        db = get_db()
        
        if 'reset' in request.args:
            save_user_preferences(current_user.id, filters={'hr_tracking': {}})
            return redirect(url_for('hr_tracking'))
            
        if 'filter_applied' in request.args:
            new_filters = {
                'employees': request.args.getlist('employees'),
                'projects': request.args.getlist('projects'),
                'statuses': request.args.getlist('statuses'),
                'created_from': request.args.get('created_from', ''),
                'created_to': request.args.get('created_to', ''),
                'creators': request.args.getlist('creators')
            }
            save_user_preferences(current_user.id, filters={'hr_tracking': new_filters})
        else:
            pref = get_user_preferences(current_user.id)
            saved = pref.get('filters', {}).get('hr_tracking', {})
            if saved:
                params = []
                for k, v in saved.items():
                    if isinstance(v, list):
                        for item in v:
                            params.append((k, item))
                    else:
                        if v:
                            params.append((k, v))
                if params:
                    params.append(('filter_applied', '1'))
                    return redirect(url_for('hr_tracking') + '?' + urllib.parse.urlencode(params))
                    
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
        
        query = '''
            SELECT t.*, u.full_name AS employee_name, creator.full_name AS creator_name, p.name AS project_name
            FROM tasks t
            JOIN users u ON t.employee_id = u.id
            LEFT JOIN users creator ON t.creator_id = creator.id
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE 1=1
        '''
        params = []
        
        if selected_employees:
            placeholders = ','.join('?' for _ in selected_employees)
            query += f" AND t.employee_id IN ({placeholders})"
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
        all_tasks = db.execute(query, params).fetchall()
        
        # Pagination setup
        page = request.args.get('page', 1, type=int)
        per_page = 20
        total_tasks = len(all_tasks)
        total_pages = max(1, (total_tasks + per_page - 1) // per_page)
        
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        offset = (page - 1) * per_page
        tasks = all_tasks[offset:offset + per_page]
        
        showing_from = offset + 1 if total_tasks > 0 else 0
        showing_to = min(offset + per_page, total_tasks)
        # Smart ellipsis page range
        if total_pages <= 7:
            page_range = list(range(1, total_pages + 1))
        else:
            page_range = []
            page_range.append(1)
            
            if page > 3:
                page_range.append(None)
                
            start = max(2, page - 1)
            end = min(total_pages - 1, page + 1)
            
            if page <= 3:
                end = 4
            elif page >= total_pages - 2:
                start = total_pages - 3
                
            for p in range(start, end + 1):
                if p not in page_range:
                    page_range.append(p)
                    
            if page < total_pages - 2:
                page_range.append(None)
                
            if total_pages not in page_range:
                page_range.append(total_pages)
        
        def page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('hr_tracking') + '?' + urllib.parse.urlencode(args, doseq=True)
            
        employees_list = db.execute("SELECT id, full_name FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
        projects_list = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
        creators_list = db.execute("SELECT id, full_name, username FROM users ORDER BY full_name").fetchall()
        
        return render_template(
            'hr/hr_tracking.html',
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
            showing_from=showing_from,
            showing_to=showing_to,
            page_range=page_range,
            page_url=page_url
        )

    @app.route('/hr/seed', methods=['POST'])
    @role_required('HR')
    def hr_seed():
        res = seed_mock_data()
        flash(f"Mock data seeded! Created {res['projects']} projects, {res['employees']} employees, and generated {res['tasks_generated']} tasks.", "success")
        return redirect(url_for('hr_dashboard'))

    @app.route('/hr/live-summary')
    @role_required('HR')
    def hr_live_summary():
        db = get_db()
        if request.args.get('reset') == '1':
            from ..database import save_user_preferences
            save_user_preferences(current_user.id, filters={'hr_live_summary': {}})
            return redirect(url_for('hr_live_summary'))
            
        # check filters
        if request.method == 'GET' and not request.args.get('reset'):
            if request.args.get('filter_applied') == '1':
                new_filters = {
                    'sum_employees': request.args.getlist('sum_employees'),
                    'sum_statuses': request.args.getlist('sum_statuses'),
                    'summary_created_from': request.args.get('summary_created_from', ''),
                    'summary_created_to': request.args.get('summary_created_to', '')
                }
                from ..database import save_user_preferences
                save_user_preferences(current_user.id, filters={'hr_live_summary': new_filters})
            else:
                from ..database import get_user_preferences
                pref = get_user_preferences(current_user.id)
                saved = pref.get('filters', {}).get('hr_live_summary', {})
                if saved:
                    params = []
                    for k, v in saved.items():
                        if isinstance(v, list):
                            for item in v:
                                params.append((k, item))
                        else:
                            if v:
                                params.append((k, v))
                    if params:
                        params.append(('filter_applied', '1'))
                        return redirect(url_for('hr_live_summary') + '?' + urllib.parse.urlencode(params))

        selected_sum_employees = [int(x) for x in request.args.getlist('sum_employees') if x.isdigit()]
        selected_sum_statuses = request.args.getlist('sum_statuses')
        
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
        
        summaries = []
        for row in employee_summaries:
            total = (row['running_cnt'] or 0) + (row['pause_cnt'] or 0) + (row['finish_cnt'] or 0)
            include = True
            if selected_sum_statuses:
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
                
        # Paginate summaries
        page = request.args.get('page', 1, type=int)
        per_page = 20
        total_items = len(summaries)
        total_pages = (total_items + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        paginated_summaries = summaries[offset:offset+per_page]
        
        # Helper to generate page ranges
        def get_pagination_range(curr, total):
            if total <= 7:
                return list(range(1, total + 1))
            res = []
            if curr <= 4:
                res.extend([1, 2, 3, 4])
                res.append(None)
                res.append(total)
            elif curr >= total - 3:
                res.append(1)
                res.append(None)
                res.extend(range(total - 3, total + 1))
            else:
                res.append(1)
                res.append(None)
                res.extend([curr - 1, curr, curr + 1])
                res.append(None)
                res.append(total)
            return res
            
        page_range = get_pagination_range(page, total_pages)
        showing_from = offset + 1 if total_items > 0 else 0
        showing_to = min(offset + per_page, total_items)
        
        def page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('hr_live_summary') + '?' + urllib.parse.urlencode(args, doseq=True)

        employees_list = db.execute("SELECT id, full_name FROM users WHERE role = 'Employee' ORDER BY full_name").fetchall()
        return render_template(
            'hr/hr_live_summary.html',
            summaries=paginated_summaries,
            employees_list=employees_list,
            selected_sum_employees=selected_sum_employees,
            selected_sum_statuses=selected_sum_statuses,
            page=page,
            total_pages=total_pages,
            page_range=page_range,
            page_url=page_url,
            showing_from=showing_from,
            showing_to=showing_to,
            total_tasks=total_items
        )

    @app.route('/hr/pending-approvals')
    @role_required('HR')
    def hr_pending_approvals():
        db = get_db()
        pending_approvals_raw = db.execute('''
            SELECT t.*, u.full_name AS employee_name, p.name AS project_name, approver.full_name AS approver_name
            FROM tasks t
            JOIN users u ON t.employee_id = u.id
            LEFT JOIN projects p ON t.project_id = p.id
            LEFT JOIN users approver ON t.approver_id = approver.id
            WHERE t.approval_status = 'Submitted' AND t.approver_id IS NOT NULL
            ORDER BY t.created_at DESC
        ''').fetchall()
        
        pending_approvals = []
        for row in pending_approvals_raw:
            task_dict = dict(row)
            try:
                created_dt = None
                try:
                    created_dt = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    created_dt = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M')
                
                delta = datetime.now() - created_dt
                if delta.days > 0:
                    pending_since = f"{delta.days}d" if session.get('lang') != 'ar' else f"منذ {delta.days} يوم"
                else:
                    hours = delta.seconds // 3600
                    minutes = (delta.seconds % 3600) // 60
                    if hours > 0:
                        pending_since = f"{hours}h {minutes}m" if session.get('lang') != 'ar' else f"منذ {hours} ساعة و {minutes} د"
                    else:
                        pending_since = f"{minutes}m" if session.get('lang') != 'ar' else f"منذ {minutes} د"
            except Exception:
                pending_since = "–"
            task_dict['pending_since'] = pending_since
            pending_approvals.append(task_dict)
            
        # Paginate pending approvals
        page = request.args.get('page', 1, type=int)
        per_page = 20
        total_items = len(pending_approvals)
        total_pages = (total_items + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        paginated_approvals = pending_approvals[offset:offset+per_page]
        
        # Helper to generate page ranges
        def get_pagination_range(curr, total):
            if total <= 7:
                return list(range(1, total + 1))
            res = []
            if curr <= 4:
                res.extend([1, 2, 3, 4])
                res.append(None)
                res.append(total)
            elif curr >= total - 3:
                res.append(1)
                res.append(None)
                res.extend(range(total - 3, total + 1))
            else:
                res.append(1)
                res.append(None)
                res.extend([curr - 1, curr, curr + 1])
                res.append(None)
                res.append(total)
            return res
            
        page_range = get_pagination_range(page, total_pages)
        showing_from = offset + 1 if total_items > 0 else 0
        showing_to = min(offset + per_page, total_items)
        
        def page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('hr_pending_approvals') + '?' + urllib.parse.urlencode(args, doseq=True)
            
        return render_template(
            'hr/hr_pending_approvals.html',
            pending_approvals=paginated_approvals,
            page=page,
            total_pages=total_pages,
            page_range=page_range,
            page_url=page_url,
            showing_from=showing_from,
            showing_to=showing_to,
            total_tasks=total_items
        )
