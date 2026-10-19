import json

import httpx
import pytest

from news_service.notion_sync import NotionClient, NotionError, blocks, notion_id


def test_notion_payload_and_idempotent_create_preserve_human_edits(monkeypatch):
    monkeypatch.setenv('NOTION_API_KEY', 'not-a-real-token')
    pages = [];requests = []
    def handler(request):
        requests.append(request)
        assert request.headers['Notion-Version'] == '2025-09-03'
        assert request.url.host == 'api.notion.com'
        body = json.loads(request.content or '{}')
        if request.url.path.endswith('/query'):
            return httpx.Response(200, json={'results': pages})
        assert request.url.path == '/v1/pages'
        assert body['parent']['type'] == 'data_source_id'
        assert body['properties']['검토상태']['select']['name'] == '검토 대기'
        assert body['properties']['자동화키']['rich_text'][0]['text']['content'] == 'fixed-run-key'
        assert all(len(b['paragraph']['rich_text'][0]['text']['content']) <= 1600 for b in body['children'])
        pages.append({'id': '2' * 32})
        return httpx.Response(200, json=pages[0])
    client = NotionClient(httpx.Client(transport=httpx.MockTransport(handler)))
    first = client.ensure_page('1' * 32, 'fixed-run-key', '제목', '근거' * 3000, '검토 대기')
    second = client.ensure_page('1' * 32, 'fixed-run-key', '수정된 제목', '다른 내용', '검토 대기')
    assert first == second and len([r for r in requests if r.url.path == '/v1/pages']) == 1
    assert len(blocks('가' * 1601)) == 2


def test_notion_database_creation_schema_and_reuse(monkeypatch):
    monkeypatch.setenv('NOTION_API_KEY', 'not-real')
    created = []
    def handler(request):
        path = request.url.path
        if path.endswith('/children'):
            return httpx.Response(200, json={'results': [] if not created else [
                {'id': '2' * 32, 'type': 'child_database', 'child_database': {'title': '원자료'}}]})
        if request.method == 'POST':
            body = json.loads(request.content)
            props = body['initial_data_source']['properties']
            assert props['이름'] == {'title': {}} and props['자동화키'] == {'rich_text': {}}
            created.append(body)
        return httpx.Response(200, json={'id': '2' * 32, 'data_sources': [{'id': '3' * 32}]})
    client = NotionClient(httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.ensure_database('1' * 32, '원자료') == '3' * 32
    assert client.ensure_database('1' * 32, '원자료') == '3' * 32
    assert len(created) == 1
    duplicate = {'results': [{'id': char * 32, 'type': 'child_database',
                  'child_database': {'title': '원자료'}} for char in ('1', '2')]}
    duplicate_client = NotionClient(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=duplicate))))
    with pytest.raises(NotionError, match='여러 개'):
        duplicate_client.ensure_database('1' * 32, '원자료')


def test_notion_errors_hide_remote_secrets_and_validate_ids(monkeypatch):
    monkeypatch.setenv('NOTION_API_KEY', 'not-a-real-token')
    client = NotionClient(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={'message': 'SECRET'}))))
    with pytest.raises(NotionError) as caught:
        client.check_schema('1' * 32)
    assert caught.value.code == 'notion_http_401' and 'SECRET' not in str(caught.value)
    assert notion_id('https://www.notion.so/hello-' + 'a' * 32 + '?source=copy_link') == 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    with pytest.raises(ValueError):
        notion_id('https://evil.invalid/no-identifier')
    props = {'이름': {'type': 'title'}, '자동화키': {'type': 'rich_text'},
             '검토상태': {'type': 'select', 'select': {'options': []}}}
    schema_client = NotionClient(httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'properties': props}))))
    with pytest.raises(NotionError, match='옵션'):
        schema_client.check_schema('1' * 32)
