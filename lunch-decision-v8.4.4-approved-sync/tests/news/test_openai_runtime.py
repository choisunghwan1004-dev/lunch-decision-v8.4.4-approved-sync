"""실제 SDK의 HTTP 직렬화·오류 처리 검사. 외부 API에는 접속하지 않습니다."""
import importlib
import json

import httpx
from openai import OpenAI
import pytest
from fastapi.testclient import TestClient
from dotenv import dotenv_values

from news_service import article_ai, openai_check
from news_service.ai_runtime import NewsAIError, configuration, create_client

TOPIC = {'region_name': '가상 지역', 'title': '연결 점검', 'category': 'other', 'is_demo': True}
FACTS = [{'id': 1, 'fact_key': 'DEMO_COUNT', 'value_text': '수업용 가상 참가자는 10명입니다.'}]
ARTICLE = {'title': '수업용 가상 참가자 안내', 'title_fact_keys': ['DEMO_COUNT'],
           'claims': [{'sentence': '수업용 가상 참가자는 10명입니다.', 'fact_keys': ['DEMO_COUNT']}]}


def response_data(article=ARTICLE):
    return {'id': 'resp_test', 'object': 'response', 'created_at': 1, 'status': 'completed', 'model': 'gpt-6-luna',
            'output': [{'id': 'msg_test', 'type': 'message', 'status': 'completed', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': json.dumps(article), 'annotations': []}]}],
            'usage': {'input_tokens': 101, 'output_tokens': 30, 'total_tokens': 131,
                      'input_tokens_details': {'cached_tokens': 5}}}


@pytest.fixture(autouse=True)
def configuration_env(monkeypatch):
    monkeypatch.setenv('OPENAI_NEWS_MODEL', 'gpt-6-luna')


def sdk(handler):
    return OpenAI(api_key='sk-test-not-a-real-api-key', max_retries=0,
                  http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_real_sdk_sends_responses_schema_once(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url == 'https://api.openai.com/v1/responses'
        body = json.loads(request.content)
        assert body['model'] == 'gpt-6-luna' and body['store'] is False
        assert body['text']['format']['strict'] is True
        assert body['reasoning'] == {'effort': 'none'}
        return httpx.Response(200, json=response_data())
    with sdk(handler) as client:
        article, usage = article_ai.generate_article(TOPIC, FACTS, client)
    assert len(calls) == 1 and usage['request_id'] == 'resp_test'
    assert usage['input_tokens'] == 101 and usage['cached_input_tokens'] == 5
    assert article['claims'][0]['fact_keys'] == ['DEMO_COUNT']


@pytest.mark.parametrize('status,provider_code,code', [(401, 'invalid_api_key', 'invalid_api_key'),
    (403, 'permission_denied', 'model_access'), (404, 'model_not_found', 'model_access'),
    (429, 'insufficient_quota', 'insufficient_quota'), (429, 'rate_limit_exceeded', 'rate_limit'),
    (400, 'bad_request', 'invalid_request'), (500, 'server_error', 'provider_error')])
def test_provider_errors_are_safe_and_never_retried(status, provider_code, code):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, json={'error': {'message': 'SECRET-KEY-FROM-PROVIDER', 'code': provider_code}})
    with sdk(handler) as client, pytest.raises(NewsAIError) as caught:
        article_ai.generate_article(TOPIC, FACTS, client)
    assert caught.value.code == code
    assert 'SECRET' not in caught.value.message and len(seen) == 1


def test_timeout_and_invalid_json_are_safe():
    def timeout(request):
        raise httpx.ReadTimeout('SECRET-TIMEOUT', request=request)
    with sdk(timeout) as client, pytest.raises(NewsAIError, match='시간') as caught:
        article_ai.generate_article(TOPIC, FACTS, client)
    assert caught.value.code == 'timeout' and 'SECRET' not in str(caught.value)
    data = response_data();data['output'][0]['content'][0]['text'] = 'not-json'
    with sdk(lambda r: httpx.Response(200, json=data)) as client, pytest.raises(NewsAIError) as caught:
        article_ai.generate_article(TOPIC, FACTS, client)
    assert caught.value.code == 'invalid_output'


def test_client_ignores_foreign_base_url_and_status_never_leaks_key(monkeypatch):
    # 테스트 호스트의 SOCKS 프록시는 이 생성자 검사에 필요하지 않습니다. 네트워크 접속은 없습니다.
    for name in ('ALL_PROXY', 'all_proxy', 'HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-a-secret-api-key-value')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://foreign.invalid')
    with create_client() as client:
        assert str(client.base_url) == 'https://api.openai.com/v1/' and client.max_retries == 0
    assert 'sk-a-secret' not in json.dumps(configuration())


def test_key_writer_preserves_db_and_eliminates_duplicate_keys(tmp_path):
    path = tmp_path / '.env'
    path.write_text('\ufeffDB_PASSWORD="keep-this"\nADMIN_PASSWORD=keep-admin\nOPENAI_API_KEY=old\nexport OPENAI_API_KEY=duplicate\nOPENAI_NEWS_MODEL=old\n', encoding='utf-8')
    key = 'sk-' + 'x' * 24
    openai_check.save_key(key, tmp_path)
    data = dotenv_values(path)
    assert data['DB_PASSWORD'] == 'keep-this' and data['ADMIN_PASSWORD'] == 'keep-admin'
    assert data['OPENAI_API_KEY'] == key and data['OPENAI_NEWS_MODEL'] == 'gpt-6-luna'
    assert path.read_text().count('OPENAI_API_KEY=') == 1
    assert not list(tmp_path.glob('.openai-env-*.tmp'))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        openai_check.save_key('sk-bad\nDB_PASSWORD=changed', tmp_path)
    assert path.read_bytes() == before


def test_live_cli_missing_key_records_failure_without_network(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.setattr(openai_check, 'ROOT', tmp_path)
    assert openai_check.main(['--live']) == 1
    report = json.loads((tmp_path / 'test-results/openai-live.json').read_text())
    assert not report['live_openai_succeeded'] and report['code'] == 'missing_api_key'
    assert '13_OpenAI' in capsys.readouterr().out


def test_live_check_uses_same_generator_with_demo_fact(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-not-real')
    def fake(topic, facts):
        assert topic['is_demo'] and facts[0]['value_number'] == 10
        return {'title': '시연', 'body': '시연'}, {'request_id': 'mock-only'}
    monkeypatch.setattr(openai_check, 'generate_article', fake)
    assert openai_check.live_check()['is_demo'] is True


def test_api_check_requires_auth_confirmation_and_no_database(monkeypatch):
    module = importlib.import_module('news_service.app')
    monkeypatch.setenv('NEWS_INTERNAL_TOKEN', 'a' * 64)
    calls = []
    monkeypatch.setattr(module, 'live_check', lambda: calls.append(1) or {'ok': True, 'test_double': True})
    with TestClient(module.app) as client:
        assert client.get('/ai/status').status_code == 403
        assert client.post('/ai/check', json={'confirmation': 'CALL_OPENAI'}).status_code == 403
        client.headers['x-news-internal-token'] = 'a' * 64
        assert client.get('/ai/status').status_code == 200
        assert client.post('/ai/check', json={}).status_code == 422
        assert client.post('/ai/check', json={'confirmation': 'CALL_OPENAI', 'api_key': 'not-allowed'}).status_code == 422
        assert client.post('/ai/check', json={'confirmation': 'CALL_OPENAI'}).status_code == 200
    assert calls == [1]


def test_generation_records_safe_error_code_and_keeps_drafts(newsroom):
    from test_workflow import prepared, call
    client, service = newsroom
    topic, _, _, _ = prepared(client)
    def fail(*args):
        raise NewsAIError('insufficient_quota', 'API 잔액이 부족합니다.', 429)
    service.generator = fail
    error = call(client, 'POST', f'/topics/{topic}/generate', {}, 429)
    assert error['code'] == 'insufficient_quota'
    assert len(call(client, 'GET', f'/topics/{topic}/drafts')) == 1
    with service.db.transaction() as tx:
        assert tx.one("SELECT error_code FROM news_ai_usage WHERE status='error'")['error_code'] == 'insufficient_quota'
