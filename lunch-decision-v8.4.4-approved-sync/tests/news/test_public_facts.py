"""검증 Fact가 기사 생성 없이 공개되고, 기사 승인·공개 중단은 그대로 지켜지는지 확인합니다."""
import pytest

from test_workflow import FACT, SOURCE, call, publish


def fact_only(client, demo=False, district=1):
    topic = call(client, 'POST', '/topics', {'district_id': district, 'title': '원문으로 확인한 행사', 'is_demo': demo}, 201)['id']
    source = call(client, 'POST', f'/topics/{topic}/sources', SOURCE, 201)['id']
    fact = call(client, 'POST', f'/topics/{topic}/facts', FACT, 201)['id']
    call(client, 'POST', f'/topics/{topic}/facts/{fact}/evidence', {
        'source_id': source, 'excerpt_reference': '첫 문단', 'evidence_note': '원문 일시와 장소 대조'})
    return topic, source, fact


def verify(client, topic, fact):
    call(client, 'POST', f'/topics/{topic}/facts/{fact}/verify', {
        'editor_confirmed': True, 'verification_note': '사람이 원문과 직접 대조했습니다.'})


def test_fact_verification_alone_shows_public_content_without_ai(newsroom):
    client, service = newsroom
    def never_call(*_):
        pytest.fail('Fact 공개 조회가 AI를 호출하면 안 됩니다.')
    service.generator = never_call
    topic, _, fact = fact_only(client)
    assert call(client, 'GET', '/public/feed') == []
    verify(client, topic, fact)
    items = call(client, 'GET', '/public/feed')
    assert len(items) == 1 and items[0]['kind'] == 'facts'
    item = call(client, 'GET', f'/public/facts/{topic}')
    assert item == items[0] and item['body'] == FACT['value_text']
    assert item['fact_count'] == 1 and item['ai_assisted'] is False
    assert item['region_name'] == '서울 / 종로구'
    assert set(item['sources'][0]) == {'id', 'source_title', 'source_url', 'organization', 'published_at'}
    for private in ('verification_note', 'verified_by', 'content_sha256', 'source_excerpt', 'evidence_note'):
        assert private not in str(item)
    assert call(client, 'GET', f'/topics/{topic}/drafts') == []
    assert call(client, 'GET', '/public') == []  # 기존 기사용 API는 형식을 유지합니다.
    with service.db.transaction() as tx:
        assert tx.one('SELECT COUNT(*) n FROM news_ai_usage')['n'] == 0


def test_verified_facts_are_grouped_and_candidates_are_excluded(newsroom):
    client, _ = newsroom
    topic, source, first = fact_only(client)
    second = call(client, 'POST', f'/topics/{topic}/facts', {
        'fact_key': 'EVENT_PLACE', 'fact_type': 'place', 'value_text': '행사 장소는 종로구입니다.'}, 201)['id']
    call(client, 'POST', f'/topics/{topic}/facts/{second}/evidence', {
        'source_id': source, 'excerpt_reference': '첫 문단', 'evidence_note': '장소 대조'})
    verify(client, topic, first)
    assert call(client, 'GET', '/public/feed')[0]['fact_count'] == 1
    verify(client, topic, second)
    items = call(client, 'GET', '/public/feed')
    assert len(items) == 1 and items[0]['fact_count'] == 2 and len(items[0]['sources']) == 1


@pytest.mark.parametrize('change', ['fact', 'source', 'evidence', 'outdated'])
def test_changed_evidence_or_fact_leaves_public_feed(newsroom, change):
    client, _ = newsroom
    topic, source, fact = fact_only(client)
    verify(client, topic, fact)
    assert call(client, 'GET', '/public/feed')
    if change == 'fact':
        call(client, 'PUT', f'/topics/{topic}/facts/{fact}', {**FACT, 'value_text': '행사 일정 변경 확인이 필요합니다.'})
    elif change == 'source':
        call(client, 'PUT', f'/topics/{topic}/sources/{source}', {**SOURCE, 'source_excerpt': SOURCE['source_excerpt'] + ' 정정.'})
    elif change == 'evidence':
        call(client, 'DELETE', f'/topics/{topic}/facts/{fact}/evidence/{source}')
    else:
        call(client, 'POST', f'/topics/{topic}/facts/{fact}/status', {'status': 'outdated', 'reason': '일정 변경으로 재확인 필요'})
    assert call(client, 'GET', '/public/feed') == []
    call(client, 'GET', f'/public/facts/{topic}', expected=404)


