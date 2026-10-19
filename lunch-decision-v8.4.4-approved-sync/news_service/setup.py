"""Create/upgrade news tables without modifying lunch/travel tables or OLD_DB_NAME."""
import argparse
from pathlib import Path
import re
import secrets

from .db import connect

ROOT = Path(__file__).resolve().parents[1]
VERSION = '8.5.2'
# Minimum signatures of the two supported predecessors: news-service / news-center.
SIGNATURES = {
    'news_topics': {'id', 'district_id', 'title', 'category', 'status', 'created_by'},
    'news_sources': {'id', 'topic_id', 'organization', 'source_url', 'source_title', 'published_at'},
    'news_facts': {'id', 'topic_id', 'fact_key', 'fact_type', 'value_text', 'value_number', 'status'},
    'news_fact_evidence': {'fact_id', 'source_id'},
    'news_drafts': {'id', 'topic_id', 'title', 'body_text', 'model_name', 'fact_snapshot_sha256', 'status', 'created_by'},
    'news_claims': {'id', 'draft_id', 'sequence_no', 'statement_text', 'status'},
    'news_claim_facts': {'claim_id', 'fact_id'},
    'news_reviews': {'id', 'draft_id', 'reviewer_key'},
    'news_publications': {'id', 'topic_id', 'draft_id', 'status', 'published_at'},
    'news_ai_usage': {'id', 'topic_id', 'model_name', 'input_tokens', 'output_tokens'},
}
ADDITIONS = {
    'news_topics': {'language_code': "VARCHAR(12) NOT NULL DEFAULT 'ko'", 'keywords': 'VARCHAR(500)',
                    'is_demo': 'BOOLEAN NOT NULL DEFAULT TRUE',
                    'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'},
    'news_sources': {'source_kind': "ENUM('official','public_api','csv','manual','other') NOT NULL DEFAULT 'manual'",
                     'source_url_sha256': 'BINARY(32)', 'checked_at': 'DATETIME', 'license_note': 'VARCHAR(500)',
                     'source_excerpt': 'MEDIUMTEXT', 'content_sha256': 'CHAR(64)', 'is_demo': 'BOOLEAN NOT NULL DEFAULT TRUE',
                     'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'},
    'news_facts': {'unit': 'VARCHAR(30)', 'event_start': 'DATE', 'event_end': 'DATE', 'verification_note': 'TEXT',
                   'verified_by': 'VARCHAR(100)', 'verified_at': 'DATETIME',
                   'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP',
                   'updated_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'},
    'news_fact_evidence': {'excerpt_reference': 'VARCHAR(500)', 'evidence_note': 'TEXT', 'checked_at': 'DATETIME'},
    'news_drafts': {'parent_draft_id': 'BIGINT UNSIGNED', 'revision_no': 'INT UNSIGNED', 'summary_text': 'TEXT',
                    'fact_snapshot_json': 'LONGTEXT',
                    'is_demo': 'BOOLEAN NOT NULL DEFAULT TRUE', 'approved_by': 'VARCHAR(100)', 'approved_at': 'DATETIME',
                    'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'},
    'news_claims': {'is_factual': 'BOOLEAN NOT NULL DEFAULT TRUE', 'check_note': 'VARCHAR(800)', 'checked_at': 'DATETIME'},
    'news_reviews': {'action': "ENUM('submitted','changes_requested','rejected','approved','published','unpublished') NOT NULL DEFAULT 'submitted'",
                     'reason': 'TEXT', 'fact_snapshot_sha256': 'CHAR(64)', 'content_sha256': 'CHAR(64)',
                     'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'},
    'news_publications': {'slug': 'VARCHAR(200)', 'unpublished_at': 'DATETIME', 'retraction_reason': 'TEXT'},
    'news_ai_usage': {'draft_id': 'BIGINT UNSIGNED', 'provider_request_id': 'VARCHAR(150)',
                      'cached_input_tokens': 'INT UNSIGNED NOT NULL DEFAULT 0', 'cost_usd': 'DECIMAL(12,6)',
                      'status': "ENUM('success','error') NOT NULL DEFAULT 'success'", 'error_code': 'VARCHAR(100)',
                      'created_at': 'DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'},
}
ENUMS = {
    ('news_facts', 'status'): ['candidate', 'verified', 'rejected', 'disputed', 'outdated'],
    ('news_drafts', 'status'): ['generated', 'in_review', 'changes_requested', 'rejected', 'approved', 'published'],
    ('news_claims', 'status'): ['supported', 'unverified', 'contradicted', 'not_applicable'],
    ('news_publications', 'status'): ['published', 'unpublished'],
}
INDEXES = {
    'news_sources': ('uq_news_source_fingerprint', ['topic_id', 'source_url_sha256']),
    'news_facts': ('uq_news_fact_topic_key', ['topic_id', 'fact_key']),
    'news_drafts': ('uq_news_draft_revision', ['topic_id', 'revision_no']),
    'news_claims': ('uq_news_claim_sequence', ['draft_id', 'sequence_no']),
}


