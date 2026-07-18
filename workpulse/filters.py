from datetime import datetime
from flask import session

TRANSLATIONS = {
    'en': {
        'dashboard': 'Dashboard',
        'manage_projects': 'Manage Projects',
        'hr_reports': 'HR Reports',
        'change_password': 'Change Password',
        'logout': 'Logout',
        'welcome': 'Welcome',
        'projects': 'Projects',
        'employees': 'Employees',
        'tasks': 'Tasks',
        'add_project': 'Add New Project',
        'project_name': 'Project Name',
        'client': 'Client',
        'start_date': 'Start Date',
        'end_date': 'End Date',
        'actions': 'Actions',
        'edit': 'Edit',
        'delete': 'Delete',
        'allocated_hours': 'Allocated Hours',
        'worked_hours': 'Worked Hours',
        'remaining_hours': 'Remaining Hours',
        'budget_status': 'Budget Status',
        'over_budget': 'Over Budget',
        'near_limit': 'Near Limit',
        'within_limit': 'Within Limit',
        'unlimited': 'Unlimited',
        'status': 'Status',
        'category': 'Category',
        'add_task': 'Add Task',
        'task_title': 'Task Title',
        'description': 'Description',
        'approval_status': 'Approval Status',
        'submit_approval': 'Submit for Approval',
        'pending_approvals': 'Pending Approvals',
        'approve': 'Approve',
        'reject': 'Reject',
        'comments': 'Comments',
        'rejection_comments': 'Rejection Comments',
        'language': 'Language',
        'save': 'Save',
        'cancel': 'Cancel',
        'top_employees': 'Top Employees (Worked Hours)',
        'project_time_distribution': 'Project Time Distribution',
        'weekly_activity': 'Weekly Activity (Hours)',
        'print_report': 'Print PDF Report',
        'filter': 'Filter',
        'all': 'All',
        'assign_employees': 'Assign Employees',
        'select_all': 'Select All',
        'subordinates': 'Subordinates',
        'subordinate_tasks': 'Subordinate Tasks',
        'add_subordinate_task': 'Assign Task to Subordinate',
        'assigned_to': 'Assigned To',
        'view_details': 'View Details',
        'client_name': 'Client Name',
        'duration': 'Duration',
        'date': 'Date',
        'unlimited_hours': 'Unlimited hours',
        'hrs_remaining': 'hrs remaining',
        'project_details': 'Project Details',
        'employee_details': 'Employee Details',
        'allocated': 'Allocated',
        'worked': 'Worked',
        'remaining': 'Remaining',
        'add_employee': 'Add Employee',
        'full_name': 'Full Name',
        'username': 'Username',
        'position': 'Position',
        'role': 'Role',
        'manager': 'Manager',
        'assign_managers': 'Assign Managers',
        'existing_employees': 'Existing Employees',
        'existing_projects': 'Existing Projects',
        'no_projects_found': 'No projects found in the system.',
        'no_employees_found': 'No employees found in the system.',
        'add_new_task': 'Add New Task',
        'select_project': 'Select Project',
        'select_category': 'Select Category',
        'select_employee': 'Select Employee',
        'subordinate': 'Subordinate',
        'no_tasks_found': 'No tasks found.',
        'date_range': 'Date Range',
        'from': 'From',
        'to': 'To',
        'export_excel': 'Export Excel',
        'status_order': 'Status Order',
        'search': 'Search',
        'submit': 'Submit',
        'timesheet': 'Timesheet',
        'submit_timesheet_desc': 'Submit all finished tasks for approval',
        'submit_finished_tasks': 'Submit Finished Tasks',
        'my_tasks': 'My Tasks',
        'assigned_tasks': 'Assigned Tasks',
        'running': 'Running',
        'pause': 'Paused',
        'finish': 'Finished',
        'not_start': 'Not Started',
        'timesheet_status': 'Timesheet Status',
        'no_pending_approvals': 'No pending approvals.',
        'comments_optional': 'Comments (Optional)'
    },
    'ar': {
        'dashboard': 'لوحة التحكم',
        'manage_projects': 'إدارة المشاريع',
        'hr_reports': 'تقارير الموارد البشرية',
        'change_password': 'تغيير كلمة المرور',
        'logout': 'تسجيل الخروج',
        'welcome': 'مرحباً',
        'projects': 'المشاريع',
        'employees': 'الموظفين',
        'tasks': 'المهام',
        'add_project': 'إضافة مشروع جديد',
        'project_name': 'اسم المشروع',
        'client': 'العميل',
        'start_date': 'تاريخ البدء',
        'end_date': 'تاريخ الانتهاء',
        'actions': 'الإجراءات',
        'edit': 'تعديل',
        'delete': 'حذف',
        'allocated_hours': 'الساعات المخصصة',
        'worked_hours': 'الساعات الفعلية',
        'remaining_hours': 'الساعات المتبقية',
        'budget_status': 'حالة الميزانية',
        'over_budget': 'تجاوز الميزانية',
        'near_limit': 'قريب من الحد',
        'within_limit': 'ضمن الحد',
        'unlimited': 'غير محدود',
        'status': 'الحالة',
        'category': 'الفئة',
        'add_task': 'إضافة مهمة',
        'task_title': 'عنوان المهمة',
        'description': 'الوصف',
        'approval_status': 'حالة الموافقة',
        'submit_approval': 'تقديم للموافقة',
        'pending_approvals': 'موافقات معلقة',
        'approve': 'موافقة',
        'reject': 'رفض',
        'comments': 'الملاحظات',
        'rejection_comments': 'ملاحظات الرفض',
        'language': 'اللغة',
        'save': 'حفظ',
        'cancel': 'إلغاء',
        'top_employees': 'الموظفون الأكثر عملاً (بالساعات)',
        'project_time_distribution': 'توزيع الوقت على المشاريع',
        'weekly_activity': 'النشاط الأسبوعي (بالساعات)',
        'print_report': 'طباعة تقرير PDF',
        'filter': 'تصفية',
        'all': 'الكل',
        'assign_employees': 'تعيين الموظفين',
        'select_all': 'تحديد الكل',
        'subordinates': 'المرؤوسين',
        'subordinate_tasks': 'مهام المرؤوسين',
        'add_subordinate_task': 'إسناد مهمة لمرؤوس',
        'assigned_to': 'مُسند إلى',
        'view_details': 'عرض التفاصيل',
        'client_name': 'اسم العميل',
        'duration': 'المدة',
        'date': 'التاريخ',
        'unlimited_hours': 'ساعات غير محدودة',
        'hrs_remaining': 'ساعة متبقية',
        'project_details': 'تفاصيل المشروع',
        'employee_details': 'تفاصيل الموظف',
        'allocated': 'المخصص',
        'worked': 'الفعلي',
        'remaining': 'المتبقي',
        'add_employee': 'إضافة موظف',
        'full_name': 'الاسم الكامل',
        'username': 'اسم المستخدم',
        'position': 'المسمى الوظيفي',
        'role': 'الدور',
        'manager': 'المدير',
        'assign_managers': 'تعيين المدراء',
        'existing_employees': 'الموظفون الحاليون',
        'existing_projects': 'المشاريع الحالية',
        'no_projects_found': 'لا توجد مشاريع في النظام.',
        'no_employees_found': 'لا يوجد موظفون في النظام.',
        'add_new_task': 'إضافة مهمة جديدة',
        'select_project': 'اختر المشروع',
        'select_category': 'اختر الفئة',
        'select_employee': 'اختر الموظف',
        'subordinate': 'المرؤوس',
        'no_tasks_found': 'لا توجد مهام.',
        'date_range': 'النطاق الزمني',
        'from': 'من',
        'to': 'إلى',
        'export_excel': 'تصدير إكسل',
        'status_order': 'ترتيب الحالات',
        'search': 'بحث',
        'submit': 'إرسال',
        'timesheet': 'جدول الساعات',
        'submit_timesheet_desc': 'إرسال جميع المهام المنتهية للاعتماد',
        'submit_finished_tasks': 'إرسال المهام المنتهية',
        'my_tasks': 'مهامي',
        'assigned_tasks': 'المهام المسندة',
        'running': 'قيد التشغيل',
        'pause': 'متوقفة مؤقتاً',
        'finish': 'منتهية',
        'not_start': 'لم تبدأ بعد',
        'timesheet_status': 'حالة الاعتماد',
        'no_pending_approvals': 'لا توجد موافقات معلقة.',
        'comments_optional': 'ملاحظات (اختياري)'
    }
}

def translate(key):
    lang = session.get('lang', 'ar')
    return TRANSLATIONS.get(lang, {}).get(key, key)

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

def format_balance(remaining, allocated):
    if allocated == 0 or allocated is None:
        return ""
    if remaining % 1 == 0:
        rem_str = f"{int(remaining)}"
    else:
        rem_str = f"{remaining:.2f}"
    if allocated % 1 == 0:
        alloc_str = f"{int(allocated)}"
    else:
        alloc_str = f"{allocated:.2f}"
    return f"{rem_str}/{alloc_str}"
