from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_user, login_required, logout_user, current_user
from workpulse.extensions import bcrypt, login_manager
from workpulse.models import User
from workpulse.database import get_db, save_user_preferences

def register_auth_routes(app):
    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

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
            db = get_db()
            row = db.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()
            if row and bcrypt.check_password_hash(row['password_hash'], password):
                user = User(row['id'], row['username'], row['role'], row['full_name'])
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
            current_password = request.form['current_password']
            new_password = request.form['new_password']
            confirm_password = request.form['confirm_password']
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return render_template('auth/change_password.html')
                
            db = get_db()
            row = db.execute('SELECT * FROM users WHERE id = ?', (current_user.id,)).fetchone()
            
            if row and bcrypt.check_password_hash(row['password_hash'], current_password):
                new_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
                db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, current_user.id))
                db.commit()
                flash('Password changed successfully.', 'success')
                return redirect(url_for('index'))
            flash('Invalid credentials.', 'danger')
        return render_template('auth/change_password.html')

    @app.route('/set_language/<lang>')
    def set_language(lang):
        if lang in ['ar', 'en']:
            session['lang'] = lang
            if current_user and current_user.is_authenticated:
                save_user_preferences(current_user.id, lang=lang)
        return redirect(request.referrer or url_for('index'))
