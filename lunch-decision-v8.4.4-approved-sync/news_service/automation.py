"""한국 시간 매일 16시: 검증 Fact → 실제 OpenAI → MySQL 초안 → 노션 검토 대기."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone, date
import getpass
import hashlib
import json
import os
import re
import sys
import warnings

from dotenv import load_dotenv

from .ai_runtime import ROOT, NewsAIError, validate_configuration
from .db import Database
from .notion_sync import NotionClient, NotionError, notion_id
from .openai_check import save_settings
from .service import NewsError, NewsService

# 한국은 UTC+9이며 예약 시간은 서버 OS의 시간대와 무관하게 계산합니다.
KST = timezone(timedelta(hours=9), 'Asia/Seoul')


def topic_ids(value):
    parts = value.split(',')
    if not 1 <= len(parts) <= 3 or any(not re.fullmatch(r'[1-9]\d{0,9}', p.strip()) for p in parts):
        raise ValueError('예약할 운영 주제 번호를 쉼표로 구분해 최대 3개 입력하세요. 예: 1,2,3')
    ids = [int(p.strip()) for p in parts]
    if len(set(ids)) != len(ids):
        raise ValueError('예약 주제 번호가 중복되었습니다.')
    return ids


class RunStore:
    def __init__(self, database):
        self.db = database

    @contextmanager
    def lock(self):
        # 연결이 닫히면 MySQL 이름 잠금도 자동 해제됩니다. 별도 프로세스의 동시 실행을 막습니다.
        name = 'news_auto_' + hashlib.sha256(os.getenv('V83_DB_NAME', 'lunch_decision_v83').encode()).hexdigest()[:32]
        with self.db.transaction() as tx:
            row = tx.one('SELECT GET_LOCK(%s,0) acquired', (name,))
            if not row or row['acquired'] != 1:
                raise NewsError('다른 예약 프로세스가 실행 중입니다.', 409)
            try:
                yield
            finally:
                tx.one('SELECT RELEASE_LOCK(%s) released', (name,))

    def get(self, day, topic):
        with self.db.transaction() as tx:
            return tx.one('SELECT * FROM news_automation_runs WHERE run_date=%s AND topic_id=%s', (day, topic))

    def claim(self, day, topic):
        with self.db.transaction() as tx:
            tx.execute("INSERT INTO news_automation_runs(run_date,topic_id,status) VALUES(%s,%s,'running')", (day, topic))

    def update(self, day, topic, status, draft=None, source=None, page=None, error=None):
        with self.db.transaction() as tx:
            tx.execute('''UPDATE news_automation_runs SET status=%s,draft_id=COALESCE(%s,draft_id),
                source_page_id=COALESCE(%s,source_page_id),notion_page_id=COALESCE(%s,notion_page_id),
                error_code=%s WHERE run_date=%s AND topic_id=%s''', (status, draft, source, page, error, day, topic))


def install(database=None):
    # 04 설치 이후의 선택 SQL입니다. 기존 기사 테이블과 원본 DB는 변경하지 않습니다.
    sql = (ROOT / 'sql/05_news_automation.sql').read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql)
    with (database or Database()).transaction() as tx:
        for statement in sql.split(';'):
            if statement.strip():
                tx.execute(statement)


def settings():
    enabled = os.getenv('NEWS_AUTO_ENABLED', '0') == '1'
    return {'enabled': enabled,
            'timezone': 'Asia/Seoul', 'daily_time': '16:00',
            'topic_ids': topic_ids(os.getenv('NEWS_AUTO_TOPIC_IDS', '')) if enabled else [],
            'source_id': notion_id(os.getenv('NOTION_SOURCE_DATA_SOURCE_ID', '')) if enabled else None,
            'draft_id': notion_id(os.getenv('NOTION_DRAFT_DATA_SOURCE_ID', '')) if enabled else None}


def run(now=None, force=False, retry_day=None, service=None, store=None, notion=None):
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    config = settings()
    if not config['enabled']:
        return {'ok': True, 'skipped': '예약이 비활성화되어 있습니다.'}
    if not force and retry_day is None and now.hour < 16:
        return {'ok': True, 'skipped': '한국 시간 16시 이전입니다.'}
    if retry_day is None:
        validate_configuration()
    service = service or NewsService()
    store = store or RunStore(service.db)
    notion = notion or NotionClient()
    day = retry_day or now.date().isoformat()
    # 여러 설치의 실행 키가 충돌하지 않도록 DB 이름 지문도 포함합니다.
    identity = hashlib.sha256(os.getenv('V83_DB_NAME', 'lunch_decision_v83').encode()).hexdigest()[:12]
    results = []
    try:
        # 노션 설정 오류를 유료 호출 전에 발견합니다.
        notion.check_schema(config['source_id'])
        notion.check_schema(config['draft_id'])
        with store.lock():
            for topic in config['topic_ids']:
                row = store.get(day, topic)
                marker = 'auto:' + day + ':' + str(topic)
                if row and row['status'] == 'success':
                    results.append({'topic_id': topic, 'status': 'already_done'});continue
                if row and not row.get('draft_id'):
                    # 호출 직후 프로세스가 종료되어도 이미 저장된 초안은 재사용합니다.
                    with service.db.transaction() as tx:
                        found = tx.one('SELECT id FROM news_drafts WHERE topic_id=%s AND created_by=%s ORDER BY id DESC LIMIT 1', (topic, marker))
                    if found:
                        store.update(day, topic, 'generated', draft=found['id'])
                        row = store.get(day, topic)
                    else:
                        results.append({'topic_id': topic, 'status': 'manual_check_required',
                                        'message': '이전 호출 상태가 불확실하거나 실패했습니다. 중복 과금을 막기 위해 AI를 다시 호출하지 않습니다.'});continue
                if not row and retry_day:
                    results.append({'topic_id': topic, 'status': 'no_saved_draft'});continue
                if not row:
                    # 사람이 검증한 운영 자료만 사용합니다. 시연 주제나 시연 출처는 제외합니다.
                    with service.db.transaction() as tx:
                        context = service.topic(tx, topic)
                        facts, _ = service.sheet(tx, context)
                    if context['is_demo'] or not facts or any(e['is_demo'] for f in facts for e in f['evidence']):
                        results.append({'topic_id': topic, 'status': 'waiting_for_verified_facts'});continue
                    store.claim(day, topic)
                    try:
                        generated = service.generate(topic, marker)
                        store.update(day, topic, 'generated', draft=generated['id'])
                        row = store.get(day, topic)
                    except Exception as error:
                        code = getattr(error, 'code', type(error).__name__)[:100]
                        store.update(day, topic, 'ai_error', error=code)
                        results.append({'topic_id': topic, 'status': 'ai_error', 'code': code});continue
                try:
                    draft = service.detail(row['draft_id'])
                    if not draft['evidence_current'] or draft['status'] != 'generated':
                        results.append({'topic_id': topic, 'status': 'manual_check_required',
                                        'message': '근거 또는 검토 상태가 바뀌었습니다. 자동 전송을 중단했습니다.'});continue
                    prefix = 'LDNEWS:' + identity + ':' + day + ':' + str(topic)
                    source, page = notion.sync(draft, prefix, config['source_id'], config['draft_id'])
                    store.update(day, topic, 'success', source=source, page=page)
                    results.append({'topic_id': topic, 'status': 'success', 'draft_id': draft['id'],
                                    'notion_url': 'https://www.notion.so/' + page.replace('-', '')})
                except Exception as error:
                    code = getattr(error, 'code', type(error).__name__)[:100]
                    store.update(day, topic, 'notion_error', error=code)
                    results.append({'topic_id': topic, 'status': 'notion_error', 'code': code})
    finally:
        notion.close()
    ok = all(r['status'] in ('success', 'already_done', 'waiting_for_verified_facts', 'no_saved_draft') for r in results)
    return {'ok': ok, 'run_date': day, 'timezone': 'Asia/Seoul', 'results': results}


def configure():
    print('노션 연결의 Read/Insert/Update Content 권한과 상위 페이지의 연결 추가가 필요합니다.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        token = getpass.getpass('노션 내부 연결 토큰 (화면에 표시하지 않음): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,}', token):
        raise ValueError('노션 내부 연결 토큰을 확인하세요.')
    parent = notion_id(input('뉴스를 저장할 노션 상위 페이지 링크: ').strip())
    ids = topic_ids(input('웹 관리자의 예약할 운영 주제 번호 (최대 3개, 예: 1,2): ').strip())
    # 존재하는 운영 주제인지 먼저 검사합니다. Fact 미검증은 예약 시 건너뜁니다.
    service = NewsService()
    with service.db.transaction() as tx:
        for ident in ids:
            if service.topic(tx, ident)['is_demo']:
                raise ValueError('시연용 주제는 예약할 수 없습니다.')
    save_settings({'NOTION_API_KEY': token, 'NOTION_NEWS_PARENT_PAGE_ID': parent})
    load_dotenv(ROOT / '.env', override=True)
    client = NotionClient()
    try:
        # 대상 페이지를 먼저 읽어 접근 권한을 확인한 뒤 두 DB를 생성/재사용합니다.
        client.request('GET', 'pages/' + parent)
        name = os.getenv('V83_DB_NAME', 'lunch_decision_v83')
        source = client.ensure_database(parent, '점심여행 원자료 [' + name + ']')
        draft = client.ensure_database(parent, '점심여행 AI초안 [' + name + ']')
        client.check_schema(source);client.check_schema(draft)
    finally:
        client.close()
    install()
    save_settings({'NOTION_SOURCE_DATA_SOURCE_ID': source, 'NOTION_DRAFT_DATA_SOURCE_ID': draft,
                   'NEWS_AUTO_TOPIC_IDS': ','.join(map(str, ids)), 'NEWS_AUTO_ENABLED': '1'})
    print('노션 DB 2개와 예약 설정 준비 완료. 16_오후4시_예약등록.bat을 실행하세요.')


def main(argv=None):
    parser = argparse.ArgumentParser(description='매일 한국 시간 16시 뉴스·노션 예약')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--configure', action='store_true')
    modes.add_argument('--install', action='store_true')
    modes.add_argument('--run-due', action='store_true', help='예약 시간 이후 오늘 자료 처리')
    modes.add_argument('--run-now', action='store_true', help='현재 시각에 오늘 작업 한 번 실행 (비용 발생)')
    modes.add_argument('--status', action='store_true')
    modes.add_argument('--retry-notion', metavar='YYYY-MM-DD', help='저장된 초안의 노션 전송만 재시도')
    args = parser.parse_args(argv)
    try:
        if args.configure:
            configure();return 0
        if args.install:
            install();print('예약 실행 테이블 준비 완료');return 0
        if args.status:
            config = settings()
            print(json.dumps({k: v for k, v in config.items() if not k.endswith('_id')}, ensure_ascii=False, indent=2))
            return 0
        day = date.fromisoformat(args.retry_notion).isoformat() if args.retry_notion else None
        result = run(force=args.run_now, retry_day=day)
    except (NewsAIError, NotionError, NewsError) as error:
        result = {'ok': False, 'code': getattr(error, 'code', type(error).__name__), 'message': error.message}
    except (ValueError, OSError, getpass.GetPassWarning, EOFError):
        result = {'ok': False, 'code': 'configuration', 'message': '예약 설정·입력·폴더 권한을 확인하세요. README_AUTOMATION.md의 설치 순서를 따르세요.'}
    except Exception as error:
        result = {'ok': False, 'code': type(error).__name__, 'message': 'MySQL 연결·뉴스 스키마·예약 테이블 설치를 확인하세요.'}
    folder = ROOT / 'test-results'
    folder.mkdir(exist_ok=True)
    (folder / 'news-automation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
