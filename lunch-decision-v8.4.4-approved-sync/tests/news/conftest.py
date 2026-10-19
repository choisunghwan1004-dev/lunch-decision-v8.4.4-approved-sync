"""Offline tests exercise real transactions in SQLite; production remains MySQL.
Set NEWS_TEST_MYSQL=1 to run the same API cases against a disposable MySQL DB.
"""
import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import sqlite3

import pytest
from fastapi.testclient import TestClient

from news_service.app import app, get_service
from news_service.db import Database, Tx
from news_service.service import NewsService
from news_service.validation import parse_draft

SQLITE_SCHEMA = '''
CREATE TABLE provinces(id INTEGER PRIMARY KEY,name TEXT);
CREATE TABLE districts(id INTEGER PRIMARY KEY,province_id INTEGER REFERENCES provinces(id),name TEXT);
CREATE TABLE news_topics(id INTEGER PRIMARY KEY AUTOINCREMENT,district_id INTEGER REFERENCES districts(id),title TEXT,category TEXT,language_code TEXT DEFAULT 'ko',keywords TEXT,status TEXT DEFAULT 'draft',is_demo INTEGER DEFAULT 0,created_by TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE news_sources(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER REFERENCES news_topics(id),source_kind TEXT,organization TEXT,source_url TEXT,source_url_sha256 BLOB,source_title TEXT,published_at TEXT,checked_at TEXT,source_excerpt TEXT,license_note TEXT,content_sha256 TEXT,is_demo INTEGER,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(topic_id,source_url_sha256));
CREATE TABLE news_facts(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER REFERENCES news_topics(id),fact_key TEXT,fact_type TEXT,value_text TEXT,value_number TEXT,unit TEXT,event_start TEXT,event_end TEXT,status TEXT DEFAULT 'candidate',verification_note TEXT,verified_by TEXT,verified_at TEXT,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,created_at TEXT DEFAULT CURRENT_TIMESTAMP,UNIQUE(topic_id,fact_key));
CREATE TABLE news_fact_evidence(fact_id INTEGER REFERENCES news_facts(id),source_id INTEGER REFERENCES news_sources(id),excerpt_reference TEXT,evidence_note TEXT,checked_at TEXT,PRIMARY KEY(fact_id,source_id));
CREATE TABLE news_drafts(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER REFERENCES news_topics(id),parent_draft_id INTEGER REFERENCES news_drafts(id),revision_no INTEGER,title TEXT,summary_text TEXT,body_text TEXT,model_name TEXT,fact_snapshot_sha256 TEXT,fact_snapshot_json TEXT,status TEXT DEFAULT 'generated',is_demo INTEGER,created_by TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,approved_by TEXT,approved_at TEXT,UNIQUE(topic_id,revision_no));
CREATE TABLE news_claims(id INTEGER PRIMARY KEY AUTOINCREMENT,draft_id INTEGER REFERENCES news_drafts(id),sequence_no INTEGER,statement_text TEXT,is_factual INTEGER DEFAULT 1,status TEXT DEFAULT 'unverified',check_note TEXT,checked_at TEXT,UNIQUE(draft_id,sequence_no));
CREATE TABLE news_claim_facts(claim_id INTEGER REFERENCES news_claims(id),fact_id INTEGER REFERENCES news_facts(id),PRIMARY KEY(claim_id,fact_id));
CREATE TABLE news_reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,draft_id INTEGER REFERENCES news_drafts(id),action TEXT,reviewer_key TEXT,reason TEXT,fact_snapshot_sha256 TEXT,content_sha256 TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE news_publications(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER REFERENCES news_topics(id),draft_id INTEGER UNIQUE REFERENCES news_drafts(id),slug TEXT UNIQUE,status TEXT,published_at TEXT DEFAULT CURRENT_TIMESTAMP,unpublished_at TEXT,retraction_reason TEXT);
CREATE TABLE news_ai_usage(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER REFERENCES news_topics(id),draft_id INTEGER REFERENCES news_drafts(id),model_name TEXT,provider_request_id TEXT,input_tokens INTEGER DEFAULT 0,output_tokens INTEGER DEFAULT 0,cached_input_tokens INTEGER DEFAULT 0,cost_usd TEXT,status TEXT,error_code TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE news_schema_version(name TEXT PRIMARY KEY,version TEXT);
INSERT INTO news_schema_version VALUES('news','8.5.2');
INSERT INTO provinces VALUES(1,'서울'),(2,'도쿄');
INSERT INTO districts VALUES(1,1,'종로구'),(2,2,'신주쿠구');
'''


