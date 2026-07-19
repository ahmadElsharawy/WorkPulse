from datetime import datetime

def _default_eos_response(employee=None, daily_basic=0.0, daily_total=0.0):
    termination_date_str = employee['termination_date'] if employee and 'termination_date' in employee.keys() else None
    return {
        'has_hire_date': False,
        'tenure_years': 0.0,
        'tenure_text': 'غير محدد',
        'gratuity_amount': 0.0,
        'gratuity_net_days': 0.0,
        'gratuity_tier1_days': 0.0,
        'gratuity_tier1_amount': 0.0,
        'gratuity_tier2_days': 0.0,
        'gratuity_tier2_amount': 0.0,
        'accrued_leave_days': 0.0,
        'used_leave_days': 0.0,
        'remaining_leave_days': 0.0,
        'daily_basic': round(daily_basic, 2),
        'daily_total': round(daily_total, 2),
        'leave_encashment_amount': 0.0,
        'leave_encashment_basic_amount': 0.0,
        'sick_leave_days': 0.0,
        'parental_leave_days': 0.0,
        'bereavement_leave_days': 0.0,
        'study_leave_days': 0.0,
        'hajj_leave_days': 0.0,
        'other_leave_days': 0.0,
        'unpaid_leave_days': 0.0,
        'active_days': 0,
        'additional_additions': 0.0,
        'additional_deductions': 0.0,
        'net_settlement_amount': 0.0,
        'net_settlement_basic_amount': 0.0,
        'adjustment_notes': '',
        'updated_by': '',
        'updated_at': '',
        'leaves_history': [],
        'financial_items': [],
        'gratuity_day_items': [],
        'yearly_leave_ledger': [],
        'accrual_text': 'غير محدد',
        'accrual_text_en': 'Not set',
        'is_active': not bool(termination_date_str)
    }

