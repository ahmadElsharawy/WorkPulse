import os

from flask import Flask, request, session
from flask_login import current_user

from .config import Config
from .database import close_db, get_pending_approvals_count, get_user_preferences
from .extensions import bcrypt, login_manager
from .filters import datetimeformat, format_balance, format_duration, total_seconds, translate
from .routes.auth import register_auth_routes
from .routes.employee import register_employee_routes
from .routes.hr import register_hr_routes
from .routes.reports import register_reports_routes
from .routes.requests import bp as requests_bp


def create_app():
    """Application factory for WorkPulse Flask web application."""
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), '..', 'static'),
    )

    app.config.from_object(Config)
    app.config['DATABASE'] = os.path.join(app.instance_path, 'database.db')

    os.makedirs(app.instance_path, exist_ok=True)

    # Initialize extensions
    login_manager.login_view = 'login'
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # Register Jinja template filters
    app.template_filter('datetimeformat')(datetimeformat)
    app.template_filter('format_duration')(format_duration)
    app.template_filter('total_seconds')(total_seconds)
    app.template_filter('format_balance')(format_balance)

    # Global context processor
    @app.context_processor
    def utility_processor():
        pending_count = get_pending_approvals_count(current_user)
        return dict(
            _=translate,
            current_lang=session.get('lang', 'ar'),
            pending_count=pending_count,
        )

    # Before request user preference sync
    @app.before_request
    def load_user_preferences_to_session():
        if request.endpoint == 'static':
            return
        if current_user and current_user.is_authenticated:
            pref = get_user_preferences(current_user.id)
            if session.get('lang') != pref['lang']:
                session['lang'] = pref['lang']

    # Teardown DB connection
    app.teardown_appcontext(close_db)

    # Register route modules
    register_auth_routes(app)
    register_hr_routes(app)
    register_employee_routes(app)
    register_reports_routes(app)
    app.register_blueprint(requests_bp)

    return app

