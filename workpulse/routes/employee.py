import urllib.parse
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from workpulse.decorators import role_required
from workpulse.database import get_db, get_user_preferences, save_user_preferences

def register_employee_routes(app):
    @app.route('/employee')
    @role_required('Employee')
    def employee_dashboard():
        db = get_db()
        
        if 'reset' in request.args:
            save_user_preferences(current_user.id, filters={'employee_dashboard': {}})
            return redirect(url_for('employee_dashboard'))
            
        if 'filter_applied' in request.args:
            new_filters = {
                'projects': request.args.getlist('projects'),
                'statuses': request.args.getlist('statuses'),
                'created_from': request.args.get('created_from', ''),
                'created_to': request.args.get('created_to', ''),
                'creators': request.args.getlist('creators'),
                'sub_employees': request.args.getlist('sub_employees'),
                'sub_projects': request.args.getlist('sub_projects'),
                'sub_statuses': request.args.getlist('sub_statuses'),
                'sub_created_from': request.args.get('sub_created_from', ''),
                'sub_created_to': request.args.get('sub_created_to', ''),
                'sub_creators': request.args.getlist('sub_creators')
            }
            save_user_preferences(current_user.id, filters={'employee_dashboard': new_filters})
        else:
            pref = get_user_preferences(current_user.id)
            saved = pref.get('filters', {}).get('employee_dashboard', {})
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
                    return redirect(url_for('employee_dashboard') + '?' + urllib.parse.urlencode(params))
        
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
        
        subordinates = db.execute('''
            SELECT u.* FROM users u
            JOIN employee_managers em ON u.id = em.employee_id
            WHERE em.manager_id = ?
        ''', (current_user.id,)).fetchall()
        
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
        
        sub_creators_list = db.execute('''
            SELECT DISTINCT creator.id, creator.full_name, creator.username
            FROM users creator
            JOIN tasks t ON t.creator_id = creator.id
            JOIN employee_managers em ON t.employee_id = em.employee_id
            WHERE em.manager_id = ?
            ORDER BY creator.full_name
        ''', (current_user.id,)).fetchall()
        
        balance_rows = db.execute('''
            SELECT p.id, p.name, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
            WHERE ep.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (current_user.id,)).fetchall()
        
        assigned_project_balances = []
        for r in balance_rows:
            allocated = r['allocated_hours']
            worked_hours = r['worked_seconds'] / 3600.0
            remaining_hours = allocated - worked_hours if allocated > 0 else 0
            assigned_project_balances.append({
                'id': r['id'],
                'name': r['name'],
                'allocated_hours': allocated,
                'remaining_hours': remaining_hours
            })
            
        chart_projects_labels = [r['name'] for r in balance_rows if r['worked_seconds'] > 0]
        chart_projects_data = [round(r['worked_seconds'] / 3600.0, 2) for r in balance_rows if r['worked_seconds'] > 0]
        
        chart_weekly_labels = []
        chart_weekly_data = []
        today = datetime.now().date()
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            chart_weekly_labels.append(day.strftime('%b %d') if session.get('lang') != 'ar' else day.strftime('%m/%d'))
            
            row = db.execute('''
                SELECT COALESCE(SUM(running_duration), 0) AS daily_seconds
                FROM tasks
                WHERE employee_id = ? AND substr(created_at, 1, 10) = ?
            ''', (current_user.id, day_str)).fetchone()
            chart_weekly_data.append(round(row['daily_seconds'] / 3600.0, 2))
            
        pending_sub_approvals = db.execute('''
            SELECT t.*, u.full_name AS employee_name, p.name AS project_name
            FROM tasks t
            JOIN users u ON t.employee_id = u.id
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE t.approver_id = ? AND t.approval_status = 'Submitted'
            ORDER BY t.created_at DESC
        ''', (current_user.id,)).fetchall()
        
        my_managers = db.execute('''
            SELECT u.id, u.full_name, u.username
            FROM users u
            JOIN employee_managers em ON u.id = em.manager_id
            WHERE em.employee_id = ?
        ''', (current_user.id,)).fetchall()
        
        return render_template(
            'employee/employee.html', 
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
            selected_sub_creators=selected_sub_creators,
            assigned_project_balances=assigned_project_balances,
            chart_projects_labels=chart_projects_labels,
            chart_projects_data=chart_projects_data,
            chart_weekly_labels=chart_weekly_labels,
            chart_weekly_data=chart_weekly_data,
            pending_sub_approvals=pending_sub_approvals,
            my_managers=my_managers
        )

    @app.route('/employee/add', methods=['GET', 'POST'])
    @role_required('Employee')
    def add_task():
        db = get_db()
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            project_id = int(request.form['project_id'])
            category = request.form.get('category', 'Other')
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id, category) VALUES (?,?,?,?,?,?,?,?,?)',
                       (current_user.id, project_id, title, description, 'Pause', now, 0, current_user.id, category))
            db.commit()
            flash('Task added.', 'success')
            return redirect(url_for('employee_dashboard'))
            
        projects_raw = db.execute('''
            SELECT p.id, p.name, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
            WHERE ep.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (current_user.id,)).fetchall()
        
        projects = []
        for p in projects_raw:
            allocated = p['allocated_hours']
            if allocated == 0:
                name_with_balance = f"{p['name']} (Unlimited hours)"
                remaining = 0
            else:
                worked_hours = p['worked_seconds'] / 3600.0
                remaining = allocated - worked_hours
                name_with_balance = f"{p['name']} ({remaining:.2f} hrs remaining of {allocated} hrs)"
            projects.append({'id': p['id'], 'name': name_with_balance, 'remaining': remaining, 'allocated': allocated})
            
        if not projects:
            raw_fallback = db.execute('SELECT * FROM projects ORDER BY name').fetchall()
            projects = [{'id': p['id'], 'name': f"{p['name']} (Unlimited hours)", 'remaining': 0, 'allocated': 0} for p in raw_fallback]
            
        return render_template('employee/add_task.html', projects=projects)

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
            category = request.form.get('category', 'Other')
            
            old_status = task['status']
            old_running_duration = task['running_duration'] or 0
            old_last_started_at = task['last_started_at']
            
            new_running_duration = old_running_duration
            new_last_started_at = old_last_started_at
            now_utc = datetime.utcnow()
            
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
                
            approver_id = None
            approval_status = 'Draft'
            if new_status == 'Finish':
                if task['creator_id'] != current_user.id:
                    approver_id = task['creator_id']
                    approval_status = 'Submitted'
                else:
                    req_approver = request.form.get('approver_id')
                    if req_approver and req_approver != '' and req_approver != '0':
                        approver_id = int(req_approver)
                        approval_status = 'Submitted'
                    else:
                        approver_id = None
                        approval_status = 'Approved'
            else:
                approval_status = 'Draft'
                approver_id = None

            db.execute('''
                UPDATE tasks 
                SET title = ?, description = ?, status = ?, running_duration = ?, last_started_at = ?, project_id = ?, category = ?, approval_status = ?, approver_id = ?
                WHERE id = ? AND employee_id = ?
            ''', (title, description, new_status, new_running_duration, new_last_started_at, project_id, category, approval_status, approver_id, task_id, current_user.id))
            db.commit()
            flash('Task updated.', 'success')
            return redirect(url_for('employee_dashboard'))
            
        projects_raw = db.execute('''
            SELECT p.id, p.name, ep.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
            WHERE ep.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (current_user.id,)).fetchall()
        
        projects = []
        for p in projects_raw:
            allocated = p['allocated_hours']
            if allocated == 0:
                name_with_balance = f"{p['name']} (Unlimited hours)"
                remaining = 0
            else:
                worked_hours = p['worked_seconds'] / 3600.0
                remaining = allocated - worked_hours
                name_with_balance = f"{p['name']} ({remaining:.2f} hrs remaining of {allocated} hrs)"
            projects.append({'id': p['id'], 'name': name_with_balance, 'remaining': remaining, 'allocated': allocated})
            
        if not projects:
            raw_fallback = db.execute('SELECT * FROM projects ORDER BY name').fetchall()
            projects = [{'id': p['id'], 'name': f"{p['name']} (Unlimited hours)", 'remaining': 0, 'allocated': 0} for p in raw_fallback]
            
        my_managers = db.execute('''
            SELECT u.id, u.full_name, u.username
            FROM users u
            JOIN employee_managers em ON u.id = em.manager_id
            WHERE em.employee_id = ?
        ''', (current_user.id,)).fetchall()

        return render_template('employee/edit_task.html', task=task, projects=projects, my_managers=my_managers)

    @app.route('/employee/task/<int:task_id>/update_status', methods=['POST'])
    @role_required('Employee')
    def update_task_status(task_id):
        db = get_db()
        task = db.execute('SELECT creator_id, employee_id, status, running_duration, last_started_at FROM tasks WHERE id = ? AND employee_id = ?', (task_id, current_user.id)).fetchone()
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
                
            approver_id = None
            approval_status = 'Draft'
            if new_status == 'Finish':
                if task['creator_id'] != current_user.id:
                    approver_id = task['creator_id']
                    approval_status = 'Submitted'
                else:
                    req_approver = request.form.get('approver_id')
                    if req_approver and req_approver != '' and req_approver != '0':
                        approver_id = int(req_approver)
                        approval_status = 'Submitted'
                    else:
                        approver_id = None
                        approval_status = 'Approved'
            else:
                approval_status = 'Draft'
                approver_id = None

            db.execute('''
                UPDATE tasks 
                SET status = ?, running_duration = ?, last_started_at = ?, approval_status = ?, approver_id = ?
                WHERE id = ? AND employee_id = ?
            ''', (new_status, new_running_duration, new_last_started_at, approval_status, approver_id, task_id, current_user.id))
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
        return render_template('employee/subordinates.html', subordinates=subordinates)

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
        return render_template('employee/subordinate_tasks.html', subordinate=subordinate, tasks=tasks)

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
            category = request.form.get('category', 'Other')
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id, category) VALUES (?,?,?,?,?,?,?,?,?)',
                       (sub_id, project_id, title, description, 'Pause', now, 0, current_user.id, category))
            db.commit()
            flash('Task assigned to employee.', 'success')
            return redirect(url_for('view_subordinate_tasks', sub_id=sub_id))
        projects_raw = db.execute('''
            SELECT p.id, p.name, ep_sub.allocated_hours,
                   COALESCE(SUM(t.running_duration), 0) AS worked_seconds
            FROM projects p
            JOIN employee_projects ep_sub ON p.id = ep_sub.project_id
            JOIN employee_projects ep_mgr ON p.id = ep_mgr.project_id
            LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep_sub.employee_id
            WHERE ep_sub.employee_id = ? AND ep_mgr.employee_id = ?
            GROUP BY p.id
            ORDER BY p.name
        ''', (sub_id, current_user.id)).fetchall()
        
        if not projects_raw:
            projects_raw = db.execute('''
                SELECT p.id, p.name, ep.allocated_hours,
                       COALESCE(SUM(t.running_duration), 0) AS worked_seconds
                FROM projects p
                JOIN employee_projects ep ON p.id = ep.project_id
                LEFT JOIN tasks t ON p.id = t.project_id AND t.employee_id = ep.employee_id
                WHERE ep.employee_id = ?
                GROUP BY p.id
                ORDER BY p.name
            ''', (sub_id,)).fetchall()
            
        projects = []
        for p in projects_raw:
            allocated = p['allocated_hours']
            if allocated == 0:
                name_with_balance = f"{p['name']} (Unlimited hours)"
            else:
                worked_hours = p['worked_seconds'] / 3600.0
                remaining = allocated - worked_hours
                name_with_balance = f"{p['name']} ({remaining:.2f} hrs remaining of {allocated} hrs)"
            projects.append({'id': p['id'], 'name': name_with_balance})
            
        if not projects:
            raw_fallback = db.execute('SELECT * FROM projects ORDER BY name').fetchall()
            projects = [{'id': p['id'], 'name': f"{p['name']} (Unlimited hours)"} for p in raw_fallback]
            
        return render_template('employee/add_subordinate_task.html', subordinate=subordinate, projects=projects)

    @app.route('/tasks/approve/<int:task_id>', methods=['POST'])
    @role_required('Employee')
    def approve_task(task_id):
        db = get_db()
        task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            flash('Task not found.', 'danger')
            return redirect(request.referrer or url_for('index'))
            
        allowed = False
        link = db.execute('SELECT 1 FROM employee_managers WHERE employee_id = ? AND manager_id = ?', 
                          (task['employee_id'], current_user.id)).fetchone()
        if link:
            allowed = True
                
        if not allowed:
            flash('Permission denied.', 'danger')
            return redirect(request.referrer or url_for('index'))
            
        db.execute('UPDATE tasks SET approval_status = "Approved", approval_comments = NULL WHERE id = ?', (task_id,))
        db.commit()
        flash('Task timesheet approved.', 'success')
        return redirect(request.referrer or url_for('index'))

    @app.route('/tasks/reject/<int:task_id>', methods=['POST'])
    @role_required('Employee')
    def reject_task(task_id):
        db = get_db()
        task = db.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
        if not task:
            flash('Task not found.', 'danger')
            return redirect(request.referrer or url_for('index'))
            
        allowed = False
        link = db.execute('SELECT 1 FROM employee_managers WHERE employee_id = ? AND manager_id = ?', 
                          (task['employee_id'], current_user.id)).fetchone()
        if link:
            allowed = True
                
        if not allowed:
            flash('Permission denied.', 'danger')
            return redirect(request.referrer or url_for('index'))
            
        comments = request.form.get('comments', '')
        db.execute('UPDATE tasks SET approval_status = "Rejected", approval_comments = ? WHERE id = ?', (comments, task_id))
        db.commit()
        flash('Task timesheet rejected.', 'warning')
        return redirect(request.referrer or url_for('index'))
