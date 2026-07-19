from flask_login import UserMixin
from .database import get_db
from .extensions import bcrypt

class User(UserMixin):
    """User domain model representing authenticated application users."""

    def __init__(self, id_, username, role, full_name=None, email=None, department=None, position=None):
        self.id = id_
        self.username = username
        self.role = role
        self.full_name = full_name
        self.email = email
        self.department = department
        self.position = position

    @classmethod
    def from_row(cls, row):
        """Factory method to construct User instance from sqlite3.Row."""
        if not row:
            return None
        return cls(
            id_=row['id'],
            username=row['username'],
            role=row['role'],
            full_name=row['full_name'] if 'full_name' in row.keys() else None,
            email=row['email'] if 'email' in row.keys() else None,
            department=row['department'] if 'department' in row.keys() else None,
            position=row['position'] if 'position' in row.keys() else None,
        )

    @staticmethod
    def get(user_id):
        """Fetch user by primary key ID."""
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return User.from_row(row)

    @staticmethod
    def find_by_username(username):
        """Fetch user by username (case-insensitive)."""
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()
        return User.from_row(row)

    @staticmethod
    def authenticate(username, password):
        """Verify user credentials and return User instance if valid."""
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()
        if row and bcrypt.check_password_hash(row['password_hash'], password):
            return User.from_row(row)
        return None

    @staticmethod
    def update_password(user_id, new_password):
        """Update password for user by ID."""
        db = get_db()
        new_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))
        db.commit()

    @property
    def is_hr(self):
        return self.role == 'HR'

    @property
    def is_employee(self):
        return self.role == 'Employee'