@pytest.mark.parametrize('change', ['demo_topic', 'demo_source', 'incomplete_source', 'changed_source', 'no_verifier'])
def test_demo_incomplete_or_unverified_records_are_never_public(newsroom, change):
    client, service = newsroom
    topic, source, fact = fact_only(client, demo=change == 'demo_topic')
    verify(client, topic, fact)
    with service.db.transaction() as tx:
        if change == 'demo_source':
            tx.execute('UPDATE news_sources SET is_demo=1 WHERE id=%s', (source,))
        elif change == 'incomplete_source':
            tx.execute("UPDATE news_sources SET license_note='' WHERE id=%s", (source,))
        elif change == 'changed_source':
            tx.execute("UPDATE news_sources SET source_excerpt='직접 변경한 원문입니다. 재검증 필요.' WHERE id=%s", (source,))
        elif change == 'no_verifier':
            tx.execute('UPDATE news_facts SET verified_by=NULL WHERE id=%s', (fact,))
    assert call(client, 'GET', '/public/feed') == []
    call(client, 'GET', f'/public/facts/{topic}', expected=404)


def test_article_replaces_fact_card_and_unpublish_does_not_restore_facts(newsroom):
    client, _ = newsroom
    topic, _, fact = fact_only(client)
    verify(client, topic, fact)
    draft = call(client, 'POST', f'/topics/{topic}/generate', {}, 201)['id']
    # 미검토 AI 초안을 만들더라도 공개하는 본문은 기존 검증 Fact뿐입니다.
    assert call(client, 'GET', '/public/feed')[0]['kind'] == 'facts'
    publication = publish(client, draft)
    items = call(client, 'GET', '/public/feed')
    assert len(items) == 1 and items[0]['kind'] == 'article' and items[0]['id'] == publication['id']
    call(client, 'GET', f'/public/facts/{topic}', expected=404)
    assert call(client, 'GET', '/topics')[0]['publication_count'] == 1
    call(client, 'POST', f'/drafts/{draft}/unpublish', {'reason': '운영자가 공개 중단함'})
    assert call(client, 'GET', '/public/feed') == []
    verify(client, topic, fact)
    assert call(client, 'GET', '/public/feed') == []


def test_feed_combines_articles_and_facts_with_filter_and_limit(newsroom):
    client, service = newsroom
    korea, _, first = fact_only(client)
    japan, _, second = fact_only(client, district=2)
    verify(client, korea, first)
    verify(client, japan, second)
    draft = call(client, 'POST', f'/topics/{japan}/generate', {}, 201)['id']
    publication = publish(client, draft)
    with service.db.transaction() as tx:
        tx.execute("UPDATE news_facts SET verified_at='2026-01-01 00:00:00' WHERE id=%s", (first,))
        tx.execute("UPDATE news_publications SET published_at='2026-10-20 01:00:00' WHERE id=%s", (publication['id'],))
    items = call(client, 'GET', '/public/feed')
    assert [item['kind'] for item in items] == ['article', 'facts']
    assert len(call(client, 'GET', '/public/feed?limit=1')) == 1
    assert call(client, 'GET', '/public/feed?district_id=1')[0]['id'] == korea
    assert call(client, 'GET', '/public/feed?district_id=2')[0]['kind'] == 'article'
    call(client, 'GET', '/public/feed?limit=31', expected=422)
    call(client, 'GET', '/public/feed?district_id=0', expected=422)
    assert client.get('/public/feed', headers={'x-news-internal-token': 'wrong'}).status_code == 403


