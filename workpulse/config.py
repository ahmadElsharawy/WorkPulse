import os

class Config:
    """Application configuration parameters."""

    SECRET_KEY = os.environ.get('SECRET_KEY', 'workpulse-default-dev-secret-key-change-in-prod')
    JSON_SORT_KEYS = False

