"""사람의 원문 확인 한 번으로 검증·승인·공개를 원자적으로 저장하는 회귀 검사."""
import pytest

from test_workflow import call, prepared, approve, SOURCE
from news_service.service import NewsError


def request_for(client, draft, **overrides):
    detail = call(client, 'GET', f'/drafts/{draft}')
    return {'source_checked': True, 'expected_content_hash': detail['content_hash'], **overrides}


def test_blank_memo_saves_and_displays_verified_news(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    assert call(client, 'GET', '/public') == []
    result = call(client, 'POST', f'/drafts/{draft}/verify-and-save', request_for(client, draft, note=''))
    article = call(client, 'GET', f'/public/{result["id"]}')
    assert article['sources'][0]['source_url'] == SOURCE['source_url']
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert detail['status'] == 'published'
    assert all(c['status'] == 'supported' and c['checked_at'] for c in detail['claims'])
    assert [r['action'] for r in detail['reviews']] == ['approved', 'published']


@pytest.mark.parametrize('checked', [False, None])
def test_human_confirmation_is_required(newsroom, checked):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    data = request_for(client, draft, source_checked=checked)
    if checked is None:
        del data['source_checked']
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', data, 422)
    assert call(client, 'GET', f'/drafts/{draft}')['status'] == 'generated'
    assert call(client, 'GET', '/public') == []


def test_short_optional_note_and_retry_are_supported(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    data = request_for(client, draft, note='확인')
    first = call(client, 'POST', f'/drafts/{draft}/verify-and-save', data)
    second = call(client, 'POST', f'/drafts/{draft}/verify-and-save', data)
    assert second['id'] == first['id'] and second['already_saved'] is True
    assert len(call(client, 'GET', f'/drafts/{draft}')['reviews']) == 2
    assert len(call(client, 'GET', '/public')) == 1


@pytest.mark.parametrize('change', ['hash', 'evidence', 'demo', 'contradicted'])
def test_simple_save_preserves_evidence_and_demo_guards(newsroom, change):
    client, _ = newsroom
    topic, source, _, draft = prepared(client, demo=(change == 'demo'))
    data = request_for(client, draft)
    if change == 'hash':
        data['expected_content_hash'] = '0' * 64
    if change == 'evidence':
        call(client, 'PUT', f'/topics/{topic}/sources/{source}', {**SOURCE, 'source_excerpt': SOURCE['source_excerpt'] + ' 자료 변경.'})
    if change == 'contradicted':
        claim = call(client, 'GET', f'/drafts/{draft}')['claims'][0]
        call(client, 'POST', f'/drafts/{draft}/claims/{claim["id"]}/review', {'status':'contradicted', 'source_checked':True, 'note':'제목 불일치 확인', 'expected_content_hash':data['expected_content_hash']})
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', data, 409)
    assert call(client, 'GET', '/public') == []


def test_storage_failure_rolls_back_claims_approval_and_publication(newsroom, monkeypatch):
    client, service = newsroom
    _, _, _, draft = prepared(client)
    def fail(*args):
        raise NewsError('공개 저장 실패 시험', 409)
    monkeypatch.setattr(service, 'store_publication', fail)
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', request_for(client, draft), 409)
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert detail['status'] == 'generated' and detail['approved_by'] is None
    assert not detail['reviews'] and detail['publication'] is None
    assert all(c['status'] == 'unverified' for c in detail['claims'])


def test_existing_approved_article_can_be_saved_without_reentering_old_checks(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    approve(client, draft)
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', request_for(client, draft))
    assert call(client, 'GET', f'/drafts/{draft}')['status'] == 'published'


def test_unpublished_article_requires_human_confirmation_to_return(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    data = request_for(client, draft)
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', data)
    call(client, 'POST', f'/drafts/{draft}/unpublish', {'reason':'관리자 공개 중단'})
    assert call(client, 'GET', '/public') == []
    call(client, 'POST', f'/drafts/{draft}/verify-and-save', data)
    assert len(call(client, 'GET', '/public')) == 1
