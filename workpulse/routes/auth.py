from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from workpulse.database import save_user_preferences
from workpulse.extensions import login_manager
from workpulse.models import User


def register_auth_routes(app):
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.is_hr:
                return redirect(url_for('hr_dashboard'))
            elif current_user.is_employee:
                return redirect(url_for('employee_dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            user = User.authenticate(username, password)
            if user:
                login_user(user)
                flash('Logged in successfully.', 'success')
                return redirect(url_for('index'))
            flash('Invalid credentials.', 'danger')
        return render_template('auth/login.html')

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
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return render_template('auth/change_password.html')

            # Verify current password using authentication method
            user = User.authenticate(current_user.username, current_password)
            if user:
                User.update_password(current_user.id, new_password)
                flash('Password changed successfully.', 'success')
                return redirect(url_for('index'))

            flash('Invalid credentials.', 'danger')
        return render_template('auth/change_password.html')

    @app.route('/set_language/<lang>')
    def set_language(lang):
        if lang in ('ar', 'en'):
            session['lang'] = lang
            if current_user and current_user.is_authenticated:
                save_user_preferences(current_user.id, lang=lang)
        return redirect(request.referrer or url_for('index'))

