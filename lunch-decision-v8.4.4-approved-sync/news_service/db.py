"""Production uses MySQL only; each operation commits or rolls back as one unit."""
import os
import re
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


def connect():
    import mysql.connector
    name = os.getenv('V83_DB_NAME', 'lunch_decision_v83')
    if not re.fullmatch(r'[A-Za-z0-9_]+', name) or name == os.getenv('OLD_DB_NAME', 'lunch_decision'):
        raise RuntimeError('V83_DB_NAME은 기존 OLD_DB_NAME과 다른 DB여야 합니다.')
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''),
        database=name, charset='utf8mb4', connection_timeout=8, autocommit=False,
    )


class Tx:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, args=()):
        self.cursor.execute(sql, args)
        return self.cursor.rowcount

    def one(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.fetchone()

    def all(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.fetchall()

    def insert(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.lastrowid


class Database:
    @contextmanager
    def transaction(self):
        conn = connect()
        cur = conn.cursor(dictionary=True)
        try:
            yield Tx(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