def calculate_uae_gratuity_and_leaves(employee, db):
    """
    Calculates End of Service Gratuity (EOSG), Annual & Custom UAE Leave Types, HR Adjustments and Net Settlement.
    """
    if not employee:
        return _default_eos_response()

    basic_salary = float(employee['basic_salary'] or 0.0) if 'basic_salary' in employee.keys() else 0.0
    total_salary = float(employee['total_salary'] or 0.0) if 'total_salary' in employee.keys() else 0.0
    hire_date_str = employee['hire_date'] if 'hire_date' in employee.keys() else None
    termination_date_str = employee['termination_date'] if 'termination_date' in employee.keys() else None
    
    daily_basic = basic_salary / 30.0 if basic_salary > 0 else 0.0
    daily_total = total_salary / 30.0 if total_salary > 0 else daily_basic
    
    if not hire_date_str:
        return _default_eos_response(employee, daily_basic, daily_total)
        
    try:
        hire_date = datetime.strptime(str(hire_date_str).strip(), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return _default_eos_response(employee, daily_basic, daily_total)

    if termination_date_str and str(termination_date_str).strip():
        try:
            end_date = datetime.strptime(str(termination_date_str).strip(), '%Y-%m-%d').date()
            is_active = False
        except (ValueError, TypeError):
            end_date = datetime.now().date()
            is_active = True
    else:
        end_date = datetime.now().date()
        is_active = True

    if end_date < hire_date:
        end_date = hire_date

    # Calculate total approved unpaid leave days to exclude from active service duration (UAE Labor Law)
    unpaid_leave_row = db.execute('''
        SELECT COALESCE(SUM(duration_days), 0) AS total_unpaid
        FROM leave_requests
        WHERE employee_id = ? AND status = 'approved' AND (leave_type = 'unpaid' OR leave_type LIKE '%بدون%')
    ''', (employee['id'],)).fetchone()
    unpaid_leave_days = float(unpaid_leave_row['total_unpaid']) if unpaid_leave_row else 0.0

    raw_total_days = (end_date - hire_date).days
    total_days = max(0, raw_total_days - int(unpaid_leave_days))
    years_float = total_days / 365.25
    
    years_part = int(total_days // 365.25)
    remaining_days_after_years = int(total_days % 365.25)
    months_part = int(remaining_days_after_years // 30.4375)
    days_part = int(remaining_days_after_years % 30.4375)

    if years_part > 0:
        tenure_text = f"{years_part} سنة و {months_part} شهر و {days_part} يوم"
        tenure_text_en = f"{years_part} yrs, {months_part} mos, {days_part} days"
    elif months_part > 0:
        tenure_text = f"{months_part} شهر و {days_part} يوم"
        tenure_text_en = f"{months_part} mos, {days_part} days"
    else:
        tenure_text = f"{days_part} يوم"
        tenure_text_en = f"{days_part} days"
    if unpaid_leave_days > 0:
        tenure_text += f" (مستبعد منها {int(unpaid_leave_days)} يوم إجازة بدون أجر)"
        tenure_text_en += f" ({int(unpaid_leave_days)} unpaid leave days excluded)"

    # 1. Gratuity Calculation (UAE Article 51)
    if years_float < 1.0:
        gratuity_tier1_days = 0.0
        gratuity_tier1_amount = 0.0
        gratuity_tier2_days = 0.0
        gratuity_tier2_amount = 0.0
        gratuity_total_days = 0.0
        gratuity_amount = 0.0
    elif years_float <= 5.0:
        gratuity_tier1_days = years_float * 21.0
        gratuity_tier1_amount = gratuity_tier1_days * daily_basic
        gratuity_tier2_days = 0.0
        gratuity_tier2_amount = 0.0
        gratuity_total_days = gratuity_tier1_days
        gratuity_amount = gratuity_tier1_amount
    else:
        gratuity_tier1_days = 5.0 * 21.0  # 105 days
        gratuity_tier1_amount = gratuity_tier1_days * daily_basic
        gratuity_tier2_days = (years_float - 5.0) * 30.0
        gratuity_tier2_amount = gratuity_tier2_days * daily_basic
        gratuity_total_days = gratuity_tier1_days + gratuity_tier2_days
        gratuity_amount = gratuity_tier1_amount + gratuity_tier2_amount
        
    # Cap at 2 years' total salary
    max_cap = (total_salary * 24.0) if total_salary > 0 else float('inf')
    if gratuity_amount > max_cap:
        gratuity_amount = max_cap
        
    # 2. Leave Accrual Calculation (UAE Article 29: Max 15 days carried forward ONLY from the immediately preceding year)
    if years_float < 1.0:
        months_worked = (total_days / 30.4375)
        accrued_leave_days = months_worked * 2.0
    else:
        completed_years = int(years_float)
        current_year_fraction = years_float - float(completed_years)
        
        # UAE Article 29 Carry-Forward Limit: max 15 days carried forward from the single immediately preceding year
        carried_forward_days = 15.0
        current_year_accrual = current_year_fraction * 30.0
        
        accrued_leave_days = carried_forward_days + current_year_accrual

    # Fetch all approved leave requests with start_date & end_date for this employee
    leave_rows = db.execute('''
        SELECT id, leave_type, start_date, end_date, duration_days, reason, status, created_at
        FROM leave_requests
        WHERE employee_id = ? AND status = 'approved'
        ORDER BY start_date DESC
    ''', (employee['id'],)).fetchall()

    # Determine the active carry-forward cycle start date for annual leave deduction
    if years_float >= 1.0:
        prev_year = end_date.year - 1
        try:
            cycle_start_date = datetime(prev_year, 1, 1).date()
        except ValueError:
            cycle_start_date = hire_date
        if hire_date > cycle_start_date:
            cycle_start_date = hire_date
    else:
        cycle_start_date = hire_date

    leave_counts = {
        'annual': 0.0,
        'sick': 0.0,
        'parental': 0.0,
        'bereavement': 0.0,
        'marriage': 0.0,
        'unpaid': 0.0,
        'other': 0.0
    }

    leaves_history = []
    for r in leave_rows:
        raw_type = str(r['leave_type'] or 'annual').strip()
        l_type = raw_type.lower()
        dur = float(r['duration_days'] or 0.0)

        # Parse start_date of this leave
        l_start = None
        if r['start_date'] and str(r['start_date']).strip():
            try:
                l_start = datetime.strptime(str(r['start_date']).strip(), '%Y-%m-%d').date()
            except (ValueError, TypeError):
                l_start = None

        is_in_current_cycle = True
        if l_start and l_start < cycle_start_date:
            is_in_current_cycle = False

        if l_type == 'annual' or 'سنو' in l_type or 'annual' in l_type or 'بدل' in l_type or 'encash' in l_type:
            if is_in_current_cycle:
                leave_counts['annual'] += dur
        elif l_type == 'unpaid' or 'بدون' in l_type or 'unpaid' in l_type:
            leave_counts['unpaid'] += dur
        elif 'مرض' in l_type or 'sick' in l_type:
            leave_counts['sick'] += dur
        elif 'والد' in l_type or 'أبو' in l_type or 'وضع' in l_type or 'parent' in l_type or 'matern' in l_type:
            leave_counts['parental'] += dur
        elif 'حداد' in l_type or 'وفا' in l_type or 'bereav' in l_type:
            leave_counts['bereavement'] += dur
        else:
            leave_counts['other'] += dur

        leaves_history.append({
            'id': r['id'],
            'leave_type': raw_type,
            'start_date': r['start_date'],
            'end_date': r['end_date'],
            'duration_days': dur,
            'reason': r['reason'] or '',
            'is_in_current_cycle': is_in_current_cycle
        })

    # Build Year-by-Year Leave Audit & Carry-Forward Ledger (من أول يوم تعيين وحتى اليوم)
    import datetime as dt_mod
    yearly_leave_ledger = []
    current_start = hire_date
    prev_carried_out = 0.0
    year_index = 1

    while current_start < end_date:
        try:
            next_start = datetime(current_start.year + 1, current_start.month, current_start.day).date()
        except ValueError:
            next_start = current_start.replace(year=current_start.year + 1, day=28)

        if next_start <= end_date:
            current_end = next_start - dt_mod.timedelta(days=1)
            is_last_year = (next_start == end_date)
            is_full_year = True
        else:
            current_end = end_date
            is_last_year = True
            is_full_year = False

        # Calculate overlap of unpaid leaves within [current_start, current_end]
        unpaid_in_segment = 0.0
        for r in leave_rows:
            raw_type = str(r['leave_type'] or 'annual').strip().lower()
            if raw_type == 'unpaid' or 'بدون' in raw_type or 'unpaid' in raw_type:
                if r['start_date'] and r['end_date']:
                    try:
                        l_start = datetime.strptime(str(r['start_date']).strip(), '%Y-%m-%d').date()
                        l_end = datetime.strptime(str(r['end_date']).strip(), '%Y-%m-%d').date()
                        overlap_start = max(current_start, l_start)
                        overlap_end = min(current_end, l_end)
                        if overlap_start <= overlap_end:
                            unpaid_in_segment += float((overlap_end - overlap_start).days + 1)
                    except (ValueError, TypeError):
                        pass

        segment_days = (current_end - current_start).days + 1
        active_days_in_segment = max(0.0, float(segment_days) - float(unpaid_in_segment))

        if is_full_year and unpaid_in_segment == 0.0:
            year_accrued = 30.0
        else:
            if year_index == 1 and not (years_float >= 1.0):
                year_accrued = (active_days_in_segment / 30.4375) * 2.0
            else:
                year_accrued = (active_days_in_segment / 365.25) * 30.0

        carried_in = prev_carried_out if year_index > 1 else 0.0
        total_avail = year_accrued + carried_in

        used_in_this_year = 0.0
        for r in leave_rows:
            raw_type = str(r['leave_type'] or 'annual').strip().lower()
            if raw_type == 'annual' or 'سنو' in raw_type or 'annual' in raw_type or 'بدل' in raw_type or 'encash' in raw_type:
                if r['start_date'] and str(r['start_date']).strip():
                    try:
                        l_start = datetime.strptime(str(r['start_date']).strip(), '%Y-%m-%d').date()
                        if current_start <= l_start <= current_end:
                            used_in_this_year += float(r['duration_days'] or 0.0)
                    except (ValueError, TypeError):
                        pass

        unused_year_end = total_avail - used_in_this_year

        if not is_last_year:
            if unused_year_end >= 0:
                carried_out = min(15.0, unused_year_end)
            else:
                carried_out = unused_year_end
        else:
            carried_out = unused_year_end

        prev_carried_out = carried_out

        yearly_leave_ledger.append({
            'year_number': year_index,
            'label': f"السنة {year_index}" + (" (الحالية)" if is_last_year else ""),
            'start_date': current_start.strftime('%Y-%m-%d'),
            'end_date': current_end.strftime('%Y-%m-%d'),
            'accrued_days': round(year_accrued, 1),
            'carried_in_days': round(carried_in, 1),
            'total_available_days': round(total_avail, 1),
            'used_days': round(used_in_this_year, 1),
            'unused_year_end_days': round(unused_year_end, 1),
            'carried_out_days': round(carried_out, 1),
            'is_current_year': is_last_year,
            'segment_days': segment_days,
            'active_days': round(active_days_in_segment, 1),
            'unpaid_leave_days': round(unpaid_in_segment, 1)
        })

        if is_last_year:
            break

        current_start = next_start
        year_index += 1

    if yearly_leave_ledger:
        last_year = yearly_leave_ledger[-1]
        accrued_leave_days = last_year['total_available_days']
        used_annual_leave_days = last_year['used_days']
        remaining_leave_days = last_year['unused_year_end_days']
    else:
        used_annual_leave_days = leave_counts['annual']
        remaining_leave_days = accrued_leave_days - used_annual_leave_days
    
    leave_encashment_basic_amount = remaining_leave_days * daily_basic
    leave_encashment_amount = remaining_leave_days * daily_total

    # Fetch HR Adjustments & Custom UAE Leaves
    adj_row = db.execute('''
        SELECT * FROM eos_settlement_adjustments WHERE employee_id = ?
    ''', (employee['id'],)).fetchone()
    gratuity_days_deduction = 0.0
    gratuity_days_deduction_reason = ''
    if adj_row and 'gratuity_days_deduction' in adj_row.keys():
        gratuity_days_deduction = float(adj_row['gratuity_days_deduction'] or 0.0)
        gratuity_days_deduction_reason = str(adj_row['gratuity_days_deduction_reason'] or '')

    # Fetch Itemized Gratuity Day Adjustments with Reasons
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

    day_item_rows = db.execute('''
        SELECT id, item_type, days_count, reason, created_by, created_at
        FROM eos_gratuity_day_items
        WHERE employee_id = ?
        ORDER BY id DESC
    ''', (employee['id'],)).fetchall()

    gratuity_day_items = []
    itemized_gratuity_day_deductions = 0.0
    itemized_gratuity_day_additions = 0.0

    for item in day_item_rows:
        cnt = float(item['days_count'] or 0.0)
        i_type = str(item['item_type'] or 'deduction').strip()
        if i_type == 'deduction':
            itemized_gratuity_day_deductions += cnt
        else:
            itemized_gratuity_day_additions += cnt

        gratuity_day_items.append({
            'id': item['id'],
            'item_type': i_type,
            'days_count': cnt,
            'reason': item['reason'],
            'created_by': item['created_by'],
            'created_at': item['created_at']
        })

    # Apply HR Gratuity Days Deductions & Additions
    total_gratuity_day_deductions = gratuity_days_deduction + itemized_gratuity_day_deductions
    gratuity_net_days = max(0.0, gratuity_total_days + itemized_gratuity_day_additions - total_gratuity_day_deductions)
    gratuity_amount = gratuity_net_days * daily_basic

    # Cap at 2 years' total salary
    max_cap = (total_salary * 24.0) if total_salary > 0 else float('inf')
    if gratuity_amount > max_cap:
        gratuity_amount = max_cap

    sick_leave_days = leave_counts.get('sick', 0.0) + (float(adj_row['sick_leave_days']) if adj_row and adj_row['sick_leave_days'] else 0.0)
    parental_leave_days = leave_counts.get('parental', 0.0) + (float(adj_row['parental_leave_days']) if adj_row and adj_row['parental_leave_days'] else 0.0)
    bereavement_leave_days = leave_counts.get('bereavement', 0.0) + (float(adj_row['bereavement_leave_days']) if adj_row and adj_row['bereavement_leave_days'] else 0.0)
    study_leave_days = 0.0
    hajj_leave_days = 0.0
    other_leave_days = leave_counts.get('other', 0.0) + (float(adj_row['other_leave_days']) if adj_row and adj_row['other_leave_days'] else 0.0)

    additional_additions = float(adj_row['additional_additions']) if adj_row and adj_row['additional_additions'] else 0.0
    additional_deductions = float(adj_row['additional_deductions']) if adj_row and adj_row['additional_deductions'] else 0.0
    adjustment_notes = str(adj_row['notes']) if adj_row and adj_row['notes'] else ''
    updated_by = str(adj_row['updated_by']) if adj_row and adj_row['updated_by'] else ''
    updated_at = str(adj_row['updated_at']) if adj_row and adj_row['updated_at'] else ''

    # Fetch Itemized Financial Adjustments with Reasons
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
    db.commit()

    item_rows = db.execute('''
        SELECT id, item_type, amount, reason, created_by, created_at
        FROM eos_financial_items
        WHERE employee_id = ?
        ORDER BY id DESC
    ''', (employee['id'],)).fetchall()

    itemized_additions = 0.0
    itemized_deductions = 0.0
    financial_items = []

    for item in item_rows:
        i_type = str(item['item_type']).lower()
        amt = float(item['amount'] or 0.0)
        if i_type == 'addition':
            itemized_additions += amt
        else:
            itemized_deductions += amt

        financial_items.append({
            'id': item['id'],
            'item_type': item['item_type'],
            'amount': amt,
            'reason': item['reason'] or '',
            'created_by': item['created_by'] or '',
            'created_at': item['created_at'] or ''
        })

    additional_additions += itemized_additions
    additional_deductions += itemized_deductions

    # Total Net Financial Settlement Amount (on Full Wage)
    net_settlement_amount = gratuity_amount + leave_encashment_amount + additional_additions - additional_deductions
    # Total Net Financial Settlement Amount (on Basic Wage)
    net_settlement_basic_amount = gratuity_amount + leave_encashment_basic_amount + additional_additions - additional_deductions

    return {
        'has_hire_date': True,
        'tenure_years': round(years_float, 2),
        'tenure_days': total_days,
        'tenure_text': tenure_text,
        'tenure_text_en': tenure_text_en,
        'gratuity_amount': round(gratuity_amount, 2),
        'gratuity_tier1_days': round(gratuity_tier1_days, 1),
        'gratuity_tier1_amount': round(gratuity_tier1_amount, 2),
        'gratuity_tier2_days': round(gratuity_tier2_days, 1),
        'gratuity_tier2_amount': round(gratuity_tier2_amount, 2),
        'gratuity_total_days': round(gratuity_total_days, 1),
        'gratuity_days_deduction': round(gratuity_days_deduction, 1),
        'gratuity_days_deduction_reason': gratuity_days_deduction_reason,
        'itemized_gratuity_day_deductions': round(itemized_gratuity_day_deductions, 1),
        'itemized_gratuity_day_additions': round(itemized_gratuity_day_additions, 1),
        'gratuity_net_days': round(gratuity_net_days, 1),
        'unpaid_leave_days': round(unpaid_leave_days, 1),
        'gratuity_day_items': gratuity_day_items,
        'accrued_leave_days': round(accrued_leave_days, 1),
        'used_leave_days': round(used_annual_leave_days, 1),
        'remaining_leave_days': round(remaining_leave_days, 1),
        'daily_basic': round(daily_basic, 2),
        'daily_total': round(daily_total, 2),
        'leave_encashment_basic_amount': round(leave_encashment_basic_amount, 2),
        'leave_encashment_amount': round(leave_encashment_amount, 2),
        'sick_leave_days': round(sick_leave_days, 1),
        'parental_leave_days': round(parental_leave_days, 1),
        'bereavement_leave_days': round(bereavement_leave_days, 1),
        'study_leave_days': round(study_leave_days, 1),
        'hajj_leave_days': round(hajj_leave_days, 1),
        'other_leave_days': round(other_leave_days, 1),
        'additional_additions': round(additional_additions, 2),
        'additional_deductions': round(additional_deductions, 2),
        'net_settlement_amount': round(net_settlement_amount, 2),
        'net_settlement_basic_amount': round(net_settlement_basic_amount, 2),
        'adjustment_notes': adjustment_notes,
        'updated_by': updated_by,
        'updated_at': updated_at,
        'leaves_history': leaves_history,
        'financial_items': financial_items,
        'yearly_leave_ledger': yearly_leave_ledger,
        'accrual_text': '15 يوماً أقصاه (مُرَحّلة من السنة السابقة) + 2.5 يوم/شهر (السنة الحالية)',
        'accrual_text_en': 'Max 15 days (carried from prior yr) + 2.5 days/month (current yr)',
        'is_active': is_active
    }
