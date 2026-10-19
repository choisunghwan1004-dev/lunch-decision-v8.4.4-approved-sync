"""Compatibility tests use disposable MySQL DBs, never the application DB."""
import os
from pathlib import Path
import re
import uuid

import pytest

from news_service.setup import migrate

pytestmark = pytest.mark.skipif(os.getenv('NEWS_TEST_MYSQL') != '1', reason='requires disposable MySQL test server')


@pytest.fixture
def legacy_connection(monkeypatch):
    import mysql.connector
    name = 'news_test_upgrade_' + uuid.uuid4().hex[:10]
    connection = mysql.connector.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                                         user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
    cur = connection.cursor(dictionary=True)
    cur.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
    cur.execute(f'USE `{name}`')
    cur.execute('CREATE TABLE provinces(id BIGINT UNSIGNED PRIMARY KEY,name VARCHAR(100)) ENGINE=InnoDB')
    cur.execute('CREATE TABLE districts(id BIGINT UNSIGNED PRIMARY KEY,province_id BIGINT UNSIGNED,name VARCHAR(100)) ENGINE=InnoDB')
    cur.execute("INSERT INTO provinces VALUES(1,'서울')")
    cur.execute("INSERT INTO districts VALUES(1,1,'종로구')")
    connection.commit()
    monkeypatch.setenv('V83_DB_NAME', name)
    try:
        yield connection, cur
    finally:
        cur.execute(f'DROP DATABASE `{name}`')
        cur.close()
        connection.close()


def load_predecessor(connection, cur, name):
    sql = (Path(__file__).parent / 'fixtures' / (name + '_v851.sql')).read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql).replace('USE lunch_decision_v83;', '')
    for statement in sql.split(';'):
        if statement.strip():
            cur.execute(statement)
    connection.commit()


@pytest.mark.parametrize('predecessor', ['independent', 'center'])
def test_upgrade_preserves_rows_revokes_old_approval_and_is_idempotent(legacy_connection, predecessor):
    connection, cur = legacy_connection
    load_predecessor(connection, cur, predecessor)
    cur.execute("INSERT INTO news_topics(district_id,title,category,created_by) VALUES(1,'기존 기사','culture','legacy')")
    topic = cur.lastrowid
    if predecessor == 'center':
        cur.execute("INSERT INTO news_sources(topic_id,source_kind,organization,source_title,source_url,source_url_sha256) VALUES(%s,'official','기관','원자료','https://example.org',UNHEX(SHA2('https://example.org',256)))", (topic,))
        cur.execute("INSERT INTO news_drafts(topic_id,revision_no,title,body_text,model_name,fact_snapshot_sha256,status,created_by) VALUES(%s,1,'기존 제목','기존 본문','gpt-4.1-mini',%s,'published','legacy')", (topic, '0' * 64))
    else:
        cur.execute("INSERT INTO news_sources(topic_id,organization,source_title,source_url,published_at) VALUES(%s,'기관','원자료','https://example.org',NOW())", (topic,))
        cur.execute("INSERT INTO news_drafts(topic_id,title,body_text,model_name,fact_snapshot_sha256,status,created_by) VALUES(%s,'기존 제목','기존 본문','gpt-4.1-mini',%s,'published','legacy')", (topic, '0' * 64))
    draft = cur.lastrowid
    cur.execute("INSERT INTO news_facts(topic_id,fact_key,fact_type,value_text,status,verified_by) VALUES(%s,'OLD_FACT','text','기존 사실 원문','verified','legacy-reviewer')", (topic,))
    if predecessor == 'center':
        cur.execute("INSERT INTO news_publications(topic_id,draft_id,slug,status) VALUES(%s,%s,'old-article','published')", (topic, draft))
    else:
        cur.execute("INSERT INTO news_publications(topic_id,draft_id,status,published_at) VALUES(%s,%s,'published',NOW())", (topic, draft))
    connection.commit()
    with pytest.raises(RuntimeError, match='--upgrade-existing'):
        migrate(connection)
    migrate(connection, allow_upgrade=True)
    cur.execute('SELECT * FROM news_drafts WHERE id=%s', (draft,))
    row = cur.fetchone()
    assert row['body_text'] == '기존 본문' and row['status'] == 'changes_requested' and row['revision_no'] == 1
    cur.execute("SELECT status,value_text,verified_by FROM news_facts WHERE topic_id=%s AND fact_key='OLD_FACT'", (topic,))
    fact = cur.fetchone()
    assert fact == {'status': 'candidate', 'value_text': '기존 사실 원문', 'verified_by': 'legacy-reviewer'}
    cur.execute('SELECT status FROM news_publications WHERE draft_id=%s', (draft,))
    assert cur.fetchone()['status'] == 'unpublished'
    # Independent schema had a mandatory check_passed column; new reviews must still work.
    cur.execute("INSERT INTO news_reviews(draft_id,action,reviewer_key,reason,content_sha256) VALUES(%s,'submitted','new-editor','새 검토',%s)", (draft, '1' * 64))
    cur.execute("UPDATE news_drafts SET status='approved' WHERE id=%s", (draft,))
    connection.commit()
    migrate(connection)
    cur.execute('SELECT status FROM news_drafts WHERE id=%s', (draft,))
    assert cur.fetchone()['status'] == 'approved'  # repeat installation must not revoke new reviews
    cur.execute('SELECT COUNT(*) n FROM news_sources WHERE topic_id=%s', (topic,))
    assert cur.fetchone()['n'] == 1


def test_unknown_schema_fails_before_mutation(legacy_connection):
    connection, cur = legacy_connection
    cur.execute('CREATE TABLE news_topics(id INT PRIMARY KEY,foreign_data TEXT) ENGINE=InnoDB')
    cur.execute("INSERT INTO news_topics VALUES(1,'보존할 외부 데이터')")
    connection.commit()
    with pytest.raises(RuntimeError, match='지원하지 않는'):
        migrate(connection, allow_upgrade=True)
    cur.execute('SELECT foreign_data FROM news_topics')
    assert cur.fetchone()['foreign_data'] == '보존할 외부 데이터'


def test_legacy_duplicates_are_not_silently_deleted(legacy_connection):
    connection, cur = legacy_connection
    load_predecessor(connection, cur, 'independent')
    cur.execute("INSERT INTO news_topics(district_id,title,created_by) VALUES(1,'중복 출처','legacy')")
    topic = cur.lastrowid
    for _ in range(2):
        cur.execute("INSERT INTO news_sources(topic_id,organization,source_title,source_url,published_at) VALUES(%s,'기관','원자료','https://example.org/duplicate',NOW())", (topic,))
    connection.commit()
    with pytest.raises(RuntimeError, match='중복 키'):
        migrate(connection, allow_upgrade=True)
    cur.execute('SELECT COUNT(*) n FROM news_sources')
    assert cur.fetchone()['n'] == 2
