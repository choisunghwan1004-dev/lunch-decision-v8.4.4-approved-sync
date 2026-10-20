"""자동 검수는 참고 기록만 만들고, 사람 확인·공개 조건을 대신하지 않는지 확인합니다."""
import json
import time

import httpx
from openai import OpenAI
import pytest

from news_service import review_ai
from news_service.ai_runtime import NewsAIError
from news_service.service import NewsError
from test_workflow import CHECKS, SOURCE, call, prepared, publish


def result_for(draft, facts, fail=False):
    return {'summary': '등록한 날짜·지역을 원문 구절과 대조했습니다.',
        'checks': [{'key': key, 'status': 'fail' if fail and key == 'numbers' else 'pass',
                    'note': '원문과 비교해 확인하세요.'} for key in review_ai.KEYS],
        'claims': [{'claim_id': c['id'], 'status': 'pass', 'note': '등록 근거와 일치합니다.',
                    'fact_keys': c['fact_keys'],
                    'source_ids': sorted({e['source_id'] for f in facts if f['fact_key'] in c['fact_keys'] for e in f['evidence']})}
                   for c in draft['claims']]}


def request_for(client, draft):
    return {'confirmation': 'RUN_AI_REVIEW', 'expected_content_hash': call(client, 'GET', f'/drafts/{draft}')['content_hash']}


def fake_reviewer(calls, fail=False):
    def review(topic, draft, facts):
        calls.append(draft['id'])
        return result_for(draft, facts, fail), {'request_id': 'review-mock-only', 'input_tokens': 20, 'output_tokens': 40}
    return review


def test_review_is_persisted_and_cached_without_approving_or_publishing(newsroom):
    client, service = newsroom
    _, _, _, draft = prepared(client)
    calls = [];service.reviewer = fake_reviewer(calls)
    first = call(client, 'POST', f'/drafts/{draft}/ai-review', request_for(client, draft))
    second = call(client, 'POST', f'/drafts/{draft}/ai-review', request_for(client, draft))
    assert not first['cached'] and second['cached'] and calls == [draft]
    assert first['review']['id'] == second['review']['id']
    assert first['review']['result']['checks'][-1]['status'] == 'unknown'  # 이용 허가는 사람 확인
    detail = call(client, 'GET', f'/drafts/{draft}')
    assert detail['status'] == 'generated' and detail['approved_by'] is None and detail['publication'] is None
    assert all(c['status'] == 'unverified' for c in detail['claims'])
    assert len(detail['review_points']) == 4 and '20%' in detail['review_points'][0]['good']
    assert [r['action'] for r in detail['reviews']] == ['submitted']
    assert detail['ai_review']['current'] and detail['ai_review']['state'] == 'completed'
    assert call(client, 'GET', '/public') == []
    assert 'ai_assisted_review' not in json.dumps(call(client, 'GET', '/public/feed'))
    with service.db.transaction() as tx:
        assert tx.one('SELECT COUNT(*) n FROM news_ai_usage WHERE draft_id=%s', (draft,))['n'] == 2  # 초안+검수


@pytest.mark.parametrize('change', ['hash', 'confirmation', 'stale'])
def test_bad_or_stale_request_never_calls_provider(newsroom, change):
    client, service = newsroom
    topic, source, _, draft = prepared(client)
    data = request_for(client, draft);calls=[];service.reviewer=fake_reviewer(calls)
    expected = 409
    if change == 'hash': data['expected_content_hash'] = '0' * 64
    elif change == 'confirmation': data['confirmation'] = 'NO';expected=422
    else: call(client, 'PUT', f'/topics/{topic}/sources/{source}', {**SOURCE, 'source_excerpt': SOURCE['source_excerpt'] + ' 변경.'})
    call(client, 'POST', f'/drafts/{draft}/ai-review', data, expected)
    assert calls == []


def test_source_changes_invalidate_review_and_next_revision_does_not_inherit_it(newsroom):
    client, service = newsroom
    topic, source, _, draft = prepared(client);service.reviewer=fake_reviewer([])
    call(client, 'POST', f'/drafts/{draft}/ai-review', request_for(client, draft))
    detail = call(client, 'GET', f'/drafts/{draft}')
    revised = call(client, 'POST', f'/drafts/{draft}/revisions', {
        'title': '새 제목 지역 행사 안내', 'title_fact_keys': detail['claims'][0]['fact_keys'],
        'claims': [{'sentence': c['statement_text'], 'fact_keys': c['fact_keys']} for c in detail['claims'][1:]],
        'reason': '제목을 수정했습니다.', 'expected_content_hash': detail['content_hash']}, 201)
    assert call(client, 'GET', f'/drafts/{revised["id"]}')['ai_review'] is None
    call(client, 'PUT', f'/topics/{topic}/sources/{source}', {**SOURCE, 'source_excerpt': SOURCE['source_excerpt'] + ' 정정.'})
    assert call(client, 'GET', f'/drafts/{draft}')['ai_review']['current'] is False


