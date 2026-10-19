"""시간·중복 과금 방지·부분 실패 복구를 확인하며 OpenAI/Notion 실제 접속은 하지 않습니다."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os

import pytest

from news_service import automation
from news_service.notion_sync import NotionError
from news_service.service import NewsError
from test_workflow import prepared


class Store:
    def __init__(self):
        self.rows = {}

    @contextmanager
    def lock(self):
        yield

    def get(self, day, topic):
        return self.rows.get((day, topic))

    def claim(self, day, topic):
        assert (day, topic) not in self.rows
        self.rows[day, topic] = {'status': 'running', 'draft_id': None}

    def update(self, day, topic, status, draft=None, source=None, page=None, error=None):
        row = self.rows[day, topic];row['status'] = status
        if draft:
            row['draft_id'] = draft
        row['error_code'] = error


class Notion:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def check_schema(self, source):
        pass

    def sync(self, draft, prefix, source_id, draft_id):
        self.sent.append(draft)
        assert draft['saved_fact_sheet'] and draft['status'] == 'generated'
        if self.fail:
            raise NotionError('notion_connection', '연결 실패')
        return '1' * 32, '2' * 32

    def close(self):
        pass


def config(monkeypatch, topic):
    for key, value in {'NEWS_AUTO_ENABLED': '1', 'NEWS_AUTO_TOPIC_IDS': str(topic),
        'OPENAI_API_KEY': 'sk-test-no-network', 'OPENAI_NEWS_MODEL': 'gpt-6-luna',
        'NOTION_SOURCE_DATA_SOURCE_ID': '1' * 32, 'NOTION_DRAFT_DATA_SOURCE_ID': '2' * 32}.items():
        monkeypatch.setenv(key, value)


def clock(hour=7, minute=0):
    return datetime(2026, 10, 20, hour, minute, tzinfo=timezone.utc)


def test_exact_korean_time_and_daily_duplicate_guard(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    original = service.generator
    calls = []
    service.generator = lambda *args: calls.append(1) or original(*args)
    store, notion = Store(), Notion()
    result = automation.run(clock(6, 59), service=service, store=store, notion=notion)
    assert 'skipped' in result and not calls
    first = automation.run(clock(), service=service, store=store, notion=notion)
    second = automation.run(clock(9), service=service, store=store, notion=notion)
    assert first['results'][0]['status'] == 'success'
    assert second['results'][0]['status'] == 'already_done'
    assert len(calls) == len(notion.sent) == 1
    assert client.get('/public').json() == []  # 예약이 승인/게시를 우회하지 않음


def test_notion_retry_never_calls_ai_again_and_needs_no_ai_key(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    store = Store()
    failed = automation.run(clock(), service=service, store=store, notion=Notion(fail=True))
    assert failed['results'][0]['status'] == 'notion_error'
    def forbidden(*args):
        raise AssertionError('AI가 다시 호출되면 안 됩니다.')
    service.generator = forbidden
    monkeypatch.delenv('OPENAI_API_KEY')
    success = automation.run(clock(), retry_day='2026-10-20', service=service, store=store, notion=Notion())
    assert success['results'][0]['status'] == 'success'


def test_crash_after_saved_draft_recovers_without_second_call(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    store = Store();store.claim('2026-10-20', topic)
    saved = service.generate(topic, 'auto:2026-10-20:' + str(topic))
    service.generator = lambda *args: pytest.fail('이미 저장된 초안은 다시 생성하지 않음')
    result = automation.run(clock(), service=service, store=store, notion=Notion())
    assert result['results'][0]['draft_id'] == saved['id']


def test_uncertain_ai_call_is_not_repeated(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    store = Store();store.claim('2026-10-20', topic)
    service.generator = lambda *args: pytest.fail('불확실한 호출은 자동 재시도하면 안 됨')
    result = automation.run(clock(), service=service, store=store, notion=Notion())
    assert result['results'][0]['status'] == 'manual_check_required' and not result['ok']


def test_demo_and_unverified_topics_are_skipped(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client, demo=True)
    config(monkeypatch, topic)
    result = automation.run(clock(), service=service, store=Store(), notion=Notion())
    assert result['results'][0]['status'] == 'waiting_for_verified_facts'


def test_notion_preflight_failure_happens_before_paid_call(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    service.generator = lambda *args: pytest.fail('노션 설정이 잘못되면 AI 호출을 하지 않음')
    class BadNotion(Notion):
        def check_schema(self, source):
            raise NotionError('notion_schema', '잘못된 속성')
    with pytest.raises(NotionError):
        automation.run(clock(), service=service, store=Store(), notion=BadNotion())


def test_default_disabled_and_topic_bounds(monkeypatch):
    monkeypatch.setenv('NEWS_AUTO_ENABLED', '0')
    assert 'skipped' in automation.run(clock())
    for bad in ['', '1,1', '0', '1,2,3,4', '1;DROP TABLE', '-1']:
        with pytest.raises(ValueError):
            automation.topic_ids(bad)


@pytest.mark.skipif(os.getenv('NEWS_TEST_MYSQL') != '1', reason='MySQL named locks and DDL require MySQL')
def test_mysql_install_lock_persistence_and_repeat(newsroom, monkeypatch):
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    config(monkeypatch, topic)
    automation.install(service.db);automation.install(service.db)
    store = automation.RunStore(service.db)
    with store.lock(), pytest.raises(NewsError, match='다른 예약'):
        with automation.RunStore(service.db).lock():
            pytest.fail('동시 잠금을 획득하면 안 됨')
    result = automation.run(clock(), service=service, store=store, notion=Notion())
    assert result['ok'] and store.get('2026-10-20', topic)['notion_page_id'] == '2' * 32
    assert automation.run(clock(), service=service, store=automation.RunStore(service.db), notion=Notion())['results'][0]['status'] == 'already_done'
