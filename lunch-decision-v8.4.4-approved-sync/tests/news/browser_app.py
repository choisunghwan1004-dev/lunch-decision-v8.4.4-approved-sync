"""Browser-test entry point. Refuses to run against any application database."""
import os
from news_service.app import app, get_service
from news_service.service import NewsService
from news_service.validation import parse_draft

if os.getenv('NEWS_BROWSER_TEST_RUN') != '1' or not os.getenv('V83_DB_NAME', '').startswith('news_test_ui_'):
    raise RuntimeError('브라우저 테스트 전용 임시 DB에서만 실행할 수 있습니다.')


def generate(topic, facts):
    data = {'title': '신주쿠 지역 소식 안내', 'title_fact_keys': [facts[0]['fact_key']],
            'claims': [{'sentence': facts[0]['value_text'], 'fact_keys': [facts[0]['fact_key']]}]}
    return parse_draft(data, {f['fact_key'] for f in facts}), {'request_id': 'browser-offline-provider', 'input_tokens': 1, 'output_tokens': 1}


app.dependency_overrides[get_service] = lambda: NewsService(generator=generate)