class SQLiteTx(Tx):
    def execute(self, sql, args=()):
        sql = sql.replace(' FOR UPDATE', '').replace('%s', '?').replace('NOW()', 'CURRENT_TIMESTAMP')
        args = tuple(str(v) if isinstance(v, (Decimal, date, datetime)) else v for v in args)
        return super().execute(sql, args)

    def one(self, sql, args=()):
        row = super().one(sql, args)
        return dict(row) if row else None

    def all(self, sql, args=()):
        return [dict(row) for row in super().all(sql, args)]


class SQLiteDatabase:
    def __init__(self, path):
        self.path = path
        with self.transaction() as tx:
            tx.cursor.executescript(SQLITE_SCHEMA)

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.create_function('UNHEX', 1, lambda value: bytes.fromhex(value))
        try:
            yield SQLiteTx(conn.cursor())
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def fake_generator(topic, facts):
    key = facts[0]['fact_key']
    data = {'title': '지역 행사 일정 안내', 'title_fact_keys': [key],
            'claims': [{'sentence': facts[0]['value_text'], 'fact_keys': [key]}]}
    return parse_draft(data, {f['fact_key'] for f in facts}), {'request_id': 'offline-test', 'input_tokens': 100, 'output_tokens': 30}


@pytest.fixture
def database(tmp_path, monkeypatch):
    if os.getenv('NEWS_TEST_MYSQL') == '1':
        # Only a separately named disposable DB is allowed; never main or OLD_DB_NAME.
        import mysql.connector
        import uuid
        from news_service.setup import migrate
        name = 'news_test_' + uuid.uuid4().hex[:12]
        admin = mysql.connector.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                                        user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
        cursor = admin.cursor()
        cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        monkeypatch.setenv('V83_DB_NAME', name)
        try:
            cursor.execute(f'USE `{name}`')
            cursor.execute('CREATE TABLE provinces(id BIGINT UNSIGNED PRIMARY KEY,name VARCHAR(100)) ENGINE=InnoDB')
            cursor.execute('CREATE TABLE districts(id BIGINT UNSIGNED PRIMARY KEY,province_id BIGINT UNSIGNED,name VARCHAR(100)) ENGINE=InnoDB')
            cursor.execute("INSERT INTO provinces VALUES(1,'서울'),(2,'도쿄')")
            cursor.execute("INSERT INTO districts VALUES(1,1,'종로구'),(2,2,'신주쿠구')")
            admin.commit()
            migrate(admin)
            yield Database()
        finally:
            cursor.execute(f'DROP DATABASE `{name}`')
            cursor.close()
            admin.close()
    else:
        yield SQLiteDatabase(str(tmp_path / 'news.sqlite3'))


@pytest.fixture
def newsroom(database, monkeypatch):
    monkeypatch.setenv('NEWS_INTERNAL_TOKEN', 'a' * 64)
    monkeypatch.setenv('OPENAI_NEWS_MODEL', 'gpt-6-luna')
    service = NewsService(database, fake_generator)
    app.dependency_overrides[get_service] = lambda: service
    with TestClient(app, raise_server_exceptions=False) as client:
        client.headers.update({'x-news-internal-token': 'a' * 64, 'x-news-editor': 'test-editor'})
        yield client, service
    app.dependency_overrides.clear()
