import pytest

SOURCE = {'source_kind': 'official', 'organization': '테스트 기관', 'source_title': '원자료 테스트',
          'source_url': 'https://example.org/official', 'published_at': '2026-10-01T00:00:00Z',
          'source_excerpt': '행사는 2026년 11월 1일 종로구에서 개최됩니다. 테스트 자료입니다.',
          'license_note': '테스트용 인용 허용'}
FACT = {'fact_key': 'EVENT_DATE', 'fact_type': 'date', 'value_text': '행사는 2026년 11월 1일 종로구에서 개최됩니다.',
        'event_start': '2026-11-01', 'event_end': '2026-11-01'}
CHECKS = dict(numbers=True, time_and_region=True, no_unfounded_causes=True, sources_and_rights=True)


def call(client, method, path, data=None, expected=200):
    response = client.request(method, path, **({'json': data} if data is not None else {}))
    assert response.status_code == expected, response.text
    return response.json()


def prepared(client, demo=False, district=1):
    topic = call(client, 'POST', '/topics', {'district_id': district, 'title': '지역 행사 일정', 'category': 'culture', 'is_demo': demo}, 201)['id']
    source = call(client, 'POST', f'/topics/{topic}/sources', SOURCE, 201)['id']
    fact = call(client, 'POST', f'/topics/{topic}/facts', FACT, 201)['id']
    call(client, 'POST', f'/topics/{topic}/facts/{fact}/evidence', {'source_id': source, 'excerpt_reference': '본문 1문단', 'evidence_note': '일시와 장소 확인'})
    call(client, 'POST', f'/topics/{topic}/facts/{fact}/verify', {'editor_confirmed': True, 'verification_note': '원문 날짜와 장소를 직접 대조함'})
    draft = call(client, 'POST', f'/topics/{topic}/generate', {}, 201)['id']
    return topic, source, fact, draft


def check_all(client, draft):
    detail = call(client, 'GET', f'/drafts/{draft}')
    for claim in detail['claims']:
        call(client, 'POST', f'/drafts/{draft}/claims/{claim["id"]}/review', {'status': 'supported', 'source_checked': True, 'note': '원자료 문구와 일치함', 'expected_content_hash': detail['content_hash']})
    return call(client, 'GET', f'/drafts/{draft}')


def approve(client, draft):
    detail = check_all(client, draft)
    call(client, 'POST', f'/drafts/{draft}/review', {'action': 'approved', 'reason': '수치와 일정 및 출처 최종 검토 완료', 'checks': CHECKS, 'expected_content_hash': detail['content_hash']})
    return detail['content_hash']


def publish(client, draft):
    digest = approve(client, draft)
    return call(client, 'POST', f'/drafts/{draft}/publish', {'confirmation': 'PUBLISH', 'expected_content_hash': digest})


def test_complete_flow_and_public_attribution(newsroom):
    client, _ = newsroom
    topic, source, fact, draft = prepared(client, district=2)
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert len(detail['claims']) == 2 and detail['claims'][0]['sequence_no'] == 0
    assert all(c['status'] == 'unverified' for c in detail['claims'])
    assert detail['model_name'] == 'gpt-6-luna' and call(client, 'GET', '/public') == []
    published = publish(client, draft)
    assert call(client, 'GET', '/public?district_id=1') == []
    article = call(client, 'GET', f'/public/{published["id"]}')
    assert article['region_name'] == '도쿄 / 신주쿠구'
    assert article['sources'][0]['source_url'] == SOURCE['source_url']
    assert 'verification_note' not in str(article) and 'content_sha256' not in str(article)
    call(client, 'POST', f'/drafts/{draft}/unpublish', {'reason': '자료 정정으로 게시 중단'})
    assert call(client, 'GET', '/public') == []
    call(client, 'GET', f'/public/{published["id"]}', expected=404)


