import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def _get_database_url() -> str:
    url = os.getenv("SUPABASE_DB_URL")

    if not url:
        raise RuntimeError("SUPABASE_DB_URL is missing from .env")

    return url


@contextmanager
def get_connection():
    conn = psycopg2.connect(_get_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_dict_cursor():
    conn = psycopg2.connect(_get_database_url())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()