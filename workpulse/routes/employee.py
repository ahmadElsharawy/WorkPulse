import urllib.parse
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, session
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
                'creators': request.args.getlist('creators')
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

        # Paginate my tasks
        page = request.args.get('page', 1, type=int)
        per_page = 20
        total_tasks = len(tasks)
        total_pages = (total_tasks + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        paginated_tasks = tasks[offset:offset+per_page]
        page_range = get_pagination_range(page, total_pages)
        showing_from = offset + 1 if total_tasks > 0 else 0
        showing_to = min(offset + per_page, total_tasks)

        def page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('employee_dashboard') + '?' + urllib.parse.urlencode(args, doseq=True)
        
        subordinates = db.execute('''
            SELECT u.* FROM users u
            JOIN employee_managers em ON u.id = em.employee_id
            WHERE em.manager_id = ?
        ''', (current_user.id,)).fetchall()
        
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
        
        # Calculate UAE Gratuity & Leave Balance
        from workpulse.helpers import calculate_uae_gratuity_and_leaves
        employee_row = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        gratuity_info = calculate_uae_gratuity_and_leaves(employee_row, db)

        return render_template(
            'employee/employee.html', 
            tasks=paginated_tasks, 
            subordinates=subordinates, 
            projects_list=projects_list,
            creators_list=creators_list,
            selected_projects=selected_projects,
            selected_statuses=selected_statuses,
            created_from=created_from,
            created_to=created_to,
            selected_creators=selected_creators,
            assigned_project_balances=assigned_project_balances,
            chart_projects_labels=chart_projects_labels,
            chart_projects_data=chart_projects_data,
            chart_weekly_labels=chart_weekly_labels,
            chart_weekly_data=chart_weekly_data,
            pending_sub_approvals=pending_sub_approvals,
            my_managers=my_managers,
            gratuity_info=gratuity_info,
            
            page=page,
            total_pages=total_pages,
            page_range=page_range,
            page_url=page_url,
            showing_from=showing_from,
            showing_to=showing_to,
            total_tasks=total_tasks
        )

    @app.route('/employee/add', methods=['GET', 'POST'])
    @role_required('Employee')
    def add_task():
        db = get_db()
        if request.method == 'POST':
            title = request.form['title']
            description = request.form.get('description', '')
            project_id = int(request.form['project_id'])
            is_retroactive = request.form.get('is_retroactive') == '1'
            
            if is_retroactive:
                start_time_str = request.form.get('start_time', '').strip()
                end_time_str = request.form.get('end_time', '').strip()
                approver_id_val = request.form.get('approver_id', '0')
                
                if not start_time_str or not end_time_str:
                    flash('يرجى تحديد تاريخ ووقت البداية والانتهاء للمهمة السابقة.' if session.get('lang') == 'ar' else 'Please specify start and end date/time for the retroactive task.', 'danger')
                    return redirect(url_for('add_task'))
                
                try:
                    start_dt = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                    end_dt = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('صيغة التاريخ أو الوقت غير صحيحة.' if session.get('lang') == 'ar' else 'Invalid date format.', 'danger')
                    return redirect(url_for('add_task'))
                
                if end_dt <= start_dt:
                    flash('تاريخ ووقت الانتهاء يجب أن يكون بعد تاريخ ووقت البداية.' if session.get('lang') == 'ar' else 'End time must be after start time.', 'danger')
                    return redirect(url_for('add_task'))
                
                duration_seconds = int((end_dt - start_dt).total_seconds())
                created_at = start_dt.strftime('%Y-%m-%d %H:%M')
                
                approver_id = int(approver_id_val) if approver_id_val.isdigit() and int(approver_id_val) > 0 else None
                approval_status = 'Submitted' if approver_id else 'Approved'
                
                db.execute('''
                    INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id, approval_status, approver_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (current_user.id, project_id, title, description, 'Finish', created_at, duration_seconds, current_user.id, approval_status, approver_id))
                db.commit()
                
                if approval_status == 'Submitted':
                    flash('تمت إضافة المهمة السابقة وإرسالها إلى مديرك للمراجعة والاعتماد.' if session.get('lang') == 'ar' else 'Retroactive task added and submitted to manager for approval.', 'success')
                else:
                    flash('تمت إضافة المهمة المكتملة بنجاح.' if session.get('lang') == 'ar' else 'Retroactive task added successfully.', 'success')
                return redirect(url_for('employee_dashboard'))
            else:
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                           (current_user.id, project_id, title, description, 'Pause', now, 0, current_user.id))
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
            
        my_managers = db.execute('''
            SELECT u.id, u.full_name, u.username
            FROM users u
            JOIN employee_managers em ON u.id = em.manager_id
            WHERE em.employee_id = ?
            ORDER BY u.full_name
        ''', (current_user.id,)).fetchall()
            
        return render_template('employee/add_task.html', projects=projects, my_managers=my_managers)

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
                SET title = ?, description = ?, status = ?, running_duration = ?, last_started_at = ?, project_id = ?, approval_status = ?, approver_id = ?
                WHERE id = ? AND employee_id = ?
            ''', (title, description, new_status, new_running_duration, new_last_started_at, project_id, approval_status, approver_id, task_id, current_user.id))
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
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            db.execute('INSERT INTO tasks (employee_id, project_id, title, description, status, created_at, running_duration, creator_id) VALUES (?,?,?,?,?,?,?,?)',
                       (sub_id, project_id, title, description, 'Pause', now, 0, current_user.id))
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

    @app.route('/profile')
    @login_required
    def profile():
        db = get_db()
        employee = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        if not employee:
            flash('Employee not found.', 'danger')
            return redirect(url_for('index'))
            
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
                'worked_hours': worked_hours,
                'remaining_hours': remaining_hours
            })
            
        from workpulse.helpers import calculate_uae_gratuity_and_leaves
        gratuity_info = calculate_uae_gratuity_and_leaves(employee, db)
            
        return render_template('employee/profile.html', employee=employee, assigned_project_balances=assigned_project_balances, gratuity_info=gratuity_info)

    @app.route('/employee/team-status')
    @role_required('Employee')
    def team_status():
        db = get_db()
        summary_query = '''
            SELECT u.id, u.full_name AS employee_name,
                SUM(CASE WHEN t.status = 'Running' THEN 1 ELSE 0 END) AS running_cnt,
                SUM(CASE WHEN t.status = 'Pause' THEN 1 ELSE 0 END) AS pause_cnt,
                SUM(CASE WHEN t.status = 'Finish' THEN 1 ELSE 0 END) AS finish_cnt,
                (SELECT COUNT(*) FROM tasks t2 WHERE t2.employee_id = u.id AND t2.status = 'Running') AS global_running_cnt
            FROM users u
            JOIN employee_managers em ON u.id = em.employee_id
            LEFT JOIN tasks t ON u.id = t.employee_id AND t.project_id IN (
                SELECT project_id FROM employee_projects WHERE employee_id = ?
            )
            WHERE em.manager_id = ? AND u.role = 'Employee'
            GROUP BY u.id
            ORDER BY u.full_name
        '''
        live_summary = db.execute(summary_query, (current_user.id, current_user.id)).fetchall()
        return render_template('employee/team_status.html', live_summary=live_summary)

    @app.route('/employee/pending-approvals')
    @role_required('Employee')
    def pending_approvals():
        db = get_db()
        pending_sub_approvals_raw = db.execute('''
            SELECT t.*, u.full_name AS employee_name, p.name AS project_name
            FROM tasks t
            JOIN users u ON t.employee_id = u.id
            LEFT JOIN projects p ON t.project_id = p.id
            WHERE t.approver_id = ? AND t.approval_status = 'Submitted'
            ORDER BY t.created_at DESC
        ''', (current_user.id,)).fetchall()
        
        # Paginate pending approvals
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

        page = request.args.get('page', 1, type=int)
        per_page = 20
        total_tasks = len(pending_sub_approvals_raw)
        total_pages = (total_tasks + per_page - 1) // per_page
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        offset = (page - 1) * per_page
        paginated_pending_approvals = pending_sub_approvals_raw[offset:offset+per_page]
        page_range = get_pagination_range(page, total_pages)
        showing_from = offset + 1 if total_tasks > 0 else 0
        showing_to = min(offset + per_page, total_tasks)

        def page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('pending_approvals') + '?' + urllib.parse.urlencode(args, doseq=True)

        return render_template(
            'employee/pending_approvals.html',
            pending_sub_approvals=paginated_pending_approvals,
            page=page,
            total_pages=total_pages,
            page_range=page_range,
            page_url=page_url,
            showing_from=showing_from,
            showing_to=showing_to,
            total_tasks=total_tasks
        )

    @app.route('/employee/subordinate-tracking')
    @role_required('Employee')
    def employee_subordinate_live_tracking():
        db = get_db()
        
        subordinates = db.execute('''
            SELECT u.* FROM users u
            JOIN employee_managers em ON u.id = em.employee_id
            WHERE em.manager_id = ?
        ''', (current_user.id,)).fetchall()
        
        if not subordinates:
            flash('You have no subordinates.' if session.get('lang') != 'ar' else 'ليس لديك مرؤوسين.', 'info')
            return redirect(url_for('employee_dashboard'))
        
        if 'reset' in request.args:
            save_user_preferences(current_user.id, filters={'subordinate_tracking': {}})
            return redirect(url_for('employee_subordinate_live_tracking'))
        
        if 'filter_applied' in request.args:
            new_filters = {
                'sub_employees': request.args.getlist('sub_employees'),
                'sub_projects': request.args.getlist('sub_projects'),
                'sub_statuses': request.args.getlist('sub_statuses'),
                'sub_created_from': request.args.get('sub_created_from', ''),
                'sub_created_to': request.args.get('sub_created_to', ''),
                'sub_creators': request.args.getlist('sub_creators')
            }
            save_user_preferences(current_user.id, filters={'subordinate_tracking': new_filters})
        else:
            pref = get_user_preferences(current_user.id)
            saved = pref.get('filters', {}).get('subordinate_tracking', {})
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
                    return redirect(url_for('employee_subordinate_live_tracking') + '?' + urllib.parse.urlencode(params))
        
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
        all_subordinate_tasks = db.execute(sub_query, sub_params).fetchall()
        
        # Pagination
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
        
        sub_page = request.args.get('page', 1, type=int)
        sub_per_page = 20
        total_sub_tasks = len(all_subordinate_tasks)
        sub_total_pages = (total_sub_tasks + sub_per_page - 1) // sub_per_page
        sub_page = max(1, min(sub_page, sub_total_pages)) if sub_total_pages > 0 else 1
        sub_offset = (sub_page - 1) * sub_per_page
        paginated_subordinate_tasks = all_subordinate_tasks[sub_offset:sub_offset+sub_per_page]
        sub_page_range = get_pagination_range(sub_page, sub_total_pages)
        sub_showing_from = sub_offset + 1 if total_sub_tasks > 0 else 0
        sub_showing_to = min(sub_offset + sub_per_page, total_sub_tasks)
        
        def sub_page_url(p):
            args = request.args.to_dict(flat=False)
            args['page'] = [str(p)]
            return url_for('employee_subordinate_live_tracking') + '?' + urllib.parse.urlencode(args, doseq=True)
        
        projects_list = db.execute('''
            SELECT p.id, p.name FROM projects p
            JOIN employee_projects ep ON p.id = ep.project_id
            WHERE ep.employee_id = ?
            ORDER BY p.name
        ''', (current_user.id,)).fetchall()
        if not projects_list:
            projects_list = db.execute("SELECT id, name FROM projects ORDER BY name").fetchall()
        
        sub_creators_list = db.execute('''
            SELECT DISTINCT creator.id, creator.full_name, creator.username
            FROM users creator
            JOIN tasks t ON t.creator_id = creator.id
            JOIN employee_managers em ON t.employee_id = em.employee_id
            WHERE em.manager_id = ?
            ORDER BY creator.full_name
        ''', (current_user.id,)).fetchall()
        
        return render_template(
            'employee/subordinate_live_tracking.html',
            subordinates=subordinates,
            subordinate_tasks=paginated_subordinate_tasks,
            projects_list=projects_list,
            sub_creators_list=sub_creators_list,
            selected_sub_employees=selected_sub_employees,
            selected_sub_projects=selected_sub_projects,
            selected_sub_statuses=selected_sub_statuses,
            sub_created_from=sub_created_from,
            sub_created_to=sub_created_to,
            selected_sub_creators=selected_sub_creators,
            sub_page=sub_page,
            sub_total_pages=sub_total_pages,
            sub_page_range=sub_page_range,
            sub_page_url=sub_page_url,
            sub_showing_from=sub_showing_from,
            sub_showing_to=sub_showing_to,
            total_sub_tasks=total_sub_tasks
        )

    @app.route('/employee/end-of-service')
    @role_required('Employee')
    def employee_end_of_service():
        db = get_db()
        employee = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
        if not employee:
            flash('Employee not found.', 'danger')
            return redirect(url_for('employee_dashboard'))
            
        from workpulse.helpers import calculate_uae_gratuity_and_leaves
        gratuity_info = calculate_uae_gratuity_and_leaves(employee, db)
        
        return render_template(
            'end_of_service.html',
            employee=employee,
            gratuity_info=gratuity_info,
            is_hr_view=False
        )