def test_duplicate_running_request_is_rejected_without_second_provider_call(newsroom):
    client, service = newsroom
    _, _, _, draft = prepared(client);data=request_for(client, draft);calls=[]
    def review(topic, article, facts):
        calls.append(1)
        with pytest.raises(NewsError, match='진행 중'):
            service.assisted_review(draft, data, 'another-editor')
        return result_for(article, facts), {}
    service.reviewer=review
    call(client, 'POST', f'/drafts/{draft}/ai-review', data)
    assert calls == [1]


def test_interrupted_request_is_recorded_before_explicit_retry(newsroom):
    client, service = newsroom
    topic, _, _, draft = prepared(client);data=request_for(client, draft);calls=[];service.reviewer=fake_reviewer(calls)
    with service.db.transaction() as tx:
        article, t = service.draft(tx, draft)
        _, digest = service.sheet(tx, t)
        service.review_log(tx, draft, 'submitted', 'test-editor', json.dumps({
            'kind': review_ai.KIND, 'state':'running', 'model':review_ai.MODEL, 'started_at':time.time()-121}), digest, article['content_hash'])
    call(client, 'POST', f'/drafts/{draft}/ai-review', data, 409)
    assert calls == [] and call(client, 'GET', f'/drafts/{draft}')['ai_review']['error_code'] == 'interrupted'
    call(client, 'POST', f'/drafts/{draft}/ai-review', data)
    assert calls == [draft]


def test_provider_error_is_safe_persisted_and_can_be_retried_manually(newsroom):
    client, service = newsroom
    _, _, _, draft = prepared(client)
    service.reviewer=lambda *_: (_ for _ in ()).throw(RuntimeError('SECRET_PROVIDER_KEY'))
    error=call(client, 'POST', f'/drafts/{draft}/ai-review', request_for(client,draft), 502)
    assert 'SECRET' not in str(error)
    detail=call(client,'GET',f'/drafts/{draft}')
    assert detail['ai_review']['state']=='error' and 'SECRET' not in str(detail)
    assert detail['status']=='generated' and all(c['status']=='unverified' for c in detail['claims'])
    service.reviewer=fake_reviewer([])
    call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft))


def test_result_changed_while_calling_is_discarded_but_usage_kept(newsroom):
    client, service = newsroom
    _, source, _, draft=prepared(client)
    def review(topic, article, facts):
        with service.db.transaction() as tx:
            tx.execute('UPDATE news_sources SET source_excerpt=%s WHERE id=%s', (SOURCE['source_excerpt']+' 검사 중 변경.',source))
        return result_for(article,facts), {'input_tokens':22,'output_tokens':33}
    service.reviewer=review
    call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft),409)
    detail=call(client,'GET',f'/drafts/{draft}')
    assert detail['ai_review']['state']=='error' and not detail['ai_review']['current']
    with service.db.transaction() as tx:
        row=tx.one('SELECT * FROM news_ai_usage WHERE draft_id=%s ORDER BY id DESC LIMIT 1',(draft,))
        assert row['error_code']=='ReviewEvidenceChanged' and row['input_tokens']==22


@pytest.mark.parametrize('bad', ['missing_check','duplicate_check','missing_title','foreign_fact','foreign_source','unlinked_pass'])
def test_invalid_ai_links_or_missing_items_are_not_success(newsroom,bad):
    client,service=newsroom
    _,_,_,draft=prepared(client)
    def review(topic,article,facts):
        result=result_for(article,facts)
        if bad=='missing_check':result['checks'].pop()
        elif bad=='duplicate_check':result['checks'][1]=result['checks'][0]
        elif bad=='missing_title':result['claims'].pop(0)
        elif bad=='foreign_fact':result['claims'][0]['fact_keys']=['FOREIGN_FACT']
        elif bad=='foreign_source':result['claims'][0]['source_ids']=[999999]
        else:result['claims'][0]['source_ids']=[]
        return result,{}
    service.reviewer=review
    error=call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft),502)
    assert error['code']=='invalid_review_output'
    assert call(client,'GET',f'/drafts/{draft}')['ai_review']['state']=='error'


def test_human_four_checks_and_ai_reference_are_stored_separately(newsroom):
    client,service=newsroom
    _,_,_,draft=prepared(client);service.reviewer=fake_reviewer([])
    result=call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft))
    data={'source_checked':True,'expected_content_hash':request_for(client,draft)['expected_content_hash'],'human_checks':CHECKS}
    call(client,'POST',f'/drafts/{draft}/verify-and-save',data)
    detail=call(client,'GET',f'/drafts/{draft}')
    approved=next(r for r in detail['reviews'] if r['action']=='approved')
    reason=json.loads(approved['reason'])
    assert reason['kind']=='human_guided_review_v1' and reason['checks']==CHECKS
    assert reason['ai_review_id']==result['review']['id'] and detail['status']=='published'