@pytest.mark.parametrize('change', ['fact', 'source', 'evidence', 'status', 'reverify'])
def test_evidence_mutation_revokes_approval_and_publication(newsroom, change):
    client, _ = newsroom
    topic, source, fact, draft = prepared(client)
    publish(client, draft)
    if change == 'fact':
        call(client, 'PUT', f'/topics/{topic}/facts/{fact}', {**FACT, 'value_text': '일정이 2026년 11월 2일로 변경되었습니다.'})
    elif change == 'source':
        call(client, 'PUT', f'/topics/{topic}/sources/{source}', {**SOURCE, 'source_excerpt': SOURCE['source_excerpt'] + ' 정정됨.'})
    elif change == 'evidence':
        call(client, 'DELETE', f'/topics/{topic}/facts/{fact}/evidence/{source}')
    elif change == 'status':
        call(client, 'POST', f'/topics/{topic}/facts/{fact}/status', {'status': 'outdated', 'reason': '일정 변경으로 만료됨'})
    else:
        call(client, 'POST', f'/topics/{topic}/facts/{fact}/verify', {'editor_confirmed': True, 'verification_note': '원문 다시 대조함'})
    assert call(client, 'GET', '/public') == []
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert detail['status'] == 'changes_requested' and detail['approved_by'] is None
    assert all(c['status'] == 'unverified' for c in detail['claims'])
    assert detail['publication']['status'] == 'unpublished'


