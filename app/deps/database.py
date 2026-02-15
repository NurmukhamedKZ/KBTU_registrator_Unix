import os

from db_models import DatabaseManager


db_manager = None


def get_db():
    global db_manager
    if db_manager is None:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            db_manager = DatabaseManager(database_url)
    return db_manager
