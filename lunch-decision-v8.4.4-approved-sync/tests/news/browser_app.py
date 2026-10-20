"""Browser-test entry point. Refuses to run against any application database."""
import os
from news_service.app import app, get_service
from news_service.service import NewsService
from news_service.validation import parse_draft
from news_service.review_ai import KEYS

if os.getenv('NEWS_BROWSER_TEST_RUN') != '1' or not os.getenv('V83_DB_NAME', '').startswith('news_test_ui_'):
    raise RuntimeError('브라우저 테스트 전용 임시 DB에서만 실행할 수 있습니다.')


def generate(topic, facts):
    data = {'title': '신주쿠 지역 소식 안내', 'title_fact_keys': [facts[0]['fact_key']],
            'claims': [{'sentence': facts[0]['value_text'], 'fact_keys': [facts[0]['fact_key']]}]}
    return parse_draft(data, {f['fact_key'] for f in facts}), {'request_id': 'browser-offline-provider', 'input_tokens': 1, 'output_tokens': 1}


def review(topic, draft, facts):
    # 실제 API 키가 없는 격리 브라우저 검사에서만 사용하는 명시적 응답 대역입니다.
    result = {'summary': '모의 AI 검수: 등록 날짜·지역을 대조했습니다. 최종 원문 확인은 사람이 진행합니다.',
              'checks': [{'key': key, 'status': 'unknown' if key == 'sources_and_rights' else 'pass',
                          'note': '테스트 원문과 대조했습니다. 이용 조건은 직접 확인하세요.'} for key in KEYS],
              'claims': [{'claim_id': c['id'], 'status': 'pass', 'note': '브라우저 검수 대역의 근거 대조 결과',
                          'fact_keys': c['fact_keys'],
                          'source_ids': sorted({e['source_id'] for f in facts if f['fact_key'] in c['fact_keys'] for e in f['evidence']})}
                         for c in draft['claims']]}
    return result, {'request_id':'browser-mock-review-only','input_tokens':30,'output_tokens':60}


app.dependency_overrides[get_service] = lambda: NewsService(generator=generate, reviewer=review)