@pytest.mark.parametrize('checks', [{}, {**CHECKS,'numbers':False}])
def test_partial_human_checks_do_not_approve(newsroom,checks):
    client,_=newsroom
    _,_,_,draft=prepared(client)
    call(client,'POST',f'/drafts/{draft}/verify-and-save',{
        'source_checked':True,'expected_content_hash':request_for(client,draft)['expected_content_hash'],'human_checks':checks},422)
    assert call(client,'GET',f'/drafts/{draft}')['status']=='generated'


def test_ai_fail_requires_human_recheck_note_even_for_old_client(newsroom):
    client,service=newsroom
    _,_,_,draft=prepared(client);service.reviewer=fake_reviewer([],fail=True)
    call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft))
    data={'source_checked':True,'expected_content_hash':request_for(client,draft)['expected_content_hash']}
    call(client,'POST',f'/drafts/{draft}/verify-and-save',data,422)
    data['human_checks']=CHECKS
    call(client,'POST',f'/drafts/{draft}/verify-and-save',data,422)
    data['ai_issue_note']='원문을 직접 재확인했고 수치가 없는 기사임을 확인했습니다.'
    call(client,'POST',f'/drafts/{draft}/verify-and-save',data)


def test_reading_draft_does_not_start_ai_and_endpoint_needs_auth(newsroom):
    client,service=newsroom
    _,_,_,draft=prepared(client);calls=[];service.reviewer=fake_reviewer(calls)
    assert call(client,'GET',f'/drafts/{draft}')['ai_review'] is None and calls==[]
    assert client.post(f'/drafts/{draft}/ai-review',json=request_for(client,draft),headers={'x-news-internal-token':'wrong'}).status_code==403
    call(client,'POST',f'/drafts/{draft}/ai-review',{'confirmation':'RUN_AI_REVIEW'},422)


def test_real_sdk_review_request_is_schema_bound_and_does_not_send_private_notes(newsroom):
    client,service=newsroom
    _,_,_,draft=prepared(client)
    with service.db.transaction() as tx:
        article,topic=service.draft(tx,draft);facts,_=service.sheet(tx,topic)
    seen=[]
    def handler(request):
        seen.append(request)
        body=json.loads(request.content)
        assert body['model']=='gpt-6-luna' and body['store'] is False
        assert body['text']['format']['name']=='regional_news_review' and body['text']['format']['strict']
        payload=json.loads(body['input'])
        assert 'verification_note' not in body['input'] and 'verified_by' not in body['input']
        assert payload['facts'][0]['evidence'][0]['source_excerpt']==SOURCE['source_excerpt']
        return httpx.Response(200,json={'id':'resp_review_mock','object':'response','created_at':1,'status':'completed','model':'gpt-6-luna',
            'output':[{'id':'msg_review','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':json.dumps(result_for(article,facts)),'annotations':[]}]}],
            'usage':{'input_tokens':40,'output_tokens':50,'total_tokens':90}})
    with OpenAI(api_key='sk-test-not-real',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(handler))) as sdk:
        result,usage=review_ai.review_article(topic,article,facts,sdk)
    assert len(seen)==1 and usage['request_id']=='resp_review_mock' and result['overall']=='warn'


@pytest.mark.parametrize('state,text,code', [('incomplete','{}','incomplete_review_output'),('completed','{','invalid_review_output')])
def test_incomplete_or_invalid_sdk_review_is_not_success(newsroom,state,text,code):
    client,service=newsroom
    _,_,_,draft=prepared(client)
    with service.db.transaction() as tx:
        article,topic=service.draft(tx,draft);facts,_=service.sheet(tx,topic)
    response={'id':'resp_bad_review','object':'response','created_at':1,'status':state,'model':'gpt-6-luna',
        'output':[{'id':'msg_bad','type':'message','status':'completed','role':'assistant','content':[{'type':'output_text','text':text,'annotations':[]}]}]}
    with OpenAI(api_key='sk-test-not-real',max_retries=0,http_client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=response)))) as sdk:
        with pytest.raises(NewsAIError) as error:
            review_ai.review_article(topic,article,facts,sdk)
    assert error.value.code==code


def test_review_on_published_article_does_not_change_publication_or_human_approval(newsroom):
    client,service=newsroom
    _,_,_,draft=prepared(client);publication=publish(client,draft)
    service.reviewer=fake_reviewer([])
    call(client,'POST',f'/drafts/{draft}/ai-review',request_for(client,draft))
    detail=call(client,'GET',f'/drafts/{draft}')
    assert detail['status']=='published' and detail['publication']['id']==publication['id']
    assert sum(r['action']=='approved' for r in detail['reviews'])==1


def test_missing_api_key_allows_human_review_without_a_fake_ai_success(newsroom,monkeypatch):
    client,_=newsroom
    _,_,_,draft=prepared(client)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    data=request_for(client,draft)
    error=call(client,'POST',f'/drafts/{draft}/ai-review',data,503)
    assert error['code']=='missing_api_key'
    assert call(client,'GET',f'/drafts/{draft}')['ai_review']['state']=='error'
    call(client,'POST',f'/drafts/{draft}/verify-and-save',{
        'source_checked':True,'expected_content_hash':data['expected_content_hash'],'human_checks':CHECKS})
