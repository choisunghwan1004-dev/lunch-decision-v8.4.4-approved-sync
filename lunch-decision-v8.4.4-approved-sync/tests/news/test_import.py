"""CSV/JSON 수집은 후보 저장만 하고 실제 원문 검증·게시는 사람에게 맡깁니다."""
import csv
from io import StringIO
import json

import pytest
from test_workflow import call

ROW = dict(source_kind='csv', organization='테스트 기관', source_title='수집 원자료',
           source_url='https://example.org/import-test', published_at='2026-10-19T00:00:00Z',
           source_excerpt='수업용 가상 지역 행사 안내입니다. 방문객은 120명입니다.', license_note='수업용 가상 데이터',
           fact_key='VISITORS', fact_type='number', value_text='가상 방문객은 120명입니다.',
           value_number='120', unit='명', excerpt_reference='본문 1문단', evidence_note='행사 집계 항목', is_demo=True)


def topic(client, demo=True):
    return call(client, 'POST', '/topics', {'district_id': 2, 'title': '수집 테스트 주제', 'is_demo': demo}, 201)['id']


@pytest.mark.parametrize('format_name', ['csv', 'json'])
def test_import_stores_sources_facts_and_evidence_but_does_not_verify(newsroom, format_name):
    client, _ = newsroom; ident = topic(client)
    rows = [ROW, {**ROW, 'fact_key': 'VISITORS_2'}]
    if format_name == 'csv':
        out = StringIO(newline='');writer = csv.DictWriter(out, fieldnames=list(ROW));writer.writeheader();writer.writerows(rows)
        content = '\ufeff' + out.getvalue()
    else:
        content = json.dumps(rows, ensure_ascii=False)
    result = call(client, 'POST', f'/topics/{ident}/import', {'format': format_name, 'content': content}, 201)
    assert result['facts_created'] == 2 and result['sources_created'] == 1
    facts = call(client, 'GET', f'/topics/{ident}/facts')
    assert len(facts) == 2 and all(f['status'] == 'candidate' and len(f['evidence']) == 1 for f in facts)
    assert call(client, 'GET', f'/topics/{ident}/fact-sheet')['facts'] == []


def test_late_conflict_rolls_back_earlier_rows(newsroom):
    client, _ = newsroom; ident = topic(client)
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps([ROW])}, 201)
    rows = [{**ROW, 'fact_key': 'NEW_FACT', 'source_url': 'https://example.org/second'}, ROW]
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps(rows)}, 409)
    assert len(call(client, 'GET', f'/topics/{ident}/facts')) == 1
    assert len(call(client, 'GET', f'/topics/{ident}/sources')) == 1


@pytest.mark.parametrize('rows,expected', [([ROW, ROW], 409), ([{**ROW, 'published_at': ''}], 422),
                                        ([{**ROW, 'unrecognized': 'x'}], 422), ([{**ROW, 'is_demo': ''}], 422),
                                        ([ROW] * 41, 422), ([], 422)])
def test_invalid_files_are_rejected_before_writing(newsroom, rows, expected):
    client, _ = newsroom; ident = topic(client)
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps(rows)}, expected)
    assert call(client, 'GET', f'/topics/{ident}/facts') == []


def test_demo_file_cannot_enter_operational_topic(newsroom):
    client, _ = newsroom; ident = topic(client, False)
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps([ROW])}, 422)
    assert call(client, 'GET', f'/topics/{ident}/sources') == []


def test_changed_existing_source_is_not_overwritten(newsroom):
    client, _ = newsroom; ident = topic(client)
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps([ROW])}, 201)
    changed = {**ROW, 'fact_key': 'NEW', 'source_excerpt': '기존 출처를 덮어쓰면 안 되는 변경 내용입니다.'}
    call(client, 'POST', f'/topics/{ident}/import', {'format': 'json', 'content': json.dumps([changed])}, 409)
    assert call(client, 'GET', f'/topics/{ident}/sources')[0]['source_excerpt'] == ROW['source_excerpt']