def test_event_dates_are_structured_and_candidate_dates_are_not_public(newsroom):
    client, _ = newsroom
    topic, source, fact = fact_only(client)
    call(client, 'PUT', f'/topics/{topic}/facts/{fact}', {**FACT, 'event_end': '2026-11-03'})
    call(client, 'POST', f'/topics/{topic}/facts', {
        **FACT, 'fact_key': 'UNVERIFIED_DATE', 'value_text': '검증하지 않은 12월 행사',
        'event_start': '2026-12-01', 'event_end': None}, 201)
    verify(client, topic, fact)
    events = call(client, 'GET', f'/public/facts/{topic}?district_id=1')['events']
    assert events == [{'label': FACT['value_text'], 'start_date': '2026-11-01', 'end_date': '2026-11-03'}]


def test_single_day_and_news_without_dates(newsroom):
    client, _ = newsroom
    topic, _, fact = fact_only(client)
    call(client, 'PUT', f'/topics/{topic}/facts/{fact}', {**FACT, 'event_end': None})
    verify(client, topic, fact)
    event = call(client, 'GET', '/public/feed')[0]['events'][0]
    assert event['start_date'] == event['end_date'] == '2026-11-01'
    call(client, 'PUT', f'/topics/{topic}/facts/{fact}', {
        'fact_key': 'NOTICE', 'fact_type': 'text', 'value_text': '일정이 없는 일반 지역 소식입니다.'})
    verify(client, topic, fact)
    assert call(client, 'GET', '/public/feed')[0]['events'] == []


def test_article_calendar_only_includes_facts_linked_to_its_claims(newsroom):
    client, _ = newsroom
    topic, source, fact = fact_only(client)
    unused = call(client, 'POST', f'/topics/{topic}/facts', {
        **FACT, 'fact_key': 'UNUSED_EVENT', 'value_text': '다른 행사 일정입니다.',
        'event_start': '2027-01-01', 'event_end': '2027-01-02'}, 201)['id']
    call(client, 'POST', f'/topics/{topic}/facts/{unused}/evidence', {
        'source_id': source, 'excerpt_reference': '첫 문단', 'evidence_note': '일정 대조'})
    verify(client, topic, fact)
    verify(client, topic, unused)
    assert len(call(client, 'GET', '/public/feed')[0]['events']) == 2
    draft = call(client, 'POST', f'/topics/{topic}/generate', {}, 201)['id']
    publication = publish(client, draft)
    events = call(client, 'GET', f'/public/{publication["id"]}')['events']
    assert len(events) == 1 and events[0]['start_date'] == '2026-11-01'


def test_public_details_respect_the_selected_district(newsroom):
    client, _ = newsroom
    korea, _, first = fact_only(client)
    japan, _, second = fact_only(client, district=2)
    verify(client, korea, first)
    verify(client, japan, second)
    call(client, 'GET', f'/public/facts/{korea}?district_id=2', expected=404)
    assert call(client, 'GET', f'/public/facts/{korea}?district_id=1')['district_id'] == 1
    draft = call(client, 'POST', f'/topics/{japan}/generate', {}, 201)['id']
    publication = publish(client, draft)
    call(client, 'GET', f'/public/{publication["id"]}?district_id=1', expected=404)
    assert call(client, 'GET', f'/public/{publication["id"]}?district_id=2')['district_id'] == 2
    call(client, 'GET', f'/public/facts/{korea}?district_id=0', expected=422)


def test_release_diagnostic_needs_auth_but_not_database_or_ai(newsroom):
    from news_service.app import app, get_service, RELEASE
    client, _ = newsroom
    original = app.dependency_overrides[get_service]
    def never_create_service():
        pytest.fail('설치 버전 조회가 DB·AI를 초기화하면 안 됩니다.')
    app.dependency_overrides[get_service] = never_create_service
    try:
        assert call(client, 'GET', '/public/version') == RELEASE
        assert client.get('/public/version', headers={'x-news-internal-token': 'wrong'}).status_code == 403
    finally:
        app.dependency_overrides[get_service] = original
