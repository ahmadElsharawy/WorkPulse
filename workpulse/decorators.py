from functools import wraps
from flask import flash, redirect, url_for
from flask_login import login_required, current_user

def role_required(*roles):
    def decorator(f):
        @login_required
        @wraps(f)
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                flash('Access denied for your role.', 'danger')
                return redirect(url_for('auth.login'))
            return f(*args, **kwargs)
        return wrapped
    return decorator
