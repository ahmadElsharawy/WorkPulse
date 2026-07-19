from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from workpulse.database import get_db

bp = Blueprint('requests', __name__, url_prefix='/requests')


def format_duration_arabic(seconds, lang='ar'):
    """Format duration in seconds into a friendly human readable string (Arabic/English)."""
    if seconds is None or seconds < 0:
        return 'غير محدد' if lang == 'ar' else 'N/A'
    
    seconds = int(seconds)
    if seconds < 60:
        return 'أقل من دقيقة' if lang == 'ar' else '< 1 min'
    
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes} دقيقة' if lang == 'ar' else f'{minutes} mins'
    
    hours = minutes // 60
    rem_minutes = minutes % 60
    if hours < 24:
        if rem_minutes > 0:
            return f'{hours} ساعة و {rem_minutes} دقيقة' if lang == 'ar' else f'{hours} hrs {rem_minutes} mins'
        return f'{hours} ساعة' if lang == 'ar' else f'{hours} hrs'
    
    days = hours // 24
    rem_hours = hours % 24
    if rem_hours > 0:
        return f'{days} يوم و {rem_hours} ساعة' if lang == 'ar' else f'{days} days {rem_hours} hrs'
    return f'{days} يوم' if lang == 'ar' else f'{days} days'


def calculate_elapsed_time(assigned_at_str):
    """Calculate elapsed seconds from assigned_at timestamp until now."""
    if not assigned_at_str:
        return 0
    try:
        assigned_dt = datetime.strptime(assigned_at_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            assigned_dt = datetime.strptime(assigned_at_str, '%Y-%m-%d %H:%M')
        except ValueError:
            return 0
    
    diff = (datetime.now() - assigned_dt).total_seconds()
    return max(0, int(diff))


@bp.route('/leaves')
@login_required
def leaves_list():
    db = get_db()
    current_lang = session.get('lang', 'ar')
    
    # 1. Fetch Leave Requests based on user role
    if current_user.role == 'HR':
        # HR sees all requests
        query = '''
            SELECT lr.*, u.full_name as employee_name, u.username as employee_username,
                   u.department, u.position
            FROM leave_requests lr
            JOIN users u ON lr.employee_id = u.id
            ORDER BY lr.created_at DESC
        '''
        leave_requests = db.execute(query).fetchall()
    else:
        # Employee sees their own requests AND requests of subordinates waiting for their approval
        query = '''
            SELECT lr.*, u.full_name as employee_name, u.username as employee_username,
                   u.department, u.position
            FROM leave_requests lr
            JOIN users u ON lr.employee_id = u.id
            WHERE lr.employee_id = ?
               OR lr.id IN (
                    SELECT leave_request_id 
                    FROM leave_request_approvals 
                    WHERE approver_id = ?
               )
            ORDER BY lr.created_at DESC
        '''
        leave_requests = db.execute(query, (current_user.id, current_user.id)).fetchall()
        
    requests_data = []
    
    for req in leave_requests:
        req_dict = dict(req)
        
        # Fetch approval chain steps for this leave request
        steps_query = '''
            SELECT lra.*, u.full_name as approver_name, u.role as approver_user_role, u.position as approver_position
            FROM leave_request_approvals lra
            LEFT JOIN users u ON lra.approver_id = u.id
            WHERE lra.leave_request_id = ?
            ORDER BY lra.approval_order ASC
        '''
        steps = db.execute(steps_query, (req['id'],)).fetchall()
        
        processed_steps = []
        can_current_user_approve = False
        current_pending_step_id = None
        
        for step in steps:
            s_dict = dict(step)
            is_ar = current_lang == 'ar'
            
            # Format time duration
            if s_dict['status'] == 'approved':
                resp_sec = s_dict.get('response_time_seconds') or 0
                s_dict['duration_text'] = f"تمت الموافقة خلال {format_duration_arabic(resp_sec, current_lang)}" if is_ar else f"Approved in {format_duration_arabic(resp_sec, current_lang)}"
            elif s_dict['status'] == 'rejected':
                resp_sec = s_dict.get('response_time_seconds') or 0
                s_dict['duration_text'] = f"تم الرفض خلال {format_duration_arabic(resp_sec, current_lang)}" if is_ar else f"Rejected in {format_duration_arabic(resp_sec, current_lang)}"
            elif s_dict['status'] == 'pending':
                elapsed_sec = calculate_elapsed_time(s_dict.get('assigned_at'))
                s_dict['duration_text'] = f"معلق منذ {format_duration_arabic(elapsed_sec, current_lang)}" if is_ar else f"Pending for {format_duration_arabic(elapsed_sec, current_lang)}"
                
                # Check if current logged-in user is authorized to approve this step
                if s_dict['approver_role'] == 'Manager' and s_dict['approver_id'] == current_user.id:
                    can_current_user_approve = True
                    current_pending_step_id = s_dict['id']
                elif s_dict['approver_role'] == 'HR' and current_user.role == 'HR':
                    can_current_user_approve = True
                    current_pending_step_id = s_dict['id']
            else:
                s_dict['duration_text'] = 'بانتظار دور الموافقة' if is_ar else 'Awaiting sequence'
                
            processed_steps.append(s_dict)
            
        req_dict['steps'] = processed_steps
        req_dict['can_approve'] = can_current_user_approve
        req_dict['pending_step_id'] = current_pending_step_id
        requests_data.append(req_dict)
        
    return render_template('requests/leaves.html', leave_requests=requests_data, current_lang=current_lang)


@bp.route('/leaves/create', methods=['POST'])
@login_required
def leaves_create():
    leave_type = request.form.get('leave_type', 'سنوية').strip()
    start_date_str = request.form.get('start_date', '').strip()
    end_date_str = request.form.get('end_date', '').strip()
    reason = request.form.get('reason', '').strip()
    
    if not start_date_str or not end_date_str:
        flash('يرجى تحديد تاريخ بداية ونهاية الإجازة.', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    try:
        s_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        e_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        if e_date < s_date:
            flash('تاريخ نهاية الإجازة يجب أن يكون بعد تاريخ البداية.', 'danger')
            return redirect(url_for('requests.leaves_list'))
        duration_days = (e_date - s_date).days + 1
    except ValueError:
        flash('صيغة التاريخ غير صحيحة.', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Check if employee has assigned managers
    managers = db.execute('''
        SELECT manager_id FROM employee_managers WHERE employee_id = ?
    ''', (current_user.id,)).fetchall()
    
    initial_status = 'pending_managers' if managers else 'pending_hr'
    
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, duration_days, reason, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (current_user.id, leave_type, start_date_str, end_date_str, duration_days, reason, initial_status, now_str, now_str))
    
    leave_id = cursor.lastrowid
    
    if managers:
        # Create approval steps for managers in sequence
        for idx, mgr in enumerate(managers, start=1):
            step_status = 'pending' if idx == 1 else 'waiting'
            cursor.execute('''
                INSERT INTO leave_request_approvals (leave_request_id, approver_id, approver_role, approval_order, status, assigned_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (leave_id, mgr['manager_id'], 'Manager', idx, step_status, now_str))
    else:
        # Directly create HR approval step
        cursor.execute('''
            INSERT INTO leave_request_approvals (leave_request_id, approver_id, approver_role, approval_order, status, assigned_at)
            VALUES (?, NULL, ?, 1, ?, ?)
        ''', (leave_id, 'HR', 'pending', now_str))
        
    db.commit()
    flash('تم تقديم طلب الإجازة بنجاح وهو قيد المتابعة.', 'success')
    return redirect(url_for('requests.leaves_list'))


@bp.route('/leaves/<int:request_id>/approve', methods=['POST'])
@login_required
def leaves_approve(request_id):
    comments = request.form.get('comments', '').strip()
    db = get_db()
    
    leave_req = db.execute('SELECT * FROM leave_requests WHERE id = ?', (request_id,)).fetchone()
    if not leave_req:
        flash('طلب الإجازة غير موجود.', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    # Find current pending approval step
    pending_step = db.execute('''
        SELECT * FROM leave_request_approvals 
        WHERE leave_request_id = ? AND status = 'pending'
        ORDER BY approval_order ASC LIMIT 1
    ''', (request_id,)).fetchone()
    
    if not pending_step:
        flash('لا توجد خطوة موافقة معلقة لهذا الطلب.', 'warning')
        return redirect(url_for('requests.leaves_list'))
        
    # Check permissions
    if pending_step['approver_role'] == 'Manager' and pending_step['approver_id'] != current_user.id:
        flash('غير مصرح لك بالموافقة على هذا الطلب.', 'danger')
        return redirect(url_for('requests.leaves_list'))
    if pending_step['approver_role'] == 'HR' and current_user.role != 'HR':
        flash('هذه الخطوة تقتصر على موافقة الاتش ار (HR).', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elapsed_sec = calculate_elapsed_time(pending_step['assigned_at'])
    
    # Update pending step to approved
    db.execute('''
        UPDATE leave_request_approvals
        SET status = 'approved', action_at = ?, response_time_seconds = ?, comments = ?, approver_id = ?
        WHERE id = ?
    ''', (now_str, elapsed_sec, comments, current_user.id, pending_step['id']))
    
    # Check for next step in approval sequence
    next_step = db.execute('''
        SELECT * FROM leave_request_approvals
        WHERE leave_request_id = ? AND status = 'waiting'
        ORDER BY approval_order ASC LIMIT 1
    ''', (request_id,)).fetchone()
    
    if next_step:
        # Activate next manager step
        db.execute('''
            UPDATE leave_request_approvals
            SET status = 'pending', assigned_at = ?
            WHERE id = ?
        ''', (now_str, next_step['id']))
    else:
        # Check if HR step exists or needs to be added/activated
        hr_step = db.execute('''
            SELECT * FROM leave_request_approvals
            WHERE leave_request_id = ? AND approver_role = 'HR'
        ''', (request_id,)).fetchone()
        
        if pending_step['approver_role'] == 'HR':
            # Final approval by HR!
            db.execute('''
                UPDATE leave_requests
                SET status = 'approved', updated_at = ?
                WHERE id = ?
            ''', (now_str, request_id))
            flash('تم الاعتماد النهائي لطلب الإجازة بنجاح.', 'success')
            db.commit()
            return redirect(url_for('requests.leaves_list'))
        elif hr_step:
            # Activate existing HR step
            db.execute('''
                UPDATE leave_request_approvals
                SET status = 'pending', assigned_at = ?
                WHERE id = ?
            ''', (now_str, hr_step['id']))
            db.execute('UPDATE leave_requests SET status = "pending_hr", updated_at = ? WHERE id = ?', (now_str, request_id))
        else:
            # Create HR step and activate it
            max_order = pending_step['approval_order'] + 1
            db.execute('''
                INSERT INTO leave_request_approvals (leave_request_id, approver_id, approver_role, approval_order, status, assigned_at)
                VALUES (?, NULL, 'HR', ?, 'pending', ?)
            ''', (request_id, max_order, now_str))
            db.execute('UPDATE leave_requests SET status = "pending_hr", updated_at = ? WHERE id = ?', (now_str, request_id))
            
    db.commit()
    flash('تم تسجيل موافقتك بنجاح وتحويل الطلب للمرحلة التالية.', 'success')
    return redirect(url_for('requests.leaves_list'))


@bp.route('/leaves/<int:request_id>/reject', methods=['POST'])
@login_required
def leaves_reject(request_id):
    comments = request.form.get('comments', 'تم الرفض').strip()
    db = get_db()
    
    leave_req = db.execute('SELECT * FROM leave_requests WHERE id = ?', (request_id,)).fetchone()
    if not leave_req:
        flash('طلب الإجازة غير موجود.', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    pending_step = db.execute('''
        SELECT * FROM leave_request_approvals 
        WHERE leave_request_id = ? AND status = 'pending'
        ORDER BY approval_order ASC LIMIT 1
    ''', (request_id,)).fetchone()
    
    if not pending_step:
        flash('لا توجد خطوة موافقة معلقة لهذا الطلب.', 'warning')
        return redirect(url_for('requests.leaves_list'))
        
    if pending_step['approver_role'] == 'Manager' and pending_step['approver_id'] != current_user.id:
        flash('غير مصرح لك برفض هذا الطلب.', 'danger')
        return redirect(url_for('requests.leaves_list'))
    if pending_step['approver_role'] == 'HR' and current_user.role != 'HR':
        flash('هذه الخطوة تقتصر على الاتش ار (HR).', 'danger')
        return redirect(url_for('requests.leaves_list'))
        
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elapsed_sec = calculate_elapsed_time(pending_step['assigned_at'])
    
    db.execute('''
        UPDATE leave_request_approvals
        SET status = 'rejected', action_at = ?, response_time_seconds = ?, comments = ?, approver_id = ?
        WHERE id = ?
    ''', (now_str, elapsed_sec, comments, current_user.id, pending_step['id']))
    
    db.execute('''
        UPDATE leave_requests
        SET status = 'rejected', rejection_reason = ?, updated_at = ?
        WHERE id = ?
    ''', (comments, now_str, request_id))
    
    db.commit()
    flash('تم رفض طلب الإجازة وتسجيل السبب.', 'info')
    return redirect(url_for('requests.leaves_list'))
