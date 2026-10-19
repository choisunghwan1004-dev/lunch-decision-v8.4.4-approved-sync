"""원자료와 AI 초안을 별도 노션 DB로 전송합니다. 사람의 편집 내용을 덮어쓰지 않습니다."""
import json
import os
import re
import time
from urllib.parse import quote
from uuid import UUID

import httpx


class NotionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def notion_id(value):
    # 노션의 페이지/DB 공유 링크나 UUID를 받아 경로에 쓸 안전한 UUID만 추출합니다.
    matches = re.findall(r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}|[a-fA-F0-9]{32}', value.split('?', 1)[0])
    if not matches:
        raise ValueError('노션 페이지/DB 링크 또는 32자리 ID를 입력하세요.')
    return str(UUID(matches[-1]))


def rich(value):
    return [{'type': 'text', 'text': {'content': str(value)}}]


def blocks(value):
    # 한 rich_text는 2,000자, 한 요청은 100블록 제한이 있어 1,600자씩 나눕니다.
    text = str(value)
    result = [{'object': 'block', 'type': 'paragraph', 'paragraph': {'rich_text': rich(text[i:i + 1600])}}
              for i in range(0, len(text), 1600)]
    if len(result) > 95:
        raise NotionError('notion_size', '노션 전송 자료가 큽니다. 원자료 구절을 줄여 주세요.')
    return result


class NotionClient:
    def __init__(self, client=None):
        token = os.getenv('NOTION_API_KEY', '').strip()
        if not token:
            raise NotionError('notion_configuration', 'NOTION_API_KEY가 없습니다. 15_노션_예약설정.bat을 실행하세요.')
        self.client = client or httpx.Client(timeout=25, follow_redirects=False)
        self.owns_client = client is None
        self.headers = {'Authorization': 'Bearer ' + token, 'Notion-Version': '2025-09-03'}
        self.previous_request = 0

    def close(self):
        if self.owns_client:
            self.client.close()

    def request(self, method, path, data=None):
        # 공식 호스트를 고정하고 초당 3회 이하로 요청합니다. 쓰기 실패를 자동 반복하지 않습니다.
        delay = 0.36 - (time.monotonic() - self.previous_request)
        if delay > 0:
            time.sleep(delay)
        self.previous_request = time.monotonic()
        try:
            response = self.client.request(method, 'https://api.notion.com/v1/' + path,
                                           headers=self.headers, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            message = ('노션 토큰·연결 권한과 상위 페이지 공유를 확인하세요.' if code in (401, 403, 404)
                       else '노션 요청이 거절됐습니다. 호출 한도·DB 속성·서비스 상태를 확인하세요.')
            raise NotionError('notion_http_' + str(code), message) from None
        except (httpx.HTTPError, ValueError):
            raise NotionError('notion_connection', '노션 응답을 확인할 수 없습니다. 실행 기록을 확인한 뒤 노션 저장만 재시도하세요.') from None

    def data_source(self, database_id):
        db = self.request('GET', 'databases/' + notion_id(database_id))
        sources = db.get('data_sources', [])
        if len(sources) != 1:
            raise NotionError('notion_schema', '이 기능 전용으로 데이터 소스가 하나인 노션 DB를 사용하세요.')
        return sources[0]['id']

    def ensure_database(self, parent_id, title):
        parent_id = notion_id(parent_id)
        cursor = None
        matches = []
        # 같은 이름의 DB를 찾아 설치를 반복해도 기존 자료를 보존합니다.
        while True:
            path = 'blocks/' + parent_id + '/children?page_size=100' + ('&start_cursor=' + quote(cursor, safe='') if cursor else '')
            data = self.request('GET', path)
            for item in data.get('results', []):
                if item.get('type') == 'child_database' and item['child_database'].get('title') == title:
                    matches.append(item['id'])
            cursor = data.get('next_cursor') if data.get('has_more') else None
            if not cursor:
                break
        if len(matches) > 1:
            raise NotionError('notion_duplicate', '상위 페이지에 같은 이름의 뉴스 DB가 여러 개입니다. 대상을 정리한 뒤 다시 설정하세요.')
        if matches:
            return self.data_source(matches[0])
        schema = {'이름': {'title': {}}, '자동화키': {'rich_text': {}},
                  '검토상태': {'select': {'options': [{'name': '원자료'}, {'name': '검토 대기'}]}}}
        db = self.request('POST', 'databases', {'parent': {'type': 'page_id', 'page_id': parent_id},
                          'title': rich(title), 'initial_data_source': {'properties': schema}})
        sources = db.get('data_sources', [])
        if not sources:
            return self.data_source(db['id'])
        return sources[0]['id']

    def check_schema(self, source_id):
        data = self.request('GET', 'data_sources/' + notion_id(source_id))
        props = data.get('properties', {})
        if any(props.get(name, {}).get('type') != kind for name, kind in
               [('이름', 'title'), ('자동화키', 'rich_text'), ('검토상태', 'select')]):
            raise NotionError('notion_schema', '노션 DB의 이름·자동화키·검토상태 속성을 확인하거나 15번 설정을 실행하세요.')
        options = {option.get('name') for option in props['검토상태'].get('select', {}).get('options', [])}
        if not {'원자료', '검토 대기'}.issubset(options):
            raise NotionError('notion_schema', '노션 검토상태에 원자료·검토 대기 옵션을 추가하세요.')

    def ensure_page(self, source_id, key, title, content, status):
        source_id = notion_id(source_id)
        found = self.request('POST', 'data_sources/' + source_id + '/query',
                             {'filter': {'property': '자동화키', 'rich_text': {'equals': key}}, 'page_size': 2})
        rows = found.get('results', [])
        if len(rows) > 1:
            raise NotionError('notion_duplicate', '동일 자동화키의 노션 페이지가 여러 개입니다. 중복을 검토하세요.')
        if rows:
            return rows[0]['id']  # 사람이 수정한 페이지는 그대로 둡니다.
        page = self.request('POST', 'pages', {'parent': {'type': 'data_source_id', 'data_source_id': source_id},
            'properties': {'이름': {'title': rich(title[:180])}, '자동화키': {'rich_text': rich(key)},
                           '검토상태': {'select': {'name': status}}}, 'children': blocks(content)})
        return page['id']

    def sync(self, draft, prefix, source_id, draft_id):
        original = json.dumps(draft['saved_fact_sheet'], ensure_ascii=False, indent=2, default=str)
        source_page = self.ensure_page(source_id, prefix + ':sources', '원자료 · ' + draft['title'],
                                      '검증 Fact와 출처의 생성 당시 스냅샷입니다. 전체 기사 자동 크롤링 자료가 아닙니다.\n\n' + original, '원자료')
        claims = '\n'.join(str(c['sequence_no']) + '. ' + c['statement_text'] + ' → ' + ', '.join(c['fact_keys']) for c in draft['claims'])
        content = ('검토 대기 · 자동 승인/게시하지 않습니다. 수정·승인은 웹 관리자에서 진행하세요.\n'
                   + '원자료: https://www.notion.so/' + source_page.replace('-', '') + '\n'
                   + '모델: ' + draft['model_name'] + '\n\n' + draft['body_text'] + '\n\n문장별 근거\n' + claims)
        page = self.ensure_page(draft_id, prefix + ':draft', draft['title'], content, '검토 대기')
        return source_page, page
