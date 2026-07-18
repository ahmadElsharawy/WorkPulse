from flask_login import UserMixin
from .database import get_db

class User(UserMixin):
    def __init__(self, id_, username, role, full_name=None):
        self.id = id_
        self.username = username
        self.role = role
        self.full_name = full_name

    @staticmethod
    def get(user_id):
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['role'], row['full_name'])
        return None

    @staticmethod
    def find_by_username(username):
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?)', (username,)).fetchone()
        if row:
            return User(row['id'], row['username'], row['role'], row['full_name'])
        return None