def initialize_env():
    path = ROOT / '.env'
    text = path.read_text(encoding='utf-8-sig') if path.exists() else (ROOT / '.env.example').read_text(encoding='utf-8')
    match = re.search(r'^NEWS_INTERNAL_TOKEN=(.*)$', text, re.M)
    if not match or not re.fullmatch(r'[0-9a-fA-F]{64}', match.group(1).strip()):
        line = 'NEWS_INTERNAL_TOKEN=' + secrets.token_hex(32)
        text = re.sub(r'^NEWS_INTERNAL_TOKEN=.*$', line, text, flags=re.M) if match else text.rstrip() + '\n' + line + '\n'
    defaults = {'NEWS_SERVICE_URL': 'http://127.0.0.1:8001', 'OPENAI_NEWS_MODEL': 'gpt-6-luna', 'OPENAI_API_KEY': ''}
    for key, value in defaults.items():
        if not re.search(r'^' + key + '=', text, re.M):
            text = text.rstrip() + '\n' + key + '=' + value + '\n'
    path.write_text(text, encoding='utf-8')
    print('.env 뉴스 내부 토큰 설정 완료 (토큰 값은 출력하지 않습니다).')


def columns(cur, table):
    cur.execute('SELECT COLUMN_NAME,COLUMN_TYPE,COLUMN_DEFAULT,IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (table,))
    return {row['COLUMN_NAME']: row for row in cur.fetchall()}


def has_unique(cur, table, fields):
    cur.execute('SELECT INDEX_NAME,COLUMN_NAME,SEQ_IN_INDEX FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND NON_UNIQUE=0 ORDER BY INDEX_NAME,SEQ_IN_INDEX', (table,))
    groups = {}
    for row in cur.fetchall():
        groups.setdefault(row['INDEX_NAME'], []).append(row['COLUMN_NAME'])
    return fields in groups.values()


def migrate(conn, allow_upgrade=False):
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')
        tables = {r['TABLE_NAME']: r['ENGINE'] for r in cur.fetchall()}
        if not {'districts', 'provinces'}.issubset(tables):
            raise RuntimeError('먼저 V8.4.4 npm run setup을 실행하세요.')
        existing = {name: columns(cur, name) for name in SIGNATURES if name in tables}
        for table, cols in existing.items():
            if not SIGNATURES[table].issubset(cols) or tables[table] != 'InnoDB':
                raise RuntimeError(f'{table}: 지원하지 않는 기존 스키마입니다. 데이터를 보존한 채 설치를 중단했습니다.')
        old_version = None
        if 'news_schema_version' in tables:
            cur.execute("SELECT version FROM news_schema_version WHERE name='news'")
            row = cur.fetchone()
            old_version = row['version'] if row else None
        if existing and old_version != VERSION and not allow_upgrade:
            raise RuntimeError('기존 뉴스 테이블을 발견했습니다. npm run backup 후 --upgrade-existing 옵션으로 실행하세요.')
        # Detect duplicate business keys before any DDL. Never delete duplicates automatically.
        checks = [('news_sources', ['topic_id', 'source_url']), ('news_facts', ['topic_id', 'fact_key']),
                  ('news_claims', ['draft_id', 'sequence_no']), ('news_publications', ['draft_id'])]
        for table, keys in checks:
            if table in existing:
                fields = ','.join('`' + key + '`' for key in keys)
                cur.execute(f'SELECT COUNT(*) n FROM `{table}` GROUP BY {fields} HAVING COUNT(*)>1 LIMIT 1')
                if cur.fetchone():
                    raise RuntimeError(f'{table}: 중복 키를 먼저 검토하세요. 기존 행을 삭제하지 않았습니다.')
        sql = (ROOT / 'sql' / '04_news_v852.sql').read_text(encoding='utf-8')
        sql = re.sub(r'--[^\n]*', '', sql)
        for statement in sql.split(';'):
            if statement.strip():
                cur.execute(statement)
        for table, specs in ADDITIONS.items():
            cols = columns(cur, table)
            for column, definition in specs.items():
                if column not in cols:
                    cur.execute(f'ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}')
        for (table, column), required in ENUMS.items():
            definition = columns(cur, table)[column]
            if definition['COLUMN_TYPE'].startswith('enum('):
                values = re.findall(r"'([^']*)'", definition['COLUMN_TYPE'])
                merged = values + [v for v in required if v not in values]
                if merged != values:
                    enum = ','.join("'" + value.replace("'", "''") + "'" for value in merged)
                    default = definition['COLUMN_DEFAULT']
                    default = str(default).strip("'") if default is not None else required[0]
                    cur.execute(f"ALTER TABLE `{table}` MODIFY `{column}` ENUM({enum}) NOT NULL DEFAULT '{default}'")
        if 'check_passed' in columns(cur, 'news_reviews'):
            cur.execute('ALTER TABLE news_reviews ALTER COLUMN check_passed SET DEFAULT 0')
        cur.execute('UPDATE news_sources SET source_url_sha256=UNHEX(SHA2(source_url,256)) WHERE source_url_sha256 IS NULL')
        cur.execute('SELECT id,topic_id,revision_no FROM news_drafts ORDER BY topic_id,id')
        revisions = cur.fetchall()
        next_revision = {}
        # Existing center revisions are preserved; legacy rows get monotonically increasing numbers.
        for row in revisions:
            next_revision[row['topic_id']] = max(next_revision.get(row['topic_id'], 0), row['revision_no'] or 0)
        for row in revisions:
            if not row['revision_no']:
                next_revision[row['topic_id']] += 1
                cur.execute('UPDATE news_drafts SET revision_no=%s WHERE id=%s', (next_revision[row['topic_id']], row['id']))
        cur.execute("UPDATE news_publications SET slug=CONCAT('news-',topic_id,'-',draft_id) WHERE slug IS NULL OR slug=''")
        for table, (name, fields) in INDEXES.items():
            if not has_unique(cur, table, fields):
                cur.execute(f'ALTER TABLE `{table}` ADD UNIQUE KEY `{name}` (' + ','.join('`' + field + '`' for field in fields) + ')')
        for name, fields in [('uq_news_publication_draft', ['draft_id']), ('uq_news_publication_slug', ['slug'])]:
            if not has_unique(cur, 'news_publications', fields):
                cur.execute(f'ALTER TABLE news_publications ADD UNIQUE KEY `{name}` (' + ','.join(fields) + ')')
        if existing and old_version != VERSION:
            # Legacy approvals were not bound to the new source/content snapshots.
            cur.execute("UPDATE news_facts SET status='candidate' WHERE status='verified'")
            cur.execute("UPDATE news_publications SET status='unpublished',unpublished_at=NOW(),retraction_reason='8.5.2 통합 후 재검토 필요' WHERE status='published'")
            cur.execute("UPDATE news_drafts SET status='changes_requested',approved_by=NULL,approved_at=NULL WHERE status IN ('approved','published','in_review')")
            cur.execute("UPDATE news_claims SET status='unverified',check_note=NULL,checked_at=NULL")
        cur.execute("INSERT INTO news_schema_version(name,version) VALUES('news',%s) ON DUPLICATE KEY UPDATE version=VALUES(version),applied_at=NOW()", (VERSION,))
        conn.commit()
        print('뉴스 MySQL 스키마 8.5.2 준비 완료. 기존 점심·여행 테이블은 변경하지 않았습니다.')
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--init-env', action='store_true')
    parser.add_argument('--upgrade-existing', action='store_true')
    args = parser.parse_args()
    if args.init_env:
        initialize_env()
        # db.py loaded dotenv before the newly written values existed.
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=True)
    conn = connect()
    try:
        migrate(conn, args.upgrade_existing)
    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Connector messages can contain host/user details; show no connection strings or secrets.
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print(f'뉴스 설치 실패: {type(error).__name__} (code={getattr(error, "errno", "unknown")}). DB 설정과 백업을 확인하세요.')
        raise SystemExit(1)
