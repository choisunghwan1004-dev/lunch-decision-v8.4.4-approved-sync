# DB 연결 담당: 프로젝트 루트 설정을 읽고 MySQL 연결과 트랜잭션을 제공합니다.
# with db.transaction() 블록은 성공하면 commit, 예외가 발생하면 rollback합니다.
# 운영 코드는 MySQL만 사용하며 SQLite는 tests/news의 테스트 대역에만 있습니다.

"""Production uses MySQL only; each operation commits or rolls back as one unit."""
import os
import re
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env')


# DB 이름부터 검증하고 연결합니다. 기존 원본 DB와 같으면 접속 전에 중단합니다.
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


# SQL 실행용 얇은 도구입니다. one은 한 행, all은 목록, insert는 새 PK를 돌려줍니다.
class Tx:
    def __init__(self, cursor):
        self.cursor = cursor

    # SQL문과 값을 별도 인자로 전달합니다. 사용자 값을 SQL 문자열에 직접 붙이지 않습니다.
    def execute(self, sql, args=()):
        self.cursor.execute(sql, args)
        return self.cursor.rowcount

    # SELECT 결과 한 행을 사전 형태로 읽습니다. 없으면 None이 됩니다.
    def one(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.fetchone()

    # SELECT 결과 전체를 사전 목록으로 읽습니다.
    def all(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.fetchall()

    # INSERT 뒤 AUTO_INCREMENT로 만들어진 id를 반환합니다.
    def insert(self, sql, args=()):
        self.execute(sql, args)
        return self.cursor.lastrowid


class Database:
    # 성공·실패와 관계없이 커서와 연결을 닫아 자원이 남지 않게 합니다.
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