def test_approval_requires_title_every_sentence_and_checklist(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    detail = call(client, 'GET', f'/drafts/{draft}')
    body = {'action': 'approved', 'reason': '최종 검토 완료', 'checks': CHECKS, 'expected_content_hash': detail['content_hash']}
    call(client, 'POST', f'/drafts/{draft}/review', body, 409)
    claim = detail['claims'][1]
    call(client, 'POST', f'/drafts/{draft}/claims/{claim["id"]}/review', {'status': 'supported', 'source_checked': True, 'note': '본문 확인 완료', 'expected_content_hash': detail['content_hash']})
    call(client, 'POST', f'/drafts/{draft}/review', body, 409)
    check_all(client, draft)
    call(client, 'POST', f'/drafts/{draft}/review', {**body, 'checks': {**CHECKS, 'numbers': False}}, 422)
    call(client, 'POST', f'/drafts/{draft}/review', body)


def test_publication_before_approval_is_rejected(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client)
    detail = call(client, 'GET', f'/drafts/{draft}')
    call(client, 'POST', f'/drafts/{draft}/publish', {'confirmation': 'PUBLISH', 'expected_content_hash': detail['content_hash']}, 409)


def test_edit_creates_revision_and_preserves_old_publication_until_replacement(newsroom):
    client, _ = newsroom
    topic, _, _, draft = prepared(client)
    published = publish(client, draft)
    old = call(client, 'GET', f'/drafts/{draft}')
    data = {'title': '지역 행사 일정 다시 안내', 'title_fact_keys': ['EVENT_DATE'], 'claims': [{'sentence': FACT['value_text'], 'fact_keys': ['EVENT_DATE']}], 'reason': '제목을 더 명확하게 수정', 'expected_content_hash': old['content_hash']}
    new = call(client, 'POST', f'/drafts/{draft}/revisions', data, 201)
    detail = call(client, 'GET', f'/drafts/{new["id"]}')
    assert detail['revision_no'] == 2 and detail['parent_draft_id'] == draft
    assert all(c['status'] == 'unverified' for c in detail['claims'])
    assert call(client, 'GET', '/public')[0]['id'] == published['id']
    publish(client, new['id'])
    articles = call(client, 'GET', '/public')
    assert len(articles) == 1 and articles[0]['title'] == data['title']
    call(client, 'POST', f'/drafts/{draft}/revisions', {**data, 'expected_content_hash': '0' * 64}, 409)


def test_cross_topic_deletion_never_removes_foreign_evidence(newsroom):
    client, _ = newsroom
    topic, source, fact, _ = prepared(client)
    other = call(client, 'POST', '/topics', {'district_id': 1, 'title': '다른 주제'}, 201)['id']
    call(client, 'DELETE', f'/topics/{other}/facts/{fact}', expected=404)
    assert call(client, 'GET', f'/topics/{topic}/facts')[0]['evidence'][0]['source_id'] == source


def test_demo_cannot_be_approved_or_published(newsroom):
    client, _ = newsroom
    _, _, _, draft = prepared(client, demo=True)
    detail = check_all(client, draft)
    call(client, 'POST', f'/drafts/{draft}/review', {'action': 'approved', 'reason': '가상 자료 검토함', 'checks': CHECKS, 'expected_content_hash': detail['content_hash']}, 409)
    assert call(client, 'GET', '/public') == []


def test_out_of_band_tampering_is_not_public(newsroom):
    client, service = newsroom
    topic, source, _, draft = prepared(client)
    publish(client, draft)
    with service.db.transaction() as tx:
        tx.execute('UPDATE news_sources SET source_excerpt=%s WHERE id=%s', ('DB에서 직접 변경된 원자료입니다.', source))
    assert call(client, 'GET', '/public') == []
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert detail['saved_fact_sheet']['facts'][0]['evidence'][0]['source_excerpt'] == SOURCE['source_excerpt']


def test_out_of_band_content_tampering_invalidates_approval(newsroom):
    client, service = newsroom
    _, _, _, draft = prepared(client)
    publish(client, draft)
    with service.db.transaction() as tx:
        tx.execute('UPDATE news_drafts SET body_text=%s WHERE id=%s', ('근거에 없는 문장', draft))
    assert call(client, 'GET', '/public') == []


def test_provider_error_stores_no_draft_and_no_secret(newsroom):
    client, service = newsroom
    topic, _, _, draft = prepared(client)
    def failing(*_):
        raise RuntimeError('secret-api-key-never-return')
    service.generator = failing
    error = call(client, 'POST', f'/topics/{topic}/generate', {}, 502)
    assert 'secret-api-key' not in str(error)
    assert len(call(client, 'GET', f'/topics/{topic}/drafts')) == 1
    with service.db.transaction() as tx:
        row = tx.one("SELECT error_code FROM news_ai_usage WHERE status='error'")
        assert row['error_code'] == 'RuntimeError'


def test_mutation_while_ai_runs_discards_draft_but_records_usage(newsroom):
    client, service = newsroom
    topic, _, fact, _ = prepared(client)
    real = service.generator
    def concurrent(t, facts):
        service.fact_status(topic, fact, {'status': 'outdated', 'reason': '생성 도중 변경됨'}, 'another-editor')
        return real(t, facts)
    service.generator = concurrent
    call(client, 'POST', f'/topics/{topic}/generate', {}, 409)
    assert len(call(client, 'GET', f'/topics/{topic}/drafts')) == 1
    with service.db.transaction() as tx:
        assert tx.one("SELECT error_code FROM news_ai_usage WHERE status='error'")['error_code'] == 'EvidenceChanged'


def test_input_guards_and_internal_auth(newsroom):
    client, _ = newsroom
    assert client.get('/topics', headers={'x-news-internal-token': 'wrong'}).status_code == 403
    call(client, 'POST', '/topics', {'district_id': 999, 'title': '없는 지역'}, 422)
    topic = call(client, 'POST', '/topics', {'district_id': 1, 'title': '검증 테스트'}, 201)['id']
    call(client, 'POST', f'/topics/{topic}/sources', {**SOURCE, 'source_url': 'javascript:alert(1)'}, 422)
    call(client, 'POST', f'/topics/{topic}/facts', {**FACT, 'event_end': '2026-01-01'}, 422)
    call(client, 'POST', f'/topics/{topic}/generate', {}, 422)
    fact = call(client, 'POST', f'/topics/{topic}/facts', FACT, 201)['id']
    call(client, 'POST', f'/topics/{topic}/facts/{fact}/verify', {'editor_confirmed': True, 'verification_note': '출처가 없는 검증'}, 422)
    assert call(client, 'GET', '/health')['model'] == 'gpt-6-luna'
