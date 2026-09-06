import psycopg
from psycopg.rows import dict_row
from config.config import Config

def get_db_connection():
    if not Config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured. Copy .env.example to .env and set it.")
    return psycopg.connect(Config.DATABASE_URL, row_factory=dict_row)
